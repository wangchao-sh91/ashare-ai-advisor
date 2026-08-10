import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const timestamp = "2026-08-10T02:00:00Z";

const citation = {
  id: "web:exchange",
  source_type: "web",
  title: "上海证券交易所公告",
  supported_claim: "公告支持该项事实",
  source_quality: "primary",
  interface: null,
  publisher: "上海证券交易所",
  domain: "sse.com.cn",
  url: "https://www.sse.com.cn/disclosure/notice",
  snippet: "公告摘要",
  published_at: "2026-08-09T00:00:00Z",
  retrieved_at: timestamp,
};

const researchAnswer = {
  kind: "research",
  summary: "近期走势偏震荡，结论需要结合风险理解。",
  facts: [
    {
      id: "fact:return",
      kind: "computed_metric",
      claim: "近三个月区间收益",
      value: "-4.21",
      unit: "%",
      instrument: {
        name: "贵州茅台",
        code: "600519",
        exchange: "SSE",
        instrument_type: "stock",
      },
      period_start: "2026-05-08",
      period_end: "2026-08-08",
      formula: "end / start - 1",
      source_ids: ["akshare:history"],
      cutoff: "2026-08-08T00:00:00Z",
      retrieved_at: timestamp,
      quality_flags: [],
    },
  ],
  analysis: ["估值与盈利预期共同影响判断。"],
  risks: ["市场与政策变化可能影响结论。"],
  citations: [citation],
  data_cutoff: "2026-08-08T00:00:00Z",
  answered_at: timestamp,
  disclaimer: "本回答仅供研究参考，不构成任何投资建议。",
  limitations: [
    {
      code: "partial_data",
      message: "部分股东数据暂不可用。",
      affected_categories: ["ownership"],
      recoverable: true,
    },
  ],
};

