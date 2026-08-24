"""Allowlist AST checks include relative imports; new dependencies require review."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1] / "src" / "aftermath"
ALLOWED = {
    "core": {"core"},
    "ports": {"core", "ports"},
    "application": {"core", "ports", "application"},
    "adapters": {"core", "ports", "adapters"},
    "api": {"core", "ports", "application", "adapters", "api", "config"},
    "worker": {"core", "ports", "application", "adapters", "worker", "config"},
    "experiments": {"core", "ports", "application", "adapters", "experiments", "config"},
    "config.py": {"config"},
}
EXTERNAL = {"core": {"pydantic"}, "ports": set(), "application": set()}


def violations(source: str, package: list[str], layer: str) -> list[str]:
    errors = []
    for node in ast.walk(ast.parse(source)):
        imports: list[str] = []
        if isinstance(node, ast.Import):
            imports = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            prefix = package[: len(package) - node.level + 1] if node.level else []
            base = ".".join(prefix + ([node.module] if node.module else []))
            imports = [base + "." + alias.name for alias in node.names]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                errors.append("dynamic imports prohibited")
        for name in imports:
            parts = name.split(".")
            if name.startswith(("aftermath.eval", "aftermath.annotation")):
                errors.append(name)
            elif parts[0] == "aftermath" and len(parts) > 1:
                if parts[1] not in ALLOWED[layer]:
                    errors.append(name)
            elif layer in EXTERNAL and parts[0] not in sys.stdlib_module_names | EXTERNAL[layer]:
                errors.append(name)
    return errors


def test_import_boundaries() -> None:
    for path in ROOT.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(ROOT)
        package = ["aftermath", *relative.parts[:-1]]
        assert not violations(path.read_text(), package, relative.parts[0]), str(path)


def test_boundary_guard_rejects_direct_relative_and_gold_imports() -> None:
    assert violations("import sqlalchemy", ["aftermath", "core"], "core")
    assert violations(
        "from ..adapters import persistence", ["aftermath", "application"], "application"
    )
    assert violations("from aftermath.eval import gold", ["aftermath", "adapters"], "adapters")
    assert not violations("from aftermath.core import contracts", ["aftermath", "ports"], "ports")
