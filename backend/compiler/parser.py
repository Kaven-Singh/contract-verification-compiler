"""Syntax analysis (stage 2): tokens -> abstract syntax tree.

A hand-written recursive-descent parser. Expression precedence is encoded in the call chain, lowest to highest::

    OR  <  AND  <  NOT  <  comparison  <  additive (+ -)  <  primary

AST nodes are plain dicts (``{"type": ..., "line": ..., "col": ...}`` plus fields) so the tree serializes straight
to JSON for the API and the AST viewer. Rule nodes also carry character spans (``span``, ``from_span``,
``guard_span``, ``unless_span``, ``goto_span``) and ``tail_pos`` — the exact offsets the repair engine edits.

Parsing stops at the first syntax error (``E102``); later stages never see a partial tree.
"""

from typing import Any

from .diagnostics import Diagnostic, diag
from .lexer import Token

Node = dict[str, Any]

COMPARISON_OPS = (">", "<", ">=", "<=", "==", "!=")
TYPE_NAMES = ("DATE", "NUMBER", "MONEY", "BOOL", "ENUM")


class ParseError(Exception):
    """Raised internally on the first syntax error; converted to an ``E102`` diagnostic by :func:`parse`."""

    def __init__(self, message: str, token: Token):
        super().__init__(message)
        self.message = message
        self.token = token


def make_node(kind: str, token: Token, **fields: Any) -> Node:
    """Create an AST node located at ``token``."""
    return {"type": kind, "line": token.line, "col": token.col, **fields}


