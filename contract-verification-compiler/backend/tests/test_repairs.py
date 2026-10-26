"""Repair generation, validation and behavioural comparison."""

import pytest
from helpers import src

from compiler import repairs
from compiler.pipeline import compile_source
from compiler.repairs import behavior


@pytest.mark.parametrize(
    "n,rid",
    [
        ("conflict", "E301:waive"),
        ("cycle", "E401:a_to_b"),
        ("type_mismatch", "E201:bad_check"),
        ("unreachable", "W302:ghost"),
    ],
)
def test_repairs(n, rid):
    r = repairs.apply(src(n), rid)
    assert r and r["resolved"] and r["valid"] and r["new_source"] != src(n)
    assert r["before"] != r["after"]


def test_repair_status_fields():
    r = repairs.apply(src("conflict"), "E301:waive")
    assert r["status"] == "resolved" and r["syntax_valid"] and r["new_issues"] == []


def test_repairs_expose_assumptions():
    for n, rid in [
        ("conflict", "E301:waive"),
        ("cycle", "E401:a_to_b"),
        ("type_mismatch", "E201:bad_check"),
        ("unreachable", "W302:ghost"),
    ]:
        r = repairs.apply(src(n), rid)
        assert r["requires_review"] and r["assumption"]
        # moving 'ghost' onto ACTIVE clashes with late_fee (PENALTY(5) vs PENALTY(2)): the engine must say so
        assert r["status"] == ("introduces_issues" if n == "unreachable" else "resolved")


def test_repair_behaviour_comparison():
    o = compile_source(src("conflict"))
    same = behavior(o, o)
    assert same["samples"] > 0 and same["differences"] == 0
    r = repairs.apply(src("conflict"), "E301:waive")["behavior"]
    assert r["differences"] > 0 and r["example"]["inputs"]["amount"] > 500  # exactly where the two rules overlapped
    assert repairs.apply(src("type_mismatch"), "E201:bad_check")["behavior"] is None


def test_typo_repairs():
    s = "VAR amount: MONEY; STATE ACTIVE INITIAL; STATE B; RULE r FROM ACTIVE: IF amoutn > 1 THEN PENALTY(1) GOTO B;"
    r = repairs.apply(s, "E202:r")
    assert r["status"] == "resolved" and "IF amount > 1" in r["new_source"]
    r = repairs.apply(s.replace("amoutn", "amount").replace("FROM ACTIVE", "FROM ACTVE"), "E204:r")
    assert r["status"] == "resolved" and "FROM ACTIVE" in r["new_source"]
    assert repairs.apply(s.replace("amoutn", "qqqq"), "E202:r") is None  # no plausible candidate: no guess


def test_sample_inputs_are_deterministic_and_cover_boundaries():
    from compiler.behavior import sample_inputs

    ast = compile_source(src("conflict"))["ast"]
    first, second = list(sample_inputs(ast)), list(sample_inputs(ast))
    assert first == second and first
    amounts = {sample["amount"] for sample in first}
    assert {99, 100, 101, 499, 500, 501} <= amounts  # both sides of every literal in the contract
