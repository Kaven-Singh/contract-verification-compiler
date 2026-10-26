"""Language-level constants shared by the semantic analyzer and the bytecode backend.

Keeping the action table in one place guarantees that what the type checker accepts is exactly what the
bytecode generator and validator can emit and execute.
"""

# Contract actions ("obligations") and the number of arguments each one takes.
ACTION_ARITY: dict[str, int] = {"PENALTY": 1, "WAIVE_PENALTY": 0, "TERMINATE": 0}
