## 1. Provider Compatibility and Configuration

- [x] 1.1 Run an opt-in compatibility probe for the current Python toolchain against Tushare `pro.daily`, verify free-account access and field/unit semantics, and pin the newest passing SDK version with redacted contract fixtures.
- [x] 1.2 Probe the Doubao Search Custom API request, `Result.WebResults` response, authority/date metadata, and documented `10406` and `700429` errors with opt-in credentials, then freeze redacted success and failure fixtures.
- [x] 1.3 Replace AKShare/MCP settings with validated Tushare token, Doubao API key, timeout, concurrency, retry, query/count, and per-category cache settings, including the documented defaults and secret-safe validation tests.

## 2. Question Normalization and Evidence Domain

- [x] 2.1 Add the structured question-normalization schema for rewritten question, intent, canonical instrument, requested categories, analysis period, freshness, and clarification state.
- [x] 2.2 Upgrade the bounded model call and prompt to emit the normalization schema from the current question plus bounded session context, with no provider or tool-selection authority.
- [x] 2.3 Validate code/name consistency, A-share `ts_code` syntax, supported scope, date ranges, category values, and ambiguous or conflicting identities; return clarification before provider calls when validation fails.
- [x] 2.4 Add unit tests for explicit instruments, pronoun follow-ups, changed instruments, mixed questions, broad indexes, unsupported assets, malformed structured output, and bounded retry/clarification behavior.
- [x] 2.5 Add application-owned evidence-category, provider-plan, category-outcome, insufficiency-reason, and Tushare/web provenance models with serialization tests.

## 3. Tushare Daily-Price Provider

- [x] 3.1 Implement the Tushare gateway around one initialized `pro_api` client and expose only canonical A-share daily retrieval with inclusive normalized dates.
- [x] 3.2 Run synchronous SDK calls through a capacity-limited worker boundary with deadlines, bounded retries where safe, late-result abandonment, and secret-safe error mapping.
- [x] 3.3 Normalize required daily fields into ordered domain records, deduplicate trading dates, and convert `vol` from hands to shares and `amount` from thousands of CNY to CNY.
- [x] 3.4 Add schema, numeric, unit, code, ordering, freshness, minimum-sample, authentication, timeout, empty-result, and malformed-response validation tests using provider-shaped fixtures.
- [x] 3.5 Add versioned daily cache keys and configurable TTL/capacity behavior with injected-clock tests for hits, expiry, eviction, and distinct stock/date ranges.
- [x] 3.6 Emit category-specific price outcomes and Tushare provenance, and add tests proving every failure path leaves price insufficient without scheduling a search fallback.

## 4. Doubao Search HTTPS Provider

- [x] 4.1 Implement a shared asynchronous client restricted to `POST https://open.feedcoopapi.com/search_api/web_search` with server-side bearer authentication and bounded network resources.
- [x] 4.2 Map category plans to provider-compliant web-only requests, enforcing query length, result count, URL/authority fields, finance filters, and normalized time ranges.
- [x] 4.3 Normalize valid `Result.WebResults` into citation evidence with category, claim, title, destination URL, publisher/domain, publication time, retrieval time, and authority metadata.
- [x] 4.4 Rank primary and authoritative sources, label secondary evidence, disclose credible conflicts, and reject malformed, uncitable, or category-irrelevant results with unit tests.
- [x] 4.5 Implement category-aware query caching, global concurrency limits, bounded transient retry/backoff, non-retryable quota handling for `10406`, and bounded rate-limit handling for `700429` with injected-clock tests.
- [x] 4.6 Expose configured, usable, rate-limited, quota-unavailable, and unavailable readiness states without leaking secrets or consuming search quota on routine probes.

## 5. Category-Based Research Orchestration

- [x] 5.1 Replace instrument-route planning with fixed application mappings from normalized categories to Tushare daily or Doubao search, including search-only broad-index handling.
- [x] 5.2 Execute independent category plan items under total request bounds and preserve successful category evidence when another provider or category fails.
- [x] 5.3 Evaluate sufficiency independently for price, financial, valuation, ownership, pledge, corporate-event, and index-context outcomes before invoking answer generation.
- [x] 5.4 Prevent web evidence from becoming a market fact or satisfying the price category, and prevent unrelated credible search results from satisfying another requested category.
- [x] 5.5 Update answer context and verification to render complete, partial, and evidence-insufficient results with category limitations, provenance, freshness, citations, risk notices, and the existing investment disclaimer.
- [x] 5.6 Add orchestration tests for price-only, search-only index, mixed knowledge/research, all-categories-success, partial-category, all-category-failure, quota failure, and Tushare-failure-with-search-success flows.

## 6. Corporate-Event Timeline Analytics

- [x] 6.1 Build stock-specific news and announcement queries from the canonical instrument and normalized analysis period, then deduplicate accepted corporate-event evidence by canonical URL and event identity.
- [x] 6.2 Align events after market close or on non-trading days to the next available trading day, retain unknown-time uncertainty, and exclude undated events from event-window calculations.
- [x] 6.3 Compute deterministic one-, three-, and five-trading-day price observations from validated Tushare records while preserving source dates, formulas, missing-window reasons, and no benchmark-relative calculation.
- [x] 6.4 Add timeline and analytics tests for trading-day, after-close, weekend/holiday, unknown-time, duplicate-event, boundary-window, and insufficient-price cases.
- [x] 6.5 Constrain prompts and answer verification to call event/price proximity a temporal association, and test that causal claims and unsupported price-reaction language are rejected or rewritten.
- [x] 6.6 Add end-to-end scenarios covering both price and event evidence, price only, events only, and neither category for a single-stock trend question.

## 7. Runtime Migration and Legacy Removal

- [x] 7.1 Compose one Tushare gateway, one shared Doubao HTTP client, provider caches, bounded executors, and provider readiness state in application startup and shutdown.
- [x] 7.2 Update deterministic analytics and provenance consumers to use normalized Tushare records and remove benchmark-relative, unsupported fundamental, year-over-year, and valuation-percentile calculations from the active path.
- [x] 7.3 Remove the AKShare gateway, runtime provider stock catalog, AKShare settings, fixtures, tests, imports, dependency, and container installation after replacement coverage passes.
- [x] 7.4 Remove the SearchInfinity MCP subprocess, discovery/allowlisting, stdio lifecycle, MCP settings, packages, fixtures, tests, health logic, and container installation after HTTP-client coverage passes.
- [x] 7.5 Add offline fake implementations for normalization, Tushare, and search so the default test suite and local development do not require live credentials or network access.

## 8. Contracts, Deployment, and Documentation

- [x] 8.1 Verify that chat request handling and SSE event shapes remain backward compatible while category limitations and citations continue through existing response structures.
- [x] 8.2 Update environment examples, dependency locks, Docker/Compose configuration, health/readiness checks, and deployment validation for Tushare and Doubao API credentials without embedding secrets.
- [x] 8.3 Update architecture, provider operations, troubleshooting, quota/cache policy, data-source limitations, provenance, and user-facing evidence-boundary documentation.
- [x] 8.4 Run unit, contract, integration, security/log-redaction, static-analysis, and container smoke suites and record the exact commands and results.
- [x] 8.5 Run opt-in live Tushare and Doubao smoke checks with bounded requests, confirm readiness and partial degradation, and document deployment monitoring plus the prior-image/config rollback procedure.
