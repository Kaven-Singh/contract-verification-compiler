"""Constraint solving for rule conditions (the decidable subset of the DSL).

Conditions are lowered to disjunctive normal form (DNF): a list of *alternatives*, each a conjunction of *atoms*
``(variable, operator, literal)`` with a numeric or BOOL literal. A conjunction over numeric variables is an
interval problem with excluded points, solved exactly over the reals — no SMT dependency is needed for this
subset. Anything outside it (date arithmetic, enum comparisons, more than ``MAX_ALTERNATIVES`` alternatives)
yields ``None`` meaning *unknown*; callers must never treat unknown as satisfiable or unsatisfiable.
"""

import operator
from typing import Any

Atom = tuple[str, str, float | int | bool]
Dnf = list[list[Atom]]

MAX_ALTERNATIVES = 64  # bounds the DNF blow-up of nested AND/OR/NOT; beyond it we answer "unknown"
_MIRROR = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "==": "==", "!=": "!="}  # swap operands: 5 < x  ==  x > 5
_NEGATED = {">": "<=", "<": ">=", ">=": "<", "<=": ">", "==": "!=", "!=": "=="}
_COMPARE = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


def _atom(expr: dict[str, Any]) -> Atom | None:
    """Return ``(variable, op, literal)`` for ``var OP literal`` / ``literal OP var`` / a bare BOOL variable."""
    if expr["type"] == "Binary" and expr["op"] in _MIRROR:
        left, right = expr["left"], expr["right"]
        if left["type"] == "Ident" and right["type"] in ("Number", "Bool"):
            return (left["name"], expr["op"], right["value"])
        if right["type"] == "Ident" and left["type"] in ("Number", "Bool"):
            return (right["name"], _MIRROR[expr["op"]], left["value"])
    if expr["type"] == "Ident":
        return (expr["name"], "==", True)
    return None


def _negate_atom(atom: Atom) -> Atom:
    variable, op, literal = atom
    if isinstance(literal, bool):
        return (variable, "==", (not literal) if op == "==" else literal)
    return (variable, _NEGATED[op], literal)


def dnf(expr: dict[str, Any], negate: bool = False) -> Dnf | None:
    """Lower ``expr`` (or ``NOT expr`` when ``negate``) to DNF, or return ``None`` if it is undecidable.

    Negation is pushed to the atoms with De Morgan's laws (negated AND becomes OR and vice versa), so NOT of a
    compound condition stays exact instead of being approximated.
    """
    kind = expr["type"]
    if kind == "Unary":
        return dnf(expr["operand"], not negate)
    if kind == "Bool":
        return [[]] if expr["value"] != negate else []  # [[]] = always true, [] = never true
    if kind == "Binary" and expr["op"] in ("AND", "OR"):
        left, right = dnf(expr["left"], negate), dnf(expr["right"], negate)
        if left is None or right is None:
            return None
        is_conjunction = (expr["op"] == "AND") != negate
        result = [a + b for a in left for b in right] if is_conjunction else left + right
        return result if len(result) <= MAX_ALTERNATIVES else None
    atom = _atom(expr)
    return None if atom is None else [[_negate_atom(atom)] if negate else [atom]]


def solve(atoms: list[Atom]) -> dict[str, Any] | None:
    """Solve a conjunction of atoms exactly. Returns a satisfying assignment, or ``None`` if unsatisfiable.

    Numeric variables get a lower and an upper bound (each strict or inclusive) plus a set of excluded values
    (``!=``); BOOL variables must not be forced to both values. A witness is picked from a finite candidate list
    that is always longer than the exclusion set, so a feasible interval can never run out of candidates.
    """
    lower: dict[str, tuple[float, bool]] = {}
    upper: dict[str, tuple[float, bool]] = {}
    forced_bool: dict[str, bool] = {}
    excluded: dict[str, set] = {}
    for variable, op, literal in atoms:
        if isinstance(literal, bool):
            wanted = literal if op == "==" else (not literal if op == "!=" else None)
            if wanted is not None and forced_bool.setdefault(variable, wanted) != wanted:
                return None
            continue
        if op == "!=":
            excluded.setdefault(variable, set()).add(literal)
            continue
        if op in (">", ">=", "=="):
            strict = op == ">"
            if variable not in lower or literal > lower[variable][0] or (literal == lower[variable][0] and strict):
                lower[variable] = (literal, strict)
        if op in ("<", "<=", "=="):
            strict = op == "<"
            if variable not in upper or literal < upper[variable][0] or (literal == upper[variable][0] and strict):
                upper[variable] = (literal, strict)
    witness: dict[str, Any] = dict(forced_bool)
    for variable in set(lower) | set(upper) | set(excluded):
        low, high, banned = lower.get(variable), upper.get(variable), excluded.get(variable, set())
        count = len(banned) + 8
        if low and high:
            if low[0] > high[0] or (low[0] == high[0] and (low[1] or high[1])):
                return None
            if low[0] == high[0]:
                candidates = [low[0]]
            else:
                step = (high[0] - low[0]) / count
                candidates = [(low[0] + high[0]) / 2] + [low[0] + step * k for k in range(1, count)]
                candidates += ([] if low[1] else [low[0]]) + ([] if high[1] else [high[0]])
        elif low:
            first = low[0] + (1 if low[1] else 0)
            candidates = [first + k for k in range(count)]
        elif high:
            first = high[0] - (1 if high[1] else 0)
            candidates = [first - k for k in range(count)]
        else:
            candidates = list(range(count))
        usable = [c for c in candidates if c not in banned]
        if not usable:
            return None
        pick = usable[0]
        witness[variable] = int(pick) if isinstance(pick, float) and pick.is_integer() else pick
    return witness


def evaluate(expr: dict[str, Any], assignment: dict[str, Any]) -> Any:
    """Evaluate a decidable-subset expression on the ORIGINAL AST under ``assignment``.

    Used to re-check solver witnesses independently of the DNF lowering; unassigned variables default to 0/False.
    """
    kind = expr["type"]
    if kind in ("Number", "Bool"):
        return expr["value"]
    if kind == "Ident":
        return assignment.get(expr["name"], 0)
    if kind == "Unary":
        return not evaluate(expr["operand"], assignment)
    left, right = evaluate(expr["left"], assignment), evaluate(expr["right"], assignment)
    if expr["op"] == "AND":
        return bool(left) and bool(right)
    if expr["op"] == "OR":
        return bool(left) or bool(right)
    return _COMPARE[expr["op"]](left, right)
