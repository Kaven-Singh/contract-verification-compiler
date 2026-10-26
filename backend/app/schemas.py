"""Pydantic request models: validation at the HTTP boundary (the compiler itself has no FastAPI dependency)."""

from typing import Any

from pydantic import BaseModel, Field

MAX_SOURCE_CHARS = 50_000
MAX_STEPS_LIMIT = 100_000


class SourceRequest(BaseModel):
    """A contract to compile/analyze/repair."""

    source: str = Field(..., max_length=MAX_SOURCE_CHARS)


class ExecuteRequest(SourceRequest):
    """Run a contract on one event. ``inputs`` maps variable names to values (dates as ISO strings)."""

    inputs: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(10_000, ge=1, le=MAX_STEPS_LIMIT)


class ApplyRequest(SourceRequest):
    """Ask for the repaired source for one suggestion id (nothing is stored server-side)."""

    repair_id: str = Field(..., max_length=200)
