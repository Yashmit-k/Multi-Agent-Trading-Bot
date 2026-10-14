import inspect
import sys
from pathlib import Path

import pytest

from quant_agents.research.h001.authorization import RestrictedSourceRefused
from quant_agents.research.h001.model import fit_h001

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_h001_threshold34_fit import assert_research_path  # noqa: E402


def test_experimental_fit_runner_refuses_holdout_paths() -> None:
    with pytest.raises(RestrictedSourceRefused, match="holdout"):
        assert_research_path("snapshots/holdout_after_20261005/nifty50_1d.jsonl", freeze_open=True)


def test_fit_h001_has_no_validation_label_argument() -> None:
    assert "y_valid" not in inspect.signature(fit_h001).parameters
