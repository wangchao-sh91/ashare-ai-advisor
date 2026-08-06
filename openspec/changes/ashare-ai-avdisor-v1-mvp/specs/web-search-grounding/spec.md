## Purpose

定义 Agent 何时使用豆包搜索 Tool，以及如何筛选、引用和降级联网信息，使具有时效性的金融回答可核验并避免把搜索摘要当作无来源事实。

## ADDED Requirements

### Requirement: Search decision
The system SHALL invoke web search when a question depends on recent events, current rules or policies, current market information, or facts requiring external verification, and SHALL avoid mandatory search for stable foundational knowledge.

#### Scenario: Current-information question
- **WHEN** the user asks about a recent company event, current market rule, current policy, or other time-sensitive fact
- **THEN** the system uses the Doubao search tool before presenting the time-sensitive claim

#### Scenario: Stable foundational knowledge
- **WHEN** the user asks for the definition of a stable financial concept without requesting current facts
- **THEN** the system can answer without invoking web search

### Requirement: Search source quality
The system MUST prefer authoritative primary sources and MUST distinguish source publication time from retrieval time.

#### Scenario: Primary source available
- **WHEN** an exchange, regulator, listed company, government agency, index publisher, or other authoritative primary source supports the claim
- **THEN** the system prioritizes that source over secondary summaries

#### Scenario: Only secondary sources available
- **WHEN** no suitable primary source can be found
- **THEN** the system labels the evidence as secondary and avoids presenting uncertain details as established fact

### Requirement: Search citation metadata
The system SHALL retain and expose a title, destination link, publisher or domain, publication time when available, retrieval time, and the supported claim for each cited search result.

#### Scenario: Search-grounded answer
- **WHEN** search evidence contributes a material claim to the answer
- **THEN** the answer includes a user-accessible citation located near the supported claim or in a clearly associated sources section

#### Scenario: Search result lacks publication date
- **WHEN** a selected result has no reliable publication date
- **THEN** the citation indicates that the publication date is unavailable and includes retrieval time

### Requirement: Conflicting search evidence
The system MUST disclose material conflicts between credible sources rather than silently selecting a convenient version.

#### Scenario: Credible sources disagree
- **WHEN** authoritative sources provide materially different values or interpretations for a fact
- **THEN** the system describes the conflict, cites the relevant sources, and qualifies any conclusion

### Requirement: Search failure degradation
The system SHALL distinguish search unavailability from absence of evidence and SHALL not claim that no event or rule exists solely because search failed.

#### Scenario: Search tool unavailable
- **WHEN** the search tool times out, rejects the request, or returns an invalid response
- **THEN** the system states that current information could not be verified and may only answer stable portions of the question

#### Scenario: No credible result found
- **WHEN** search succeeds but returns no credible evidence for the requested current claim
- **THEN** the system reports that it could not find sufficient reliable evidence and does not fabricate a citation

