from pathlib import Path

from quant_agents._lint.feature_arithmetic import scan_file, scan_sources, scan_targets


def test_scanned_modules_are_clean() -> None:
    assert scan_sources() == []
    names = {path.name for path in scan_targets()}
    assert "base.py" in names
    assert "feature_view.py" in names
    assert "agent.py" in names
    assert "technical.py" in names


def test_scanner_self_test_reports_each_banned_construct() -> None:
    path = Path(__file__).with_name("_bad_agent_fixture.py")
    findings = scan_file(path)
    joined = "\n".join(findings)
    assert "arithmetic operator" in joined
    assert "augmented assignment" in joined
    assert "unary minus" in joined
    assert "banned import math" in joined
    assert "banned import operator" in joined
    assert "banned import statistics" in joined
    assert "banned import numpy" in joined
    assert "banned import pandas" in joined
    assert "banned call sum" in joined
    assert "banned call abs" in joined
    assert "banned call min" in joined
    assert "banned call max" in joined
    assert "banned call round" in joined
    assert "banned call pow" in joined
    assert "banned call divmod" in joined
    assert "banned call fsum" in joined
