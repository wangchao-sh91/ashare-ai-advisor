import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from app.domain import Exchange, Instrument, InstrumentType, MarketDataCategory
from app.providers.akshare_allowlist import MarketOperation, interface_for
from app.services.market_normalizer import (
    normalize_financial_overview,
    normalize_ownership,
    normalize_pledges,
    normalize_price_history,
    normalize_valuation,
)

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "akshare"
NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="沪市示例",
    code="600001",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)
INDEX = Instrument(
    name="宽基示例指数",
    code="000300",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.BROAD_INDEX,
)
FIXTURES = {
    MarketOperation.STOCK_CATALOG: "stock_catalog.json",
    MarketOperation.INDEX_CATALOG: "index_catalog.json",
    MarketOperation.STOCK_HISTORY: "stock_history.json",
    MarketOperation.INDEX_HISTORY: "index_history.json",
    MarketOperation.FINANCIAL_OVERVIEW: "financial_overview.json",
    MarketOperation.VALUATION_HISTORY: "valuation_history.json",
    MarketOperation.OWNERSHIP: "ownership.json",
    MarketOperation.PLEDGE: "pledge.json",
}


def load_fixture(operation: MarketOperation) -> tuple[pd.DataFrame, dict[str, str]]:
    payload = cast(dict[str, object], json.loads((FIXTURE_DIR / FIXTURES[operation]).read_text()))
    records = cast(list[dict[str, object]], payload["records"])
    expected_units = cast(dict[str, str], payload["expected_units"])
    return pd.DataFrame(records), expected_units


def assert_provider_contract(operation: MarketOperation, frame: pd.DataFrame) -> None:
    missing = interface_for(operation).required_columns - set(frame.columns)
    assert not missing, f"{operation.value} missing upstream fields: {sorted(missing)}"


@pytest.mark.parametrize("operation", list(MarketOperation))
def test_sanitized_fixtures_match_allowlisted_upstream_contract(
    operation: MarketOperation,
) -> None:
    frame, _ = load_fixture(operation)
    assert_provider_contract(operation, frame)


def test_contract_detects_upstream_field_drift() -> None:
    frame, _ = load_fixture(MarketOperation.STOCK_HISTORY)
    drifted = frame.rename(columns={"收盘": "最新价"})

    with pytest.raises(AssertionError, match="收盘"):
        assert_provider_contract(MarketOperation.STOCK_HISTORY, drifted)


def test_history_fixtures_preserve_canonical_unit_contracts() -> None:
    stock_frame, stock_units = load_fixture(MarketOperation.STOCK_HISTORY)
    index_frame, index_units = load_fixture(MarketOperation.INDEX_HISTORY)
    stock_records = normalize_price_history(
        stock_frame,
        instrument=STOCK,
        category=MarketDataCategory.PRICE,
        interface=interface_for(MarketOperation.STOCK_HISTORY).interface,
        upstream_source="sanitized fixture",
        retrieved_at=NOW,
    )
    index_records = normalize_price_history(
        index_frame,
        instrument=INDEX,
        category=MarketDataCategory.INDEX_PRICE,
        interface=interface_for(MarketOperation.INDEX_HISTORY).interface,
        upstream_source="sanitized fixture",
        retrieved_at=NOW,
    )

    assert stock_records[0].units == stock_units
    assert index_records[0].units == index_units


def test_fundamental_fixtures_preserve_canonical_fields_and_units() -> None:
    financial_frame, financial_units = load_fixture(MarketOperation.FINANCIAL_OVERVIEW)
    valuation_frame, valuation_units = load_fixture(MarketOperation.VALUATION_HISTORY)
    ownership_frame, ownership_units = load_fixture(MarketOperation.OWNERSHIP)
    pledge_frame, pledge_units = load_fixture(MarketOperation.PLEDGE)

    financial = normalize_financial_overview(
        financial_frame,
        instrument=STOCK,
        interface=interface_for(MarketOperation.FINANCIAL_OVERVIEW).interface,
        upstream_source="sanitized fixture",
        retrieved_at=NOW,
    )
    valuation = normalize_valuation(
        valuation_frame,
        instrument=STOCK,
        interface=interface_for(MarketOperation.VALUATION_HISTORY).interface,
        upstream_source="sanitized fixture",
        retrieved_at=NOW,
    )
    ownership = normalize_ownership(
        ownership_frame,
        instrument=STOCK,
        interface=interface_for(MarketOperation.OWNERSHIP).interface,
        upstream_source="sanitized fixture",
        retrieved_at=NOW,
    )
    pledges = normalize_pledges(
        pledge_frame,
        instrument=STOCK,
        interface=interface_for(MarketOperation.PLEDGE).interface,
        upstream_source="sanitized fixture",
        retrieved_at=NOW,
    )

    assert {
        str(record.values["metric"]): record.units["value"] for record in financial
    } == financial_units
    assert valuation[0].units == valuation_units
    assert ownership[0].units == ownership_units
    assert pledges[0].units == pledge_units
    provider_fields = {"指标", "PE(TTM)", "持股比例", "占总股本比例"}
    assert provider_fields.isdisjoint(
        set().union(*(record.values for record in financial + valuation + ownership + pledges))
    )
