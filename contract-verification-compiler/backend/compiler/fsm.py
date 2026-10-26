"""FSM intermediate representation (stage 4): validated AST -> finite-state machine.

Each STATE becomes a node; each RULE becomes a *transition* ``src -> dst`` guarded by its IF condition (and
exception). A rule without GOTO has ``dst = None``: it fires an obligation but stays in its state, so it is not an
edge for graph analyses. A state with no outgoing rule is *terminal*. Transitions keep their guard ASTs and source
text so analyses can solve them and the UI can display them. The result is JSON-serializable.
"""

import json
from typing import Any

Fsm = dict[str, Any]


def _strip_locations(node: Any) -> Any:
    """Copy an AST fragment without line/col/span so structurally equal expressions compare equal."""
    if isinstance(node, dict):
        return {k: _strip_locations(v) for k, v in node.items() if k not in ("line", "col", "span")}
    if isinstance(node, list):
        return [_strip_locations(item) for item in node]
    return node


def _argument_text(arg: dict[str, Any]) -> str:
    """Readable, comparable text of an action argument (used to tell PENALTY(2) from PENALTY(5))."""
    if arg["type"] == "Number":
        return str(arg["value"])
    if arg["type"] == "Ident":
        return arg["name"]
    return json.dumps(_strip_locations(arg), sort_keys=True)


def build_fsm(ast: dict[str, Any], source: str) -> Fsm:
    """Lower a semantically valid AST to the FSM IR. ``source`` supplies the guard/exception text."""
    initial = next(s["name"] for s in ast["states"] if s["initial"])
    has_outgoing = {rule["from"] for rule in ast["rules"]}
    states = [
        {
            "name": s["name"],
            "initial": s["initial"],
            "terminal": s["name"] not in has_outgoing,
            "line": s["line"],
            "col": s["col"],
        }
        for s in ast["states"]
    ]

    def text(span: tuple[int, int] | None) -> str | None:
        """Source text of a character span, or None when the span is absent."""
        return source[span[0] : span[1]] if span else None

    transitions = [
        {
            "id": rule["name"],
            "src": rule["from"],
            "dst": rule["goto"],
            "guard": rule["guard"],
            "guard_text": text(rule["guard_span"]),
            "unless": rule["unless"],
            "unless_text": text(rule["unless_span"]),
            "action": {
                "name": rule["action"]["name"],
                "argc": len(rule["action"]["args"]),
                "args": [_argument_text(a) for a in rule["action"]["args"]],
            },
            "line": rule["line"],
            "col": rule["col"],
        }
        for rule in ast["rules"]
    ]
    return {"initial": initial, "states": states, "transitions": transitions}
