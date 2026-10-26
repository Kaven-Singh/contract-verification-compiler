"""Semantic analysis (stage 3): symbol resolution and type checking.

Walks the AST once, building a symbol table (variables, enum literals, states) and checking every rule:
declared names, comparable operand types, boolean conditions, and well-formed actions. Diagnostics carry
the enclosing rule name so the repair engine can address them, plus spans and close-match candidates for
typos (``E202``/``E204``) and replacement variables for type mismatches (``E201``).

Types are the strings DATE, NUMBER, MONEY, BOOL, DURATION and ``ENUM(<variable>)`` (each enum is its own type,
so two different enums are never comparable). The analysis never stops early: all errors are reported in one run.
"""

from difflib import get_close_matches
from typing import Any

from .diagnostics import Diagnostic, diag
from .lang import ACTION_ARITY

Node = dict[str, Any]

# Result type of `left (+|-) right`. DATE - DATE (days between) is handled separately in _arithmetic.
_ARITHMETIC_RESULT = {
    ("DATE", "DURATION"): "DATE",
    ("DURATION", "DURATION"): "DURATION",
    ("NUMBER", "NUMBER"): "NUMBER",
    ("MONEY", "MONEY"): "MONEY",
    ("MONEY", "NUMBER"): "MONEY",
    ("NUMBER", "MONEY"): "MONEY",
}


