## Why

The current backend depends on multiple AKShare interfaces and a supervised Doubao MCP subprocess, but the intended v1.1 deployment must operate within the actually available free-provider limits. The evidence pipeline also needs explicit category-level sufficiency so that daily prices, searched financial facts, and corporate events cannot incorrectly substitute for one another.

## What Changes

- **BREAKING** Replace all runtime AKShare operations with the pinned Tushare Python SDK and allow only the free unadjusted A-share `daily` endpoint for stock price history.
- **BREAKING** Remove deterministic broad-index market-data retrieval; retain supported broad indexes as search-grounded research subjects without time-series metrics.
- **BREAKING** Replace the Doubao SearchInfinity MCP subprocess, discovery, and stdio lifecycle with the authenticated Doubao Search Custom HTTPS API.
- Upgrade the single structured model classification call into a bounded question-normalization contract that rewrites the current question and returns canonical instrument identity, requested evidence categories, analysis period, freshness, and clarification state.
- Route price, financial, valuation, ownership, pledge, corporate-event, and index evidence independently, with explicit provider and failure behavior for each category.
- Never fall back to search for missing or invalid stock daily prices; report price evidence as insufficient while preserving unrelated valid categories.
- Support combined daily-price and news/announcement analysis on one trading-day timeline, including deterministic event-window observations without causal claims.
- Add provider quota, rate-limit, cache, readiness, provenance, unit-normalization, and secret-safe failure behavior for Tushare and the Doubao Search API.
- Remove AKShare- and MCP-specific runtime dependencies, container packaging, configuration, fixtures, tests, and operational documentation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `market-data-grounding`: Restrict deterministic market data to validated Tushare A-share daily records, update provenance and units, prohibit price search fallback, and define event-window calculations.
- `web-search-grounding`: Replace MCP transport with the bounded Doubao Search Custom HTTPS API and extend search evidence to unsupported financial categories, broad indexes, and corporate events with quota-aware degradation.
- `research-question-answering`: Normalize each question and instrument in one structured LLM call, route and assess evidence by category, retain search-only broad indexes, and define partial and combined price/event answers.

## Impact

- Backend providers, settings, runtime composition, readiness, orchestration planning/execution, domain models, normalization, validation, analytics, evidence aggregation, and answer verification.
- Python dependencies and container builds: remove AKShare and MCP SearchInfinity server/runtime dependencies; add and pin Tushare and use the existing asynchronous HTTP stack for Doubao Search.
- Provider configuration changes from AKShare/MCP settings to `TUSHARE_TOKEN` and a Doubao Search API key plus bounded timeout, retry, cache, and concurrency settings.
- Existing provider fixtures, unit/contract/integration tests, fake-provider paths, live smoke checks, deployment checks, environment examples, and operator/user documentation.
- No intentional change to the HTTP chat request or SSE response protocol; the frontend may receive more explicit category-level limitations and partial-answer states through existing structures.