class Parser:
    """Recursive-descent parser over a token list that ends with an EOF token."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        """The token about to be consumed."""
        return self.tokens[self.index]

    def _at(self, *texts: str) -> bool:
        """True if the current token is a keyword/operator whose text is one of ``texts``."""
        return self.current.kind in ("KW", "OP") and self.current.text in texts

    def _expect(self, text: str | None = None, kind: str | None = None) -> Token:
        """Consume and return the current token, or raise ParseError if it is not the expected one."""
        token = self.current
        wrong_text = text is not None and not (token.kind in ("KW", "OP") and token.text == text)
        wrong_kind = kind is not None and token.kind != kind
        if token.kind == "EOF" or wrong_text or wrong_kind:
            raise ParseError(f"Expected {text or kind}, found {token.text or 'end of input'!r}", token)
        self.index += 1
        return token

    # ---- declarations -------------------------------------------------------------------------------------

    def parse_program(self) -> Node:
        """Program := (VarDecl | StateDecl | Rule)* EOF"""
        program: Node = {"type": "Program", "line": 1, "col": 1, "vars": [], "states": [], "rules": []}
        while self.current.kind != "EOF":
            if self._at("VAR"):
                program["vars"].append(self._parse_var())
            elif self._at("STATE"):
                program["states"].append(self._parse_state())
            elif self._at("RULE"):
                program["rules"].append(self._parse_rule())
            else:
                raise ParseError(f"Expected VAR, STATE or RULE, found {self.current.text!r}", self.current)
        return program

    def _parse_var(self) -> Node:
        """VarDecl := 'VAR' ID ':' (DATE | NUMBER | MONEY | BOOL | 'ENUM' '(' ID (',' ID)* ')') ';'"""
        self._expect("VAR")
        name = self._expect(kind="ID")
        self._expect(":")
        type_token = self.current
        if not self._at(*TYPE_NAMES):
            raise ParseError(f"Expected a type, found {type_token.text!r}", type_token)
        self.index += 1
        values: list[str] = []
        if type_token.text == "ENUM":
            self._expect("(")
            values.append(self._expect(kind="ID").text)
            while self._at(","):
                self._expect()
                values.append(self._expect(kind="ID").text)
            self._expect(")")
        self._expect(";")
        return make_node("Var", name, name=name.text, vtype=type_token.text, values=values)

    def _parse_state(self) -> Node:
        """StateDecl := 'STATE' ID ['INITIAL'] ';'"""
        self._expect("STATE")
        name = self._expect(kind="ID")
        initial = self._at("INITIAL")
        if initial:
            self._expect()
        self._expect(";")
        return make_node("State", name, name=name.text, initial=initial)

    def _parse_rule(self) -> Node:
        """Rule := 'RULE' ID 'FROM' ID ':' 'IF' Expr 'THEN' ID '(' [Expr (',' Expr)*] ')'
        ['UNLESS' Expr] ['GOTO' ID] ';'"""
        start = self._expect("RULE")
        name = self._expect(kind="ID")
        self._expect("FROM")
        source_state = self._expect(kind="ID")
        self._expect(":")
        self._expect("IF")
        guard_start = self.current.pos
        guard = self._or()
        guard_end = self.tokens[self.index - 1].end
        self._expect("THEN")
        action_name = self._expect(kind="ID")
        self._expect("(")
        args: list[Node] = []
        if not self._at(")"):
            args.append(self._or())
            while self._at(","):
                self._expect()
                args.append(self._or())
        self._expect(")")
        # Offset where an UNLESS clause would start: the repair engine inserts exceptions here.
        tail_pos = self.current.pos
        unless = unless_span = goto = goto_span = None
        if self._at("UNLESS"):
            self._expect()
            unless_start = self.current.pos
            unless = self._or()
            unless_span = (unless_start, self.tokens[self.index - 1].end)
        if self._at("GOTO"):
            self._expect()
            target = self._expect(kind="ID")
            goto, goto_span = target.text, (target.pos, target.end)
        semicolon = self._expect(";")
        return make_node(
            "Rule",
            start,
            name=name.text,
            **{"from": source_state.text},
            from_span=(source_state.pos, source_state.end),
            guard=guard,
            guard_span=(guard_start, guard_end),
            action=make_node("Action", action_name, name=action_name.text, args=args),
            unless=unless,
            unless_span=unless_span,
            tail_pos=tail_pos,
            goto=goto,
            goto_span=goto_span,
            span=(start.pos, semicolon.end),
        )

    # ---- expressions (one method per precedence level) ----------------------------------------------------

    def _or(self) -> Node:
        left = self._and()
        while self._at("OR"):
            op = self._expect()
            left = make_node("Binary", op, op="OR", left=left, right=self._and())
        return left

    def _and(self) -> Node:
        left = self._not()
        while self._at("AND"):
            op = self._expect()
            left = make_node("Binary", op, op="AND", left=left, right=self._not())
        return left

    def _not(self) -> Node:
        if self._at("NOT"):
            op = self._expect()
            return make_node("Unary", op, op="NOT", operand=self._not())
        return self._comparison()

    def _comparison(self) -> Node:
        # Comparisons do not chain: `a < b < c` is a syntax error, which avoids ambiguous typing rules.
        left = self._additive()
        if self._at(*COMPARISON_OPS):
            op = self._expect()
            return make_node("Binary", op, op=op.text, left=left, right=self._additive())
        return left

    def _additive(self) -> Node:
        left = self._primary()
        while self._at("+", "-"):
            op = self._expect()
            left = make_node("Binary", op, op=op.text, left=left, right=self._primary())
        return left

    def _primary(self) -> Node:
        token = self.current
        if token.kind == "NUM":
            self.index += 1
            value = float(token.text) if "." in token.text else int(token.text)
            if self._at("DAYS", "MONTHS"):  # `30 DAYS` is one Duration literal, not a number followed by a word
                return make_node("Duration", token, value=value, unit=self._expect().text)
            return make_node("Number", token, value=value)
        if token.kind == "ID":
            self.index += 1
            return make_node("Ident", token, name=token.text, span=(token.pos, token.end))
        if self._at("TRUE", "FALSE"):
            self.index += 1
            return make_node("Bool", token, value=token.text == "TRUE")
        if self._at("("):
            self._expect()
            inner = self._or()
            self._expect(")")
            return inner
        raise ParseError(f"Expected expression, found {token.text or 'end of input'!r}", token)


def parse(tokens: list[Token]) -> tuple[Node | None, list[Diagnostic]]:
    """Parse ``tokens`` into a Program node. Returns ``(None, [E102])`` on the first syntax error."""
    try:
        return Parser(tokens).parse_program(), []
    except ParseError as error:
        return None, [diag("E102", error.message, error.token.line, error.token.col)]