class SemanticAnalyzer:
    """Single-pass checker. Use :func:`analyze` rather than instantiating directly."""

    def __init__(self, ast: Node):
        self.ast = ast
        self.diagnostics: list[Diagnostic] = []
        self.symbols: dict[str, str] = {}  # variable name -> type
        self.enum_literals: dict[str, str] = {}  # enum literal -> type of its enum
        self.states: dict[str, Node] = {}
        self._rule: str | None = None  # rule being checked; attached to diagnostics
        self._legal_months: set[int] = set()  # ids of MONTHS durations already accepted by their parent

    def _error(self, code: str, message: str, node: Node, **data: Any) -> None:
        self.diagnostics.append(diag(code, message, node["line"], node["col"], rule=self._rule, data=data))

    # ---- declarations -------------------------------------------------------------------------------------

    def run(self) -> tuple[list[Diagnostic], dict[str, str]]:
        """Declare symbols, then check every rule; returns ``(diagnostics, symbol table)``."""
        self._declare_variables()
        self._declare_states()
        seen_rules: set[str] = set()
        for rule in self.ast["rules"]:
            self._rule = rule["name"]
            if rule["name"] in seen_rules:
                self._error("E203", f"Duplicate rule name '{rule['name']}'", rule)
            seen_rules.add(rule["name"])
            self._check_rule(rule)
            self._rule = None
        return self.diagnostics, self.symbols

    def _is_taken(self, name: str) -> bool:
        return name in self.symbols or name in self.enum_literals or name in self.states

    def _declare_variables(self) -> None:
        for var in self.ast["vars"]:
            if self._is_taken(var["name"]):
                self._error("E203", f"Duplicate identifier '{var['name']}'", var)
                continue
            self.symbols[var["name"]] = f"ENUM({var['name']})" if var["vtype"] == "ENUM" else var["vtype"]
            for literal in var["values"]:
                if self._is_taken(literal):
                    self._error("E203", f"Duplicate identifier '{literal}'", var)
                else:
                    self.enum_literals[literal] = self.symbols[var["name"]]

    def _declare_states(self) -> None:
        initial = []
        for state in self.ast["states"]:
            if self._is_taken(state["name"]):
                self._error("E203", f"Duplicate identifier '{state['name']}'", state)
            else:
                self.states[state["name"]] = state
            if state["initial"]:
                initial.append(state)
        if len(initial) != 1:
            anchor = initial[1] if initial else (self.ast["states"][0] if self.ast["states"] else self.ast)
            self._error("E207", "Exactly one INITIAL state is required", anchor)

    # ---- rules --------------------------------------------------------------------------------------------

    def _check_state_reference(self, rule: Node, field: str, span_field: str) -> None:
        name = rule[field]
        if name is not None and name not in self.states:
            candidates = get_close_matches(name, list(self.states), n=1, cutoff=0.6)
            self._error(
                "E204", f"Unknown state '{name}'", rule, name=name, span=rule[span_field], candidates=candidates
            )

    def _check_rule(self, rule: Node) -> None:
        self._check_state_reference(rule, "from", "from_span")
        self._check_state_reference(rule, "goto", "goto_span")
        self._require_bool(rule["guard"], "IF condition")
        if rule["unless"]:
            self._require_bool(rule["unless"], "UNLESS condition")
        self._check_action(rule["action"])

    def _require_bool(self, node: Node, what: str) -> None:
        found = self._type_of(node)
        if found and found != "BOOL":
            self._error("E205", f"{what} must be BOOL, found {found}", node)

    def _check_action(self, action: Node) -> None:
        name, args = action["name"], action["args"]
        if name not in ACTION_ARITY:
            self._error("E206", f"Unknown action '{name}'", action)
        elif len(args) != ACTION_ARITY[name]:
            self._error("E206", f"{name} expects {ACTION_ARITY[name]} argument(s), got {len(args)}", action)
        for arg in args:
            found = self._type_of(arg)
            if found and found not in ("NUMBER", "MONEY"):
                self._error("E206", f"Action argument must be NUMBER or MONEY, found {found}", arg)

    # ---- expressions --------------------------------------------------------------------------------------

    def _type_of(self, node: Node) -> str | None:
        """Type of an expression, or ``None`` after an error (suppresses cascading diagnostics)."""
        kind = node["type"]
        if kind == "Number":
            return "NUMBER"
        if kind == "Bool":
            return "BOOL"
        if kind == "Duration":
            if node["unit"] == "MONTHS" and id(node) not in self._legal_months:
                self._error("E210", "MONTHS durations are only supported as DATE +/- n MONTHS", node)
            return "DURATION"
        if kind == "Ident":
            return self._identifier_type(node)
        if kind == "Unary":
            found = self._type_of(node["operand"])
            if found and found != "BOOL":
                self._error("E205", f"NOT requires BOOL, found {found}", node)
            return "BOOL"
        return self._binary_type(node)

    def _identifier_type(self, node: Node) -> str | None:
        name = node["name"]
        if name in self.enum_literals:
            return self.enum_literals[name]
        if name not in self.symbols:
            candidates = get_close_matches(name, list(self.symbols) + list(self.enum_literals), n=1, cutoff=0.6)
            self._error(
                "E202", f"Undeclared variable '{name}'", node, name=name, span=node["span"], candidates=candidates
            )
            return None
        return self.symbols[name]

    def _binary_type(self, node: Node) -> str | None:
        op = node["op"]
        if op in ("+", "-") and node["right"]["type"] == "Duration":
            # MONTHS is calendar arithmetic, so it is legal only directly after + or - on a DATE.
            self._legal_months.add(id(node["right"]))
        left, right = self._type_of(node["left"]), self._type_of(node["right"])
        if op in ("AND", "OR"):
            for found, operand in ((left, node["left"]), (right, node["right"])):
                if found and found != "BOOL":
                    self._error("E205", f"{op} requires BOOL operands, found {found}", operand)
            return "BOOL"
        if op in ("+", "-"):
            return self._arithmetic(node, left, right)
        if left and right:
            self._check_comparison(node, left, right)
        return "BOOL"

    def _arithmetic(self, node: Node, left: str | None, right: str | None) -> str | None:
        if not (left and right):
            return None
        result = _ARITHMETIC_RESULT.get((left, right))
        if result is None and node["op"] == "-" and left == right == "DATE":
            result = "NUMBER"  # days between two dates
        if result is None:
            self._error("E209", f"Operator {node['op']} cannot be applied to {left} and {right}", node)
        return result

    def _check_comparison(self, node: Node, left: str, right: str) -> None:
        orderable_only_for_equality = left == "BOOL" or left.startswith("ENUM(")
        if left == right and orderable_only_for_equality and node["op"] not in ("==", "!="):
            self._error("E208", f"Operator {node['op']} is not supported for {left}", node)
        elif not (left == right or {left, right} == {"MONEY", "NUMBER"}):
            self._error(
                "E201", f"{left} cannot be compared with {right}.", node, **self._replacement_hint(node, left, right)
            )

    def _replacement_hint(self, node: Node, left: str, right: str) -> dict[str, Any]:
        """Suggest replacing one operand by another declared variable of the other operand's type (for repairs)."""
        used = {node["left"].get("name"), node["right"].get("name")}
        for operand, wanted in ((node["right"], left), (node["left"], right)):
            if operand["type"] == "Ident":
                candidate = next((n for n, t in self.symbols.items() if t == wanted and n not in used), None)
                if candidate:
                    return {"operand": operand["name"], "replacement": candidate, "span": operand["span"]}
        return {}


def analyze(ast: Node) -> tuple[list[Diagnostic], dict[str, str]]:
    """Type-check ``ast``. Returns ``(diagnostics, symbol_table)``."""
    return SemanticAnalyzer(ast).run()
