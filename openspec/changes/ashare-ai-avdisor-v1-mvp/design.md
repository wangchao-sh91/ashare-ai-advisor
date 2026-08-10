## Context

See `proposal.md` for motivation and the four delta specs for observable behavior. The repository currently contains planning material but no application implementation, so this change establishes the initial codebase and architectural boundaries.

The product runs locally for one user through Docker Compose, has no identity system or database, and sends model requests to the cloud. Market data comes from AKShare's upstream-backed interfaces; time-sensitive public information comes from a Doubao search Tool. Both sources can be slow, unavailable, stale, or structurally inconsistent. The supplied Penpot file (`81f57451-85cc-819d-8008-6fe553a2574d`) contains the desktop reference board “A股 AI 投研助手 / Desktop 1440” (`46abee9f-97c0-80ce-8008-6ff3f10e4923`) and component states.

## Goals / Non-Goals

**Goals:**

- Establish independently testable web, API, orchestration, financial-data, search, and model-adapter boundaries.
- Keep critical calculations deterministic and make every material external fact traceable to source and time metadata.
- Stream progress and answer events to the browser while keeping conversation state ephemeral and browser-owned.
- Make upstream failures produce explicit partial or unavailable results instead of unsupported model output.
- Match the Penpot desktop information hierarchy and interaction states using reusable frontend components and tokens.
- Keep external model and search protocols behind adapters so exact model endpoints, model identifiers, MCP transport details, and credentials do not leak into domain logic.
- Provide a reproducible Docker Compose deployment that exposes one loopback-only browser entry point and verifies service health.

**Non-Goals:**

- A database, durable job queue, distributed execution, background ingestion pipeline, vector store, or retrieval knowledge base.
- Server-side conversation sessions, cross-device state, authentication, authorization, or secrets in the browser.
- General autonomous browsing or an unconstrained tool-calling loop.
- Intraday trading-grade latency or completeness guarantees for upstream public data.
- Mobile-specific layouts beyond preserving basic usability at narrower desktop widths.

## Decisions

### 1. Repository layout and runtime boundaries

Use a small monorepo-style layout:

```text
apps/
  api/                 Python 3.12, FastAPI, LangChain
    Dockerfile
    app/
      api/             HTTP routes and stream serialization
      agent/           routing, orchestration, prompts, policies
      domain/          typed evidence, answer and error models
      providers/       AKShare, Doubao search, DeepSeek adapters
      services/        normalization, validation, calculations
      core/            settings, logging and lifecycle
    tests/
  web/                 React, TypeScript, Vite
    Dockerfile
    nginx.conf
    src/
      api/             stream client and wire types
      components/      reusable presentation components
      features/chat/   chat state and workspace composition
      styles/          Penpot-derived tokens and global styles
compose.yaml           Local frontend/backend orchestration
```

The API process is the only component that holds provider credentials. In the Compose deployment, the browser communicates with the web container, which proxies `/api` requests to FastAPI over the internal container network.

Alternatives considered:

- A single Python-rendered application would reduce setup but conflicts with the requested React/Vite implementation and makes faithful component-state work harder.
- Multiple backend services would isolate providers but add deployment and failure complexity with no first-version benefit.

### 2. Stateless HTTP API with browser-owned conversation context

The browser stores current messages in React memory only. Every chat request sends the bounded current conversation needed for follow-up resolution. The backend does not assign session identifiers or persist messages. Refreshing or reopening the page naturally removes the conversation; “新建对话” and “清空对话” reset the same in-memory state and cancel any active request.

The request contract is conceptually:

```json
{
  "question": "它的估值呢？",
  "messages": [
    {"role": "user", "content": "分析贵州茅台近期走势"},
    {"role": "assistant", "content": "...prior answer summary..."}
  ]
}
```

The API enforces a maximum question length of 500 characters plus bounded message count and total context size. The frontend may retain the full rendered answer, while requests send a compact context representation sufficient for entity and conversational reference resolution.

Alternatives considered:

