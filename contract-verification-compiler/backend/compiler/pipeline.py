"""Compilation pipeline: runs the stages in order and records each stage's outcome.

Stages: lexer -> parser -> semantic -> fsm -> static analysis -> bytecode. A stage that reports an *error* stops
the pipeline: later stages stay ``skipped`` so the UI never shows a downstream success for a broken contract.
Warnings never stop it. The result dict is exactly what ``POST /api/compile`` returns.
"""

from typing import Any

from .analysis import analyze as analyze_fsm
from .bytecode import generate, validate
from .diagnostics import Diagnostic, diag, has_errors
from .fsm import build_fsm
from .lexer import lex
from .parser import parse
from .semantic import analyze as analyze_semantics

STAGES = ["lexer", "parser", "semantic", "fsm", "static", "bytecode"]


def compile_source(source: str) -> dict[str, Any]:
    """Compile contract source. Pure function: the same source always yields the same result."""
    result: dict[str, Any] = {
        "ok": False,
        "stages": {name: {"status": "skipped"} for name in STAGES},
        "diagnostics": [],
        "tokens": [],
        "ast": None,
        "symbols": None,
        "fsm": None,
        "analysis": None,
        "bytecode": None,
    }

    def finish_stage(name: str, diagnostics: list[Diagnostic], **info: Any) -> bool:
        """Record a stage; return True if the pipeline may continue."""
        result["diagnostics"] += diagnostics
        failed = has_errors(diagnostics)
        result["stages"][name] = {"status": "failed" if failed else "ok", "diagnostics": len(diagnostics), **info}
        return not failed

    tokens, lex_diagnostics = lex(source)
    result["tokens"] = [token._asdict() for token in tokens]
    if not finish_stage("lexer", lex_diagnostics, tokens=len(tokens) - 1):
        return result
    result["ast"], parse_diagnostics = parse(tokens)
    if not finish_stage("parser", parse_diagnostics):
        return result
    semantic_diagnostics, result["symbols"] = analyze_semantics(result["ast"])
    if not finish_stage("semantic", semantic_diagnostics):
        return result
    result["fsm"] = build_fsm(result["ast"], source)
    finish_stage("fsm", [], states=len(result["fsm"]["states"]), transitions=len(result["fsm"]["transitions"]))
    result["analysis"] = analyze_fsm(result["fsm"])
    if not finish_stage("static", result["analysis"]["diagnostics"]):
        return result
    program = generate(result["ast"], result["fsm"])
    problems = [diag("E501", message, 1, 1) for message in validate(program)]
    if finish_stage("bytecode", problems, instructions=len(program["code"])):
        result["bytecode"], result["ok"] = program, True
    return result
