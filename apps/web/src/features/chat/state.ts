import type {
  AnswerDeltaEvent,
  Citation,
  ErrorEvent,
  Instrument,
  StatusEvent,
  StructuredAnswer,
} from "../../api";

export type ChatPhase =
  | "idle"
  | "submitting"
  | "streaming"
  | "completed"
  | "failed"
  | "cancelled";
export type AnswerSections = Record<AnswerDeltaEvent["section"], string[]>;

export interface ChatTurn {
  id: string;
  question: string;
  submittedAt: string;
  phase: Exclude<ChatPhase, "idle">;
  status?: StatusEvent;
  instrument?: Instrument;
  sections: AnswerSections;
  citations: Citation[];
  answer?: StructuredAnswer;
  error?: ErrorEvent | { message: string; recoverable: boolean };
}

export interface ChatState {
  phase: ChatPhase;
  draft: string;
  turns: ChatTurn[];
}

export const emptySections = (): AnswerSections => ({
  summary: [],
  fact: [],
  analysis: [],
  risk: [],
  limitation: [],
  disclaimer: [],
});

export const initialChatState: ChatState = {
  phase: "idle",
  draft: "",
  turns: [],
};

export type ChatAction =
  | { type: "draft"; value: string }
  | { type: "submit"; turn: ChatTurn }
  | { type: "accepted"; id: string }
  | { type: "status"; id: string; status: StatusEvent }
  | { type: "start"; id: string; instrument?: Instrument }
  | { type: "delta"; id: string; event: AnswerDeltaEvent }
  | { type: "citation"; id: string; citation: Citation }
  | { type: "complete"; id: string; answer: StructuredAnswer }
  | { type: "fail"; id: string; error: ChatTurn["error"] }
  | { type: "cancel"; id: string }
  | { type: "reset" };

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "draft":
      return { ...state, draft: action.value };
    case "submit":
      return {
        ...state,
        phase: "submitting",
        turns: [...state.turns, action.turn],
      };
    case "accepted":
      return updateTurn(state, action.id, { phase: "streaming" }, "streaming");
    case "status":
      return updateTurn(
        state,
        action.id,
        { phase: "streaming", status: action.status },
        "streaming",
      );
    case "start":
      return updateTurn(
        state,
        action.id,
        { phase: "streaming", instrument: action.instrument },
        "streaming",
      );
    case "delta":
      return mapTurn(
        state,
        action.id,
        (turn) => ({
          ...turn,
          phase: "streaming",
          sections: {
            ...turn.sections,
            [action.event.section]: [
              ...turn.sections[action.event.section],
              action.event.delta,
            ],
          },
        }),
        "streaming",
      );
    case "citation":
      return mapTurn(state, action.id, (turn) => ({
        ...turn,
        citations: [...turn.citations, action.citation],
      }));
    case "complete":
      return {
        ...updateTurn(
          state,
          action.id,
          { phase: "completed", answer: action.answer },
          "completed",
        ),
        draft: "",
      };
    case "fail":
      return updateTurn(
        state,
        action.id,
        { phase: "failed", error: action.error },
        "failed",
      );
    case "cancel":
      return updateTurn(state, action.id, { phase: "cancelled" }, "cancelled");
    case "reset":
      return initialChatState;
  }
}

function updateTurn(
  state: ChatState,
  id: string,
  patch: Partial<ChatTurn>,
  phase: ChatPhase = state.phase,
): ChatState {
  return mapTurn(state, id, (turn) => ({ ...turn, ...patch }), phase);
}

function mapTurn(
  state: ChatState,
  id: string,
  update: (turn: ChatTurn) => ChatTurn,
  phase: ChatPhase = state.phase,
): ChatState {
  if (!state.turns.some((turn) => turn.id === id)) return state;
  return {
    ...state,
    phase,
    turns: state.turns.map((turn) => (turn.id === id ? update(turn) : turn)),
  };
}
