import { AnswerContent, Composer, Icon } from "../../components";
import type { ChatTurn } from "./state";
import type { useChat } from "./useChat";

const phaseLabels = {
  idle: "等待提问",
  submitting: "正在提交",
  streaming: "分析中",
  completed: "分析完成",
  failed: "分析失败",
  cancelled: "已取消",
} as const;

export function ChatWorkspace({ chat }: { chat: ReturnType<typeof useChat> }) {
  const latest = chat.state.turns.at(-1);
  return (
    <>
      <section className="chat-workspace" aria-labelledby="workspace-title">
        <header className="chat-header">
          <span className="chat-header__icon">
            <Icon name="sparkle" size={17} />
          </span>
          <div>
            <h2 id="workspace-title">
              {latest ? questionTitle(latest.question) : "AI 投研助手"}
            </h2>
            <p>
              {latest?.instrument
                ? `${latest.instrument.name} · ${latest.instrument.code}.${latest.instrument.exchange}`
                : "单只 A 股 · 宽基指数 · 金融知识"}
            </p>
          </div>
          <span
            className={`status-badge status-badge--${chat.state.phase}`}
            role="status"
            aria-live="polite"
          >
            {chat.state.phase === "completed" && (
              <Icon name="check" size={15} />
            )}
            {phaseLabels[chat.state.phase]}
          </span>
          {chat.active && (
            <button
              className="cancel-button"
              type="button"
              onClick={chat.cancel}
            >
              停止生成
            </button>
          )}
        </header>

        <div
          className="conversation"
          aria-live="polite"
          aria-relevant="additions text"
        >
          {chat.state.turns.length === 0 ? (
            <WelcomePanel />
          ) : (
            chat.state.turns.map((turn) => (
              <Turn
                key={turn.id}
                turn={turn}
                onRetry={() => chat.retry(turn.question)}
              />
            ))
          )}
        </div>

        <Composer
          active={chat.active}
          onChange={chat.setDraft}
          onClear={chat.reset}
          onSubmit={chat.submit}
          value={chat.state.draft}
        />
      </section>
      <p className="persistent-disclaimer">
        免责声明：本助手提供的信息仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。
      </p>
    </>
  );
}

function WelcomePanel() {
  return (
    <section className="welcome-panel" aria-labelledby="welcome-title">
      <span className="welcome-panel__icon">
        <Icon name="chat" size={24} />
      </span>
      <h2 id="welcome-title">从一个明确的研究问题开始</h2>
      <p>请指定一只 A 股或受支持的宽基指数，也可以询问基础金融知识。</p>
      <div className="scope-grid">
        <div>
          <strong>可以这样问</strong>
          <span>分析贵州茅台近期走势和主要风险</span>
        </div>
        <div>
          <strong>也支持</strong>
          <span>解释市盈率以及使用时的局限</span>
        </div>
        <div>
          <strong>首版边界</strong>
          <span>不提供多股对比、文件分析或买卖建议</span>
        </div>
      </div>
    </section>
  );
}

function Turn({ turn, onRetry }: { turn: ChatTurn; onRetry: () => void }) {
  const waiting =
    turn.phase === "submitting" ||
    (turn.phase === "streaming" && !hasContent(turn));
  return (
    <article className="turn" aria-label={`问题：${turn.question}`}>
      <div className="message-row message-row--user">
        <span
          className="message-avatar message-avatar--user"
          aria-hidden="true"
        >
          人
        </span>
        <div className="user-message">
          <p>{turn.question}</p>
          <time dateTime={turn.submittedAt}>
            {formatTime(turn.submittedAt)}
          </time>
        </div>
      </div>
      <div className="message-row message-row--assistant">
        <span
          className="message-avatar message-avatar--assistant"
          aria-hidden="true"
        >
          AI
        </span>
        <div className={`assistant-message assistant-message--${turn.phase}`}>
          {turn.status &&
            (turn.phase === "submitting" || turn.phase === "streaming") && (
              <p className="progress-line" role="status">
                <span className="progress-dot" />
                {turn.status.message}
              </p>
            )}
          {waiting && (
            <div className="loading-state">
              <span />
              <span />
              <span />
              <em>正在组织可验证的信息</em>
            </div>
          )}
          {hasContent(turn) && (
            <AnswerContent
              answer={turn.answer}
              citations={turn.citations}
              sections={turn.sections}
            />
          )}
          {turn.error && (
            <div className="error-notice" role="alert">
              <strong>本次分析未能完成</strong>
              <p>{turn.error.message}</p>
              {turn.error.recoverable && (
                <button type="button" onClick={onRetry}>
                  重新尝试
                  <Icon name="chevron-right" size={15} />
                </button>
              )}
            </div>
          )}
          {turn.phase === "cancelled" && (
            <div className="cancelled-notice">
              生成已停止，问题仍保留在输入框中。
            </div>
          )}
          <time className="assistant-time" dateTime={turn.submittedAt}>
            {formatTime(turn.submittedAt)}
          </time>
        </div>
      </div>
    </article>
  );
}

function hasContent(turn: ChatTurn): boolean {
  return Boolean(
    turn.answer ||
      turn.citations.length ||
      Object.values(turn.sections).some((items) => items.length),
  );
}
function questionTitle(question: string): string {
  return question.length > 22 ? `${question.slice(0, 22)}…` : question;
}
function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}
