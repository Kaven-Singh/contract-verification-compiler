"""Application wiring: middleware, error handling, API router and the static frontend.

Business logic lives in the ``compiler`` package; this module only configures HTTP concerns.
"""

import collections
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import routes
from .ratelimit import RateLimiter

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cvc")

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
UNLIMITED_PATHS = ("/api/health", "/api/metrics")

app = FastAPI(title="Contract Verification Compiler")
app.state.limiter = RateLimiter(int(os.getenv("CVC_RATE_LIMIT", "300")))
app.state.metrics = collections.Counter()


@app.middleware("http")
async def limit_and_count(request: Request, call_next):
    """Rate-limit /api calls per client address and keep simple counters."""
    path = request.url.path
    if path.startswith("/api/") and path not in UNLIMITED_PATHS:
        app.state.metrics["requests"] += 1
        client = request.client.host if request.client else "unknown"  # behind a proxy this is the proxy's address
        if not app.state.limiter.allow(client):
            app.state.metrics["rate_limited"] += 1
            log.warning("rate limited %s", client)
            return JSONResponse(status_code=429, content={"error": "rate_limited"}, headers={"Retry-After": "60"})
    response = await call_next(request)
    app.state.metrics[f"status_{response.status_code}"] += 1
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Uniform 422 body; only field locations and messages are returned (never the submitted values)."""
    details = [{"loc": [str(part) for part in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "invalid_request", "details": details})


@app.exception_handler(Exception)
async def internal_error(request: Request, exc: Exception) -> JSONResponse:
    """Log the traceback server-side; the client only learns that something unexpected happened."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": "Unexpected internal error."})


app.include_router(routes.router)
if FRONTEND_DIR.exists():  # mounted last so it never shadows /api
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")
