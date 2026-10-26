"""Diagnostic records emitted by every compiler stage.

A diagnostic is a plain JSON-serializable dict so it can travel unchanged from the compiler to the REST API
and the browser. Fields: ``code`` (stable identifier such as ``E201``), ``severity`` (``error`` or
``warning``), a human-readable ``message``, 1-based ``line``/``col``, the affected ``rule`` name (or ``None``)
and a stage-specific ``data`` payload that the repair engine reads (spans, replacement candidates, witnesses).

Code ranges: E1xx lexing/parsing, E2xx semantic, E301 conflict, E401 cycle, E501 bytecode,
W3xx/W4xx static-analysis warnings.
"""

from collections.abc import Iterable
from typing import Any

Diagnostic = dict[str, Any]

ERROR = "error"
WARNING = "warning"


def diag(
    code: str,
    message: str,
    line: int,
    col: int,
    severity: str = ERROR,
    rule: str | None = None,
    data: dict[str, Any] | None = None,
) -> Diagnostic:
    """Build a diagnostic record."""
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "line": line,
        "col": col,
        "rule": rule,
        "data": data or {},
    }


def has_errors(diagnostics: Iterable[Diagnostic]) -> bool:
    """Return True if any diagnostic is an error (warnings never block later stages)."""
    return any(d["severity"] == ERROR for d in diagnostics)
