"""Source news article. published_at and retrieved_at are distinct clocks."""

from typing import Self

from pydantic import AnyHttpUrl, AwareDatetime, Field, model_validator

from contracts.schemas.common import ContractModel, JsonObject, NonEmptyStr, Sha256Hex, Symbol


class NewsArticle(ContractModel):
    """A retrieved article. retrieved_at is never a substitute for published_at."""

    article_id: NonEmptyStr
    source: NonEmptyStr
    title: NonEmptyStr
    url: AnyHttpUrl
    published_at: AwareDatetime = Field(description="Time the source published the article.")
    retrieved_at: AwareDatetime = Field(description="Time this system obtained the article.")
    content_hash: Sha256Hex = Field(description="sha256 hex of raw_text, used for duplicate detection.")
    symbols: list[Symbol] = Field(min_length=1)
    raw_text: NonEmptyStr
    metadata: JsonObject

    @model_validator(mode="after")
    def _retrieval_follows_publication(self) -> Self:
        if self.retrieved_at < self.published_at:
            raise ValueError("retrieved_at cannot precede published_at")
        return self
