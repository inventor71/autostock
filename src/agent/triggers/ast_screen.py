"""Static pre-screen for agent-authored predicate source (SECURITY-05, defense-in-depth).

This is **not** the security boundary — the Docker sandbox (``src/`` un-mounted,
``--network=none``, secrets stripped, non-root, cap-drop) is. The screen is a cheap
first filter that rejects obviously-hostile or malformed predicates at registration
time so they never reach the sandbox and never start tripping the auto-disable
counter for the wrong reason. It is deliberately conservative: an import/builtin
allow-list plus a ban on the classic Python sandbox-escape patterns (dunder crawling
like ``().__class__.__bases__``). Anything not on the allow-list is rejected.

Contract checked here:
* the module parses,
* it defines a top-level ``should_fire`` function,
* every ``import`` targets an allow-listed module,
* no banned builtin (``eval``/``exec``/``open``/``compile``/``__import__``/…) is called,
* no dunder attribute access (``__globals__``/``__subclasses__``/``__class__``/…).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# Modules a pure predicate legitimately needs to reason over injected ``ctx`` data.
# No os/sys/subprocess/socket/importlib/ctypes/pathlib/builtins — those have no place
# in a network-less, fs-less computation and are the usual escape vectors.
ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {"math", "statistics", "json", "re", "datetime", "decimal", "fractions",
     "itertools", "functools", "collections", "typing", "operator"}
)

# Builtins that enable code loading, reflection, or I/O.
BANNED_NAMES: frozenset[str] = frozenset(
    {"eval", "exec", "compile", "open", "__import__", "input", "globals", "locals",
     "vars", "getattr", "setattr", "delattr", "memoryview", "breakpoint", "help"}
)

ENTRYPOINT = "should_fire"


@dataclass(frozen=True)
class AstViolation:
    """One rejection, with a line number for the agent's feedback."""

    code: str          # short machine code, e.g. "banned-import"
    message: str
    lineno: int = 0

    def __str__(self) -> str:
        return f"L{self.lineno}: [{self.code}] {self.message}"


class _Walker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[AstViolation] = []
        self.has_entrypoint = False

    def _add(self, code: str, msg: str, node: ast.AST) -> None:
        self.violations.append(AstViolation(code, msg, getattr(node, "lineno", 0)))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == ENTRYPOINT:
            self.has_entrypoint = True
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # An async should_fire can't be driven by the sync sandbox entrypoint.
        if node.name == ENTRYPOINT:
            self._add("async-entrypoint", f"{ENTRYPOINT} must be a regular (non-async) function", node)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            if top not in ALLOWED_IMPORTS:
                self._add("banned-import", f"import of {alias.name!r} is not allowed", node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        top = (node.module or "").split(".", 1)[0]
        if node.level and node.level > 0:
            self._add("relative-import", "relative imports are not allowed", node)
        elif top not in ALLOWED_IMPORTS:
            self._add("banned-import", f"import from {node.module!r} is not allowed", node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in BANNED_NAMES:
            self._add("banned-name", f"use of {node.id!r} is not allowed", node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Block dunder attribute crawling — the canonical sandbox-escape route
        # (e.g. ``().__class__.__bases__[0].__subclasses__()``).
        if node.attr.startswith("__") and node.attr.endswith("__"):
            self._add("dunder-access", f"access to dunder attribute {node.attr!r} is not allowed", node)
        self.generic_visit(node)


class AstScreen:
    """Reject obviously-unsafe or malformed predicate source before it reaches the sandbox."""

    def check(self, predicate_src: str) -> list[AstViolation]:
        """Return a list of violations; empty list means the predicate passed the screen."""
        try:
            tree = ast.parse(predicate_src)
        except SyntaxError as e:
            return [AstViolation("syntax-error", f"predicate does not parse: {e.msg}", e.lineno or 0)]

        walker = _Walker()
        walker.visit(tree)
        violations = list(walker.violations)
        if not walker.has_entrypoint:
            violations.append(
                AstViolation("no-entrypoint", f"predicate must define a top-level {ENTRYPOINT}(ctx) function")
            )
        return violations
