## Purpose

定义本地单用户助手可接受的研究与金融知识问题、回答边界和证据化输出，使用户获得清晰、可核验且不构成投资建议的回答。

## ADDED Requirements

### Requirement: Supported question routing
The system SHALL classify each submitted question as single-stock research, broad-based-index research, financial knowledge, mixed research and knowledge, or out of scope before producing a final answer.

#### Scenario: Single-stock research question
- **WHEN** the user asks about a uniquely identified supported A-share stock
- **THEN** the system routes the question through the market-data research path

#### Scenario: Broad-based-index research question
- **WHEN** the user asks about a supported broad-based index
- **THEN** the system routes the question through the index market-data research path

#### Scenario: Stable financial knowledge question
- **WHEN** the user asks a foundational financial question that does not require current information
- **THEN** the system answers without requiring market data or web search

#### Scenario: Mixed question
- **WHEN** a question combines a financial concept with analysis of a supported instrument
- **THEN** the system combines the concept explanation with grounded instrument data in one coherent answer

### Requirement: Supported instrument scope
The system SHALL support research questions about one A-share stock or one supported broad-based index per question and SHALL identify out-of-scope instruments and comparison requests explicitly.

#### Scenario: One supported instrument
- **WHEN** the user asks about one supported A-share stock or broad-based index
- **THEN** the system accepts the research request

#### Scenario: Multiple-instrument comparison
- **WHEN** the user requests a comparison of multiple stocks or indexes
- **THEN** the system explains that multi-instrument comparison is outside the first-version scope and suggests a single-instrument question

#### Scenario: Unsupported asset class
- **WHEN** the user requests research on an industry, concept, fund, bond, futures contract, Hong Kong stock, US stock, or portfolio
- **THEN** the system states the supported scope without fabricating an analysis

### Requirement: Instrument disambiguation
The system MUST resolve a research instrument to a canonical name, code, exchange, and instrument type before requesting instrument-specific data.

#### Scenario: Unique name or code
- **WHEN** the submitted stock or index name or code maps to exactly one supported instrument
- **THEN** the system proceeds using the canonical instrument identity

#### Scenario: Ambiguous instrument
- **WHEN** the submitted term maps to multiple instruments or cannot be identified confidently
- **THEN** the system requests clarification and does not guess an instrument

### Requirement: Evidence-separated research answer
The system SHALL present instrument research answers with a conclusion summary, grounded facts, model analysis, risk notices, sources and freshness information, and an investment disclaimer.

#### Scenario: Complete research answer
- **WHEN** sufficient validated evidence is available for a research question
- **THEN** the final answer distinguishes factual observations from interpretive analysis and includes sources and data cutoff information

#### Scenario: Knowledge-only answer
- **WHEN** the question is a financial knowledge question with no instrument research component
- **THEN** the answer uses a clear explanatory structure without forcing empty market-data sections

### Requirement: Investment-safety boundary
The system MUST NOT provide guaranteed returns, deterministic price predictions, personalized suitability judgments, direct buy or sell instructions, or automated trading actions.

#### Scenario: Request for a buy or sell instruction
- **WHEN** the user asks whether they should buy, sell, or hold an instrument
- **THEN** the system reframes the response around objective evidence, research considerations, and risks without issuing a direct instruction

#### Scenario: Request for guaranteed prediction
- **WHEN** the user asks for a guaranteed return or precise future price
- **THEN** the system refuses the guarantee and explains the uncertainty and relevant research factors

### Requirement: Current-context follow-up
The system SHALL use messages from the current page session to interpret follow-up questions while allowing explicit clarification to override prior context.

#### Scenario: Pronoun-based follow-up
- **WHEN** the user asks a follow-up such as “它的估值呢” after discussing a uniquely identified instrument
- **THEN** the system resolves the reference from the current conversation context

#### Scenario: Explicitly changed instrument
- **WHEN** the user names a different instrument in a follow-up
- **THEN** the system uses the newly named instrument rather than the prior context

