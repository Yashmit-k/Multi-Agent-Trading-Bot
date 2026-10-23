"""Closed Intelligence reason-code vocabulary and evidence-supported quality gate."""

from __future__ import annotations

import re
from dataclasses import replace

from intelligence_agents.llm.types import LLMAssessment
from intelligence_agents.llm.validate import ValidationError

NEWS_CODES = frozenset(
    {
        "regulatory_approval",
        "order_win",
        "corporate_action",
        "management_change",
        "product_update",
        "capacity_expansion",
        "operating_updates",
        "profit_growth",
        "price_move",
        "capital_raise",
        "results_preview",
        "analyst_view",
    }
)
FUNDAMENTAL_CODES = frozenset(
    {"revenue_growth", "eps", "profit_growth", "margin", "roe", "roce", "debt", "cash_flow"}
)
EARNINGS_CODES = frozenset({"profit_growth", "eps", "margin", "operating_updates"})
VALUATION_CODES = frozenset({"last_price"})
ALLOWLISTS = {
    "news": NEWS_CODES,
    "fundamental": FUNDAMENTAL_CODES,
    "earnings": EARNINGS_CODES,
    "valuation": VALUATION_CODES,
}

_ORDER = re.compile(r"\b(buy|sell|place order|market order|limit order)\b", re.IGNORECASE)
_ID_LIKE = re.compile(
    r"(^news_)|(^article_)|(https?:)|(www\.)|(_20\d{6}$)|([a-f0-9]{32})|(^\d+$)",
    re.IGNORECASE,
)
_PHRASES = {
    "regulatory_approval": ("regulatory approval", "regulatory clearance", "licence", "license granted"),
    "order_win": ("material contract", "major order", "order win", "bagged order"),
    "corporate_action": ("merger", "acquisition", "takeover", "strategic transaction"),
    "management_change": ("management change", "ceo resign", "appointed ceo", "new cfo"),
    "product_update": ("product launch", "product update", "new product"),
    "capacity_expansion": ("capacity expansion", "new facility", "new plant"),
    "operating_updates": (
        "operating update", "operating updates", "operational update", "business update", "expansion", "plans to",
        "launches", "partnership", "agreement", "contract", "deal", "deliveries", "sales", "volumes", "operations",
        "subsidiary", "unit", "facility", "plant", "board", "approves", "announces",
    ),
    "capital_raise": ("ipo", "qip", "rights issue", "fundraise", "fund raise", "raise funds", "raises", "stake sale", "block deal", "anchor", "share sale", "offer for sale", "listing"),
    "results_preview": ("results preview", "q1 preview", "q2 preview", "q3 preview", "q4 preview", "earnings preview", "results today", "results date", "to announce", "ahead of q", "ahead of results", "q2 results", "q1 results", "q3 results", "q4 results"),
    "analyst_view": ("target price", "upgrade", "downgrade", "rating", "brokerage", "analyst", "price target", "outperform", "underperform", "overweight", "underweight"),
    "price_move": (
        "share price", "shares", "stock price", "hits", "falls", "rises", "jumps", "surges", "slumps",
        "rallies", "gainers", "losers", "52-week", "month low", "month high", "record high",
    ),
    "profit_growth": ("profit growth", "earnings growth", "profit rose", "profit beat", "higher profit"),
    "revenue_growth": ("revenue growth", "sales growth"),
    "margin": ("margin",),
    "roe": ("roe", "return on equity"),
    "roce": ("roce", "return on capital"),
    "debt": ("debt", "leverage"),
    "cash_flow": ("cash flow", "cash-flow"),
}


AGENT_PROMPTS = {
    "news": (
        "Score news evidence for an Indian equity. Use only the article body. "
        "Ignore identifiers, article IDs, URLs, tickers, dates, and source names. "
        "A valid reason is an event type supported by the article, not a copied word. "
        "Do not invent events or numbers. Do not place orders. "
        "If the article is only an operational/business update, use operating_updates. "
        "Use profit_growth only if the article states profit or earnings growth. "
        "If the article mainly reports a share-price move or market performance, use price_move. "
        "Use capital_raise for IPOs, QIPs, rights issues, block deals, or stake sales; results_preview for upcoming results; "
        "analyst_view for brokerage ratings or target-price changes; operating_updates for business news such as deals, launches, expansion, or volumes. "
        "If nothing in the article supports a score, return reason_codes [insufficient_data] with sentiment 0."
    ),
    "fundamental": (
        "Interpret computed fundamental metrics. Metric names and values are authoritative. "
        "Do not invent metrics. Ignore identifiers. Do not place orders. "
        "Pick reason_codes from metric names that actually appear."
    ),
    "valuation": (
        "Interpret a computed valuation. last_price, eps, and implied_pe are authoritative. "
        "Do not invent prices. If last_price is the decisive evidence, reason_codes must be [last_price]. "
        "Ignore identifiers. Do not place orders."
    ),
    "earnings": (
        "Interpret earnings context from supplied EPS metrics and/or article body. "
        "Ignore identifiers, article IDs, URLs, and tickers. Do not invent results. "
        "Use eps when EPS figures are supplied, operating_updates only when operational commentary is material, "
        "profit_growth only when profit or earnings growth is explicit. Do not place orders."
    ),
}


