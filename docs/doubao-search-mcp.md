# Doubao Search MCP compatibility record

- Audit date: 2026-08-07
- Official repository: `https://github.com/volcengine/mcp-server`
- Audited commit: `2ead744c290e3cb87295bda6504a5a329c10f4fa` (2026-08-05)
- Package: `server/mcp_server_askecho_search_infinity`, version `0.1.0`
- License: MIT, copyright Beijing Volcano Engine Technology Ltd.
- Python: official range `>=3.12,<3.14`; this application uses Python 3.12
- Runtime dependencies declared upstream: `mcp>=1.9.4`, `aiohttp>=3.9.0`

The dependency is installed from the immutable commit during application/image installation. Runtime startup must use the installed `mcp-server-askecho-search-infinity` entry point and must not download code with `uvx` or Git.

## Approved tool contract

Only the discovered tool named `web_search` is approved. Other tools returned by discovery are ignored and are never made available to the model.

| Input | Constraint used by this application |
| --- | --- |
| `Query` | Required, trimmed, 1–100 characters |
| `Count` | Required by the gateway, 1–50 |
| `SearchType` | Always `web` |
| `TimeRange` | Omitted or `OneDay`, `OneWeek`, `OneMonth`, `OneYear` |
| `AuthLevel` | `0` normally, `1` for an explicit authority intent |

The audited result model contains `Id`, `SortId`, `Title`, `Snippet`, optional `SiteName`, `Url`, `Summary`, `Content`, `PublishTime`, `LogoUrl`, and `RankScore`. Application code accepts provider envelopes defensively, bounds `Snippet`/`Summary`, excludes `Content` from model context, validates HTTP(S) URLs, and generates `retrieved_at` locally.

## Authentication and transport

The official server accepts either `ASK_ECHO_SEARCH_INFINITY_API_KEY` or the pair `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY`. The application exposes product-level settings and maps only the selected credentials into the child environment. API-key and AK/SK modes are mutually exclusive.

The MVP uses one supervised stdio child per API process. SSE and Streamable HTTP exist upstream but are not approved for this single-worker deployment. The child executable is fixed by application code rather than configurable user input.

## Known upstream considerations

- The upstream package is versioned `0.1.0`, so tool discovery and result-field contract tests are required.
- The API-key implementation currently uses the provider endpoint internally; that endpoint is deliberately not copied into application configuration.
- Upstream returns tool-level failures as an `error` object in some successful MCP calls. The gateway treats that envelope as `search_upstream_error` rather than as an empty result.
- Search API credentials are distinct from model-provider credentials. Quota and live response fields are verified only by the opt-in smoke test.

## Local verification on 2026-08-07

- The pinned package installed successfully alongside MCP Python SDK `1.29.0`.
- A credentialed stdio initialization and `web_search` discovery handshake succeeded.
- A credentialed search call exceeded the initial 20-second test window and was mapped to `search_timeout` without exposing the upstream body. Live result-field and quota verification remains assigned to task 10.9, where a provider-appropriate smoke-test timeout can be documented separately from normal request policy.
