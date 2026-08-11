## MODIFIED Requirements

### Requirement: Grounded market-data retrieval
The system SHALL retrieve instrument-specific unadjusted A-share daily price data only through the approved Tushare `daily` interface selected for the requested stock and analysis period.

#### Scenario: Daily data available
- **WHEN** Tushare `daily` returns valid records for the requested A-share stock and period
- **THEN** the system normalizes the records into a consistent market-evidence representation for downstream analysis

#### Scenario: Unsupported structured market-data request
- **WHEN** the request needs a market-data category other than supported A-share daily prices
- **THEN** the system identifies that category as unsupported by the market-data provider and does not ask the model to infer its values

### Requirement: Deterministic metric computation
The system MUST compute supported numeric research metrics outside the language model using defined formulas and validated Tushare daily inputs.

#### Scenario: Supported daily-price metrics requested
- **WHEN** the answer needs interval return, moving averages, volume change, volatility, or an event-window price observation that can be calculated from valid daily records
- **THEN** the system calculates the metric deterministically and supplies the computed value, formula context, and calculation period as evidence

#### Scenario: Unsupported metric requested
- **WHEN** the answer needs benchmark-relative return, year-over-year fundamentals, valuation percentile, or another metric whose required structured inputs are unavailable
- **THEN** the system omits the metric and identifies the missing input category instead of estimating it

#### Scenario: Insufficient calculation inputs
- **WHEN** required observations are missing or use incompatible periods or units
- **THEN** the system omits the affected metric and reports why it could not be calculated

### Requirement: Data provenance and freshness
The system SHALL associate each material market-data fact with the Tushare `daily` interface, canonical stock identity, covered period, data cutoff date, and retrieval time.

#### Scenario: Research answer with market data
- **WHEN** Tushare daily data contributes to the final answer
- **THEN** the user can see the effective data date and a human-readable Tushare source attribution

#### Scenario: Data older than requested
- **WHEN** the latest available daily record predates the requested period or expected freshness
- **THEN** the answer explicitly displays the actual cutoff and qualifies conclusions affected by stale data

### Requirement: Data quality validation
The system MUST validate required Tushare fields, canonical stock code, numeric types, normalized units, date ordering, duplicate trading dates, and minimum sample sufficiency before using daily data as evidence.

#### Scenario: Data passes validation
- **WHEN** the retrieved dataset satisfies validation rules for the selected calculation
- **THEN** the system marks the evidence as usable after converting `vol` from hands to shares and `amount` from thousands of CNY to CNY

#### Scenario: Data fails validation
- **WHEN** the dataset contains a critical schema change, invalid unit, missing required field, duplicate conflict, or insufficient observations
- **THEN** the system excludes affected facts and returns a visible partial-data or unavailable-data notice

### Requirement: Market-data failure isolation
The system SHALL degrade at the evidence-category level so that a failed Tushare daily request makes price evidence insufficient without invalidating unrelated validated search evidence.

#### Scenario: Price retrieval fails while another category succeeds
- **WHEN** Tushare daily retrieval fails or returns invalid data and valid evidence exists for a requested non-price category
- **THEN** the system may answer from the valid category while clearly stating that price evidence is insufficient

#### Scenario: No sufficient research evidence
- **WHEN** all evidence categories necessary to answer the research question are unavailable or invalid
- **THEN** the system returns an evidence-unavailable response and does not generate unsupported analysis

## ADDED Requirements

### Requirement: Price-source exclusivity
The system MUST treat validated Tushare daily records as the only admissible source of stock price evidence and MUST NOT use search results to replace missing, failed, or invalid daily records.

#### Scenario: Search result contains a quoted stock price
- **WHEN** Tushare daily evidence is unavailable but a search result mentions a price or return
- **THEN** the system does not classify that result as price evidence and reports the price category as insufficient

#### Scenario: Search supports a separate requested category
- **WHEN** Tushare daily evidence is unavailable and search returns credible news, announcement, financial, or ownership evidence
- **THEN** the system retains that evidence only in its own category and does not use it for deterministic price calculations

### Requirement: Corporate-event trading-day alignment
The system SHALL align dated corporate-event evidence to the stock trading-day calendar and SHALL calculate configured event-window price observations only from validated daily records.

#### Scenario: Event occurs on a non-trading day or after market close
- **WHEN** a credible event is published on a non-trading day or is reliably timestamped after market close
- **THEN** the system maps the event to the next available trading day and records the mapping rule

#### Scenario: Event publication time is unknown
- **WHEN** a credible event has a publication date but no reliable time
- **THEN** the system labels the timing uncertainty and avoids claiming an exact same-day market reaction

#### Scenario: Event window can be calculated
- **WHEN** sufficient daily records exist around an aligned event date
- **THEN** the system calculates configured one-, three-, and five-trading-day observations deterministically and describes them as temporal observations rather than causal effects

## REMOVED Requirements

### Requirement: Benchmark transparency
**Reason**: The free-provider scope no longer includes structured broad-index daily series, so the system cannot calculate reliable benchmark-relative performance.

**Migration**: Broad-index questions remain supported through search-grounded evidence, while stock answers omit benchmark-relative metrics and explicitly identify the missing structured benchmark input.
