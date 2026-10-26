"""REST API and static frontend."""

from helpers import OK, src


def test_api():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert c.get("/api/health").json() == {"status": "ok"}
    assert len(c.get("/api/examples").json()) == 8
    o = c.post("/api/compile", json={"source": src("conflict")}).json()
    assert o["stages"]["static"]["status"] == "failed" and o["stages"]["bytecode"]["status"] == "skipped"
    assert c.post("/api/bytecode", json={"source": src("conflict")}).status_code == 422
    assert c.get("/api/examples/nope").status_code == 404
    r = c.post("/api/execute", json={"source": src("valid_service"), "inputs": OK}).json()
    assert r["final_state"] == "LATE"
    assert c.post("/api/repair", json={"source": src("conflict")}).json()["repairs"][0]["id"] == "E301:waive"


def test_frontend_served():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert "Contract Verification Compiler" in c.get("/").text
    assert c.get("/js/app.js").status_code == 200 and c.get("/api/health").status_code == 200


def test_api_malformed_requests():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert c.post("/api/compile", json={}).status_code == 422
    assert c.post("/api/compile", content="not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert c.post("/api/compile", json={"source": "x" * 50001}).status_code == 422
    assert (
        c.post("/api/execute", json={"source": src("valid_service"), "inputs": OK, "max_steps": 0}).status_code == 422
    )
    r = c.post("/api/execute", json={"source": src("valid_service"), "inputs": {}})
    assert r.status_code == 200 and r.json()["status"] == "error"  # HTTP 200 does not imply successful execution
    assert c.post("/api/repair/apply", json={"source": src("conflict"), "repair_id": "nope"}).status_code == 404


def test_rate_limit_and_metrics(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import RateLimiter, app

    monkeypatch.setattr(app.state, "limiter", RateLimiter(2, 60))
    c = TestClient(app)
    assert [c.get("/api/examples").status_code for _ in range(3)] == [200, 200, 429]
    assert c.get("/api/health").status_code == 200  # health is exempt
    assert c.get("/api/metrics").json()["rate_limited"] >= 1


def test_error_shapes_are_uniform_and_do_not_echo_input():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    body = client.post("/api/compile", json={"source": 123}).json()
    assert body["error"] == "invalid_request" and body["details"][0]["loc"][-1] == "source"
    assert "123" not in str(body)  # submitted values are never echoed back
    assert client.get("/api/examples/nope").json() == {"error": "example_not_found"}
    assert client.get("/api/examples/..%2Fpytest").status_code == 404  # path traversal attempt


def test_unexpected_errors_return_generic_500_without_internals(monkeypatch):
    from fastapi.testclient import TestClient

    from app import routes
    from app.main import app

    def boom(source):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr(routes, "compile_source", boom)
    response = TestClient(app, raise_server_exceptions=False).post("/api/compile", json={"source": "x"})
    assert response.status_code == 500 and response.json()["error"] == "internal_error"
    assert "secret" not in response.text and "Traceback" not in response.text


def test_example_listing_survives_an_empty_file(tmp_path, monkeypatch):
    """Regression: an empty example file used to raise IndexError on the title lookup."""
    from fastapi.testclient import TestClient

    from app import routes
    from app.main import app

    (tmp_path / "empty.cvc").write_text("")
    monkeypatch.setattr(routes, "EXAMPLES_DIR", tmp_path)
    response = TestClient(app).get("/api/examples")
    assert response.status_code == 200 and response.json() == [{"id": "empty", "title": ""}]


def test_rate_limiter_forgets_idle_clients():
    """Regression: the per-client table used to grow forever; idle keys are now swept."""
    import time

    from app.ratelimit import RateLimiter

    limiter = RateLimiter(limit=1, window=0.01)
    for i in range(1500):
        limiter.allow(f"client-{i}")
    time.sleep(0.03)
    limiter.allow("latecomer")
    assert list(limiter.hits) == ["latecomer"]
