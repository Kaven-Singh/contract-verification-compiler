"""Repair engine: turns diagnostics into concrete, reviewable source edits.

Each supported diagnostic maps to a *text edit* (replace/insert at character offsets recorded by the parser) so the
original formatting is preserved. A suggestion is never applied silently: it is recompiled and reported with

* ``syntax_valid`` / ``resolved`` — the edited source parses and the targeted diagnostic is gone;
* ``new_issues`` — diagnostics the edit introduced (``status`` becomes ``introduces_issues``);
* ``behavior`` — a bounded differential run of the VM (see :mod:`compiler.behavior`);
* ``assumption`` — the guess the repair makes about the author's intent.

Repairs are proposals: they can remove a diagnostic and still change what the contract means.
"""

from typing import Any

from .behavior import behavior
from .diagnostics import Diagnostic, has_errors
from .pipeline import compile_source

Edit = tuple[str, int, int, str, str]  # (rule name, start, end, replacement, description)

ASSUMPTIONS = {
    "E201": "Assumes the replacement variable is the one the author meant to compare.",
    "W302": "Assumes the rule was meant to start from the initial state.",
    "E301": "Assumes the other rule is the more specific one and should take precedence.",
    "W311": "Assumes the other rule is the more specific one and should take precedence.",
    "E401": "Assumes redirecting this rule to the terminal state is the intended way to end the cycle.",
    "E202": "Assumes the undeclared name is a typo of the closest declared name.",
    "E204": "Assumes the unknown state is a typo of the closest declared state.",
}


def _edit_for(diagnostic: Diagnostic, rules: dict[str, dict[str, Any]]) -> Edit | None:
    """The text edit that addresses ``diagnostic``, or ``None`` if this category has no safe automatic repair."""
    code, data, rule = diagnostic["code"], diagnostic["data"], diagnostic["rule"]
    if code == "E201" and data.get("replacement"):
        start, end = data["span"]
        return (
            rule,
            start,
            end,
            data["replacement"],
            f"Replace {data['operand']} with {data['replacement']} so both operands have the same type",
        )
    if code == "W302":
        start, end = rules[rule]["from_span"]
        return rule, start, end, data["initial"], f"Start the rule from reachable initial state {data['initial']}"
    if code in ("E301", "W311") and data.get("fix_rule") and rules[data["fix_rule"]]["unless"] is None:
        # Insert `UNLESS (<other guard>)` so the earlier rule yields where the later, more specific one applies.
        position = rules[data["fix_rule"]]["tail_pos"]
        description = f"Make '{data['fix_rule']}' yield to the more specific rule '{rule}' with an UNLESS exception"
        return data["fix_rule"], position, position, f" UNLESS ({data['other_guard']}) ", description
    if code == "E401" and data.get("terminal") and rules[data["fix_rule"]]["goto_span"]:
        start, end = rules[data["fix_rule"]]["goto_span"]
        description = f"Break the cycle: redirect '{data['fix_rule']}' to terminal state {data['terminal']}"
        return data["fix_rule"], start, end, data["terminal"], description
    if code in ("E202", "E204") and data.get("candidates"):
        start, end = data["span"]
        kind = "name" if code == "E202" else "state"
        description = (
            f"Replace unknown {kind} '{data['name']}' with the closest declared {kind} '{data['candidates'][0]}'"
        )
        return rule, start, end, data["candidates"][0], description
    return None


def suggest(source: str, compiled: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """All repair suggestions for ``source``. Pass ``compiled`` to reuse an existing compile result."""
    compiled = compiled or compile_source(source)
    if not compiled["ast"]:
        return []  # nothing parsed, so there are no spans to edit
    rules = {rule["name"]: rule for rule in compiled["ast"]["rules"]}
    key = lambda d: (d["code"], d["rule"])  # noqa: E731 - identity of a diagnostic across recompiles
    before = {key(d) for d in compiled["diagnostics"]}
    suggestions: list[dict[str, Any]] = []
    used_ids: dict[str, int] = {}
    for diagnostic in compiled["diagnostics"]:
        edit = _edit_for(diagnostic, rules)
        if not edit:
            continue
        rule_name, start, end, replacement, description = edit
        new_source = source[:start] + replacement + source[end:]
        after = compile_source(new_source)
        syntax_valid = all(after["stages"][stage]["status"] == "ok" for stage in ("lexer", "parser"))
        resolved = syntax_valid and key(diagnostic) not in {key(d) for d in after["diagnostics"]}
        introduced = [{"code": d["code"], "rule": d["rule"]} for d in after["diagnostics"] if key(d) not in before]
        if not syntax_valid:
            status = "invalid_syntax"
        elif not resolved:
            status = "ineffective"
        else:
            status = "introduces_issues" if introduced else "resolved"
        rule_start, rule_end = rules[rule_name]["span"]
        repair_id = f"{diagnostic['code']}:{diagnostic['rule'] or rule_name}"
        duplicate = used_ids.get(repair_id, 0)
        used_ids[repair_id] = duplicate + 1
        suggestions.append(
            {
                "id": repair_id if duplicate == 0 else f"{repair_id}#{duplicate}",
                "code": diagnostic["code"],
                "rule": rule_name,
                "description": description,
                "before": source[rule_start:rule_end],
                "after": new_source[rule_start : rule_end + len(replacement) - (end - start)],
                "new_source": new_source,
                "assumption": ASSUMPTIONS[diagnostic["code"]],
                "requires_review": True,
                "behavior": behavior(compiled, after),
                "syntax_valid": syntax_valid,
                "resolved": resolved,
                "new_issues": introduced,
                "status": status,
                "valid": syntax_valid and not has_errors(after["diagnostics"]),
                "after_diagnostics": after["diagnostics"],
            }
        )
    return suggestions


def apply(source: str, repair_id: str) -> dict[str, Any] | None:
    """The suggestion with ``repair_id`` (stateless: nothing is stored or applied server-side), or ``None``."""
    return next((s for s in suggest(source) if s["id"] == repair_id), None)
