"""Lexer and parser."""

from compiler.lexer import lex
from compiler.parser import parse


def test_lexer():
    t, d = lex("VAR a: DATE; @")
    assert [x.text for x in t[:3]] == ["VAR", "a", ":"]
    assert d[0]["code"] == "E101" and (d[0]["line"], d[0]["col"]) == (1, 14)


def test_parser_precedence_and_error():
    t, _ = lex("VAR a: BOOL;STATE S INITIAL;RULE r FROM S: IF a OR a AND a THEN TERMINATE();")
    g = parse(t)[0]["rules"][0]["guard"]
    assert g["op"] == "OR" and g["right"]["op"] == "AND"
    ast, d = parse(lex("VAR a: DATE")[0])
    assert ast is None and d[0]["code"] == "E102"
