# Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q                       # all backend tests
ruff format --check compiler app tests   # formatting (Black-compatible; Black itself also works)
ruff check compiler app tests           # lint
```
(One command per line: Windows PowerShell 5.1 does not support `&&`.)

Troubleshooting: Black refuses to run on Python 3.12.5 (a known interpreter bug; `--fast` does not bypass it). Use
`ruff format --check compiler app tests` instead, or run Black on Python 3.12.6+ / 3.12.4.
Browser end-to-end test (Node 18+). Terminal 1: `cd backend` then `uvicorn app.main:app`. Terminal 2, from the
repository root (not `backend/`):
```bash
npm install
npm run e2e      # drives the real page in jsdom (not a real browser engine); pass another URL after --
```

| File | Covers |
|---|---|
| `test_syntax.py` | lexer positions/errors, precedence, syntax errors |
| `test_semantic.py` | type checking, ENUM, calendar months |
| `test_analysis.py` | the 8 example contracts, solver (random cross-check against brute force), nested boolean conditions, reachability, conflicts, cycles, witness verification |
| `test_repairs.py` | each repair category, status/assumption fields, behavioural comparison, sampler determinism |
| `test_bytecode_vm.py` | execution semantics, validation, adversarial and fuzzed bytecode, fast-path equivalence |
| `test_api.py` | endpoints, uniform error shapes, generic 500, rate limiter, static frontend |
| `tests/e2e_browser.js` | compile/repair/undo/execute/clear/reset flows, stale responses, API failures, safe rendering, keyboard tabs |

Helpers shared by the test files are in `backend/tests/helpers.py`. Not covered: a real browser engine (layout and
pixel alignment of the highlight layer), load/concurrency tests, multi-process deployments.
