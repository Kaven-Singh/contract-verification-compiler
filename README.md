# Contract Verification Compiler

Compiles structured contract clauses written in a small DSL, verifies their **logical consistency (not legal
validity)**, suggests reviewable repairs, and executes them on a stack VM with an auditable trace.

```
DSL → lexer → parser → AST → semantic analysis → FSM → static analysis → bytecode → VM → trace + repairs
```

## Requirements
Python 3.10+ (Node 18+ only for the optional browser test).

## Install and run
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload        # UI and API at http://127.0.0.1:8000
```
Windows (PowerShell) and Linux use the same commands. Open the page, pick an example from **Load example…**, then use
**Compile & Analyze**, the tabs (Pipeline, AST, FSM, Analysis, Repairs, Bytecode & VM) and **Execute**.

## Test
```bash
cd backend && pip install -r requirements-dev.txt && pytest -q
npm install && npm run e2e           # from the repo root, with the server running
```

## API
`GET /api/health | /api/metrics | /api/examples | /api/examples/{id}`;
`POST /api/compile | analyze | fsm | bytecode | execute | repair | repair/apply` with `{"source": "..."}`
(`execute` adds `inputs`, `max_steps`). `/execute` returns HTTP 200 whenever the VM ran — check `status`.
Errors always look like `{"error": "<code>", ...}`. Rate limit: `CVC_RATE_LIMIT` requests/min per client (default 300).

## Documentation
[Architecture](docs/ARCHITECTURE.md) · [DSL grammar](docs/DSL_GRAMMAR.md) · [Bytecode & VM](docs/BYTECODE.md) ·
[Testing](docs/TESTING.md) · [Limitations](docs/LIMITATIONS.md)
