## 1. Project Foundation

- [x] 1.1 Create the `apps/api` Python 3.12 package structure and configure FastAPI, LangChain, linting, type checking, and test dependencies
- [x] 1.2 Create the `apps/web` React + TypeScript + Vite project structure and configure linting, formatting, and frontend tests
- [x] 1.3 Add root-level developer commands for installing, running, checking, and testing both applications without introducing a database
- [x] 1.4 Add backend and frontend `.env.example` files with redacted provider, CORS, timeout, retry, cache, and local endpoint settings
- [x] 1.5 Add repository ignore rules and automated secret checks so local provider credentials and generated artifacts cannot be committed

## 2. Backend Domain and Configuration

- [ ] 2.1 Implement validated backend settings for DeepSeek, Doubao search, AKShare timeouts, cache TTL, CORS origins, logging, and direct-development/container bind modes
- [ ] 2.2 Define typed instrument, normalized market record, evidence, citation, quality flag, limitation, structured answer, and error-code models
- [ ] 2.3 Define bounded chat request models with the 500-character question limit, allowed message roles, message-count limit, and total-context limit
- [ ] 2.4 Define and serialize the accepted, status, answer-start, answer-delta, citation, answer-complete, and error stream event schemas
- [ ] 2.5 Add structured logging with correlation IDs and redaction tests proving that secrets, full conversations, and raw search documents are omitted
- [ ] 2.6 Implement process health and configuration-readiness checks that never expose secret values

## 3. AKShare Data Grounding

- [ ] 3.1 Run a compatibility spike against the pinned AKShare version and record the initial approved stock, broad-index, history, financial, valuation, ownership, and pledge interface allowlist
- [ ] 3.2 Implement canonical A-share and approved broad-index lookup with name/code/exchange normalization and ambiguity results
- [ ] 3.3 Implement the AKShare gateway operations with bounded thread-pool execution, timeouts, retries, and provider-specific errors
- [ ] 3.4 Normalize approved price and index history responses into typed records with canonical fields, units, source metadata, and retrieval timestamps
- [ ] 3.5 Normalize approved financial, valuation, ownership, and pledge responses into typed records without leaking provider-specific columns downstream
- [ ] 3.6 Implement data validation for schema, required fields, numeric types, dates, duplicates, units, coverage, and minimum sample size
- [ ] 3.7 Implement the in-process TTL cache keyed by normalized operation parameters and verify that conversation clearing does not affect it
- [ ] 3.8 Add sanitized provider fixtures and contract tests that detect upstream field or unit changes

## 4. Deterministic Analytics

- [ ] 4.1 Implement and unit-test interval return calculations with explicit effective trading-date ranges
- [ ] 4.2 Implement and unit-test benchmark date alignment and benchmark-relative return calculations
- [ ] 4.3 Implement and unit-test moving averages, volume change, historical volatility, and other approved trend metrics
- [ ] 4.4 Implement and unit-test financial year-over-year changes and valuation percentile calculations with sufficiency checks
- [ ] 4.5 Convert retrieved facts and computed metrics into evidence items carrying formula, period, unit, source IDs, cutoff, and quality flags
- [ ] 4.6 Implement category-level partial failure aggregation and the no-sufficient-evidence outcome

## 5. External Model and Search Providers

- [ ] 5.1 Implement a configurable LangChain-backed DeepSeek V4 Pro model gateway with injectable base URL, exact model ID, timeouts, retries, and low-temperature structured output
- [ ] 5.2 Add model gateway fakes and tests for success, timeout, rate limit, invalid structured output, retry, and secret-safe errors
- [ ] 5.3 Confirm the Doubao search Tool protocol and implement its gateway with configurable authentication, query, result limit, and freshness intent
- [ ] 5.4 Normalize Doubao results into citations containing title, HTTP(S) URL, publisher/domain, snippet, publication time when available, and retrieval time
- [ ] 5.5 Implement source-priority scoring, primary-versus-secondary labeling, duplicate removal, and credible-source conflict preservation
- [ ] 5.6 Add search gateway tests for valid results, missing dates, malformed URLs, timeout, no credible results, conflicts, and prompt-injection-like content

## 6. Controlled LangChain Orchestration

- [ ] 6.1 Implement structured intent classification for single-stock, broad-index, stable knowledge, mixed, and out-of-scope questions
- [ ] 6.2 Implement current-context entity resolution, explicit instrument override, canonical resolution, and clarification for ambiguous instruments
- [ ] 6.3 Implement the bounded evidence planner that maps intents to approved market operations and time-sensitive claims to Doubao search
- [ ] 6.4 Implement constrained tool execution with per-tool call limits, timeouts, retry budgets, and total evidence-size limits
- [ ] 6.5 Implement prompts that isolate untrusted search content and generate typed research or knowledge answers only from validated evidence
- [ ] 6.6 Implement answer verification for numeric evidence references, time-sensitive citations, section separation, limitations, and required disclaimer
- [ ] 6.7 Implement the investment-safety policy for buy/sell requests, guaranteed predictions, personalized suitability, and unsupported asset or comparison requests
- [ ] 6.8 Add orchestrator tests covering every routing path, follow-up resolution, tool selection, partial failure, conflicting sources, unsupported scope, and no-evidence refusal

