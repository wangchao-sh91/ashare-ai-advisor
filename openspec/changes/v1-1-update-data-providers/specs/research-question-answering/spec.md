## MODIFIED Requirements

### Requirement: Supported question routing
The system SHALL normalize and classify each submitted question as single-stock research, broad-based-index research, financial knowledge, mixed research and knowledge, or out of scope before producing a final answer.

#### Scenario: Single-stock research question
- **WHEN** the user asks about a uniquely identified supported A-share stock
- **THEN** the system routes requested price evidence to Tushare daily and requested non-price current evidence to category-specific search

#### Scenario: Broad-based-index research question
- **WHEN** the user asks about a supported broad-based index
- **THEN** the system routes the question through a search-only research path and does not promise deterministic index time-series metrics

#### Scenario: Stable financial knowledge question
- **WHEN** the user asks a foundational financial question that does not require current information
- **THEN** the system answers without requiring market data or web search

#### Scenario: Mixed question
- **WHEN** a question combines a financial concept with analysis of a supported instrument
- **THEN** the system combines the concept explanation with available category-grounded instrument evidence in one coherent answer

### Requirement: Supported instrument scope
The system SHALL support research questions about one A-share stock or one supported broad-based index per question and SHALL identify out-of-scope instruments and comparison requests explicitly.

#### Scenario: One supported A-share stock
- **WHEN** the user asks about one supported A-share stock
- **THEN** the system accepts the request and can use Tushare daily plus planned search categories

#### Scenario: One supported broad-based index
- **WHEN** the user asks about one supported broad-based index
- **THEN** the system accepts the request with an explicit search-only evidence limitation

#### Scenario: Multiple-instrument comparison
- **WHEN** the user requests a comparison of multiple stocks or indexes
- **THEN** the system explains that multi-instrument comparison is outside the first-version scope and suggests a single-instrument question

#### Scenario: Unsupported asset class
- **WHEN** the user requests research on an industry, concept, fund, bond, futures contract, Hong Kong stock, US stock, or portfolio
- **THEN** the system states the supported scope without fabricating an analysis

### Requirement: Instrument disambiguation
The system MUST resolve a research instrument to a canonical name, code, exchange, and instrument type through the structured question-normalization result before requesting instrument-specific evidence.

#### Scenario: Unique name or code
- **WHEN** the submitted stock or index name or code can be resolved confidently to one supported instrument
- **THEN** the system proceeds using the canonical identity and, for an A-share stock, its canonical Tushare `ts_code`

#### Scenario: Ambiguous instrument
- **WHEN** the submitted term maps to multiple instruments or cannot be identified confidently
- **THEN** the system requests clarification and does not guess an instrument or invoke instrument-specific providers

#### Scenario: Name and code conflict
- **WHEN** the submitted name and code or current-session context identify different instruments
- **THEN** the system marks the normalization result for clarification and does not silently prefer one identity

### Requirement: Evidence-separated research answer
The system SHALL present instrument research answers with a conclusion summary, category-grouped grounded facts, model analysis, category-level limitations, risk notices, sources and freshness information, and an investment disclaimer.

#### Scenario: Complete research answer
- **WHEN** sufficient validated evidence is available for every category required by a research question
- **THEN** the final answer distinguishes factual observations from interpretive analysis and includes sources and data cutoff information

#### Scenario: Partial research answer
- **WHEN** one or more requested categories are insufficient but another category has valid evidence that can answer part of the question
- **THEN** the final answer limits its analysis to valid categories and lists each insufficient category explicitly

#### Scenario: Knowledge-only answer
- **WHEN** the question is a financial knowledge question with no instrument research component
- **THEN** the answer uses a clear explanatory structure without forcing empty market-data or search sections

### Requirement: Current-context follow-up
The system SHALL provide bounded messages from the current page session to question normalization so follow-up questions can be rewritten as self-contained requests while explicit clarification overrides prior context.

#### Scenario: Pronoun-based follow-up
- **WHEN** the user asks a follow-up such as “它的估值呢” after discussing a uniquely identified instrument
- **THEN** the normalized question contains the canonical prior instrument and requests the valuation category

#### Scenario: Explicitly changed instrument
- **WHEN** the user names a different instrument in a follow-up
- **THEN** the normalized question uses the newly named instrument rather than the prior context

## ADDED Requirements

### Requirement: Structured question normalization
The system MUST use one bounded structured language-model call per submitted question to rewrite the request as self-contained and return intent, canonical instrument identity, requested evidence categories, analysis period, freshness intent, and clarification state.

#### Scenario: Valid structured result
- **WHEN** the model returns a schema-valid, internally consistent normalization result
- **THEN** the application validates its fields and builds the evidence plan without allowing the model to select arbitrary provider operations

#### Scenario: Invalid or inconsistent structured result
- **WHEN** required fields are missing, values violate the schema, or instrument fields conflict
- **THEN** the system retries only within the configured bound or requests clarification without invoking research providers

#### Scenario: No instrument is required
- **WHEN** the normalized intent is stable financial knowledge
- **THEN** the result may omit instrument identity and evidence categories that require external providers

### Requirement: Category-level evidence sufficiency
The system MUST determine sufficiency independently for every evidence category required by the normalized question before generating the final answer.

#### Scenario: All required categories are sufficient
- **WHEN** each required category contains validated evidence meeting its category rules
- **THEN** the system may produce a complete answer grounded in those categories

#### Scenario: Some required categories are insufficient
- **WHEN** at least one required category is insufficient and at least one other category is sufficient
- **THEN** the system produces only a partial answer that cannot use a sufficient category to conceal or replace an insufficient one

#### Scenario: All required categories are insufficient
- **WHEN** no required category has sufficient evidence
- **THEN** the system returns an evidence-insufficient response and does not ask the answer model to speculate

### Requirement: Combined daily-price and corporate-event analysis
The system SHALL support a single-stock question that requests analysis based on both daily prices and news or announcements by evaluating price and corporate-event evidence independently and then aligning valid evidence on one timeline.

#### Scenario: Price and event evidence are sufficient
- **WHEN** validated Tushare daily records and credible dated corporate-event evidence cover the normalized analysis period
- **THEN** the answer may describe price trends, relevant events, and deterministic event-window observations with separate provenance

#### Scenario: Only price evidence is sufficient
- **WHEN** daily records are valid but corporate-event search is unavailable or insufficient
- **THEN** the answer may provide price-based analysis while stating that event context could not be verified

#### Scenario: Only event evidence is sufficient
- **WHEN** credible corporate-event evidence is available but Tushare daily retrieval fails or is invalid
- **THEN** the answer may summarize verified events but does not describe price trends or market reactions

#### Scenario: Neither category is sufficient
- **WHEN** both daily-price and corporate-event evidence are unavailable or invalid
- **THEN** the system returns an evidence-insufficient response without trend analysis

### Requirement: Temporal-association boundary
The system MUST describe proximity between corporate events and price movement as temporal association unless independently grounded evidence establishes a stronger relationship.

#### Scenario: Price changes near an event
- **WHEN** a deterministic event-window observation shows a price change around a corporate event
- **THEN** the answer states the dates and observed movement and does not claim that the event caused the movement

#### Scenario: User asks for a causal conclusion
- **WHEN** the user asks whether a news item or announcement caused the stock move
- **THEN** the system explains that timeline alignment alone cannot establish causality and presents supported alternative or confounding considerations when available
