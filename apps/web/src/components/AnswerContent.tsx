import type {
  Citation,
  EvidenceItem,
  Limitation,
  StructuredAnswer,
} from "../api";
import type { AnswerSections } from "../features/chat/state";
import { Icon } from "./Icon";

interface AnswerContentProps {
  answer?: StructuredAnswer;
  sections: AnswerSections;
  citations: Citation[];
}

export function AnswerContent({
  answer,
  sections,
  citations,
}: AnswerContentProps) {
  const summary = answer?.summary || sections.summary.join("");
  const facts = answer?.facts;
  const analysis = answer?.analysis ?? sections.analysis;
  const risks = answer?.risks ?? sections.risk;
  const limitations = answer?.limitations;
  const sources = answer?.citations.length ? answer.citations : citations;
  const disclaimer = answer?.disclaimer || sections.disclaimer.join("");
  return (
    <div className="answer-content">
      {summary && (
        <section className="answer-summary" aria-label="结论摘要">
          <h3>结论摘要</h3>
          <p>{summary}</p>
        </section>
      )}
      {(facts?.length || sections.fact.length > 0) && (
        <SemanticSection kind="fact" title="事实">
          {facts ? (
            <FactList facts={facts} />
          ) : (
            <TextList items={sections.fact} />
          )}
        </SemanticSection>
      )}
      {analysis.length > 0 && (
        <SemanticSection kind="analysis" title="分析">
          <TextList items={analysis} />
        </SemanticSection>
      )}
      {risks.length > 0 && (
        <SemanticSection kind="risk" title="风险提示">
          <TextList items={risks} />
        </SemanticSection>
      )}
      {((limitations?.length ?? 0) > 0 || sections.limitation.length > 0) && (
        <SemanticSection kind="limitation" title="数据与能力限制">
          {limitations ? (
            <LimitationList limitations={limitations} />
          ) : (
            <TextList items={sections.limitation} />
          )}
        </SemanticSection>
      )}
      {sources.length > 0 && <CitationList citations={sources} />}
      {answer && (
        <dl className="answer-meta">
          {answer.data_cutoff && (
            <>
              <dt>数据截止</dt>
              <dd>{formatDate(answer.data_cutoff)}</dd>
            </>
          )}
          <dt>回答时间</dt>
          <dd>{formatDate(answer.answered_at)}</dd>
        </dl>
      )}
      {disclaimer && <p className="answer-disclaimer">{disclaimer}</p>}
    </div>
  );
}

function SemanticSection({
  kind,
  title,
  children,
}: {
  kind: "fact" | "analysis" | "risk" | "limitation";
  title: string;
  children: React.ReactNode;
}) {
  const icon =
    kind === "risk"
      ? "risk"
      : kind === "analysis"
        ? "sparkle"
        : kind === "limitation"
          ? "help"
          : "fact";
  return (
    <section className={`semantic-section semantic-section--${kind}`}>
      <h3>
        <span>
          <Icon name={icon} size={15} />
        </span>
        {title}
      </h3>
      {children}
    </section>
  );
}

function TextList({ items }: { items: string[] }) {
  return (
    <ul>
      {items.map((item, index) => (
        <li key={`${index}-${item}`}>{item}</li>
      ))}
    </ul>
  );
}
function FactList({ facts }: { facts: EvidenceItem[] }) {
  return (
    <ul>
      {facts.map((fact) => (
        <li key={fact.id}>
          {fact.claim}
          {fact.value != null && (
            <>
              ：<strong>{fact.value}</strong>
              {fact.unit ? ` ${fact.unit}` : ""}
            </>
          )}
          {(fact.period_start || fact.period_end) && (
            <small>
              （{formatDate(fact.period_start)}–{formatDate(fact.period_end)}）
            </small>
          )}
        </li>
      ))}
    </ul>
  );
}
function LimitationList({ limitations }: { limitations: Limitation[] }) {
  return (
    <ul>
      {limitations.map((item, index) => (
        <li key={`${item.code}-${index}`}>{item.message}</li>
      ))}
    </ul>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  return (
    <section className="citations" aria-label="来源与引用">
      <h3>来源与引用</h3>
      <ol>
        {citations.map((citation) => {
          const url = safeExternalUrl(citation.url);
          return (
            <li key={citation.id}>
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  {citation.title}
                  <Icon name="external" size={13} />
                  <span className="sr-only">（在新窗口打开）</span>
                </a>
              ) : (
                <span>{citation.title}</span>
              )}
              <p>{citation.supported_claim}</p>
              <small>
                {citation.publisher ||
                  citation.domain ||
                  citation.interface ||
                  "公开信息"}{" "}
                · 发布：
                {citation.published_at
                  ? formatDate(citation.published_at)
                  : "日期未知"}{" "}
                · 获取：{formatDate(citation.retrieved_at)}
              </small>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function safeExternalUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
function formatDate(value: string | null | undefined): string {
  if (!value) return "未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}
