## Context

The current backend grounds stock and index analysis through several AKShare interfaces and reaches Doubao Search through a supervised SearchInfinity MCP subprocess. That shape does not match the v1.1 operating constraints: the available free Tushare account can reliably supply only unadjusted A-share daily records, while non-price financial facts, broad-index context, news, and announcements must be attempted through the Doubao Search Custom HTTPS API.

The current question classifier, runtime stock catalog, provider planner, and evidence model also assume that an instrument route largely determines the available data. v1.1 instead needs category-level planning and sufficiency so daily prices, searched financial facts, and corporate events retain distinct provenance and failure behavior. The public chat request and SSE response protocol should remain stable.

## Goals / Non-Goals

**Goals:**

- Resolve and rewrite each current question through one structured LLM call, including canonical instrument identity, requested categories, analysis period, freshness, and clarification state.
- Make validated Tushare `daily` records the sole admissible stock-price source and normalize their fields and units deterministically.
- Replace MCP search transport with a typed, bounded, quota-aware Doubao Search Custom HTTPS client.
- Plan, validate, and report evidence sufficiency independently by category.
- Support daily-price plus news/announcement analysis on a shared trading-day timeline without making causal claims.
- Preserve deterministic calculations, provenance, safety boundaries, partial answers, readiness visibility, and the existing HTTP/SSE contract.

**Non-Goals:**

- Adding paid Tushare interfaces, adjusted price series, intraday quotes, or alternative structured providers.
- Using search snippets or pages as fallback price observations.
- Restoring deterministic broad-index time series or benchmark-relative stock metrics.
- Inferring that an event caused a price movement from timing alone.
- Supporting multiple-instrument comparison, other asset classes, automated trading, or personalized investment advice.
- Redesigning the frontend or introducing durable research-result persistence.

## Decisions

### 1. Normalize a question once into an application-owned schema

Replace the separate intent/instrument interpretation path with one bounded structured LLM call whose result contains `rewritten_question`, `intent`, canonical `instrument` fields, `requested_categories`, `analysis_period`, `time_sensitive`, and `clarification`. Bounded current-session context allows pronoun-based follow-ups to become self-contained. Application validation rejects missing fields, unsupported categories, name/code conflicts, and invalid date ranges before any provider is called.

The model describes the research need but does not select URLs, SDK methods, or arbitrary tools. The application maps validated categories to a fixed evidence plan. This reduces duplicated model calls while keeping provider authority and safety checks deterministic.

Alternative considered: retain the current classifier and perform instrument resolution in a second model or catalog step. This preserves smaller schemas but adds latency and creates two potentially conflicting interpretations of the same question.

### 2. Represent planning and outcomes by evidence category

Introduce an application-owned category vocabulary covering at least `price_daily`, `financial`, `valuation`, `ownership`, `pledge`, `corporate_event`, and `index_context`. Each plan item records the category, provider, period, normalized query or stock code, requirement level, and bounded limits. Each outcome records `sufficient`, `insufficient`, or `unavailable` plus evidence and a machine-readable reason.

Price routes only to Tushare. Non-price stock categories and index context route to search. Sufficiency is evaluated per category before answer generation, and the answer model receives only accepted evidence plus explicit limitations. A credible fact in one category cannot satisfy another category.

Alternative considered: retain a single aggregate evidence score. It is simpler but can incorrectly allow a news result to conceal missing prices or a price series to conceal missing event context.

### 3. Encapsulate the synchronous Tushare SDK behind a bounded gateway

Add a Tushare gateway with one pinned Python SDK dependency and one initialized `pro_api` client. It exposes only an application-level stock-daily method and invokes the synchronous SDK in a capacity-limited worker thread with a deadline. Requests use a canonical `ts_code` and normalized inclusive analysis dates; responses are copied into domain records rather than leaking DataFrames into orchestration.

Validation requires the daily schema and unique ordered trade dates. `vol` is converted from hands to shares by multiplying by 100, and `amount` from thousands of CNY to CNY by multiplying by 1,000. Raw and normalized unit semantics are covered by fixtures. Cache keys include stock code, date range, and provider/schema version.

Any exception, timeout, authentication failure, empty required range, schema failure, or insufficient sample produces an insufficient price outcome. Search is never scheduled as price fallback.

Alternative considered: call Tushare directly from orchestration services. This avoids a wrapper but spreads sync/async handling, units, validation, caching, and error mapping across the application.

### 4. Use a fixed typed client for the Doubao Search Custom API

Replace the MCP subprocess with a shared asynchronous HTTP client that calls only `POST https://open.feedcoopapi.com/search_api/web_search`. Authentication uses a server-side bearer key. The request mapper fixes `SearchType` to web, enforces provider query and count limits, requests URLs and authority information, applies the finance industry filter where appropriate, and maps the normalized period or freshness need to `TimeRange`.

The response adapter accepts only valid `Result.WebResults` entries and normalizes title, destination URL, publisher/domain, publication time, retrieval time, authority metadata, snippet/context, supported claim, category, and query. Provider payloads and secrets do not enter prompts or user-visible errors.

Alternative considered: keep an MCP abstraction but implement an HTTP-backed server. It preserves transport indirection without providing model tool discovery value and retains unnecessary process and lifecycle complexity.

