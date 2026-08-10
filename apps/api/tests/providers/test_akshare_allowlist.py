import inspect
from importlib.metadata import version

import akshare

from app.providers.akshare_allowlist import (
    AKSHARE_INTERFACES,
    AKSHARE_VERSION,
)


def test_akshare_version_is_exactly_pinned() -> None:
    assert version("akshare") == AKSHARE_VERSION


def test_approved_interfaces_exist_with_expected_parameters() -> None:
    for spec in AKSHARE_INTERFACES.values():
        interface = getattr(akshare, spec.interface)
        actual_parameters = set(inspect.signature(interface).parameters)
        assert spec.allowed_parameters <= actual_parameters
        assert spec.required_columns
        assert spec.upstream_source


def test_allowlist_covers_each_market_operation_once() -> None:
    assert {spec.operation for spec in AKSHARE_INTERFACES.values()} == set(AKSHARE_INTERFACES)
