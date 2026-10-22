"""PAPER evaluation against Core FeatureSets. Does not train and does not place orders."""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

from contracts.enums import Horizon, Timeframe
from contracts.fakes import FakeFundamentalProvider, FakeMarketDataProvider, FakeNewsProvider
from contracts.interfaces import AgentContext, SignalSink
from contracts.schemas.feature_set import FeatureSet

from quant_agents.agents import MeanReversionAgent, MomentumAgent, RegimeAgent, TechnicalAgent, VolumeAgent
from quant_agents.ml.agent import MlAgent
from quant_agents.calendar.static_nse import StaticNseCalendar
from quant_agents.clock import ReplayClock

logger = logging.getLogger(__name__)
READY_ATTEMPTS = 20
READY_DELAY_SECONDS = 1.0
_ML_SKIP_REASONS = frozenset(
    {
        "ml.no_eligible_model",
        "ml.artifact_corrupt",
        "ml.feature_version_mismatch",
        "ml.timeframe_mismatch",
        "ml.feature_invalid",
        "neutral.forced",
        "calendar.not_covered",
    }
)

_AGENTS = (TechnicalAgent, MomentumAgent, MeanReversionAgent, VolumeAgent, RegimeAgent)
_SWING = {"horizon": Horizon.SWING, "timeframe": Timeframe.D1, "regime_index_symbols": ()}
INDEX_SYMBOLS = ("NIFTY50", "INDIAVIX")


class _OneFeatureProvider:
    def __init__(self, feature_set: FeatureSet, extras: tuple[FeatureSet, ...] = ()) -> None:
        self._sets = {feature_set.symbol: feature_set}
        for item in extras:
            self._sets[item.symbol] = item

    def get_feature_set(self, symbol: str, timeframe: Timeframe | str, as_of: datetime) -> FeatureSet:
        found = self._sets.get(symbol.strip().upper())
        if found is None or found.timestamp > as_of:
            raise LookupError(symbol)
        return found


def publish_symbol_signals(
    symbol: str,
    feature_set: FeatureSet,
    sink: SignalSink,
    *,
    agents=_AGENTS,
    clock=None,
    calendar=None,
    configuration: dict | None = None,
    index_sets: tuple[FeatureSet, ...] = (),
    ml_registry=None,
    ml_demo: bool = False,
) -> int:
    """Evaluate every quant agent once at the feature timestamp and submit each signal."""
    as_of = feature_set.timestamp
    clock = clock or ReplayClock(as_of)
    calendar = calendar or StaticNseCalendar()
    context = AgentContext(
        market_data_provider=FakeMarketDataProvider(),
        feature_provider=_OneFeatureProvider(feature_set, index_sets),
        news_provider=FakeNewsProvider(),
        fundamental_provider=FakeFundamentalProvider(),
        configuration=configuration or _SWING,
    )
    written = 0
    for agent_cls in agents:
        signal = agent_cls(clock, calendar).evaluate(symbol, as_of, context)
        sink.submit(signal)
        written += 1
    if ml_registry is not None:
        written += _publish_ml(symbol, as_of, context, sink, clock, calendar, ml_registry, ml_demo)
    return written


def _ml_submittable(signal, *, demo: bool) -> bool:
    if any(code in _ML_SKIP_REASONS for code in signal.reason_codes):
        return False
    if demo:
        if signal.metadata.get("demo") is not True:
            return False
        if signal.metadata.get("training_data") != "synthetic_unvalidated_demo":
            return False
    return True


def _publish_ml(symbol, as_of, context, sink, clock, calendar, registry, demo: bool) -> int:
    try:
        signal = MlAgent(clock, calendar, registry).evaluate(symbol, as_of, context)
    except Exception:
        logger.exception("quant_ml_skipped", extra={"symbol": symbol})
        return 0
    if not _ml_submittable(signal, demo=demo):
        logger.warning(
            "quant_ml_skipped",
            extra={"symbol": symbol, "reason_codes": list(signal.reason_codes)},
        )
        return 0
    sink.submit(signal)
    return 1