beforeEach(() => {
  let uuidSequence = 0;
  vi.stubGlobal("crypto", {
    randomUUID: vi.fn(
      () =>
        `00000000-0000-4000-8000-${String(++uuidSequence).padStart(12, "0")}`,
    ),
  });
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("research workspace", () => {
  it("renders the initial state and visibly disables unsupported controls", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "投研问答" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("A股 AI 投研助手")).toBeInTheDocument();
    expect(screen.getByText("从一个明确的研究问题开始")).toBeInTheDocument();
    expect(screen.getByText(/不构成任何投资建议/)).toBeInTheDocument();
    for (const label of [
      "首页",
      "自选股",
      "市场行情",
      "研报中心",
      "投资组合",
      "设置",
    ]) {
      expect(
        screen.getByRole("button", { name: new RegExp(label) }),
      ).toBeDisabled();
    }
    expect(
      screen.queryByRole("button", { name: /附件|上传/ }),
    ).not.toBeInTheDocument();
  });

  it("rejects blank input and enforces the live 500-character limit", () => {
    render(<App />);
    const input = screen.getByLabelText("请输入投资研究问题");
    const send = screen.getByRole("button", { name: "发送问题" });

    fireEvent.change(input, { target: { value: "   " } });
    expect(send).toBeDisabled();
    fireEvent.change(input, { target: { value: "问".repeat(500) } });
    expect(screen.getByText("500/500")).toBeInTheDocument();
    expect(send).toBeEnabled();
    expect(input).toHaveAttribute("maxlength", "500");
  });

  it("moves through submitting, streaming, and completed states without duplicate submission", async () => {
    let streamController:
      | ReadableStreamDefaultController<Uint8Array>
      | undefined;
    const fetchMock = vi.fn(() =>
      Promise.resolve(
        sseResponse(
          new ReadableStream<Uint8Array>({
            start(controller) {
              streamController = controller;
              controller.enqueue(
                encode(
                  frame("accepted", {
                    event: "accepted",
                    request_id: "r1",
                    timestamp,
                  }),
                ),
              );
              controller.enqueue(
                encode(
                  frame("status", {
                    event: "status",
                    request_id: "r1",
                    timestamp,
                    stage: "market_data",
                    message: "正在获取并验证市场数据",
                  }),
                ),
              );
            },
          }),
        ),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    submitQuestion("分析贵州茅台近期走势");
    expect(screen.getByText("正在提交")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
    fireEvent.submit(
      screen.getByRole("button", { name: "发送问题" }).closest("form")!,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await screen.findByText("正在获取并验证市场数据");
    expect(screen.getByText("分析中")).toBeInTheDocument();
    streamController?.enqueue(
      encode(
        frame("answer-delta", {
          event: "answer-delta",
          request_id: "r1",
          timestamp,
          section: "analysis",
          sequence: 0,
          delta: "正在形成分析。",
          evidence_ids: [],
        }),
      ),
    );
    await screen.findByText("正在形成分析。");
    streamController?.enqueue(completeFrame(researchAnswer));
    streamController?.close();

    await screen.findByText("分析完成");
    expect(screen.getByText(researchAnswer.summary)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders research sections, citations, dates, and safe external links", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(completedResponse(researchAnswer))),
    );
    render(<App />);
    submitQuestion("分析贵州茅台近期走势和风险");

    await screen.findByText(researchAnswer.summary);
    expect(screen.getByRole("heading", { name: "事实" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "分析" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "风险提示" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "数据与能力限制" }),
    ).toBeInTheDocument();
    expect(screen.getByText("数据截止")).toBeInTheDocument();
    expect(screen.getByText("回答时间")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /上海证券交易所公告/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders a knowledge answer without empty research-only sections", async () => {
    const knowledgeAnswer = {
      ...researchAnswer,
      kind: "knowledge",
      summary: "市盈率是股价与每股收益的比值。",
      facts: [],
      risks: [],
      citations: [],
      data_cutoff: null,
      limitations: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(completedResponse(knowledgeAnswer))),
    );
    render(<App />);
    submitQuestion("什么是市盈率？");

    await screen.findByText(knowledgeAnswer.summary);
    expect(
      screen.queryByRole("heading", { name: "事实" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "风险提示" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "来源与引用" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("数据截止")).not.toBeInTheDocument();
  });

  it("preserves failed input and retries an actionable failure", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        sseResponse(
          streamOf(
            frame("error", {
              event: "error",
              request_id: "r1",
              timestamp,
              code: "model_unavailable",
              message: "模型服务当前不可用，请稍后重试。",
              recoverable: true,
              details: {},
            }),
          ),
        ),
      )
      .mockResolvedValueOnce(completedResponse(researchAnswer));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    submitQuestion("分析贵州茅台");

    await screen.findByRole("alert");
    expect(screen.getByLabelText("请输入投资研究问题")).toHaveValue(
      "分析贵州茅台",
    );
    fireEvent.click(screen.getByRole("button", { name: /重新尝试/ }));
    await screen.findByText(researchAnswer.summary);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("cancels an active request and keeps the question editable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          }),
      ),
    );
    render(<App />);
    submitQuestion("分析沪深300走势");
    fireEvent.click(await screen.findByRole("button", { name: "停止生成" }));

    await screen.findByText("已取消");
    expect(screen.getByText(/生成已停止/)).toBeInTheDocument();
    expect(screen.getByLabelText("请输入投资研究问题")).toHaveValue(
      "分析沪深300走势",
    );
  });
});

describe("ephemeral conversation lifecycle", () => {
  it("clear and new conversation cancel work and reset visible messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(completedResponse(researchAnswer))),
    );
    render(<App />);
    submitQuestion("分析贵州茅台");
    await screen.findByText(researchAnswer.summary);

    fireEvent.click(screen.getByRole("button", { name: /清空对话/ }));
    expect(screen.getByText("从一个明确的研究问题开始")).toBeInTheDocument();
    submitQuestion("分析贵州茅台");
    await screen.findByText(researchAnswer.summary);
    fireEvent.click(screen.getByRole("button", { name: "新建对话" }));
    expect(screen.getByText("从一个明确的研究问题开始")).toBeInTheDocument();
    expect(screen.queryByText(researchAnswer.summary)).not.toBeInTheDocument();
  });

  it("refresh-style remount and application reopen ignore browser storage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(completedResponse(researchAnswer))),
    );
    const first = render(<App />);
    submitQuestion("分析贵州茅台");
    await screen.findByText(researchAnswer.summary);
    localStorage.setItem(
      "ashare-chat",
      JSON.stringify({ turns: [researchAnswer] }),
    );
    sessionStorage.setItem("agent-context", "贵州茅台");

    first.unmount();
    render(<App />);
    expect(screen.getByText("从一个明确的研究问题开始")).toBeInTheDocument();
    expect(screen.queryByText(researchAnswer.summary)).not.toBeInTheDocument();
    expect(localStorage.getItem("ashare-chat")).not.toBeNull();
  });
});

function submitQuestion(question: string): void {
  fireEvent.change(screen.getByLabelText("请输入投资研究问题"), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
}

function completedResponse(answer: object): Response {
  return sseResponse(
    streamOf(
      frame("accepted", { event: "accepted", request_id: "r1", timestamp }),
      completeFrame(answer),
    ),
  );
}

function completeFrame(answer: object): Uint8Array {
  const value = frame("answer-complete", {
    event: "answer-complete",
    request_id: "r1",
    timestamp,
    answer,
  });
  return encode(value);
}

function frame(event: string, data: object): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function encode(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function streamOf(
  ...chunks: (string | Uint8Array)[]
): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) =>
        controller.enqueue(typeof chunk === "string" ? encode(chunk) : chunk),
      );
      controller.close();
    },
  });
}

function sseResponse(body: ReadableStream<Uint8Array>): Response {
  return new Response(body, {
    headers: { "Content-Type": "text/event-stream" },
  });
}
