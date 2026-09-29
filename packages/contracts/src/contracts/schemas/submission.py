"""Result of submitting an agent signal through SignalSink."""

from typing import Self

from pydantic import model_validator

from contracts.schemas.common import ContractModel, NonEmptyStr


class SubmissionResult(ContractModel):
    """Acknowledgement from the signal sink. duplicate submissions are not accepted."""

    accepted: bool
    signal_id: NonEmptyStr
    duplicate: bool
    message: NonEmptyStr

    @model_validator(mode="after")
    def _duplicate_is_not_accepted(self) -> Self:
        if self.duplicate and self.accepted:
            raise ValueError("duplicate submissions are not accepted")
        return self
