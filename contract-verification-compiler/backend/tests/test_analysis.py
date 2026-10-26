"""Solver, reachability, conflict and cycle analyses and the sample contracts."""

import random

import pytest
from helpers import EXPECT, holds, overlaps, src

from compiler import analysis as anmod
from compiler.analysis import solve
from compiler.pipeline import compile_source


@pytest.mark.parametrize("n,exp", EXPECT.items())
def test_examples(n, exp):
    assert {d["code"] for d in compile_source(src(n))["diagnostics"]} == exp


def test_analysis_details():
    a = compile_source(src("conflict"))["analysis"]
    assert a["conflicts"][0]["witness"] == {"amount": 501}
    c = compile_source(src("cycle"))["analysis"]["cycles"][0]
    assert set(c["states"]) == {"A", "B"} and not c["has_exit"]
    assert compile_source(src("unreachable"))["analysis"]["reachability"]["unreachable_states"] == ["ORPHAN"]


def test_unless_is_part_of_effective_condition():
    base = (
        "VAR amount: MONEY; STATE A INITIAL; RULE fee FROM A: IF amount > 100 THEN PENALTY(2) UNLESS amount > {u}; "
        "RULE waive FROM A: IF amount > 500 THEN WAIVE_PENALTY();"
    )
    assert compile_source(base.format(u=400))["analysis"]["conflicts"] == []
    c = compile_source(base.format(u=600))["analysis"]["conflicts"]
    assert c and c[0]["overlap"] == "proven" and 500 < c[0]["witness"]["amount"] <= 600


def test_cycle_exit_status():
    t = (
        "VAR amount: MONEY; STATE A INITIAL; STATE B; STATE DONE; "
        "RULE ab FROM A: IF amount > 0 THEN PENALTY(1) GOTO B; "
        "RULE ba FROM B: IF amount > 0 THEN PENALTY(1) GOTO A; RULE out FROM B: IF {g} THEN PENALTY(1) GOTO DONE;"
    )
    bad = compile_source(t.format(g="amount > 5 AND amount < 3"))
    assert bad["analysis"]["cycles"][0]["exit_status"] == "infeasible"
    assert "E401" in {d["code"] for d in bad["diagnostics"]}
    ok = compile_source(t.format(g="amount > 5"))
    assert ok["analysis"]["cycles"][0]["exit_status"] == "feasible"
    codes = {d["code"] for d in ok["diagnostics"]}
    assert "W402" in codes and "E401" not in codes


def test_solver_not_equal_is_exact():
    assert solve([("x", "==", 5), ("x", "!=", 5)]) is None
    assert solve([("x", ">=", 5), ("x", "<=", 5), ("x", "!=", 5)]) is None
    assert solve([("x", ">", 5), ("x", "<=", 5)]) is None
    assert solve([("x", ">=", 5), ("x", "<=", 5)]) == {"x": 5}
    w = solve([("x", ">", 0), ("x", "<", 2), ("x", "!=", 1)])
    assert 0 < w["x"] < 2 and w["x"] != 1
    assert solve([("b", "==", True), ("b", "!=", True)]) is None


@pytest.mark.parametrize(
    "g1,g2,expected",
    [
        ("a > 5 OR b", "a < 3 AND NOT b", False),
        ("a > 5 OR b", "a < 3", True),
        ("NOT (a > 5 AND b)", "a > 9 AND b", False),
        ("NOT (a > 5 AND b)", "a > 9 AND NOT b", True),
        ("a >= 5", "a <= 5", True),
        ("a > 5", "a < 5", False),
        ("a > 5", "a <= 5", False),
        ("a != 5", "a == 5", False),
        ("a != 5", "a >= 5 AND a <= 5", False),
        ("a != 5", "a > 4", True),
        ("NOT NOT b", "NOT b", False),
    ],
)
def test_nested_boolean_conflicts(g1, g2, expected):
    assert overlaps(g1, g2) is expected


def test_logical_reachability_and_new_conflict_kinds():
    o = compile_source(
        "VAR a: NUMBER; STATE S INITIAL; STATE T; RULE r FROM S: IF a > 5 AND a < 3 THEN PENALTY(1) GOTO T;"
    )
    r = o["analysis"]["reachability"]
    assert "T" in r["reachable"] and r["logically_unreachable_states"] == ["T"]
    assert {"W303", "W304"} <= {d["code"] for d in o["diagnostics"]}
    t = (
        "VAR a: NUMBER; STATE S INITIAL; STATE T; STATE U; "
        "RULE r1 FROM S: IF a > 0 THEN {x1}; RULE r2 FROM S: IF a > 0 THEN {x2};"
    )
    assert (
        compile_source(t.format(x1="PENALTY(1)", x2="PENALTY(2)"))["analysis"]["conflicts"][0]["reason"]
        == "different penalties"
    )
    assert compile_source(t.format(x1="PENALTY(1)", x2="PENALTY(1)"))["analysis"]["conflicts"] == []
    two = t.replace("THEN {x1}", "THEN PENALTY(1) GOTO T").replace("THEN {x2}", "THEN PENALTY(1) GOTO U")
    assert compile_source(two)["analysis"]["conflicts"][0]["reason"] == "different target states"


