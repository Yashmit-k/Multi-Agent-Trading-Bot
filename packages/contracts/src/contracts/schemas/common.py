"""Shared field types for contract models."""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

FROZEN_CONFIG = ConfigDict(extra="forbid", frozen=True)

_FEATURE_NAME = re.compile(r"^[a-z0-9_]+$")


def _normalize_symbol(value: object) -> object:
    if isinstance(value, str):
        return value.strip().upper()
    return value


Symbol = Annotated[
    str,
    BeforeValidator(_normalize_symbol),
    StringConstraints(min_length=1, pattern=r"^[A-Z0-9&-]+$"),
]
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ReasonCode = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_.]+$", min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Score = Annotated[float, Field(ge=-1, le=1)]
UnitFloat = Annotated[float, Field(ge=0, le=1)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
DrawdownFraction = Annotated[Decimal, Field(ge=0, le=1)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, str | bool):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


def _json_object(value: object) -> object:
    if not isinstance(value, dict) or not _is_json_value(value):
        raise ValueError("metadata must be a JSON object")
    return value


def _features(value: object) -> object:
    if not isinstance(value, dict):
        raise ValueError("features must be an object")
    cleaned: dict[str, str | int | float | bool] = {}
    for key, item in value.items():
        if not isinstance(key, str) or _FEATURE_NAME.fullmatch(key) is None:
            raise ValueError("feature names must match ^[a-z0-9_]+$")
        if isinstance(item, bool):
            cleaned[key] = item
        elif isinstance(item, int):
            cleaned[key] = item
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("feature values must be finite")
            cleaned[key] = item
        elif isinstance(item, str):
            cleaned[key] = item
        else:
            raise ValueError("feature values must be JSON scalars")
    return cleaned


JsonObject = Annotated[dict[str, Any], BeforeValidator(_json_object)]
Features = Annotated[dict[str, str | int | float | bool], BeforeValidator(_features)]


class ContractModel(BaseModel):
    model_config = FROZEN_CONFIG
