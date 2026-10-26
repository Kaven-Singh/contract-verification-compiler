"""Static analyses over the FSM IR (stage 5): reachability, conflict detection and cycle detection.

All three passes work on each transition's *effective condition* — ``guard AND NOT unless`` lowered to DNF by
:mod:`compiler.solver`. When a condition is outside the decidable subset its effective condition is ``None``
(unknown) and every pass degrades to a warning instead of guessing. Nothing here proves runtime behavior:
graph reachability ignores guards, logical reachability drops only provably dead edges, and cycles are
structural.
"""

from collections import deque
from typing import Any

from .diagnostics import ERROR, WARNING, Diagnostic, diag
from .solver import MAX_ALTERNATIVES, Dnf, dnf, evaluate, solve

Transition = dict[str, Any]
Effective = dict[str, Dnf | None]

# Pairs of different obligations that cannot both hold for the same event.
INCOMPATIBLE_OBLIGATIONS = {frozenset(("PENALTY", "WAIVE_PENALTY")), frozenset(("PENALTY", "TERMINATE"))}


def effective_condition(transition: Transition) -> Dnf | None:
    """``guard AND NOT unless`` as DNF, or ``None`` if either part is undecidable or too large."""
    guard = dnf(transition["guard"])
    if guard is None:
        return None
    if transition["unless"] is None:
        return guard
    not_unless = dnf(transition["unless"], negate=True)
    if not_unless is None:
        return None
    combined = [g + e for g in guard for e in not_unless]
    return combined if len(combined) <= MAX_ALTERNATIVES else None


def find_overlap(first: Dnf, second: Dnf) -> dict[str, Any] | None:
    """A joint assignment satisfying one alternative of each condition, or ``None`` if they are exclusive."""
    for a in first:
        for b in second:
            witness = solve(a + b)
            if witness is not None:
                return witness
    return None


def verify(transition: Transition, witness: dict[str, Any]) -> bool:
    """True iff ``witness`` makes the rule fire per its ORIGINAL guard and UNLESS expressions.

    Independent of the DNF lowering, so a solver or lowering bug can downgrade a conflict but never fabricate a
    "proven" one.
    """
    try:
        fires = bool(evaluate(transition["guard"], witness))
        return fires and not (transition["unless"] is not None and evaluate(transition["unless"], witness))
    except (KeyError, TypeError):
        return False


def _is_dead(alternatives: Dnf | None) -> bool:
    """True iff the condition is decidable and provably never satisfiable."""
    return alternatives is not None and all(solve(alt) is None for alt in alternatives)


def _bfs(initial: str, transitions: list[Transition]) -> list[str]:
    """Breadth-first search from ``initial`` over transitions that change state; returns states in visit order."""
    adjacency: dict[str, list[str]] = {}
    for t in transitions:
        if t["dst"]:
            adjacency.setdefault(t["src"], []).append(t["dst"])
    order, seen, queue = [initial], {initial}, deque([initial])
    while queue:
        for nxt in adjacency.get(queue.popleft(), []):
            if nxt not in seen:
                seen.add(nxt)
                order.append(nxt)
                queue.append(nxt)
    return order


