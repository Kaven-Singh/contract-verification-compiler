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
Every command is on its own line, so it works unchanged in Windows PowerShell, CMD and Linux shells
(PowerShell 5.1 does not support `&&`). Open the page, pick an example from **Load example…**, then use
**Compile & Analyze**, the tabs (Pipeline, AST, FSM, Analysis, Repairs, Bytecode & VM) and **Execute**.

## Test
```bash
cd backend
pip install -r requirements-dev.txt
pytest -q
ruff format --check compiler app tests
ruff check compiler app tests
```
Browser end-to-end test (needs Node 18+). Start the server in one terminal (see above), then in a second terminal
**from the repository root** (not `backend/`):
```bash
cd <path to contract-verification-compiler>
npm install
npm run e2e
```

## API
`GET /api/health | /api/metrics | /api/examples | /api/examples/{id}`;
`POST /api/compile | analyze | fsm | bytecode | execute | repair | repair/apply` with `{"source": "..."}`
(`execute` adds `inputs`, `max_steps`). `/execute` returns HTTP 200 whenever the VM ran — check `status`.
Errors always look like `{"error": "<code>", ...}`. Rate limit: `CVC_RATE_LIMIT` requests/min per client (default 300).

## Documentation
[Architecture](docs/ARCHITECTURE.md) · [DSL grammar](docs/DSL_GRAMMAR.md) · [Bytecode & VM](docs/BYTECODE.md) ·
[Testing](docs/TESTING.md) · [Limitations](docs/LIMITATIONS.md)