### 5. Protect search quota with cache, concurrency, and explicit error mapping

Normalize semantically equivalent category queries into cache keys containing instrument, category, period/freshness, language, and request-shaping version. Reuse fresh normalized results before issuing a provider request. Bound concurrent calls and retries globally. Retry only transient failures with bounded backoff; treat the provider quota error (`10406`) as non-retryable and rate limiting (`700429`) as bounded-retryable.

Readiness distinguishes configured/usable, temporarily rate limited, quota unavailable, and generally unavailable without performing expensive searches on every probe. The initial deployment keeps cache lifetime and capacity configurable because news and financial categories have different freshness requirements.

Alternative considered: issue a search for every category on every question. This is easier to reason about but is incompatible with the free monthly quota and 5 QPS limit.

### 6. Keep provenance types and trust boundaries explicit

Market evidence records use a Tushare provenance type and carry interface, stock identity, covered dates, cutoff, retrieval time, and units. Search evidence records use a web provenance type and carry citation metadata and authority classification. A search result that mentions a price remains web context and cannot be converted to a market fact.

Answer verification checks that every material numeric price claim traces to validated market evidence and every current event or searched fact traces to an accepted citation. Category outcomes and limitations are rendered explicitly for complete, partial, and evidence-insufficient answers.

### 7. Align corporate events conservatively to trading dates

Corporate-event evidence is searched within the normalized analysis period and deduplicated by canonical URL and event identity. Events reliably published after close or on non-trading days map to the next available trading day. Events with only a publication date retain timing uncertainty and cannot support an exact same-day reaction claim.

When daily observations exist, deterministic analytics calculate configured one-, three-, and five-trading-day price observations around the aligned date. Outputs are raw temporal observations, not abnormal returns or causal estimates, because structured benchmark series and causal controls are unavailable.

Alternative considered: let the answer model narratively align event dates and price records. That would make calendar handling and calculations non-reproducible.

### 8. Simplify runtime composition and removal boundaries

Runtime composition owns one Tushare gateway, one shared search HTTP client, bounded provider executors, caches, and readiness state. Remove the AKShare gateway, runtime stock-catalog dependency used for provider lookup, Doubao MCP subprocess supervision, discovery/allowlisting, stdio protocol, MCP-specific settings, packages, Docker layers, fixtures, and operational procedures after the replacement paths pass tests.

Provider fakes implement the new application interfaces so default tests require neither network access nor real credentials. Optional live smoke checks remain opt-in and secret-safe.

## Risks / Trade-offs

- **Model resolves the wrong instrument.** Validate canonical code format and name/code consistency, require clarification on ambiguity, and test adversarial follow-up context. The compatibility spike will determine whether an authority lookup is needed for cases the one-call contract cannot safely resolve.
- **Free search quota is too small for category fan-out.** Cache normalized results, merge compatible queries carefully, cap per-request categories and counts, and surface quota state rather than repeatedly failing.
- **A timed-out synchronous SDK call can continue in its worker thread.** Limit worker capacity, abandon late results, keep calls idempotent, and avoid unbounded retries.
- **Search results may lack primary sources or reliable dates.** Rank authority metadata, retain secondary labels, and exclude undated items from event-window alignment.
- **Removing index series reduces quantitative context.** State the search-only limitation and omit benchmark-relative metrics instead of presenting incomparable or inferred figures.
- **Provider schema or unit semantics may drift.** Pin the SDK, validate required fields, version response adapters and cache keys, and maintain provider-shaped contract fixtures.
- **Category-level partial answers add response complexity.** Use a single outcome model and render limitations from machine-readable reasons rather than generating free-form failure explanations.

## Migration Plan

1. Run a compatibility spike against the pinned Tushare SDK and Doubao API contract using opt-in credentials; freeze representative redacted fixtures, unit conversions, error mappings, and configuration defaults.
2. Add the question-normalization, evidence-plan, category-outcome, provenance, and provider interfaces while keeping the old runtime selectable for comparison in tests.
3. Implement and test the Tushare daily gateway, Doubao HTTP client, caches, readiness states, and deterministic event alignment/analytics.
4. Move orchestration and answer verification to category-based planning and sufficiency; verify complete, partial, and no-evidence flows without changing the public chat/SSE protocol.
5. Switch runtime composition and deployment configuration to the new providers, then remove AKShare and MCP code, dependencies, images, settings, fixtures, and documentation.
6. Run unit, contract, integration, container, readiness, and opt-in live smoke checks. Deploy with provider/category observability and retain the previous image and configuration for rollback.

Rollback restores the previous application image and its AKShare/MCP configuration together. Caches contain only derived provider responses and require no data migration.

## Resolved Implementation Defaults

- Pin the newest Tushare SDK version that passes the compatibility spike in the repository's current Python toolchain, and record the verified version and response contract in the lockfile and provider documentation.
- Keep cache policy configurable, with initial defaults of six hours for daily prices, thirty minutes for corporate events, twenty-four hours for other stock financial categories, one hour for index context, and 512 normalized entries per provider cache. Tests use an injected clock and explicit per-test values rather than depending on these defaults.
- If the one-call normalizer cannot confidently establish a canonical A-share `ts_code`, the first release always asks for clarification. A separate authority lookup is outside this change.
