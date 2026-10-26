"""Bounded behavioural comparison of two compiled contracts (used to qualify repair suggestions).

Both programs are run on the same deterministic sample of inputs built from the contract's own constants (each
literal, one below and one above, so boundaries are exercised). The comparison is evidence that a repair changes
behavior — and where — but it is *not* a proof of equivalence or of non-equivalence.
"""

import itertools
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from .bytecode import Program, generate, validate
from .vm import run

SAMPLE_CAP = 400  # upper bound on compared inputs per repair
_VALUES_PER_VARIABLE = 10


def _collect_literals(node: Any, found: list[tuple[str, str | None, Any]]) -> None:
    if isinstance(node, dict):
        if node.get("type") in ("Number", "Duration"):
            found.append((node["type"], node.get("unit"), node["value"]))
        for child in node.values():
            _collect_literals(child, found)
    elif isinstance(node, list):
        for child in node:
            _collect_literals(child, found)


def _spread(values: set | list, limit: int = _VALUES_PER_VARIABLE) -> list:
    """Sorted values thinned to ``limit`` entries spread over the whole range (a prefix would drop the large ones)."""
    ordered = sorted(values)
    if len(ordered) <= limit:
        return ordered
    return [ordered[round(i * (len(ordered) - 1) / (limit - 1))] for i in range(limit)]


def sample_inputs(ast: dict[str, Any], cap: int = SAMPLE_CAP) -> Iterator[dict[str, Any]]:
    """Yield deterministic input assignments covering literal boundaries; at most about ``cap`` of them."""
    literals: list[tuple[str, str | None, Any]] = []
    _collect_literals(ast["rules"], literals)
    numbers = {0} | {v + d for kind, _, v in literals if kind == "Number" for d in (-1, 0, 1)}
    day_offsets = {0} | {
        v * (30 if unit == "MONTHS" else 1) + d for kind, unit, v in literals if kind == "Duration" for d in (-1, 0, 1)
    }
    domains: dict[str, list] = {}
    for var in ast["vars"]:
        if var["vtype"] in ("NUMBER", "MONEY"):
            domains[var["name"]] = _spread(numbers)
        elif var["vtype"] == "BOOL":
            domains[var["name"]] = [False, True]
        elif var["vtype"] == "ENUM":
            domains[var["name"]] = var["values"]
        else:
            domains[var["name"]] = [(date(2026, 1, 1) + timedelta(days=d)).isoformat() for d in _spread(day_offsets)]
    names = list(domains)
    total = 1
    for name in names:
        total *= max(1, len(domains[name]))
    stride = max(1, total // cap)  # evenly thin the cross product instead of taking a biased prefix
    for combo in itertools.islice(itertools.product(*(domains[n] for n in names)), 0, None, stride):
        yield dict(zip(names, combo, strict=True))


def _program_of(compiled: dict[str, Any]) -> Program | None:
    """Bytecode for a compile result that reached FSM generation, or None if unavailable or invalid."""
    if not (compiled["ast"] and compiled["fsm"]):
        return None
    program = generate(compiled["ast"], compiled["fsm"])
    return None if validate(program) else program


def behavior(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any] | None:
    """Compare two compile results on sampled inputs; ``None`` if either has no runnable program."""
    program_before, program_after = _program_of(before), _program_of(after)
    if not program_before or not program_after:
        return None

    def outcome(run_result: dict[str, Any]) -> tuple:
        """The observable result that is compared between the two programs."""
        return (run_result["status"], run_result["final_state"], run_result["obligations"], run_result["transitions"])

    compared = differences = 0
    example = None
    for inputs in sample_inputs(before["ast"]):
        # Both programs were validated just above, so skip per-run validation and trace recording (hot loop).
        old = run(program_before, inputs, record_trace=False, validate_program=False)
        new = run(program_after, inputs, record_trace=False, validate_program=False)
        compared += 1
        if outcome(old) != outcome(new):
            differences += 1
            example = example or {
                "inputs": inputs,
                "before": {"state": old["final_state"], "obligations": old["obligations"]},
                "after": {"state": new["final_state"], "obligations": new["obligations"]},
            }
    return {
        "samples": compared,
        "differences": differences,
        "example": example,
        "note": "bounded sampling, not a proof",
    }
