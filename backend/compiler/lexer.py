"""Lexical analysis (stage 1): source text -> tokens.

Produces a flat token list terminated by an ``EOF`` token. Whitespace and ``#`` comments are dropped; invalid
characters become ``E101`` diagnostics so a single run reports every lexical problem. Token positions carry both
line/column (for diagnostics) and character offsets (for the repair engine's text edits).
"""

import re
from typing import NamedTuple

from .diagnostics import Diagnostic, diag

KEYWORDS = frozenset(
    {"VAR", "STATE", "INITIAL", "RULE", "FROM", "IF", "THEN", "UNLESS", "GOTO", "AND", "OR", "NOT", "TRUE", "FALSE"}
    | {"DAYS", "MONTHS", "DATE", "NUMBER", "MONEY", "BOOL", "ENUM"}
)

# One alternation, tried in order; the final BAD branch guarantees every character is consumed exactly once.
_TOKEN_PATTERN = re.compile(
    r"(?P<WS>\s+)|(?P<COMMENT>#[^\n]*)|(?P<NUM>\d+(?:\.\d+)?)|(?P<ID>[A-Za-z_]\w*)"
    r"|(?P<OP>>=|<=|==|!=|[<>+\-(),:;])|(?P<BAD>.)"
)


class Token(NamedTuple):
    """A lexical token. ``kind`` is KW, ID, NUM, OP or EOF; ``pos``/``end`` are character offsets."""

    kind: str
    text: str
    line: int
    col: int
    pos: int
    end: int


def lex(source: str) -> tuple[list[Token], list[Diagnostic]]:
    """Tokenize ``source``, returning ``(tokens, diagnostics)``. Never raises on malformed input."""
    tokens: list[Token] = []
    diagnostics: list[Diagnostic] = []
    line, line_start = 1, 0
    for match in _TOKEN_PATTERN.finditer(source):
        kind, text, col = match.lastgroup, match.group(), match.start() - line_start + 1
        if kind == "WS":
            newlines = text.count("\n")
            if newlines:
                line += newlines
                line_start = match.start() + text.rfind("\n") + 1
        elif kind == "BAD":
            diagnostics.append(diag("E101", f"Invalid character {text!r}", line, col))
        elif kind != "COMMENT":
            if kind == "ID" and text in KEYWORDS:
                kind = "KW"
            tokens.append(Token(kind, text, line, col, match.start(), match.end()))
    tokens.append(Token("EOF", "", line, len(source) - line_start + 1, len(source), len(source)))
    return tokens, diagnostics
