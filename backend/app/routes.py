"""REST endpoints. Thin adapters: parse the request, call the compiler, serialize the result."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from compiler import repairs
from compiler.pipeline import compile_source
from compiler.vm import run

from .schemas import ApplyRequest, ExecuteRequest, SourceRequest

log = logging.getLogger("cvc.routes")
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
router = APIRouter(prefix="/api")
_EXAMPLE_ID = re.compile(r"[a-z0-9_]+")  # whitelist: prevents path traversal through the example id


def error_response(status: int, error: str, **extra) -> JSONResponse:
    """The single error shape used by every endpoint: ``{"error": <code>, ...}``."""
    return JSONResponse(status_code=status, content={"error": error, **extra})


@router.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/metrics")
def metrics(request: Request) -> dict:
    """Counters since process start (requests, rate-limited calls, responses by status)."""
    return dict(request.app.state.metrics)


@router.get("/examples")
def list_examples() -> list[dict]:
    """Bundled example contracts as ``{id, title}``."""
    items = []
    for path in sorted(EXAMPLES_DIR.glob("*.cvc")):
        lines = path.read_text().splitlines()
        title = lines[0].removeprefix("# title:").strip() if lines else ""
        items.append({"id": path.stem, "title": title})
    return items


@router.get("/examples/{example_id}")
def get_example(example_id: str):
    """Source text of one bundled example."""
    path = EXAMPLES_DIR / f"{example_id}.cvc"
    if not _EXAMPLE_ID.fullmatch(example_id) or not path.exists():
        return error_response(404, "example_not_found")
    return {"id": example_id, "source": path.read_text()}


@router.post("/compile")
def compile_contract(body: SourceRequest) -> dict:
    """Run the full pipeline and return every stage's result."""
    log.info("compile %d chars", len(body.source))
    return compile_source(body.source)


@router.post("/analyze")
def analyze_contract(body: SourceRequest) -> dict:
    """Compile and return only stage status, static analysis and diagnostics."""
    compiled = compile_source(body.source)
    return {key: compiled[key] for key in ("ok", "stages", "analysis", "diagnostics")}


@router.post("/fsm")
def get_fsm(body: SourceRequest):
    """The FSM IR, or 422 with diagnostics if compilation failed before FSM generation."""
    compiled = compile_source(body.source)
    return compiled["fsm"] or error_response(422, "compilation_failed", diagnostics=compiled["diagnostics"])


@router.post("/bytecode")
def get_bytecode(body: SourceRequest):
    """The validated bytecode program, or 422 with diagnostics."""
    compiled = compile_source(body.source)
    return compiled["bytecode"] or error_response(422, "compilation_failed", diagnostics=compiled["diagnostics"])


@router.post("/execute")
def execute_contract(body: ExecuteRequest):
    """Compile then run. HTTP 200 means the VM ran; the outcome is in ``status`` (halted, error, invalid, ...)."""
    compiled = compile_source(body.source)
    if not compiled["bytecode"]:
        return error_response(422, "compilation_failed", diagnostics=compiled["diagnostics"])
    return run(compiled["bytecode"], body.inputs, body.max_steps)


@router.post("/repair")
def suggest_repairs(body: SourceRequest) -> dict:
    """Repair suggestions for the diagnostics of the submitted source."""
    return {"repairs": repairs.suggest(body.source)}


@router.post("/repair/apply")
def apply_repair(body: ApplyRequest):
    """Stateless: returns the repaired source and its re-analysis; the client decides whether to adopt it."""
    repair = repairs.apply(body.source, body.repair_id)
    return repair or error_response(404, "repair_not_found")
