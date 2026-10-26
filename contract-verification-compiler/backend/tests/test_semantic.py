"""Semantic analysis, ENUM and calendar-month typing."""

from helpers import src

from compiler.pipeline import compile_source
from compiler.vm import run


def test_semantic():
    o = compile_source(src("type_mismatch"))
    assert o["diagnostics"][0]["message"] == "DATE cannot be compared with MONEY."
    assert o["stages"]["fsm"]["status"] == "skipped"
    o = compile_source("STATE S INITIAL; RULE r FROM S: IF x > 1 THEN TERMINATE();")
    assert o["diagnostics"][0]["code"] == "E202"


def test_enum():
    s = (
        "VAR level: ENUM(LOW, HIGH); VAR amount: MONEY; STATE A INITIAL; STATE B; "
        "RULE r FROM A: IF level == HIGH THEN PENALTY(1) GOTO B;"
    )
    o = compile_source(s)
    assert o["ok"]
    assert run(o["bytecode"], {"level": "HIGH", "amount": 1})["final_state"] == "B"
    assert run(o["bytecode"], {"level": "LOW", "amount": 1})["final_state"] == "A"
    assert run(o["bytecode"], {"level": "MID", "amount": 1})["status"] == "error"
    assert compile_source(s.replace("level == HIGH", "level == 3"))["diagnostics"][0]["code"] == "E201"
    assert compile_source(s.replace("level == HIGH", "level > HIGH"))["diagnostics"][0]["code"] == "E208"


def test_calendar_months():
    s = "VAR p: DATE; VAR d: DATE; STATE A INITIAL; STATE B; RULE r FROM A: IF p > d + 1 MONTHS THEN PENALTY(1) GOTO B;"
    bc = compile_source(s)["bytecode"]
    assert run(bc, {"p": "2026-03-01", "d": "2026-01-31"})["final_state"] == "B"  # Jan 31 + 1 month = Feb 28
    assert run(bc, {"p": "2026-02-28", "d": "2026-01-31"})["final_state"] == "A"
    assert "E210" in {x["code"] for x in compile_source(s.replace("d + 1 MONTHS", "1 MONTHS + d"))["diagnostics"]}