def _open_ml_registry(ml_demo: bool, ml_demo_dir: str | None, ml_artifact_dir: str | None):
    if not ml_demo and not ml_artifact_dir:
        return None
    try:
        if ml_demo:
            from pathlib import Path

            from quant_agents.ml.demo import prepare_demo_artifact

            return prepare_demo_artifact(Path(ml_demo_dir or ""))
        from pathlib import Path

        from quant_agents.ml.registry import ModelRegistry

        return ModelRegistry(Path(ml_artifact_dir or ""))
    except Exception:
        logger.exception("quant_ml_skipped")
        return None


def core_is_ready(client: httpx.Client, base_url: str) -> bool:
    try:
        response = client.get(f"{base_url.rstrip('/')}/health")
    except httpx.TransportError:
        return False
    return response.status_code == 200


def wait_for_core_api(
    client: httpx.Client,
    base_url: str,
    *,
    attempts: int = READY_ATTEMPTS,
    delay_seconds: float = READY_DELAY_SECONDS,
    sleep=time.sleep,
) -> bool:
    """Bounded health wait. A refused connection is not a paper pass."""
    for attempt in range(1, attempts + 1):
        if core_is_ready(client, base_url):
            return True
        logger.warning("quant_core_api_not_ready", extra={"attempt": attempt, "attempts": attempts})
        if attempt < attempts:
            sleep(delay_seconds)
    return False


def fetch_feature(
    client: httpx.Client,
    base_url: str,
    token: str,
    symbol: str,
    *,
    attempts: int = 3,
    delay_seconds: float = READY_DELAY_SECONDS,
    sleep=time.sleep,
    timeframe: Timeframe | str = Timeframe.D1,
) -> FeatureSet | None:
    """Retry only when no response arrives. A received response is not retried."""
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(
                f"{base_url.rstrip('/')}/api/v1/features/{symbol}",
                params={"timeframe": timeframe.value if isinstance(timeframe, Timeframe) else str(timeframe)},
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.TransportError:
            logger.warning("quant_feature_unreachable", extra={"symbol": symbol, "attempt": attempt})
            if attempt == attempts:
                raise
            sleep(delay_seconds)
            continue
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return FeatureSet.model_validate(response.json())
    return None


def run_paper_pass(
    base_url: str,
    read_token: str,
    symbols: tuple[str, ...],
    sink: SignalSink,
    *,
    client: httpx.Client | None = None,
    configuration: dict | None = None,
    sleep=time.sleep,
    ready_attempts: int = READY_ATTEMPTS,
    ml_demo: bool = False,
    ml_demo_dir: str | None = None,
    ml_artifact_dir: str | None = None,
) -> int:
    owned = client or httpx.Client(timeout=30.0)
    close = client is None
    written = 0
    try:
        if not wait_for_core_api(owned, base_url, attempts=ready_attempts, sleep=sleep):
            logger.error("quant_core_api_unavailable")
            return 0
        ml_registry = _open_ml_registry(ml_demo, ml_demo_dir, ml_artifact_dir)
        # NIFTY 50 and INDIA VIX for the regime agent; absent until Core has collected them.
        config = dict(configuration or _SWING)
        timeframe = config.get("timeframe", Timeframe.D1)
        index_sets = tuple(
            item
            for item in (fetch_feature(owned, base_url, read_token, name, attempts=1, sleep=sleep, timeframe=timeframe) for name in INDEX_SYMBOLS)
            if item is not None
        )
        if index_sets:
            config["regime_index_symbols"] = tuple(item.symbol for item in index_sets)
        for symbol in symbols:
            feature_set = fetch_feature(owned, base_url, read_token, symbol, sleep=sleep, timeframe=timeframe)
            if feature_set is None:
                logger.info("quant_skip_symbol", extra={"symbol": symbol, "reason": "no_features"})
                continue
            written += publish_symbol_signals(
                symbol,
                feature_set,
                sink,
                configuration=config,
                index_sets=index_sets,
                ml_registry=ml_registry,
                ml_demo=ml_demo,
            )
    finally:
        if close:
            owned.close()
    logger.info("quant_paper_pass", extra={"signals": written, "symbols": len(symbols)})
    return written
