"""Bytecode backend (stage 6): FSM/AST -> stack-machine program, plus static validation.

A program is JSON-serializable: ``{"vars", "states", "initial", "enums", "code"}`` where ``code`` is a list of
``{"op", "arg"}`` instructions. Each rule compiles to a block::

    RULE name
    CHECK_STATE src ; JUMP_IF_FALSE next      # rule only applies in its source state
    <guard>         ; JUMP_IF_FALSE next      # guard must hold
    <unless> NOT    ; JUMP_IF_FALSE next      # exception must not hold (optional)
    <args> TRIGGER_OBLIGATION {name, argc}
    TRANSITION dst                            # optional GOTO
    next:  (the following RULE, or HALT)

Every jump goes forward to a RULE/HALT boundary, so programs always terminate. :func:`validate` re-checks all of
this (and stack depth/types) so the VM never executes bytecode that was not verified.
"""

import functools
from typing import Any

from .lang import ACTION_ARITY

Program = dict[str, Any]

# Opcode -> operand count (0 or 1). STORE is part of the instruction set and VM but the generator never emits it.
OPCODES: dict[str, int] = {
    **{
        op: 0
        for op in ("ADD", "SUB", "ADD_MONTHS", "SUB_MONTHS", "CMP_EQ", "CMP_NE", "CMP_LT", "CMP_GT", "CMP_LE", "CMP_GE")
    },
    **{op: 0 for op in ("AND", "OR", "NOT", "HALT")},
    **{
        op: 1
        for op in (
            "PUSH",
            "LOAD",
            "STORE",
            "JUMP",
            "JUMP_IF_FALSE",
            "CHECK_STATE",
            "TRANSITION",
            "TRIGGER_OBLIGATION",
            "RULE",
        )
    },
}
_OPERATOR_OPCODE = {
    "+": "ADD",
    "-": "SUB",
    ">": "CMP_GT",
    "<": "CMP_LT",
    ">=": "CMP_GE",
    "<=": "CMP_LE",
    "==": "CMP_EQ",
    "!=": "CMP_NE",
    "AND": "AND",
    "OR": "OR",
}
_DAY_UNITS = {"DAYS": 1}  # MONTHS is calendar-aware and compiled to ADD_MONTHS/SUB_MONTHS instead
_VALUE_TYPE = {"DATE": "num", "NUMBER": "num", "MONEY": "num", "BOOL": "bool", "ENUM": "str"}  # dates are ordinal days
# (operand types..., result type) for instructions with a fixed stack effect.
_STACK_EFFECT = {
    **{op: ("num", "num", "num") for op in ("ADD", "SUB", "ADD_MONTHS", "SUB_MONTHS")},
    **{op: ("num", "num", "bool") for op in ("CMP_GT", "CMP_LT", "CMP_GE", "CMP_LE")},
    "AND": ("bool", "bool", "bool"),
    "OR": ("bool", "bool", "bool"),
}


def generate(ast: dict[str, Any], fsm: dict[str, Any]) -> Program:
    """Compile the validated AST to a bytecode program."""
    code: list[dict[str, Any]] = []
    enum_literals = {value for var in ast["vars"] for value in var["values"]}

    def emit(op: str, arg: Any = None) -> int:
        """Append an instruction and return its address (needed to patch jumps later)."""
        code.append({"op": op, "arg": arg})
        return len(code) - 1

    def emit_expression(expr: dict[str, Any]) -> None:
        """Emit stack code that leaves the expression's value on the stack."""
        kind = expr["type"]
        if kind in ("Number", "Bool"):
            emit("PUSH", expr["value"])
        elif kind == "Duration":
            emit("PUSH", expr["value"] * _DAY_UNITS[expr["unit"]])
        elif kind == "Ident":
            emit("PUSH", expr["name"]) if expr["name"] in enum_literals else emit("LOAD", expr["name"])
        elif kind == "Unary":
            emit_expression(expr["operand"])
            emit("NOT")
        elif expr["op"] in ("+", "-") and expr["right"]["type"] == "Duration" and expr["right"]["unit"] == "MONTHS":
            emit_expression(expr["left"])
            emit("PUSH", expr["right"]["value"])
            emit("ADD_MONTHS" if expr["op"] == "+" else "SUB_MONTHS")
        else:
            emit_expression(expr["left"])
            emit_expression(expr["right"])
            emit(_OPERATOR_OPCODE[expr["op"]])

    for rule in ast["rules"]:
        emit("RULE", rule["name"])
        skips = []  # jumps to patch with the address of the next rule once this block's length is known
        emit("CHECK_STATE", rule["from"])
        skips.append(emit("JUMP_IF_FALSE"))
        emit_expression(rule["guard"])
        skips.append(emit("JUMP_IF_FALSE"))
        if rule["unless"]:
            emit_expression(rule["unless"])
            emit("NOT")
            skips.append(emit("JUMP_IF_FALSE"))
        for arg in rule["action"]["args"]:
            emit_expression(arg)
        emit("TRIGGER_OBLIGATION", {"name": rule["action"]["name"], "argc": len(rule["action"]["args"])})
        if rule["goto"]:
            emit("TRANSITION", rule["goto"])
        for address in skips:
            code[address]["arg"] = len(code)
    emit("HALT")
    return {
        "vars": {v["name"]: v["vtype"] for v in ast["vars"]},
        "states": [s["name"] for s in ast["states"]],
        "initial": fsm["initial"],
        "enums": {v["name"]: v["values"] for v in ast["vars"] if v["vtype"] == "ENUM"},
        "code": code,
    }


