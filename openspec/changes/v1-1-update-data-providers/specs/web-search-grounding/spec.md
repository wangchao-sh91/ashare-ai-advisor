## MODIFIED Requirements

### Requirement: Search decision
The system SHALL invoke web search when a question depends on recent events, current rules or policies, current market information, a broad-based index, or a requested financial-data category unsupported by Tushare daily data, and SHALL avoid mandatory search for stable foundational knowledge.

#### Scenario: Current-information question
- **WHEN** the user asks about a recent company event, current market rule, current policy, or other time-sensitive fact
- **THEN** the system uses the Doubao Search Custom API before presenting the time-sensitive claim

#### Scenario: Unsupported financial category
- **WHEN** a stock question requests financial, valuation, ownership, pledge, announcement, or news evidence that Tushare daily cannot provide
- **THEN** the system creates a bounded search request for that evidence category

#### Scenario: Broad-based-index question
- **WHEN** the user asks about a supported broad-based index
- **THEN** the system uses search-grounded evidence and does not imply that structured index time-series data was retrieved

#### Scenario: Stable foundational knowledge
- **WHEN** the user asks for the definition of a stable financial concept without requesting current facts
- **THEN** the system can answer without invoking web search

### Requirement: Search source quality
The system MUST prefer authoritative primary sources, use available authority metadata to rank results, and distinguish source publication time from retrieval time.

#### Scenario: Primary source available
- **WHEN** an exchange, regulator, listed company, government agency, index publisher, or other authoritative primary source supports the claim
- **THEN** the system prioritizes that source over secondary summaries

#### Scenario: Only secondary sources available
- **WHEN** no suitable primary source can be found
- **THEN** the system labels the evidence as secondary and avoids presenting uncertain details as established fact

### Requirement: Search failure degradation
The system SHALL distinguish API unavailability, quota or rate limiting, and absence of credible evidence, and SHALL not claim that no event, fact, or rule exists solely because search failed.

#### Scenario: Search API unavailable
- **WHEN** the search request times out, is rejected, or returns an invalid response
- **THEN** the system states that the affected current-information categories could not be verified and may only answer from unrelated valid evidence

#### Scenario: Search quota or rate limit reached
- **WHEN** the API reports exhausted quota or rate limiting and no suitable cached result is available
- **THEN** the system marks affected search categories unavailable without retrying unboundedly or exposing credentials

#### Scenario: No credible result found
- **WHEN** search succeeds but returns no credible evidence for the requested claim
- **THEN** the system reports that it could not find sufficient reliable evidence and does not fabricate a citation

## ADDED Requirements

### Requirement: Controlled Doubao Search API invocation
The system SHALL access search only through the configured Doubao Search Custom HTTPS endpoint using an application-controlled evidence plan, bounded request parameters, and server-side bearer authentication.

#### Scenario: Bounded web search call
- **WHEN** an approved evidence plan requires a search category
- **THEN** the system sends a bounded `POST` request with `SearchType` set to web, a query no longer than the provider limit, a result count no greater than the provider limit, and applicable finance, freshness, URL, and authority filters

#### Scenario: Secret-safe authentication
- **WHEN** the system authenticates or records a search failure
- **THEN** the bearer API key is read from server configuration and is absent from model input, user output, logs, and error details

#### Scenario: Invalid provider response
- **WHEN** the API returns malformed data, an unrecognized schema, or results without the required link and claim-supporting fields
- **THEN** the system rejects the affected results and follows search-unavailable degradation behavior

### Requirement: Search evidence category isolation
The system SHALL associate every accepted search result with the planned financial, valuation, ownership, pledge, corporate-event, or index category and SHALL NOT let evidence from one category satisfy another.

#### Scenario: Search finds an unrelated credible fact
- **WHEN** a credible result supports the instrument but not the requested evidence category
- **THEN** the result does not make the requested category sufficient

#### Scenario: Search supports only some categories
- **WHEN** credible results support a subset of the planned search categories
- **THEN** the system preserves those categories and marks the remaining categories insufficient

### Requirement: Search quota protection and cache
The system MUST bound search concurrency and retries and SHOULD reuse a fresh cached normalized result for an equivalent category query before consuming provider quota.

#### Scenario: Equivalent fresh query is cached
- **WHEN** a normalized category query has a valid cached result within its configured freshness window
- **THEN** the system reuses the cached result and retains its original publication metadata plus the current access time

#### Scenario: Provider reports rate limiting
- **WHEN** the provider returns its rate-limit error
- **THEN** the system performs only the configured bounded backoff and then degrades the category if no result is obtained

#### Scenario: Provider reports exhausted quota
- **WHEN** the provider returns its quota-exhausted error
- **THEN** the system does not retry that request and reports search as quota unavailable for readiness and answer limitations

### Requirement: Corporate-event search evidence
The system SHALL search for stock-specific news and announcements within the normalized analysis period and retain event date, publication time when available, publisher, title, link, and supported claim.

#### Scenario: Credible event evidence is found
- **WHEN** a primary or otherwise credible source reports a company event in the requested period
- **THEN** the system emits a corporate-event evidence item that can be aligned with the stock trading calendar

#### Scenario: Event date cannot be established
- **WHEN** a result is relevant but has no reliable publication or event date
- **THEN** the system may cite it as context but does not use it for event-window alignment

## REMOVED Requirements

### Requirement: Controlled MCP search invocation
**Reason**: Search transport is moving from a supervised SearchInfinity MCP subprocess to the official Doubao Search Custom HTTPS API, so MCP discovery, allowlisting, initialization, and stdio lifecycle no longer apply.

**Migration**: Replace the MCP runtime with a typed asynchronous HTTP client, fixed request mapping, response normalization, readiness checks, error mapping, quota protection, and server-side API-key configuration.