- Server-memory sessions simplify request payloads but introduce lifecycle, cleanup, concurrency, and accidental retention concerns.
- Browser local storage would violate the explicit no-history behavior after refresh or reopen.

### 3. POST streaming over fetch

Expose `POST /api/chat/stream` and return `text/event-stream` frames consumed with `fetch` and a readable-stream parser. Native `EventSource` is not used because it cannot submit the structured POST body. Each frame has a stable event type and JSON payload:

```text
event: accepted        request accepted and validated
event: status          routing, data, search, or generation status
event: answer-start    structured response metadata
event: answer-delta    incremental content for a semantic section
event: citation        normalized market or web source
event: answer-complete final structured answer and cutoff metadata
event: error           typed recoverable or terminal error
```

The client uses an `AbortController` for clear/new actions and page teardown. A terminal `answer-complete` or `error` closes the stream. Event schemas are shared semantically through generated or manually synchronized TypeScript types backed by backend JSON-schema fixtures and contract tests.

Alternatives considered:

- WebSockets are unnecessary for a client-request/server-stream interaction and complicate reconnect and proxy behavior.
- A single non-streaming response is simpler but does not meet the Penpot progress experience and can leave the interface inert during slow upstream calls.

### 4. Controlled LangChain orchestration

Use LangChain for model clients, structured-output parsing, prompt composition, tool wrappers, and runnable composition. The Agent is a bounded workflow rather than an open-ended ReAct loop:

```text
validate request
  → classify intent and resolve instrument
  → build explicit evidence plan
  → execute approved tools with per-tool limits
  → normalize and validate evidence
  → compute deterministic metrics
  → generate typed answer
  → verify facts/citations/policy
  → stream completion
```

Each stage produces typed domain data. Tool choice is constrained by intent: stable knowledge can go directly to generation; instrument research invokes approved market-data operations; time-sensitive claims invoke Doubao search; mixed questions can use both. The workflow limits tool count, timeout, retries, and total evidence volume. MCP discovery is validated by application lifecycle code, but MCP tools are not dynamically bound to the model: the evidence planner selects the application-level `SearchGateway`, which alone may invoke the allowlisted `web_search` tool.

Alternatives considered:

- A fully autonomous tool-calling agent is flexible but makes scope enforcement, latency, cost, and reproducibility harder.
- Pure rule routing cannot interpret the variety of natural-language questions; structured model classification plus deterministic validation balances flexibility and control.

### 5. Provider abstraction for DeepSeek V4 Pro

Wrap the LangChain chat model behind an application-level `ModelGateway`. Configure API key, base URL, exact provider model identifier, temperature, timeouts, retry count, and maximum output through environment settings. The product-level name is DeepSeek V4 Pro, but the wire identifier remains deployment configuration so provider naming or endpoint changes do not leak into domain logic.

Use low-temperature structured outputs for routing and evidence planning. Final narrative generation accepts only validated evidence and source identifiers. Provider credentials are loaded by the backend and are redacted from logs and errors.

Alternatives considered:

- Calling the provider SDK throughout the application creates lock-in and makes deterministic tests harder.
- Sending credentials from the browser exposes secrets and is rejected.

### 6. AKShare gateway, interface allowlist, and normalization

Expose domain operations such as instrument lookup, daily history, index history, financial overview, valuation, ownership, and pledge data. Map each operation to a version-tested allowlist of AKShare interfaces rather than allowing the model to choose arbitrary function names or parameters.

Provider DataFrames are normalized into typed records with canonical field names, explicit units, dates, interface names, reported upstream sources, and retrieval timestamps. Validation checks schema, types, duplicate dates, ordering, unit expectations, minimum observations, and requested coverage. Provider-specific Chinese column names stay inside the adapter.

AKShare calls are blocking, so FastAPI executes them in a bounded thread pool with per-operation timeouts. A small in-process TTL cache keyed by operation and normalized parameters reduces duplicate calls; it is market-data infrastructure, not conversation state, and disappears on API restart.

Alternatives considered:

