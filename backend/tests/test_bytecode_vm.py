"""Bytecode validation and VM execution, including adversarial inputs."""

import copy
import random

import pytest
from helpers import OK, mutated, src

from compiler import vm as vmmod
from compiler.bytecode import OPCODES
from compiler.pipeline import compile_source
from compiler.vm import run


def test_vm():
    bc = compile_source(src("valid_service"))["bytecode"]
    r = run(bc, OK)
    assert r["status"] == "halted" and r["final_state"] == "LATE"
    assert r["obligations"] == [{"rule": "late_fee", "name": "PENALTY", "args": [2]}]
    r = run(bc, {**OK, "forceMajeure": True})
    assert r["final_state"] == "ACTIVE" and r["obligations"] == []
    r = run(bc, {**OK, "paymentDate": "2026-06-01"})
    assert r["status"] == "terminated" and r["final_state"] == "TERMINATED"
    assert run(bc, OK, max_steps=3)["status"] == "step_limit"
    assert run(bc, {"amount": 1})["status"] == "error"


def test_vm_rejects_invalid_bytecode():
    bc = compile_source(src("valid_service"))["bytecode"]
    next(i for i in bc["code"] if i["op"] == "JUMP_IF_FALSE")["arg"] = 999
    assert run(bc, OK)["status"] == "invalid"


def test_stack_validation():
    bc = compile_source(src("valid_service"))["bytecode"]
    bad = copy.deepcopy(bc)
    next(x for x in bad["code"] if x["op"] == "CMP_GT")["op"] = "AND"
    r = run(bad, OK)
    assert r["status"] == "invalid" and any("expects bool" in e for e in r["errors"])
    bad = copy.deepcopy(bc)
    bad["code"].insert(1, {"op": "ADD", "arg": None})
    for x in bad["code"]:
        if x["op"] == "JUMP_IF_FALSE":
            x["arg"] += 1  # keep control flow valid so only the stack error remains
    assert any("underflow" in e for e in run(bad, OK)["errors"])


RULES = {
    "r1": "RULE r1 FROM A: IF amount > 0 THEN PENALTY(1) GOTO B;",
    "r2": "RULE r2 FROM B: IF amount > 0 THEN PENALTY(2) GOTO C;",
    "r0": "RULE r0 FROM C: IF amount > 0 THEN PENALTY(3);",
}


def chain_program(order):
    """Bytecode for a three-state chain whose rules appear in the given source order."""
    header = "VAR amount: MONEY; STATE A INITIAL; STATE B; STATE C; "
    return compile_source(header + " ".join(RULES[name] for name in order))["bytecode"]


def test_execution_semantics_single_ordered_pass():
    """A transition is visible to LATER rules in the same pass; earlier rules are not re-evaluated."""
    result = run(chain_program(["r1", "r2", "r0"]), {"amount": 1})
    assert [o["rule"] for o in result["obligations"]] == ["r1", "r2", "r0"] and result["final_state"] == "C"
    result = run(chain_program(["r0", "r1", "r2"]), {"amount": 1})  # r0 precedes the transitions into C
    assert [o["rule"] for o in result["obligations"]] == ["r1", "r2"] and result["final_state"] == "C"


def test_fast_path_matches_full_run():
    """record_trace=False / validate_program=False (used for bulk comparison) must not change any outcome."""
    program = compile_source(src("valid_service"))["bytecode"]
    for late in ("2026-01-10", "2026-03-10", "2026-06-01"):
        inputs = {**OK, "paymentDate": late}
        full = run(program, inputs)
        fast = run(program, inputs, record_trace=False, validate_program=False)
        assert fast["trace"] == [] and full["trace"]
        for key in ("status", "final_state", "obligations", "transitions", "guard_evals", "steps"):
            assert fast[key] == full[key]


@pytest.mark.parametrize(
    "f",
    [
        lambda b: next(i for i in b["code"] if i["op"] == "JUMP_IF_FALSE").update(arg=0),  # backward jump
        lambda b: next(i for i in b["code"] if i["op"] == "JUMP_IF_FALSE").update(arg=2),  # not a boundary
        lambda b: next(i for i in b["code"] if i["op"] == "PUSH").update(op="BOGUS"),
        lambda b: next(i for i in b["code"] if i["op"] == "TRIGGER_OBLIGATION").update(arg={"name": "NUKE", "argc": 0}),
        lambda b: next(i for i in b["code"] if i["op"] == "TRIGGER_OBLIGATION").update(
            arg={"name": "PENALTY", "argc": 0}
        ),
        lambda b: next(i for i in b["code"] if i["op"] == "TRANSITION").update(arg="NOWHERE"),
        lambda b: next(i for i in b["code"] if i["op"] == "LOAD").update(arg="ghost"),
        lambda b: b["code"].insert(1, {"op": "PUSH", "arg": 1}),
        lambda b: b["code"].pop(),
        lambda b: b.pop("code"),
        lambda b: b.pop("vars"),
    ],
)
def test_adversarial_bytecode_is_rejected_cleanly(f):
    r = mutated(f)
    assert r["status"] == "invalid" and r["errors"]


def test_malformed_program_object_and_runtime_second_line(monkeypatch):
    assert run({}, OK)["status"] == "invalid" and run("junk", OK)["status"] == "invalid"
    bc = copy.deepcopy(compile_source(src("valid_service"))["bytecode"])
    next(i for i in bc["code"] if i["op"] == "CMP_GT")["op"] = "AND"
    monkeypatch.setattr(vmmod, "validate", lambda p: [])  # bypass static validation: runtime must still refuse
    assert run(bc, OK)["status"] == "error"


def test_vm_fuzz_never_raises_and_never_leaks_running():
    rnd = random.Random(7)
    base = compile_source(src("valid_service"))["bytecode"]
    ops = [*OPCODES, "BOGUS"]
    for _ in range(1500):
        bc = copy.deepcopy(base)
        for _ in range(rnd.randint(1, 3)):
            m, code = rnd.randrange(5), bc["code"]
            i = rnd.randrange(len(code))
            if m == 0:
                code[i]["op"] = rnd.choice(ops)
            elif m == 1:
                code[i]["arg"] = rnd.choice(
                    [None, 0, 1, -1, 999, "x", True, 3.5, {"name": "PENALTY", "argc": 1}, "ACTIVE"]
                )
            elif m == 2:
                del code[i]
            elif m == 3:
                code.insert(i, {"op": rnd.choice(ops), "arg": rnd.choice([None, 1, "LATE"])})
            else:
                code[i] = {"op": rnd.choice(ops)}
        assert run(bc, OK, max_steps=500)["status"] in {"invalid", "error", "halted", "terminated", "step_limit"}
