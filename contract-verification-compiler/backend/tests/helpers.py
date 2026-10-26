"""Shared test helpers: example loading, expected diagnostics and small contract builders."""

import copy
import pathlib

from compiler.pipeline import compile_source
from compiler.vm import run

EXAMPLES = pathlib.Path(__file__).resolve().parent.parent / "examples"
EXPECT = {
    "valid_service": set(),
    "unreachable": {"W301", "W302"},
    "conflict": {"E301"},
    "cycle": {"E401", "W301"},
    "type_mismatch": {"E201"},
    "force_majeure": set(),
    "terminating": set(),
    "repaired": set(),
}
OK = {"paymentDate": "2026-03-10", "dueDate": "2026-01-01", "forceMajeure": False, "amount": 100}


def src(name: str) -> str:
    """Source text of a bundled example contract."""
    return (EXAMPLES / f"{name}.cvc").read_text()


def mutated(mutation):
    """Run the valid_service bytecode after applying ``mutation`` to a deep copy of it."""
    program = copy.deepcopy(compile_source(src("valid_service"))["bytecode"])
    mutation(program)
    return run(program, OK)


def overlaps(guard_one: str, guard_two: str) -> bool:
    """True if two rules with these guards (and incompatible actions) are reported as conflicting."""
    source = (
        f"VAR a: NUMBER; VAR b: BOOL; STATE S INITIAL; RULE r1 FROM S: IF {guard_one} THEN PENALTY(1); "
        f"RULE r2 FROM S: IF {guard_two} THEN WAIVE_PENALTY();"
    )
    return bool(compile_source(source)["analysis"]["conflicts"])


def holds(atom, assignment) -> bool:
    """Evaluate one solver atom ``(var, op, literal)`` under ``assignment``."""
    variable, op, literal = atom
    value = assignment[variable]
    return {
        ">": value > literal,
        "<": value < literal,
        ">=": value >= literal,
        "<=": value <= literal,
        "==": value == literal,
        "!=": value != literal,
    }[op]
