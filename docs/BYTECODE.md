# Bytecode and VM

A program is JSON: `{"vars", "states", "initial", "enums", "code"}`; `code` is a list of `{"op", "arg"}`. Dates are
ordinal day numbers at runtime. Each rule compiles to one block:

```
RULE name
CHECK_STATE src      JUMP_IF_FALSE next     # only in the source state
<guard>              JUMP_IF_FALSE next
<unless> NOT         JUMP_IF_FALSE next     # only if the rule has UNLESS
<args> TRIGGER_OBLIGATION {name, argc}
TRANSITION dst                              # only if the rule has GOTO
next: (next RULE or HALT)
```

| Instruction | Effect |
|---|---|
| `PUSH v` / `LOAD x` / `STORE x` | push literal / push variable / pop into variable (`STORE` is never emitted) |
| `ADD SUB` | numeric arithmetic (also dates in days) |
| `ADD_MONTHS SUB_MONTHS` | calendar-month arithmetic on a date |
| `CMP_EQ CMP_NE` | equality on same-kind operands |
| `CMP_LT CMP_GT CMP_LE CMP_GE` | numeric ordering |
| `AND OR NOT` | BOOL operations (no short-circuit) |
| `JUMP t` / `JUMP_IF_FALSE t` | forward jump / pop BOOL and jump if false |
| `CHECK_STATE s` | push whether the current state is `s` |
| `TRIGGER_OBLIGATION {name, argc}` | pop `argc` args, record the obligation |
| `TRANSITION s` | change the current state |
| `RULE name` | rule boundary marker (labels the trace) |
| `HALT` | stop |

## Validation (`bytecode.validate`, always run before execution)
Known opcodes with the right operand count; jumps go **forward** to a `RULE`/`HALT` boundary (so programs cannot loop);
known variables, states and actions with the right arity; program starts at a boundary and ends with `HALT`; then
abstract interpretation of the stack: no underflow, correct operand types, empty stack at every boundary, identical
stacks where paths join.

## Execution semantics
One call = one event = one pass over the rules in source order. A rule fires at most once. `TRANSITION` takes effect
immediately, so **later** rules in the pass see the new state; **earlier** rules are not re-evaluated. Status:
`halted`, `terminated` (a TERMINATE obligation fired), `step_limit`, `error`, `invalid`. The result lists obligations,
transitions, every guard evaluation and, unless disabled, a per-instruction trace.
