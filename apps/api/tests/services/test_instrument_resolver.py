import pandas as pd
import pytest

from app.domain import Exchange, InstrumentType
from app.services.instrument_resolver import InstrumentResolver, ResolutionStatus


@pytest.fixture
def resolver() -> InstrumentResolver:
    return InstrumentResolver(
        pd.DataFrame(
            [
                {"code": "600519", "name": "贵州茅台"},
                {"code": "000001", "name": "平安银行"},
                {"code": "430047", "name": "诺思兰德"},
            ]
        )
    )


@pytest.mark.parametrize("query", ["贵州茅台", "600519", "SH600519", "600519.SH"])
def test_resolves_stock_name_code_and_exchange_forms(
    resolver: InstrumentResolver, query: str
) -> None:
    result = resolver.resolve(query)

    assert result.status is ResolutionStatus.RESOLVED
    assert result.instrument is not None
    assert result.instrument.code == "600519"
    assert result.instrument.exchange is Exchange.SSE


@pytest.mark.parametrize("query", ["沪深300", "CSI 300", "SH000300", "000300.SH"])
def test_resolves_only_approved_broad_indexes(resolver: InstrumentResolver, query: str) -> None:
    result = resolver.resolve(query)

    assert result.instrument is not None
    assert result.instrument.instrument_type is InstrumentType.BROAD_INDEX
    assert result.instrument.code == "000300"


def test_bare_colliding_code_is_ambiguous_but_exchange_qualifier_resolves(
    resolver: InstrumentResolver,
) -> None:
    ambiguous = resolver.resolve("000001")
    assert ambiguous.status is ResolutionStatus.AMBIGUOUS
    assert len(ambiguous.candidates) == 2

    stock = resolver.resolve("SZ000001")
    index = resolver.resolve("SH000001")
    assert stock.instrument is not None and stock.instrument.name == "平安银行"
    assert index.instrument is not None and index.instrument.name == "上证指数"


def test_resolves_beijing_exchange_a_share(resolver: InstrumentResolver) -> None:
    result = resolver.resolve("430047.BJ")

    assert result.instrument is not None
    assert result.instrument.exchange is Exchange.BSE


def test_unknown_or_unsupported_index_is_not_guessed(resolver: InstrumentResolver) -> None:
    assert resolver.resolve("中证1000").status is ResolutionStatus.NOT_FOUND


def test_catalog_schema_is_validated() -> None:
    with pytest.raises(ValueError, match="required columns"):
        InstrumentResolver(pd.DataFrame([{"symbol": "600519"}]))