def validate(program: Program) -> list[str]:
    """Return a list of problems (empty if the program is safe to run).

    Checks, in order: structure and operands of each instruction, forward jumps to RULE/HALT boundaries, known
    variables/states/actions, then (only if those pass) stack depth and operand types along every path.
    """
    errors: list[str] = []
    code = program.get("code") or []
    if not code or code[-1].get("op") != "HALT":
        errors.append("program must end with HALT")
    if code and code[0].get("op") not in ("RULE", "HALT"):
        errors.append("program must start at a RULE or HALT boundary")
    for i, instruction in enumerate(code):
        op, arg = instruction.get("op"), instruction.get("arg")
        if op not in OPCODES:
            errors.append(f"{i}: unknown opcode {op!r}")
        elif (OPCODES[op] == 1) != (arg is not None):
            errors.append(f"{i}: {op} has wrong operand count")
        elif op in ("JUMP", "JUMP_IF_FALSE"):
            # Forward-only jumps rule out loops, which is what guarantees termination.
            if not (isinstance(arg, int) and not isinstance(arg, bool) and i < arg < len(code)):
                errors.append(f"{i}: {op} target {arg!r} must be a forward index in range")
            elif code[arg].get("op") not in ("RULE", "HALT"):
                errors.append(f"{i}: {op} target {arg} is not a RULE or HALT boundary")
        elif op in ("LOAD", "STORE") and arg not in program["vars"]:
            errors.append(f"{i}: unknown variable {arg!r}")
        elif op in ("CHECK_STATE", "TRANSITION") and arg not in program["states"]:
            errors.append(f"{i}: unknown state {arg!r}")
        elif op == "TRIGGER_OBLIGATION":
            valid = (
                isinstance(arg, dict)
                and arg.get("name") in ACTION_ARITY
                and arg.get("argc") == ACTION_ARITY[arg["name"]]
            )
            if not valid:
                errors.append(f"{i}: malformed or unknown obligation operand")
    if not errors:
        errors += _check_stack(program)
    return errors


def _pop(stack: list[str], errors: list[str], pc: int, op: str, expected: str | None = None) -> str | None:
    """Pop one abstract value type, recording underflow or a type mismatch against ``expected``."""
    if not stack:
        errors.append(f"{pc}: stack underflow at {op}")
        return None
    value_type = stack.pop()
    if expected and value_type != expected:
        errors.append(f"{pc}: {op} expects {expected}, got {value_type}")
    return value_type


def _check_stack(program: Program) -> list[str]:
    """Abstract interpretation: track the stack of value *types* at every reachable address.

    Detects underflow, wrong operand types, a non-empty stack at a RULE/HALT boundary, and paths that reach the
    same address with different stacks. Since jumps are forward-only, each address is visited once per distinct
    predecessor and the worklist terminates quickly.
    """
    code, errors = program["code"], []
    seen: dict[int, tuple[str, ...]] = {0: ()}
    worklist = [0]
    while worklist:
        pc = worklist.pop()
        stack = list(seen[pc])
        op, arg = code[pc]["op"], code[pc].get("arg")
        problems_before = len(errors)

        pop = functools.partial(_pop, stack, errors, pc, op)

        successors = [pc + 1]
        if op in ("RULE", "HALT") and stack:
            errors.append(f"{pc}: non-empty stack at {op} boundary")
        if op == "PUSH":
            if isinstance(arg, (bool, str, int, float)):
                stack.append("bool" if isinstance(arg, bool) else "str" if isinstance(arg, str) else "num")
            else:
                errors.append(f"{pc}: PUSH operand must be a literal")
        elif op == "LOAD":
            stack.append(_VALUE_TYPE[program["vars"][arg]])
        elif op == "STORE":
            pop(_VALUE_TYPE[program["vars"][arg]])
        elif op in ("CMP_EQ", "CMP_NE"):
            right, left = pop(), pop()
            if left and right and left != right:
                errors.append(f"{pc}: {op} compares {left} with {right}")
            stack.append("bool")
        elif op in _STACK_EFFECT:
            *operands, result = _STACK_EFFECT[op]
            for expected in operands:
                pop(expected)
            stack.append(result)
        elif op == "NOT":
            pop("bool")
            stack.append("bool")
        elif op == "JUMP":
            successors = [arg]
        elif op == "JUMP_IF_FALSE":
            pop("bool")
            successors = [pc + 1, arg]
        elif op == "CHECK_STATE":
            stack.append("bool")
        elif op == "TRIGGER_OBLIGATION":
            for _ in range(arg["argc"]):
                pop("num")
        elif op == "HALT":
            successors = []
        if len(errors) > problems_before:
            continue  # do not propagate a broken state along this path
        for target in successors:
            if target not in seen:
                seen[target] = tuple(stack)
                worklist.append(target)
            elif seen[target] != tuple(stack):
                errors.append(f"{pc}: inconsistent stack at jump target {target}")
    return errors
