import type { AnswerDeltaEvent, ChatRequest, StreamEvent } from "./wire";
import { streamEventNames } from "./wire";

const DEFAULT_API_BASE_URL = "/api";

export class ChatStreamError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ChatStreamError";
  }
}

export interface ChatStreamOptions {
  signal: AbortSignal;
  onEvent: (event: StreamEvent) => void;
  apiBaseUrl?: string;
}

export async function streamChat(
  payload: ChatRequest,
  {
    signal,
    onEvent,
    apiBaseUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
  }: ChatStreamOptions,
): Promise<void> {
  const response = await fetch(`${apiBaseUrl.replace(/\/$/, "")}/chat/stream`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    throw new ChatStreamError(responseMessage(response), response.status);
  }
  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new ChatStreamError(
      "服务返回了无法识别的响应格式。",
      response.status,
    );
  }
  if (!response.body) {
    throw new ChatStreamError("浏览器未收到流式响应内容。", response.status);
  }

  let terminal = false;
  for await (const frame of parseEventStream(response.body, signal)) {
    const event = validateStreamEvent(frame.event, frame.data);
    onEvent(event);
    if (event.event === "answer-complete" || event.event === "error") {
      terminal = true;
      break;
    }
  }
  if (!terminal && !signal.aborted) {
    throw new ChatStreamError("响应在完成前意外中断，请重试。");
  }
}

interface RawFrame {
  event: string;
  data: string;
}

async function* parseEventStream(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
): AsyncGenerator<RawFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      buffer += decoder
        .decode(value, { stream: !done })
        .replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const frame = parseFrame(raw);
        if (frame) yield frame;
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    const finalFrame = parseFrame(buffer.trim());
    if (finalFrame) yield finalFrame;
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(raw: string): RawFrame | null {
  if (!raw || raw.startsWith(":")) return null;
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

function validateStreamEvent(frameName: string, json: string): StreamEvent {
  let value: unknown;
  try {
    value = JSON.parse(json);
  } catch {
    throw new ChatStreamError("服务返回了无效的流式 JSON 数据。");
  }
  if (!isRecord(value) || !isString(value.event) || value.event !== frameName) {
    throw new ChatStreamError("流式事件名称与数据不一致。");
  }
  if (
    !streamEventNames.includes(value.event as (typeof streamEventNames)[number])
  ) {
    throw new ChatStreamError("服务返回了未知的流式事件。");
  }
  if (!isString(value.request_id) || !isString(value.timestamp)) {
    throw new ChatStreamError("流式事件缺少请求标识或时间戳。");
  }
  switch (value.event) {
    case "accepted":
      break;
    case "status":
      requireString(value, "stage");
      requireString(value, "message");
      break;
    case "answer-start":
      requireString(value, "answer_kind");
      break;
    case "answer-delta":
      requireString(value, "section");
      requireString(value, "delta");
      if (
        !Number.isInteger(value.sequence) ||
        !isStringArray(value.evidence_ids)
      )
        invalid();
      break;
    case "citation":
      if (!isCitation(value.citation)) invalid();
      break;
    case "answer-complete":
      if (!isAnswer(value.answer)) invalid();
      break;
    case "error":
      requireString(value, "code");
      requireString(value, "message");
      if (typeof value.recoverable !== "boolean") invalid();
      break;
  }
  return value as unknown as StreamEvent;
}

function isAnswer(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.kind) &&
    isString(value.summary) &&
    Array.isArray(value.facts) &&
    isStringArray(value.analysis) &&
    isStringArray(value.risks) &&
    Array.isArray(value.citations) &&
    value.citations.every(isCitation) &&
    isString(value.answered_at) &&
    isString(value.disclaimer) &&
    Array.isArray(value.limitations)
  );
}

function isCitation(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(value.id) &&
    isString(value.source_type) &&
    isString(value.title) &&
    isString(value.supported_claim) &&
    isString(value.retrieved_at)
  );
}

function requireString(value: Record<string, unknown>, key: string): void {
  if (!isString(value[key])) invalid();
}
function invalid(): never {
  throw new ChatStreamError("服务返回了不符合契约的流式事件。");
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function isString(value: unknown): value is string {
  return typeof value === "string";
}
function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function responseMessage(response: Response): string {
  if (response.status === 422) return "问题内容不符合要求，请检查长度后重试。";
  if (response.status >= 500) return "投研服务暂时不可用，请稍后重试。";
  return `请求失败（${response.status}），请重试。`;
}

export function appendDelta(
  current: Record<AnswerDeltaEvent["section"], string[]>,
  event: AnswerDeltaEvent,
): Record<AnswerDeltaEvent["section"], string[]> {
  return {
    ...current,
    [event.section]: [...current[event.section], event.delta],
  };
}
