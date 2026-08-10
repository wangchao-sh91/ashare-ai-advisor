export const MAX_QUESTION_CHARS = 500;
export const MAX_MESSAGE_CHARS = 4000;
export const MAX_MESSAGES = 20;
export const MAX_TOTAL_CONTEXT_CHARS = 12000;

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ChatRequest {
  question: string;
  messages: ChatMessage[];
}

export type AnswerKind = "research" | "knowledge" | "mixed" | "clarification";
export type SourceType = "akshare" | "web";
export type SourceQuality = "primary" | "secondary";

export interface Instrument {
  name: string;
  code: string;
  exchange: "SSE" | "SZSE" | "BSE";
  instrument_type: "stock" | "broad_index";
}

export interface QualityFlag {
  code:
    | "stale"
    | "partial_coverage"
    | "insufficient_sample"
    | "unit_uncertain"
    | "source_conflict";
  detail: string;
}

export interface EvidenceItem {
  id: string;
  kind: "market_fact" | "computed_metric" | "web_fact";
  claim: string;
  value: string | null;
  unit: string | null;
  instrument: Instrument | null;
  period_start: string | null;
  period_end: string | null;
  formula: string | null;
  source_ids: string[];
  cutoff: string | null;
  retrieved_at: string;
  quality_flags: QualityFlag[];
}

export interface Citation {
  id: string;
  source_type: SourceType;
  title: string;
  supported_claim: string;
  source_quality: SourceQuality;
  interface: string | null;
  publisher: string | null;
  domain: string | null;
  url: string | null;
  snippet: string | null;
  published_at: string | null;
  retrieved_at: string;
}

export interface Limitation {
  code:
    | "data_unavailable"
    | "data_stale"
    | "partial_data"
    | "search_unverified"
    | "source_conflict"
    | "unsupported_category";
  message: string;
  affected_categories: string[];
  recoverable: boolean;
}

export interface StructuredAnswer {
  kind: AnswerKind;
  summary: string;
  facts: EvidenceItem[];
  analysis: string[];
  risks: string[];
  citations: Citation[];
  data_cutoff: string | null;
  answered_at: string;
  disclaimer: string;
  limitations: Limitation[];
}

export type ErrorCode =
  | "invalid_request"
  | "context_too_large"
  | "ambiguous_instrument"
  | "unsupported_scope"
  | "market_data_unavailable"
  | "search_unavailable"
  | "model_unavailable"
  | "provider_rate_limited"
  | "validation_failed"
  | "cancelled"
  | "internal_error";

interface EventBase {
  request_id: string;
  timestamp: string;
}

export interface AcceptedEvent extends EventBase {
  event: "accepted";
}

export interface StatusEvent extends EventBase {
  event: "status";
  stage:
    | "routing"
    | "market_data"
    | "web_search"
    | "calculation"
    | "generation"
    | "verification";
  message: string;
}

export interface AnswerStartEvent extends EventBase {
  event: "answer-start";
  answer_kind: AnswerKind;
  instrument: Instrument | null;
}

export interface AnswerDeltaEvent extends EventBase {
  event: "answer-delta";
  section:
    | "summary"
    | "fact"
    | "analysis"
    | "risk"
    | "limitation"
    | "disclaimer";
  sequence: number;
  delta: string;
  evidence_ids: string[];
}

export interface CitationEvent extends EventBase {
  event: "citation";
  citation: Citation;
}

export interface AnswerCompleteEvent extends EventBase {
  event: "answer-complete";
  answer: StructuredAnswer;
}

export interface ErrorEvent extends EventBase {
  event: "error";
  code: ErrorCode;
  message: string;
  recoverable: boolean;
  details: Record<string, string>;
}

export type StreamEvent =
  | AcceptedEvent
  | StatusEvent
  | AnswerStartEvent
  | AnswerDeltaEvent
  | CitationEvent
  | AnswerCompleteEvent
  | ErrorEvent;

export const streamEventNames = [
  "accepted",
  "status",
  "answer-start",
  "answer-delta",
  "citation",
  "answer-complete",
  "error",
] as const;