- Disk caching could improve cold-start behavior but adds freshness and cleanup semantics not needed for this MVP.
- Passing raw DataFrames to the model is token-heavy, exposes unstable schemas, and encourages model-side calculations.

### 7. Deterministic analytics and evidence model

Implement calculations as pure functions over validated normalized records. Formula metadata includes metric name, value, unit, aligned start/end dates, benchmark when applicable, input source IDs, and any quality flags. Relative performance aligns stock and benchmark observations on common trading dates before calculating returns.

Use a common evidence envelope:

```text
EvidenceItem
  id
  kind: market_fact | computed_metric | web_fact
  claim/value/unit
  instrument and period
  source references
  cutoff and retrieved_at
  quality flags

Citation
  id
  source_type: akshare | web
  title/interface/upstream publisher
  URL when available
  published_at when available
  retrieved_at
```

The final typed answer contains `summary`, `facts`, `analysis`, `risks`, `citations`, `data_cutoff`, `disclaimer`, and `limitations`. Knowledge-only answers may omit research-only sections.

### 8. Doubao search through the official MCP Server

Implement the application-level `SearchGateway` as an MCP client for the official Doubao SearchInfinity MCP Server. For the single-worker MVP, the API process supervises one long-lived stdio MCP subprocess and owns its initialization and shutdown through the FastAPI lifespan. The API image installs the official server at build time from an audited, immutable revision; application startup never downloads or executes an unpinned remote package. A future multi-worker deployment may move the same server behind an internal Streamable HTTP sidecar without changing the domain gateway.

At initialization, the client performs the MCP handshake and verifies that the server exposes the expected `web_search` tool. It does not forward the discovered tool collection to DeepSeek. The gateway accepts only a bounded query, result limit, freshness intent, and authority intent, then maps them to the provider contract: `Query`, `Count`, forced `SearchType=web`, optional `TimeRange`, and optional `AuthLevel`. Provider query-length and result-count limits are validated before the call. Timeouts, retries, cancellation, reconnect behavior, and secret-safe errors remain application-owned even though execution crosses the MCP boundary.

Normalize `Title`, `Url`, `SiteName`, bounded `Snippet`/`Summary`, and `PublishTime` into provider-independent citations with an application-generated retrieval time. Treat provider `RankScore` as relevance metadata rather than source credibility. Do not send unbounded `Content` to the model. Validate every URL as HTTP(S), derive the domain independently, and apply an application source-priority policy that favors regulators, exchanges, listed-company disclosures, government agencies, and index publishers.

Search pages, snippets, and summaries are untrusted content. They are quoted as evidence only, never treated as instructions; prompt boundaries explicitly prevent retrieved text from changing tool policy or revealing configuration. URLs rendered by the frontend are opened with safe external-link attributes. Conflicting credible evidence is preserved for disclosure rather than silently collapsed.

Alternatives considered:

- A Skill package is appropriate for a general Agent harness that implements Skill discovery and execution, but this application has a fixed FastAPI workflow and would need a second runtime abstraction only to reach the same search API.
- Calling the search REST API directly would minimize process overhead but would duplicate the provider-maintained protocol adapter and diverge from the official MCP integration path selected for this change.
- Running the MCP Server as a third Compose service would improve process isolation, but adds deployment and health-ordering complexity that is unnecessary for the single-worker MVP; Streamable HTTP remains the scale-out path.
- General model browsing would reduce integration code but weakens provider control and citation normalization.
- Treating snippets as authoritative facts is rejected because snippets can be truncated, stale, or misleading.

### 9. Answer verification and graceful degradation

Before completion, validate that every numeric fact in fact sections references a computed or retrieved evidence item, every time-sensitive web claim has a citation, and required safety text is present. Analysis may interpret evidence but cannot introduce new ungrounded numeric claims.

Provider failures become typed categories such as `ambiguous_instrument`, `unsupported_scope`, `market_data_unavailable`, `search_unavailable`, `model_unavailable`, and `validation_failed`. The orchestrator can finish with partial validated sections and explicit limitations. It must stop research generation when no evidence is sufficient.

