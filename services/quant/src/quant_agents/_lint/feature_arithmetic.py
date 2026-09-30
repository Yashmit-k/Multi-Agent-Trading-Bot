"""Static check: agents must not do arithmetic on features."""

from __future__ import annotations

import ast
from pathlib import Path

BANNED_IMPORTS = frozenset({"math", "statistics", "numpy", "pandas", "operator"})
BANNED_CALLS = frozenset({"sum", "abs", "min", "max", "round", "pow", "divmod", "fsum"})


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def scan_targets() -> list[Path]:
    root = package_root()
    paths: list[Path] = [root / "feature_view.py", root / "base.py", root / "ml" / "agent.py"]
    agents = root / "agents"
    if agents.is_dir():
        paths.extend(sorted(agents.glob("*.py")))
    return [path for path in paths if path.exists() and path.name != "__init__.py"]


def scan_file(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and not isinstance(node.op, (ast.BitOr, ast.BitAnd)):
            findings.append(f"{path.name}:{node.lineno}: arithmetic operator")
        elif isinstance(node, ast.AugAssign):
            findings.append(f"{path.name}:{node.lineno}: augmented assignment")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            if not isinstance(node.operand, ast.Constant):
                findings.append(f"{path.name}:{node.lineno}: unary minus on non-literal")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".", 1)[0]
                if root_name in BANNED_IMPORTS:
                    findings.append(f"{path.name}:{node.lineno}: banned import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root_name = module.split(".", 1)[0]
            if root_name in BANNED_IMPORTS:
                findings.append(f"{path.name}:{node.lineno}: banned import {module}")
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in BANNED_CALLS:
                findings.append(f"{path.name}:{node.lineno}: banned call {name}")
    return findings


def scan_sources(paths: list[Path] | None = None) -> list[str]:
    findings: list[str] = []
    for path in paths or scan_targets():
        findings.extend(scan_file(path))
    return findings


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