def test_solver_matches_brute_force_on_random_systems():
    rnd = random.Random(1234)
    grid = [
        k / 2 for k in range(-6, 31)
    ]  # integer constants => half-integer grid decides satisfiability over the reals
    for _ in range(4000):
        at = [
            (rnd.choice("xy"), rnd.choice([">", "<", ">=", "<=", "==", "!="]), rnd.randint(0, 12))
            for _ in range(rnd.randint(1, 6))
        ]
        w = solve(at)
        brute = any(all(holds(a, {"x": gx, "y": gy}) for a in at) for gx in grid for gy in grid)
        assert (w is not None) == brute, at
        if w is not None:
            w = {"x": 0, "y": 0, **w}
            assert all(holds(a, w) for a in at), (at, w)


def test_solver_narrow_intervals_and_many_exclusions():
    w = solve([("x", ">", 0), ("x", "<", 1), ("x", "!=", 0.5)])
    assert 0 < w["x"] < 1 and w["x"] != 0.5
    bad = [("x", "!=", k / 21) for k in range(1, 21)]
    w = solve([("x", ">", 0), ("x", "<", 1)] + bad)
    assert 0 < w["x"] < 1 and all(w["x"] != k / 21 for k in range(1, 21))
    assert solve([("x", ">", 5)] + [("x", "!=", k) for k in range(6, 40)])["x"] > 39 or True
    w = solve([("x", ">", 5)] + [("x", "!=", k) for k in range(6, 40)])
    assert w["x"] > 5 and w["x"] not in range(6, 40)
    assert solve([("x", ">=", 3), ("x", "<=", 3), ("y", ">", 1), ("y", "<", 1)]) is None


def test_possible_vs_proven_conflicts_are_distinct():
    o = compile_source(
        "VAR p: DATE; VAR d: DATE; STATE S INITIAL; RULE r1 FROM S: IF p > d + 30 DAYS THEN PENALTY(1); "
        "RULE r2 FROM S: IF p > d + 60 DAYS THEN WAIVE_PENALTY();"
    )
    c = o["analysis"]["conflicts"][0]
    assert c["overlap"] == "possible" and c["witness"] is None and {d["code"] for d in o["diagnostics"]} == {"W311"}
    assert compile_source(src("conflict"))["analysis"]["conflicts"][0]["overlap"] == "proven"


def test_proven_conflicts_have_verified_witnesses():
    for n in EXPECT:
        for c in compile_source(src(n))["analysis"]["conflicts"] if compile_source(src(n))["analysis"] else []:
            assert c["overlap"] != "proven" or c["witness_verified"]
    rnd = random.Random(5)
    for _ in range(300):

        def guard():
            atoms = (
                f"a {rnd.choice(['>', '<', '>=', '<=', '==', '!='])} {rnd.randint(0, 9)}"
                for _ in range(rnd.randint(1, 3))
            )
            return " AND ".join(atoms)

        u = rnd.choice(["", f" UNLESS a {rnd.choice(['>', '<'])} {rnd.randint(0, 9)}"])
        s = (
            f"VAR a: NUMBER; STATE S INITIAL; RULE r1 FROM S: IF {guard()} THEN PENALTY(1){u}; "
            f"RULE r2 FROM S: IF {guard()} THEN WAIVE_PENALTY();"
        )
        o = compile_source(s)
        for c in o["analysis"]["conflicts"]:
            assert c["overlap"] == "proven" and c["witness_verified"]
            rules = {r["name"]: r for r in o["ast"]["rules"]}
            for rn in c["rules"]:
                assert anmod.verify({"guard": rules[rn]["guard"], "unless": rules[rn]["unless"]}, c["witness"])


def test_unverified_witness_is_never_labelled_proven(monkeypatch):
    monkeypatch.setattr(anmod, "solve", lambda at: {"amount": -5})  # a deliberately wrong solver
    c = compile_source(src("conflict"))["analysis"]["conflicts"][0]
    assert c["overlap"] == "possible" and c["witness_verified"] is False
