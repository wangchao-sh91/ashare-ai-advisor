# market-data-grounding Specification

## Purpose

定义投研回答如何取得、计算、校验和标注公开金融数据，确保关键数字来自确定性处理并在数据异常时安全降级，而不是由模型补全。

## Requirements

### Requirement: Grounded market-data retrieval
The system SHALL retrieve instrument-specific public market data through approved AKShare interfaces selected for the requested instrument and analysis type.

#### Scenario: Data available
- **WHEN** the selected interfaces return valid data for the requested instrument and period
- **THEN** the system normalizes the results into a consistent evidence representation for downstream analysis

#### Scenario: Unsupported data request
- **WHEN** no approved interface can provide a requested data category reliably
- **THEN** the system identifies the unavailable category and does not ask the model to infer its values

### Requirement: Deterministic metric computation
The system MUST compute numeric research metrics outside the language model using defined formulas and validated inputs.

#### Scenario: Trend metrics requested
- **WHEN** the answer needs interval return, benchmark-relative return, moving averages, volume change, volatility, year-over-year change, or valuation percentile
- **THEN** the system calculates the metric deterministically and supplies the computed value and calculation period as evidence

#### Scenario: Insufficient calculation inputs
- **WHEN** required observations are missing or use incompatible periods or units
- **THEN** the system omits the affected metric and reports why it could not be calculated

### Requirement: Data provenance and freshness
The system SHALL associate each material market-data fact with the AKShare interface, reported upstream source, covered period, data cutoff time, and retrieval time when those fields are available.

#### Scenario: Research answer with market data
- **WHEN** market data contributes to the final answer
- **THEN** the user can see the effective data date and a human-readable source attribution

#### Scenario: Data older than requested
- **WHEN** the latest available data predates the requested period or expected freshness
- **THEN** the answer explicitly displays the actual cutoff and qualifies conclusions affected by stale data

### Requirement: Data quality validation
The system MUST validate required fields, numeric types, units, date ordering, duplicate observations, and minimum sample sufficiency before using data as evidence.

#### Scenario: Data passes validation
- **WHEN** the retrieved dataset satisfies validation rules for the selected calculation
- **THEN** the system marks the evidence as usable

#### Scenario: Data fails validation
- **WHEN** the dataset contains a critical schema change, invalid unit, missing required field, or insufficient observations
- **THEN** the system excludes affected facts and returns a visible partial-data or unavailable-data notice

### Requirement: Market-data failure isolation
The system SHALL degrade at the data-category level so that one failed upstream request does not invalidate unrelated validated evidence.

#### Scenario: Partial interface failure
- **WHEN** price history is available but a shareholder or valuation interface fails
- **THEN** the system may answer from price history while clearly listing the unavailable categories

#### Scenario: No sufficient research evidence
- **WHEN** all evidence necessary to answer the research question is unavailable or invalid
- **THEN** the system returns an evidence-unavailable response and does not generate unsupported analysis

### Requirement: Benchmark transparency
The system SHALL identify the benchmark and aligned trading-date range whenever it presents benchmark-relative performance.

#### Scenario: Relative performance shown
- **WHEN** a stock return is compared with a broad-based index
- **THEN** the answer names the benchmark and uses the common available trading dates for both series

