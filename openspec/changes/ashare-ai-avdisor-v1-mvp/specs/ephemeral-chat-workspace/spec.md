## Purpose

定义与既有 Penpot 桌面端设计一致的单用户问答工作区、消息状态和临时上下文生命周期，使首版交互清晰且不会形成隐性会话历史。

## ADDED Requirements

### Requirement: Penpot-aligned research workspace
The system SHALL provide a desktop research-chat workspace that follows the supplied Penpot design's information hierarchy, visual states, and structured-answer presentation.

#### Scenario: Initial workspace
- **WHEN** the application opens with no current conversation
- **THEN** the user sees the research-question heading, supported-scope guidance, question composer, and no restored messages

#### Scenario: Active conversation
- **WHEN** the user has submitted a question
- **THEN** the workspace displays the current user message, assistant response state, and any completed structured answer in chronological order

### Requirement: Unsupported navigation and attachment visibility
The system MUST hide or visibly disable navigation destinations and attachment controls that are not included in the first-version scope.

#### Scenario: User views the first-version workspace
- **WHEN** the page renders
- **THEN** the interface does not imply that home dashboards, watchlists, market screens, research-report libraries, portfolios, settings, or file analysis are operational

### Requirement: Question submission states
The system SHALL provide observable idle, submitting, streaming, completed, and failed states and SHALL prevent duplicate submission while one request is active.

#### Scenario: Successful streaming answer
- **WHEN** the user submits a valid non-empty question and the backend streams a response
- **THEN** the user sees progress followed by incrementally rendered answer content and a completed state

#### Scenario: Submission fails
- **WHEN** the request fails due to validation, upstream service failure, timeout, or connectivity loss
- **THEN** the workspace shows an actionable error and preserves the submitted question for retry or editing

#### Scenario: Duplicate submission attempt
- **WHEN** the user attempts to submit again while a request is active
- **THEN** the system does not start a second concurrent request for the same conversation

### Requirement: Question input constraints
The system SHALL reject blank questions and SHALL enforce the 500-character input limit represented in the Penpot design.

#### Scenario: Blank input
- **WHEN** the composer contains only whitespace
- **THEN** submission remains unavailable

#### Scenario: Input reaches maximum length
- **WHEN** the question reaches 500 characters
- **THEN** the character counter shows the limit and the user cannot submit content beyond it

### Requirement: Structured answer rendering
The workspace SHALL visibly distinguish conclusion, facts, analysis, risk notices, citations, data cutoff, answer time, and disclaimer when those sections are present.

#### Scenario: Instrument research response
- **WHEN** the backend returns a complete instrument research answer
- **THEN** the workspace renders its semantic sections and source metadata without merging facts and model analysis into an indistinguishable block

#### Scenario: Knowledge response
- **WHEN** the backend returns a financial knowledge answer
- **THEN** the workspace renders the available explanatory content and citations without empty research-only sections

### Requirement: Ephemeral conversation lifecycle
The system MUST keep conversation messages and Agent context non-persistent and limited to the current page session.

#### Scenario: Page refresh
- **WHEN** the user refreshes the page
- **THEN** the application starts with no conversation history or restored Agent context

#### Scenario: Browser reopened
- **WHEN** the user closes and later reopens the browser or application
- **THEN** no prior conversation is restored

#### Scenario: New conversation
- **WHEN** the user activates “新建对话”
- **THEN** the visible messages and current Agent context are cleared and the initial workspace is shown

#### Scenario: Clear conversation
- **WHEN** the user activates “清空对话”
- **THEN** the visible messages and current Agent context are cleared without deleting unrelated market-data caches

### Requirement: Source and safety visibility
The workspace SHALL display source links, data cutoff information, and a persistent investment-risk disclaimer wherever applicable.

#### Scenario: Answer has cited evidence
- **WHEN** a response includes market-data or web-search evidence
- **THEN** the user can inspect its source attribution and relevant date metadata

#### Scenario: Research workspace displayed
- **WHEN** the research workspace is visible
- **THEN** the interface communicates that generated information is for research reference and does not constitute investment advice
