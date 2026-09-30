import ast
from pathlib import Path

from quant_agents.ml.preprocessing import make_preprocessor


def test_preprocessor_has_no_feature_binops() -> None:
    path = Path(make_preprocessor.__module__.replace(".", "/") if False else "")
    source = Path(__file__).resolve().parents[2] / "src" / "quant_agents" / "ml" / "preprocessing.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    binops = [node for node in ast.walk(tree) if isinstance(node, ast.BinOp)]
    assert binops == []