def allowlist_for(task: str) -> frozenset[str]:
    return ALLOWLISTS.get(task, frozenset())


def instruction_for(task: str) -> str:
    allowed = ",".join(sorted(allowlist_for(task)))
    hint = AGENT_PROMPTS.get(task, "Use only supplied evidence. Do not invent facts.")
    return (
        f"task={task}. {hint} Allowed reason_codes: {allowed}. "
        "reason_codes must be a non-empty subset of the allowed list and must be supported by the evidence. "
        "Never copy example reason_codes. Never emit fixture.heuristic. Never emit article IDs."
    )


def sanitize_llm_text(text: str) -> str:
    """Drop identifier-like tokens so they never appear as copied reasons."""
    cleaned = re.sub(r"\bnews-[a-z0-9_-]+\b", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"\b[a-f0-9]{32,64}\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _blob(evidence: str) -> str:
    return re.sub(r"\s+", " ", evidence.lower())


def _has_valuation_price(blob: str) -> bool:
    # The valuation prompt carries the price only as the bucketed P/E (pe_bucket), so the LLM cache can reuse the
    # answer between cycles; older prompts carried last_price itself.
    return "last_price" in blob or "pe_bucket" in blob


def evidence_supports(code: str, *, task: str, evidence: str) -> bool:
    blob = _blob(evidence)
    if task == "valuation" and code == "last_price":
        return _has_valuation_price(blob)
    if task == "fundamental":
        if code == "eps":
            return bool(re.search(r"\beps\b", blob))
        if code == "revenue_growth":
            return "revenue" in blob
        if code == "cash_flow":
            return "cash" in blob and "flow" in blob
        if code in FUNDAMENTAL_CODES:
            return code.replace("_", " ") in blob or code in blob
        return False
    if task == "earnings" and code == "eps":
        return bool(re.search(r"\beps\b", blob)) or "eps=" in blob or "'eps'" in blob
    phrases = _PHRASES.get(code, ())
    return any(phrase in blob for phrase in phrases)


def _looks_like_identifier(code: str) -> bool:
    if _ID_LIKE.search(code):
        return True
    if re.fullmatch(r"[a-z]+_[a-z0-9]+_\d+", code):
        return True
    return False


def normalize_reason_code(code: str, *, task: str, evidence: str) -> str | None:
    item = code.strip().lower().replace("-", "_")
    if item in {"from_supplied_context", "context_token", "example_code", "fixture.heuristic"}:
        return None
    if _looks_like_identifier(item):
        return None
    if task == "valuation" and "price" in item.replace(".", "_") and _has_valuation_price(_blob(evidence)):
        item = "last_price"
    allowed = allowlist_for(task)
    if item not in allowed:
        return None
    if not evidence_supports(item, task=task, evidence=evidence):
        return None
    return item


def quality_gate(assessment: LLMAssessment, *, task: str, evidence: str, raw: str = "") -> LLMAssessment:
    if assessment.fallback or assessment.model == "fixture":
        return assessment
    if raw and _ORDER.search(raw):
        raise ValidationError("order_language")
    kept: list[str] = []
    for code in assessment.reason_codes:
        mapped = normalize_reason_code(code, task=task, evidence=evidence)
        if mapped and mapped not in kept:
            kept.append(mapped)
    if not kept:
        # The model's own "no usable evidence" answer is a valid, neutral opinion.
        if any(code.strip().lower() == "insufficient_data" for code in assessment.reason_codes):
            return replace(assessment, reason_codes=("insufficient_data",), sentiment=0.0, impact=0.0, high_impact=False)
        raise ValidationError("unsupported_reason")
    return replace(assessment, reason_codes=tuple(kept))