def _reachability(fsm: dict[str, Any], effective: Effective) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Graph reachability (ignores guards) and logical reachability (drops provably dead transitions)."""
    transitions, initial = fsm["transitions"], fsm["initial"]
    dead = {t["id"] for t in transitions if _is_dead(effective[t["id"]])}
    graph = _bfs(initial, transitions)
    logical = _bfs(initial, [t for t in transitions if t["id"] not in dead])
    unreachable_states = [s for s in fsm["states"] if s["name"] not in graph]
    unreachable_rules = [t for t in transitions if t["src"] not in graph]
    diagnostics: list[Diagnostic] = []
    for s in unreachable_states:
        message = f"State {s['name']} is unreachable from initial state {initial}"
        diagnostics.append(diag("W301", message, s["line"], s["col"], WARNING, data={"state": s["name"]}))
    for t in unreachable_rules:
        message = f"Rule '{t['id']}' is unreachable: source state {t['src']} cannot be reached"
        diagnostics.append(
            diag("W302", message, t["line"], t["col"], WARNING, t["id"], {"from": t["src"], "initial": initial})
        )
    logically_unreachable = [s for s in graph if s not in logical]
    for s in fsm["states"]:
        if s["name"] in logically_unreachable:
            message = f"State {s['name']} is graph-reachable only through transitions whose conditions can never hold"
            diagnostics.append(diag("W304", message, s["line"], s["col"], WARNING, data={"state": s["name"]}))
    for t in transitions:
        if t["id"] in dead:
            message = f"Effective condition of rule '{t['id']}' (guard and not exception) can never be true"
            diagnostics.append(diag("W303", message, t["line"], t["col"], WARNING, t["id"]))
    section = {
        "reachable": graph,
        "logically_reachable": logical,
        "unreachable_states": [s["name"] for s in unreachable_states],
        "logically_unreachable_states": logically_unreachable,
        "unreachable_rules": [t["id"] for t in unreachable_rules],
        "note": "Graph reachability ignores guards; logical reachability drops transitions whose effective condition "
        "is provably unsatisfiable (decidable subset only).",
    }
    return section, diagnostics


def _conflict_reason(first: Transition, second: Transition) -> str | None:
    """Why two rules of the same state would be inconsistent if both fired (None if they are compatible)."""
    if first["src"] != second["src"]:
        return None
    a, b = first["action"], second["action"]
    if frozenset((a["name"], b["name"])) in INCOMPATIBLE_OBLIGATIONS:
        return "incompatible obligations"
    if a["name"] == b["name"] == "PENALTY" and a["args"] != b["args"]:
        return "different penalties"
    if first["dst"] and second["dst"] and first["dst"] != second["dst"]:
        return "different target states"
    return None


def _normalized(text: str | None) -> str | None:
    # Textual fallback for undecidable guards only: "(a > 1)" and "a>1" count as the same condition.
    return text.replace(" ", "").strip("()") if text else None


def _conflicts(transitions: list[Transition], effective: Effective) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    """Pairwise check of rules that share a source state, on their effective conditions."""
    conflicts: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    for i, first in enumerate(transitions):
        for second in transitions[i + 1 :]:
            reason = _conflict_reason(first, second)
            if not reason:
                continue
            alts_first, alts_second = effective[first["id"]], effective[second["id"]]
            if alts_first is not None and alts_second is not None:
                witness = find_overlap(alts_first, alts_second)
                if witness is None:
                    continue  # mutually exclusive, e.g. thanks to an UNLESS clause
                # "proven" only if the witness satisfies the original conditions, not just the solver's form.
                kind = "proven" if verify(first, witness) and verify(second, witness) else "possible"
            else:
                exclusive = _normalized(first["unless_text"]) == _normalized(second["guard_text"]) or _normalized(
                    second["unless_text"]
                ) == _normalized(first["guard_text"])
                if exclusive:
                    continue
                witness, kind = None, "possible"
            a, b = first["action"], second["action"]
            conflicts.append(
                {
                    "state": first["src"],
                    "rules": [first["id"], second["id"]],
                    "actions": [a["name"], b["name"]],
                    "overlap": kind,
                    "reason": reason,
                    "witness": witness,
                    "witness_verified": kind == "proven",
                }
            )
            message = (
                f"Rules '{first['id']}' and '{second['id']}' can both fire in state {first['src']} ({reason}: "
                f"{a['name']}({', '.join(a['args'])}) vs {b['name']}({', '.join(b['args'])}))"
                + (f"; witness {witness}" if witness is not None else "; guards outside the decidable subset")
            )
            data = {
                "rules": [first["id"], second["id"]],
                "witness": witness,
                "fix_rule": first["id"],
                "other_guard": second["guard_text"],
            }
            code, severity = ("E301", ERROR) if kind == "proven" else ("W311", WARNING)
            diagnostics.append(diag(code, message, second["line"], second["col"], severity, second["id"], data))
    return conflicts, diagnostics


def _tarjan(nodes: list[str], adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Tarjan's strongly connected components (single DFS, linear time).

    ``low[v]`` is the smallest DFS index reachable from v's subtree via at most one back edge; v is the root of an
    SCC exactly when ``low[v] == index[v]``, at which point the stack down to v is that component.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []
    counter = [0]

    def visit(v: str) -> None:
        """Depth-first visit; pops a component when ``v`` is the root of an SCC."""
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adjacency.get(v, []):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            component = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == v:
                    break
            components.append(component)

    for node in nodes:
        if node not in index:
            visit(node)
    return components


def _exit_status(exits: list[Transition], effective: Effective) -> str:
    """none | infeasible | unknown | feasible — whether a way out of the cycle can ever be taken."""
    if not exits:
        return "none"
    alternatives = [effective[t["id"]] for t in exits]
    if any(alt is not None and any(solve(a) is not None for a in alt) for alt in alternatives):
        return "feasible"
    return "unknown" if any(alt is None for alt in alternatives) else "infeasible"


def _cycles(fsm: dict[str, Any], effective: Effective) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    """Structural cycles (SCCs with an internal edge) and whether each has a satisfiable exit.

    A cycle with no satisfiable exit is an error (``E401``); one with a possible exit is only a warning because
    the guards may still keep taking the cycle — termination is never claimed or refuted here.
    """
    transitions, names = fsm["transitions"], [s["name"] for s in fsm["states"]]
    adjacency: dict[str, list[str]] = {}
    for t in transitions:
        if t["dst"]:
            adjacency.setdefault(t["src"], []).append(t["dst"])
    cycles: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    for component in _tarjan(names, adjacency):
        if len(component) == 1 and component[0] not in adjacency.get(component[0], []):
            continue  # a single state without a self-loop is not a cycle
        members = [n for n in names if n in component]
        inside = [t for t in transitions if t["src"] in members and t["dst"] in members]
        exits = [
            t
            for t in transitions
            if t["src"] in members and ((t["dst"] and t["dst"] not in members) or t["action"]["name"] == "TERMINATE")
        ]
        status = _exit_status(exits, effective)
        first, last = min(inside, key=lambda t: t["line"]), max(inside, key=lambda t: t["line"])
        terminal = next((s["name"] for s in fsm["states"] if s["terminal"] and s["name"] not in members), None)
        rules = [t["id"] for t in inside]
        cycles.append(
            {
                "states": members,
                "rules": rules,
                "structural": True,
                "exit_status": status,
                "has_exit": status in ("feasible", "unknown"),
            }
        )
        data = {"states": members, "rules": rules, "exit_status": status, "fix_rule": last["id"], "terminal": terminal}
        if status in ("none", "infeasible"):
            why = "no exit transition or TERMINATE" if status == "none" else "every exit guard is unsatisfiable"
            message = f"Potential non-terminating cycle through {members}: {why}"
            diagnostics.append(diag("E401", message, first["line"], first["col"], ERROR, first["id"], data))
        else:
            kind = "satisfiable" if status == "feasible" else "undecidable"
            message = (
                f"Structural cycle through {members}: an exit is {kind} but termination is not guaranteed "
                "(guards may keep taking the cycle)"
            )
            diagnostics.append(diag("W402", message, first["line"], first["col"], WARNING, first["id"], data))
    return cycles, diagnostics


def analyze(fsm: dict[str, Any]) -> dict[str, Any]:
    """Run all three analyses. Diagnostics are ordered reachability, conflicts, cycles."""
    effective = {t["id"]: effective_condition(t) for t in fsm["transitions"]}
    reachability, reach_diags = _reachability(fsm, effective)
    conflicts, conflict_diags = _conflicts(fsm["transitions"], effective)
    cycles, cycle_diags = _cycles(fsm, effective)
    return {
        "reachability": reachability,
        "conflicts": conflicts,
        "cycles": cycles,
        "diagnostics": reach_diags + conflict_diags + cycle_diags,
    }
