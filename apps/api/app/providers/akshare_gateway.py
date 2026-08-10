"""Bounded asynchronous gateway for approved AKShare operations."""

from enum import StrEnum
from functools import partial

import akshare
import pandas as pd
from anyio import CapacityLimiter, fail_after, to_thread

from app.providers.akshare_allowlist import MarketOperation, interface_for
from app.services.ttl_cache import TTLCache

CacheKey = tuple[str, tuple[tuple[str, str], ...]]


class AKShareErrorCode(StrEnum):
    TIMEOUT = "akshare_timeout"
    UPSTREAM_ERROR = "akshare_upstream_error"
    INVALID_RESPONSE = "akshare_invalid_response"
    INVALID_PARAMETERS = "akshare_invalid_parameters"


class AKShareGatewayError(RuntimeError):
    """Secret-safe provider failure."""

    def __init__(self, code: AKShareErrorCode, operation: MarketOperation) -> None:
        self.code = code
        self.operation = operation
        super().__init__(f"AKShare operation {operation.value} failed with {code.value}")


def _cache_key(operation: MarketOperation, parameters: dict[str, object]) -> CacheKey:
    normalized = tuple(sorted((key, str(value).strip()) for key, value in parameters.items()))
    return operation.value, normalized


class AKShareGateway:
    """Execute only allowlisted interfaces with bounded resources."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        max_workers: int,
        cache: TTLCache[CacheKey, pd.DataFrame] | None = None,
        provider: object = akshare,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._limiter = CapacityLimiter(max_workers)
        self._cache = cache
        self._provider = provider

    async def fetch(self, operation: MarketOperation, **parameters: object) -> pd.DataFrame:
        spec = interface_for(operation)
        unknown = set(parameters) - spec.allowed_parameters
        if unknown:
            raise AKShareGatewayError(AKShareErrorCode.INVALID_PARAMETERS, operation)

        key = _cache_key(operation, parameters)
        if self._cache is not None and (cached := self._cache.get(key)) is not None:
            return cached

        interface = getattr(self._provider, spec.interface)
        for attempt in range(self._max_retries + 1):
            try:
                with fail_after(self._timeout_seconds):
                    result = await to_thread.run_sync(
                        partial(interface, **parameters),
                        limiter=self._limiter,
                        abandon_on_cancel=True,
                    )
                if not isinstance(result, pd.DataFrame):
                    raise AKShareGatewayError(AKShareErrorCode.INVALID_RESPONSE, operation)
                if not spec.required_columns <= set(result.columns):
                    raise AKShareGatewayError(AKShareErrorCode.INVALID_RESPONSE, operation)
                if self._cache is not None:
                    self._cache.set(key, result)
                return result.copy(deep=True)
            except TimeoutError as exc:
                if attempt == self._max_retries:
                    raise AKShareGatewayError(AKShareErrorCode.TIMEOUT, operation) from exc
            except AKShareGatewayError:
                raise
            except Exception as exc:
                if attempt == self._max_retries:
                    raise AKShareGatewayError(AKShareErrorCode.UPSTREAM_ERROR, operation) from exc
        raise AssertionError("unreachable retry state")

    def close(self, *, wait: bool = True) -> None:
        """Retained for lifecycle symmetry; AnyIO owns worker teardown."""
