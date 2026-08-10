"""Canonical A-share and approved broad-index resolution."""

import re
import unicodedata
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.domain import Exchange, Instrument, InstrumentType

_EXCHANGE_ALIASES = {
    "SH": Exchange.SSE,
    "SSE": Exchange.SSE,
    "SZ": Exchange.SZSE,
    "SZSE": Exchange.SZSE,
    "BJ": Exchange.BSE,
    "BSE": Exchange.BSE,
}

APPROVED_BROAD_INDEXES: tuple[tuple[Instrument, frozenset[str]], ...] = (
    (
        Instrument(
            name="上证指数",
            code="000001",
            exchange=Exchange.SSE,
            instrument_type=InstrumentType.BROAD_INDEX,
        ),
        frozenset({"上证指数", "上证综指", "SSE COMPOSITE"}),
    ),
    (
        Instrument(
            name="上证50",
            code="000016",
            exchange=Exchange.SSE,
            instrument_type=InstrumentType.BROAD_INDEX,
        ),
        frozenset({"上证50", "SSE 50"}),
    ),
    (
        Instrument(
            name="沪深300",
            code="000300",
            exchange=Exchange.SSE,
            instrument_type=InstrumentType.BROAD_INDEX,
        ),
        frozenset({"沪深300", "CSI300", "CSI 300"}),
    ),
    (
        Instrument(
            name="中证500",
            code="000905",
            exchange=Exchange.SSE,
            instrument_type=InstrumentType.BROAD_INDEX,
        ),
        frozenset({"中证500", "CSI500", "CSI 500"}),
    ),
    (
        Instrument(
            name="深证成指",
            code="399001",
            exchange=Exchange.SZSE,
            instrument_type=InstrumentType.BROAD_INDEX,
        ),
        frozenset({"深证成指", "深证成份指数", "SZSE COMPONENT"}),
    ),
    (
        Instrument(
            name="创业板指",
            code="399006",
            exchange=Exchange.SZSE,
            instrument_type=InstrumentType.BROAD_INDEX,
        ),
        frozenset({"创业板指", "创业板指数", "CHINEXT"}),
    ),
)


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class InstrumentResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ResolutionStatus
    candidates: list[Instrument] = Field(default_factory=list)

    @property
    def instrument(self) -> Instrument | None:
        return self.candidates[0] if self.status is ResolutionStatus.RESOLVED else None


def _normalize_text(value: object) -> str:
    return "".join(unicodedata.normalize("NFKC", str(value)).upper().split())


def _stock_exchange(code: str) -> Exchange | None:
    if code.startswith(("4", "8")):
        return Exchange.BSE
    if code.startswith("6"):
        return Exchange.SSE
    if code.startswith(("0", "3")):
        return Exchange.SZSE
    return None


def _query_parts(query: str) -> tuple[str, Exchange | None]:
    normalized = _normalize_text(query)
    prefix_match = re.fullmatch(r"(SH|SSE|SZ|SZSE|BJ|BSE)(\d{6})", normalized)
    if prefix_match:
        return prefix_match.group(2), _EXCHANGE_ALIASES[prefix_match.group(1)]
    suffix_match = re.fullmatch(r"(\d{6})\.(SH|SSE|SZ|SZSE|BJ|BSE)", normalized)
    if suffix_match:
        return suffix_match.group(1), _EXCHANGE_ALIASES[suffix_match.group(2)]
    return normalized, None


class InstrumentResolver:
    """Resolve exact catalog identities without fuzzy guessing."""

    def __init__(self, stock_catalog: pd.DataFrame) -> None:
        missing = {"code", "name"} - set(stock_catalog.columns)
        if missing:
            raise ValueError(f"stock catalog is missing required columns: {sorted(missing)}")
        self._stocks = self._build_stocks(stock_catalog)

    @staticmethod
    def _build_stocks(stock_catalog: pd.DataFrame) -> tuple[Instrument, ...]:
        instruments: list[Instrument] = []
        for row in stock_catalog[["code", "name"]].itertuples(index=False, name=None):
            code = str(row[0]).strip().zfill(6)
            exchange = _stock_exchange(code)
            name = str(row[1]).strip()
            if exchange is not None and re.fullmatch(r"\d{6}", code) and name:
                instruments.append(
                    Instrument(
                        name=name,
                        code=code,
                        exchange=exchange,
                        instrument_type=InstrumentType.STOCK,
                    )
                )
        return tuple(instruments)

    def resolve(self, query: str) -> InstrumentResolution:
        normalized, exchange_hint = _query_parts(query)
        candidates: list[Instrument] = []
        for stock in self._stocks:
            if normalized in {stock.code, _normalize_text(stock.name)}:
                candidates.append(stock)
        for index, aliases in APPROVED_BROAD_INDEXES:
            normalized_aliases = {_normalize_text(alias) for alias in aliases}
            if normalized in {index.code, *normalized_aliases}:
                candidates.append(index)
        if exchange_hint is not None:
            candidates = [item for item in candidates if item.exchange is exchange_hint]

        unique = list({(item.instrument_type, item.symbol): item for item in candidates}.values())
        if len(unique) == 1:
            return InstrumentResolution(status=ResolutionStatus.RESOLVED, candidates=unique)
        if unique:
            return InstrumentResolution(status=ResolutionStatus.AMBIGUOUS, candidates=unique)
        return InstrumentResolution(status=ResolutionStatus.NOT_FOUND)

    def resolve_text(self, text: str) -> InstrumentResolution:
        """Resolve explicit exact catalog mentions embedded in natural-language text."""
        normalized = _normalize_text(text)
        candidates: list[Instrument] = []
        code_mentions = set(re.findall(r"(?<!\d)\d{6}(?!\d)", normalized))
        for code in code_mentions:
            candidates.extend(self.resolve(code).candidates)
        for stock in self._stocks:
            if _normalize_text(stock.name) in normalized:
                candidates.append(stock)
        for index, aliases in APPROVED_BROAD_INDEXES:
            if any(_normalize_text(alias) in normalized for alias in aliases):
                candidates.append(index)

        unique = list({(item.instrument_type, item.symbol): item for item in candidates}.values())
        if len(unique) == 1:
            return InstrumentResolution(status=ResolutionStatus.RESOLVED, candidates=unique)
        if unique:
            return InstrumentResolution(status=ResolutionStatus.AMBIGUOUS, candidates=unique)
        return InstrumentResolution(status=ResolutionStatus.NOT_FOUND)
