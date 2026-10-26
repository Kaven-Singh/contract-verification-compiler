# Architecture

```
DSL source ─► lexer ─► parser ─► semantic ─► fsm ─► analysis ─► bytecode ─► vm
              tokens    AST       types       IR     diagnostics  program    result
                                                        │
                                                    repairs (+ behavior)
```

| Module (`backend/compiler/`) | Responsibility |
|---|---|
| `lexer.py` | Characters → tokens; reports invalid characters (`E101`). |
| `parser.py` | Recursive descent → AST; precedence in the call chain; first syntax error (`E102`). |
| `semantic.py` | Symbol table, type checking, typo candidates (`E2xx`). |
| `fsm.py` | AST → finite-state machine (states, guarded transitions, terminal states). |
| `solver.py` | Guards → DNF; exact interval solver for the decidable subset; witness evaluation. |
| `analysis.py` | Reachability (BFS, graph and logical), conflicts, cycles (Tarjan). |
| `bytecode.py` | Code generation and static validation (operands, forward jumps, stack types). |
| `vm.py` | Stack VM: one ordered pass per event, step limit, deterministic result. |
| `behavior.py` | Bounded differential run of two programs on sampled inputs. |
| `repairs.py` | Diagnostics → text edits, recompiled and qualified. |
| `pipeline.py` | Runs the stages, stops at the first failing one, records per-stage status. |
| `lang.py`, `diagnostics.py` | Shared constants and the diagnostic record. |

`backend/app/` is the only code that knows about HTTP: `schemas.py` (validation), `routes.py` (endpoints),
`ratelimit.py`, `main.py` (middleware, error handlers, static files). The compiler has no FastAPI dependency.

## Decisions worth knowing
* **AST, FSM and diagnostics are plain dicts**, not classes. They are the API's JSON, the repair engine edits by
  recorded character offsets, and the browser renders them unchanged. Dataclasses would add a conversion layer without
  adding safety here; the shapes are documented in each module's docstring.
* **Stateless API.** Every endpoint recompiles the submitted source; nothing is stored. `repair/apply` returns the
  repaired source and the client decides whether to adopt it.
* **Errors:** invalid source → diagnostics (HTTP 200 from `/compile`, 422 from `/fsm|/bytecode|/execute`); invalid
  request → `422 {"error": "invalid_request", "details": [...]}`; unexpected failure → logged, then
  `500 {"error": "internal_error"}` with no internals. `/execute` returns 200 whenever the VM ran — read `status`.
* **Frontend:** plain scripts sharing one `window.CVC` namespace (`util → api → editor/pipeline/ast/fsm/analysis/repairs/
  execution → app`). ES modules would be tidier but the jsdom browser test cannot load them. Every API string is escaped
  by `CVC.util.esc` before it reaches `innerHTML`; stale responses are discarded with request tickets.

## Performance notes (measured)
Compiling the 8 examples takes about 2 ms and a 60-state contract about 7 ms. The only hot path is the repair
comparison, which previously re-validated bytecode and recorded a trace for every sampled input; skipping both (the
program is validated once) made a 343-sample comparison about 5x faster (≈44 ms → ≈8.5 ms, same results).
