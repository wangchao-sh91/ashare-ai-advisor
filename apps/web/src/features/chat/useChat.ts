import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  MAX_MESSAGE_CHARS,
  MAX_MESSAGES,
  MAX_QUESTION_CHARS,
  MAX_TOTAL_CONTEXT_CHARS,
  ChatStreamError,
  streamChat,
  type ChatMessage,
  type StreamEvent,
} from "../../api";
import {
  chatReducer,
  emptySections,
  initialChatState,
  type ChatTurn,
} from "./state";

const activePhases = new Set(["submitting", "streaming"]);

export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const stateRef = useRef(state);
  const controllerRef = useRef<AbortController | null>(null);
  stateRef.current = state;

  useEffect(() => () => controllerRef.current?.abort(), []);

  const submit = useCallback(async (override?: string) => {
    const current = stateRef.current;
    if (activePhases.has(current.phase) || controllerRef.current) return;
    const question = (override ?? current.draft).trim();
    if (!question || question.length > MAX_QUESTION_CHARS) return;

    const id = crypto.randomUUID();
    const controller = new AbortController();
    controllerRef.current = controller;
    dispatch({
      type: "submit",
      turn: {
        id,
        question,
        submittedAt: new Date().toISOString(),
        phase: "submitting",
        sections: emptySections(),
        citations: [],
      },
    });
    try {
      await streamChat(
        { question, messages: buildContext(current.turns, question.length) },
        {
          signal: controller.signal,
          onEvent: (event) => dispatchStreamEvent(id, event, dispatch),
        },
      );
    } catch (error) {
      if (controller.signal.aborted) {
        if (controllerRef.current === controller)
          dispatch({ type: "cancel", id });
      } else {
        const message =
          error instanceof ChatStreamError
            ? error.message
            : "无法连接投研服务，请检查网络后重试。";
        dispatch({ type: "fail", id, error: { message, recoverable: true } });
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    dispatch({ type: "reset" });
  }, []);

  const cancel = useCallback(() => controllerRef.current?.abort(), []);
  const retry = useCallback(
    (question: string) => {
      void submit(question);
    },
    [submit],
  );

  return {
    state,
    active: activePhases.has(state.phase),
    setDraft: (value: string) => dispatch({ type: "draft", value }),
    submit: () => {
      void submit();
    },
    retry,
    reset,
    cancel,
  };
}

function dispatchStreamEvent(
  id: string,
  event: StreamEvent,
  dispatch: React.Dispatch<import("./state").ChatAction>,
): void {
  switch (event.event) {
    case "accepted":
      dispatch({ type: "accepted", id });
      break;
    case "status":
      dispatch({ type: "status", id, status: event });
      break;
    case "answer-start":
      dispatch({
        type: "start",
        id,
        instrument: event.instrument ?? undefined,
      });
      break;
    case "answer-delta":
      dispatch({ type: "delta", id, event });
      break;
    case "citation":
      dispatch({ type: "citation", id, citation: event.citation });
      break;
    case "answer-complete":
      dispatch({ type: "complete", id, answer: event.answer });
      break;
    case "error":
      dispatch({ type: "fail", id, error: event });
      break;
  }
}

function buildContext(
  turns: ChatTurn[],
  questionLength: number,
): ChatMessage[] {
  const remaining = MAX_TOTAL_CONTEXT_CHARS - questionLength;
  const context: ChatMessage[] = [];
  let used = 0;
  for (const turn of [...turns].reverse()) {
    if (turn.phase !== "completed" || !turn.answer) continue;
    const pair: ChatMessage[] = [
      { role: "user", content: turn.question.slice(0, MAX_MESSAGE_CHARS) },
      {
        role: "assistant",
        content: turn.answer.summary.slice(0, MAX_MESSAGE_CHARS),
      },
    ];
    const size = pair.reduce((sum, message) => sum + message.content.length, 0);
    if (used + size > remaining || context.length + pair.length > MAX_MESSAGES)
      break;
    context.unshift(...pair);
    used += size;
  }
  return context;
}
