"""Contract virtual machine: executes validated bytecode against runtime inputs.

One call processes one *event*: a single ordered pass over the rules in source order. A rule fires at most once;
a ``GOTO`` takes effect immediately, so *later* rules in the same pass see the new state while earlier rules are
not re-evaluated. The result is a deterministic, auditable record: status, final state, obligations, transitions,
every guard evaluation and (optionally) a per-instruction trace.

Safety layers: programs are validated before running (:func:`compiler.bytecode.validate`), a step limit bounds
execution, runtime operand types are re-checked, and any malformed-program failure is reported as a status
instead of an exception.
"""

import calendar
import operator
from datetime import date
from typing import Any

from .bytecode import Program, validate

# Failures a malformed program or bad runtime data can cause; anything else is a genuine bug and should propagate.
_RUNTIME_FAILURES = (ArithmeticError, AttributeError, IndexError, KeyError, TypeError, ValueError)

_BINARY_OPS = {
    "ADD": operator.add,
    "SUB": operator.sub,
    "CMP_GT": operator.gt,
    "CMP_LT": operator.lt,
    "CMP_GE": operator.ge,
    "CMP_LE": operator.le,
    "CMP_EQ": operator.eq,
    "CMP_NE": operator.ne,
}
_NUMERIC_OPS = frozenset(("ADD", "SUB", "CMP_GT", "CMP_LT", "CMP_GE", "CMP_LE"))
_CHECK_NAMES = ("state", "guard", "unless")  # meaning of the 1st/2nd/3rd JUMP_IF_FALSE inside a rule block


def is_number(value: Any) -> bool:
    """True for int/float (bool is excluded: BOOL must never silently act as a number)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def add_months(ordinal_day: int, months: int) -> int:
    """Calendar-month arithmetic on an ordinal day number; the day clamps to month end (Jan 31 + 1 month = Feb 28)."""
    start = date.fromordinal(ordinal_day)
    year_offset, month_index = divmod(start.month - 1 + months, 12)
    year = start.year + year_offset
    day = min(start.day, calendar.monthrange(year, month_index + 1)[1])
    return date(year, month_index + 1, day).toordinal()


def _bind_inputs(program: Program, inputs: dict[str, Any]) -> dict[str, Any]:
    """Convert user inputs to runtime values (dates become ordinal days). Raises ValueError/TypeError if invalid."""
    env: dict[str, Any] = {}
    for name, var_type in program["vars"].items():
        if name not in inputs:
            raise ValueError(f"missing input '{name}'")
        value = inputs[name]
        if var_type == "DATE":
            value = date.fromisoformat(value).toordinal()
        elif var_type == "ENUM":
            allowed = program.get("enums", {}).get(name, [])
            if value not in allowed:
                raise ValueError(f"'{name}' must be one of {allowed}")
        elif var_type == "BOOL":
            if not isinstance(value, bool):
                raise ValueError(f"'{name}' must be a boolean")
        elif not is_number(value):
            raise ValueError(f"'{name}' must be a number")
        env[name] = value
    return env


def _pop_bool(stack: list[Any], op: str) -> bool:
    value = stack.pop()
    if type(value) is not bool:
        raise TypeError(f"{op} requires BOOL")
    return value


def run(
    program: Program,
    inputs: dict[str, Any],
    max_steps: int = 10000,
    *,
    record_trace: bool = True,
    validate_program: bool = True,
) -> dict[str, Any]:
    """Execute ``program`` once.

    ``status`` is one of ``halted``, ``terminated`` (a TERMINATE obligation fired), ``step_limit``, ``error``
    (bad inputs / runtime failure) or ``invalid`` (bytecode rejected). ``record_trace=False`` skips the per-step
    trace and ``validate_program=False`` skips re-validation; both exist for the repair engine's bulk comparison,
    which validates once up front.
    """
    result: dict[str, Any] = {
        "status": "invalid",
        "final_state": None,
        "obligations": [],
        "transitions": [],
        "guard_evals": [],
        "trace": [],
        "steps": 0,
        "errors": [],
    }
    if validate_program:
        try:
            result["errors"] = validate(program)
        except _RUNTIME_FAILURES as error:  # a structurally broken program can violate any assumption validate makes
            result["errors"] = [f"malformed program: {error!r}"]
        if result["errors"]:
            return result
    try:
        env = _bind_inputs(program, inputs)
    except (ValueError, TypeError) as error:
        result.update(status="error", errors=[f"invalid input: {error}"])
        return result

    code, state = program["code"], program["initial"]
    stack: list[Any] = []
    pc, rule, checks_in_rule, terminated = 0, None, 0, False
    result["status"] = "running"
    try:
        while True:
            if result["steps"] >= max_steps:
                result["status"] = "step_limit"
                break
            op, arg = code[pc]["op"], code[pc].get("arg")
            result["steps"] += 1
            next_pc, halted = pc + 1, False
            if op == "PUSH":
                stack.append(arg)
            elif op == "LOAD":
                stack.append(env[arg])
            elif op == "STORE":
                env[arg] = stack.pop()
            elif op in _BINARY_OPS:
                right, left = stack.pop(), stack.pop()
                if op in _NUMERIC_OPS:
                    well_typed = is_number(left) and is_number(right)
                else:  # equality needs both sides of the same kind (number / bool / string)
                    well_typed = (type(left) is bool, isinstance(left, str)) == (
                        type(right) is bool,
                        isinstance(right, str),
                    )
                if not well_typed:
                    raise TypeError(f"{op} operand type mismatch")
                stack.append(_BINARY_OPS[op](left, right))
            elif op in ("ADD_MONTHS", "SUB_MONTHS"):
                months = int(stack.pop())
                stack.append(add_months(stack.pop(), months if op == "ADD_MONTHS" else -months))
            elif op in ("AND", "OR"):
                right, left = _pop_bool(stack, op), _pop_bool(stack, op)
                stack.append(left and right if op == "AND" else left or right)
            elif op == "NOT":
                stack.append(not _pop_bool(stack, op))
            elif op == "JUMP":
                next_pc = arg
            elif op == "JUMP_IF_FALSE":
                passed = _pop_bool(stack, op)
                result["guard_evals"].append(
                    {"rule": rule, "check": _CHECK_NAMES[min(checks_in_rule, 2)], "result": passed}
                )
                checks_in_rule += 1
                if not passed:
                    next_pc = arg
            elif op == "CHECK_STATE":
                stack.append(state == arg)
            elif op == "RULE":
                rule, checks_in_rule = arg, 0
            elif op == "TRIGGER_OBLIGATION":
                args = [stack.pop() for _ in range(arg["argc"])][::-1]
                result["obligations"].append({"rule": rule, "name": arg["name"], "args": args})
                terminated = terminated or arg["name"] == "TERMINATE"
            elif op == "TRANSITION":
                result["transitions"].append({"rule": rule, "from": state, "to": arg})
                state = arg
            elif op == "HALT":
                halted = True
            if record_trace:
                result["trace"].append({"step": result["steps"], "pc": pc, "op": op, "arg": arg, "stack": list(stack)})
            if halted:
                result["status"] = "terminated" if terminated else "halted"
                break
            pc = next_pc
    except _RUNTIME_FAILURES as error:
        result.update(status="error", errors=[f"runtime error: {error!r}"])
    result["final_state"] = state
    return result