### 10. Penpot-derived frontend component system

Implement the supplied 1440×1024 desktop board using semantic React components instead of a screenshot or absolute-positioned monolith. Extract typography, color, spacing, radii, shadows, and component states from Penpot into CSS custom properties. Principal components include top bar, scoped sidebar, page header, chat card/header, message row, semantic answer section, citation/source list, status badge, composer, error notice, and disclaimer.

Only the投研问答 destination is interactive. Unsupported navigation and attachment controls are removed or rendered visibly disabled with no misleading actions. The answer renderer maps semantic stream sections to the Penpot fact/analysis/risk visual treatments. The layout targets the desktop reference and uses fluid content widths and sensible overflow below 1440 pixels without inventing a separate mobile design.

Alternatives considered:

- Copying board coordinates directly would match one viewport but fail with variable answer length and streaming.
- Introducing a third-party visual component system would create style drift from the supplied UX; small accessible primitives are preferable.

### 11. Configuration, logging, and local security posture

Use validated environment configuration for model endpoints, provider credentials, model ID, Doubao MCP authentication/transport, CORS origins, timeouts, retries, cache TTL, and log level. The application may retain a product-level Doubao API-key setting and map it only into the official subprocess environment name; it does not expose an arbitrary configurable command or retain the provisional HTTP base-URL assumption. For direct development, bind the API to loopback and allow only the configured local Vite origin. In Compose, the API listens on the container interface but is not published to the host; only the web entry point is bound to host loopback. Provide a redacted `.env.example`; never commit secrets.

Structured logs include request correlation ID, stage, duration, provider, interface/operation, evidence counts, and typed error code. They exclude full conversation text, provider credentials, MCP environment values, and raw search documents by default so logs do not become a hidden chat history. Add `/health` for process health and a separate readiness result that combines configuration presence with MCP initialization and required-tool availability without echoing secrets.

### 12. Testing strategy

- Unit tests cover instrument normalization, date alignment, formulas, validation, routing policies, citation rules, and answer safety checks.
- Provider contract tests use recorded sanitized MCP `CallToolResult` fixtures and explicit schema assertions; lifecycle tests use a fake MCP transport/server, and live-provider smoke tests are opt-in because upstream availability is nondeterministic.
- Orchestrator tests replace model, AKShare, and search gateways with fakes to verify tool selection, partial failure, no-evidence refusal, and follow-up resolution.
- FastAPI integration tests validate input limits, streaming event order, cancellation behavior, typed errors, CORS, and secret redaction.
- Frontend tests cover initial/streaming/completed/error states, 500-character limit, clear/new behavior, citation rendering, and no browser persistence.
- End-to-end tests exercise a stock question, index question, stable knowledge question, search-grounded current question, ambiguous symbol, upstream failure, and page refresh.
- Visual checks compare the implemented desktop workspace with the Penpot board at the reference viewport and inspect content growth states.
- Compose integration checks build both images, wait for health checks, access the application through the web entry point, verify streaming through the reverse proxy, and confirm the API port is not directly exposed.

### 13. Docker Compose local deployment

Use a root `compose.yaml` with two services:

```text
browser → 127.0.0.1:<configured-port> → web (Nginx) → /api → api (FastAPI)
                                                        ├── AKShare upstreams
                                                        ├── supervised stdio MCP subprocess → Doubao search
                                                        └── DeepSeek V4 Pro
```

The API image uses a pinned Python 3.12 base and installs only runtime dependencies, including the official Doubao MCP Server at an audited immutable revision, in its final stage. The server runs as a child of the same non-root API user; no `uvx` or Git download occurs at container startup. The API container has a health check against `/health`, while readiness also reflects the MCP handshake and required-tool state. The web image uses a Node build stage for the Vite application and a minimal Nginx runtime stage that serves static assets, supports SPA fallback, preserves streaming response behavior, and proxies `/api` to the internal API service.