## 7. FastAPI Streaming Interface

- [ ] 7.1 Implement `POST /api/chat/stream` validation and connect it to the controlled orchestration workflow
- [ ] 7.2 Implement ordered `text/event-stream` serialization for progress, semantic answer deltas, citations, completion, and typed terminal errors
- [ ] 7.3 Propagate client cancellation through orchestration and provider calls where supported, and stop emitting events after disconnect
- [ ] 7.4 Configure direct local-development CORS for the allowed Vite origin and loopback binding while supporting an unexposed container-network bind mode
- [ ] 7.5 Add API integration tests for blank/oversized input, bounded context, event ordering, completed and failed streams, cancellation, CORS, health, and readiness
- [ ] 7.6 Export JSON-schema fixtures for request and stream events and add a contract check against the frontend TypeScript wire types

## 8. Penpot-Aligned React Workspace

- [ ] 8.1 Reinspect the supplied Penpot reference board and component-state board, then extract verified typography, color, spacing, radius, shadow, and sizing tokens into CSS custom properties
- [ ] 8.2 Build the semantic desktop shell with top bar, scoped sidebar, page heading, chat workspace, and persistent disclaimer matching the Penpot hierarchy
- [ ] 8.3 Remove or visibly disable unsupported navigation destinations and attachment affordances so they do not imply first-version functionality
- [ ] 8.4 Implement the in-memory chat state model for idle, submitting, streaming, completed, failed, and cancelled states without local or session storage
- [ ] 8.5 Implement the fetch-based POST stream client, event parser, runtime payload validation, and `AbortController` cancellation
- [ ] 8.6 Build user and assistant message rows, chat header/status, loading progress, actionable error, retry, and completed-state components
- [ ] 8.7 Build semantic summary, fact, analysis, risk, limitation, citation, cutoff, timestamp, and disclaimer renderers matching the Penpot visual treatments
- [ ] 8.8 Implement the composer with whitespace validation, live `0/500` counter, maximum length, active-request submission lock, and preserved input on failure
- [ ] 8.9 Implement “新建对话” and “清空对话” to cancel active work and reset only current React messages/context to the initial workspace
- [ ] 8.10 Add safe external citation links and accessible labels, focus states, keyboard submission, status announcements, and semantic landmarks
- [ ] 8.11 Add fluid desktop sizing and content overflow behavior below the 1440-pixel reference without creating an unsupported mobile redesign

## 9. Frontend and End-to-End Verification

- [ ] 9.1 Add frontend tests for initial, submitting, streaming, completed, failed, retry, duplicate-submit, and cancellation states
- [ ] 9.2 Add frontend tests for 500-character enforcement, blank submission, structured research and knowledge rendering, citations, and unsupported controls
- [ ] 9.3 Add tests proving clear, new, refresh, and application reopen do not restore messages or Agent context
- [ ] 9.4 Add end-to-end tests with fake providers for a stock question, broad-index question, stable knowledge question, search-grounded current question, and contextual follow-up
- [ ] 9.5 Add end-to-end tests for ambiguous instruments, unsupported scope, partial market-data failure, search failure, model failure, and no-evidence refusal
- [ ] 9.6 Compare the implemented 1440×1024 page and variable-length answer states against Penpot exports and resolve material visual or interaction differences

## 10. Local Deployment and Final Validation

- [ ] 10.1 Add production-ready API and web `.dockerignore` files that exclude credentials, local environments, caches, tests not needed at runtime, and generated build output
- [ ] 10.2 Create a pinned Python 3.12 API Dockerfile with a minimal runtime stage, non-root user, runtime dependencies, and `/health` health check
- [ ] 10.3 Create a multi-stage web Dockerfile that builds the Vite application and serves it from a minimal non-root-compatible Nginx runtime
- [ ] 10.4 Configure Nginx SPA fallback and `/api` reverse proxy behavior with buffering disabled and suitable timeouts for streaming chat responses
- [ ] 10.5 Create `compose.yaml` with API health dependency, an internal service network, runtime-only API secrets, restart policies, no persistent volumes, and only the web port bound to `127.0.0.1`
- [ ] 10.6 Add Compose configuration validation and integration checks for clean image builds, health convergence, web access, API reverse proxying, incremental streaming, restart, shutdown, and lack of a host-published API port
- [ ] 10.7 Document Docker Engine and Compose prerequisites, environment setup, provider configuration, `docker compose up` startup, health checks, logs, shutdown, rebuild, and troubleshooting
- [ ] 10.8 Document supported question examples, approved instruments/data categories, source semantics, data limitations, cloud processing, and investment disclaimer
- [ ] 10.9 Add an opt-in live smoke-test command for AKShare, DeepSeek V4 Pro, and Doubao search that skips safely when credentials or network access are unavailable
- [ ] 10.10 Run backend linting, typing, unit, contract, integration, and fake-provider orchestration tests and resolve all failures
- [ ] 10.11 Run frontend linting, type checking, unit, accessibility, contract, and end-to-end tests and resolve all failures
- [ ] 10.12 Perform a clean Docker Compose startup using documented steps and verify the MVP acceptance scenarios from all four delta specs
