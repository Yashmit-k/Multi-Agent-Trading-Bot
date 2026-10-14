from datetime import date

import pytest

from quant_agents.research.h001.events import ExclusionReason
from quant_agents.research.h001.split import (
    INCONCLUSIVE,
    SATISFIED,
    UnexpectedDecisionDate,
    assign_partition,
    smaller_class_check,
)


def test_split_cutoff_and_purge() -> None:
    purged = assign_partition("1", "RELIANCE", date(2024, 6, 28), date(2024, 7, 1))
    assert purged.partition == "purged"
    assert purged.reason == ExclusionReason.PURGED_EMBARGO
    trained = assign_partition("1", "RELIANCE", date(2024, 6, 28), date(2024, 6, 30))
    assert trained.partition == "train"
    assert trained.reason is None
    validated = assign_partition("1", "RELIANCE", date(2024, 7, 2), date(2024, 7, 3))
    assert validated.partition == "validation"
    with pytest.raises(UnexpectedDecisionDate) as raised:
        assign_partition("1", "RELIANCE", date(2025, 2, 15), date(2025, 2, 17))
    assert raised.value.decision == date(2025, 2, 15)


def test_minority_bar_and_validation_labels_are_not_an_input() -> None:
    assert smaller_class_check((0,) * 33 + (1,) * 100).status == INCONCLUSIVE
    assert smaller_class_check((0, 1) * 34).status == SATISFIED
    assert "y_valid" not in assign_partition.__annotations__
    assert smaller_class_check((0, 1) * 34).minority_count == 34