Compose waits for API health before starting or marking the web service ready. Only the web service publishes a port, bound explicitly to `127.0.0.1`; the API remains reachable only on the Compose network. Provider credentials enter the API container through a local environment file or host environment and are never baked into images or passed to the web build. No persistent volumes are defined because conversations and the in-process market cache are intentionally ephemeral. Containers use restart policies appropriate for a local application and bounded health-check intervals.

Alternatives considered:

- Running Python and Node directly on the host remains useful for development but does not provide the requested reproducible deployment boundary.
- Publishing both web and API ports is convenient for debugging but unnecessarily expands the host attack surface and bypasses the single-origin reverse proxy.
- Adding database or cache containers is rejected because the MVP has no persistent state and the in-process cache is not a correctness dependency.

## Risks / Trade-offs

- [AKShare upstream interfaces can change without notice] → Pin a tested version, use an interface allowlist, validate schemas, isolate adapters, and maintain fixture-based contract tests.
- [Free public data can be stale, incomplete, or internally inconsistent] → Display actual cutoffs, carry quality flags, align dates explicitly, and omit unsupported metrics.
- [DeepSeek V4 Pro product naming may not match a stable API model identifier] → Keep the exact identifier and base URL configurable and fail readiness checks when missing.
- [Search results can contain misinformation or prompt injection] → Prefer primary sources, treat all retrieved text as untrusted evidence, normalize metadata, and verify citations.
- [The official MCP Server is an early-version dependency whose contract or packaging can change] → Pin an audited immutable revision, validate tool discovery and result fixtures, and isolate all protocol mapping behind `SearchGateway`.
- [The stdio MCP child can fail independently or complicate cancellation and shutdown] → Supervise it through application lifespan, bound every call, expose readiness separately from liveness, and convert transport failures into `search_unavailable`.
- [Sending current context on every request increases payload and cloud exposure] → Bound and compact context, send only what is needed, disclose cloud processing, and never persist request content in application logs.
- [In-process cache is lost at restart and does not coordinate multiple workers] → Accept cold starts and default to a single API worker for MVP; the cache is an optimization, not a correctness dependency.
- [A stateless stream cannot be resumed after connection loss] → Show a retry action with the preserved local question; do not imply resumability.
- [Faithful desktop UX may not translate directly to small screens] → Preserve usable overflow and content reflow while treating a dedicated mobile design as future work.
- [Structured generation can fail schema validation] → Retry once with validation feedback, then return a typed model error instead of malformed content.
- [Container images add build time and platform-specific dependency risk] → Pin base images and application dependencies, use multi-stage builds, and test clean builds on the supported host architecture.
- [Reverse proxies may buffer or terminate streaming responses] → Disable buffering for `/api/chat/stream`, use generous read timeouts, and verify incremental delivery in Compose integration tests.
- [Secrets can leak into image layers or web build arguments] → Inject secrets only into the runtime API container, exclude local environment files from build contexts, and inspect final image configuration in tests.

## Migration Plan

1. Add backend and frontend scaffolds, container build files, Compose configuration, and redacted local configuration examples.
2. Implement and test provider adapters, including the pinned official Doubao MCP client/subprocess boundary, normalized evidence types, calculations, and controlled orchestration.
3. Implement the streaming API contract and Penpot-aligned frontend states.
4. Run automated tests with fake/fixture providers, then opt-in live smoke tests with locally supplied credentials.
5. Build clean images and verify startup, health checks, streaming, restart, and shutdown through Docker Compose with only the web port bound to loopback.

This is a greenfield deployment with no user data migration. Rollback consists of running `docker compose down` and returning to a previous image or repository revision; no conversation records, volumes, or database schema require restoration.

## Open Questions

- Confirm the provider's exact DeepSeek V4 Pro wire model identifier and base URL when credentials are configured.
- Select and record the audited official Doubao MCP Server commit and verify the account quota plus live result-field behavior when credentials are available.
- Finalize the initial approved AKShare interface/index allowlist through a fixture-backed compatibility spike during implementation.
