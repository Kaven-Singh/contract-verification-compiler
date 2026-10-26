# DSL grammar

```
Program   := (VarDecl | StateDecl | Rule)*
VarDecl   := 'VAR' ID ':' Type ';'
Type      := 'DATE' | 'NUMBER' | 'MONEY' | 'BOOL' | 'ENUM' '(' ID (',' ID)* ')'
StateDecl := 'STATE' ID ['INITIAL'] ';'                       # exactly one INITIAL
Rule      := 'RULE' ID 'FROM' ID ':' 'IF' Expr 'THEN' ID '(' [Expr (',' Expr)*] ')'
             ['UNLESS' Expr] ['GOTO' ID] ';'
Expr      := Or ;  Or := And ('OR' And)* ;  And := Not ('AND' Not)* ;  Not := 'NOT' Not | Cmp
Cmp       := Add [('>'|'<'|'>='|'<='|'=='|'!=') Add]           # comparisons do not chain
Add       := Primary (('+'|'-') Primary)*
Primary   := NUMBER ['DAYS'|'MONTHS'] | ID | 'TRUE' | 'FALSE' | '(' Expr ')'
```
Comments start with `#`. Keywords are upper-case and case-sensitive. Actions: `PENALTY(n)`, `WAIVE_PENALTY()`, `TERMINATE()`.

## Types
`MONEY` and `NUMBER` compare with each other. `DATE ± DURATION → DATE`, `DATE - DATE → NUMBER` (days). `n MONTHS` is
legal only directly after `+`/`-` on a DATE and uses calendar months (Jan 31 + 1 month = Feb 28); `n DAYS` is a duration.
`BOOL` and each `ENUM` support only `==`/`!=`; an enum's literals are its own type. Conditions and exceptions must be BOOL.

## Diagnostics
| Code | Meaning | Code | Meaning |
|---|---|---|---|
| E101 | invalid character | E208 | ordering operator on BOOL/ENUM |
| E102 | syntax error | E209 | invalid arithmetic operand types |
| E201 | incomparable types (e.g. `DATE cannot be compared with MONEY.`) | E210 | MONTHS used outside DATE ± n MONTHS |
| E202 | undeclared name | E301 | proven conflict (verified witness) |
| E203 | duplicate identifier / rule | E401 | cycle with no satisfiable exit |
| E204 | unknown state | E501 | bytecode validation failure |
| E205 | non-BOOL condition | W301/W302 | unreachable state / rule (graph) |
| E206 | invalid action or arguments | W303/W304 | dead guard / logically unreachable state |
| E207 | not exactly one INITIAL state | W311 | possible (undecided) conflict |
|  |  | W402 | cycle that may have an exit; termination not guaranteed |

Examples that follow this grammar are in `backend/examples/`.
