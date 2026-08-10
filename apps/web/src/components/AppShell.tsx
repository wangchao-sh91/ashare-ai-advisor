import type { ReactNode } from "react";

import { Icon } from "./Icon";

interface AppShellProps {
  children: ReactNode;
  onNewChat: () => void;
}

const unavailableDestinations = [
  "首页",
  "自选股",
  "市场行情",
  "研报中心",
  "投资组合",
  "设置",
];

export function AppShell({ children, onNewChat }: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand" aria-label="A股 AI 投研助手">
          <span className="brand__mark">
            <Icon name="arrow-up-right" size={21} />
          </span>
          <span className="brand__name">A股 AI 投研助手</span>
        </div>
        <div className="topbar__scope">本地单用户 · 研究辅助</div>
      </header>

      <aside className="sidebar" aria-label="产品导航">
        <nav className="sidebar__nav">
          {unavailableDestinations.slice(0, 1).map((label) => (
            <button
              key={label}
              className="nav-item nav-item--disabled"
              disabled
              title="首版暂未开放"
            >
              <span className="nav-item__dot" />
              {label}
              <span className="sr-only">，暂未开放</span>
            </button>
          ))}
          <button className="nav-item nav-item--active" aria-current="page">
            <Icon name="sparkle" size={17} />
            投研问答
          </button>
          {unavailableDestinations.slice(1).map((label) => (
            <button
              key={label}
              className="nav-item nav-item--disabled"
              disabled
              title="首版暂未开放"
            >
              <span className="nav-item__dot" />
              {label}
              <span className="sr-only">，暂未开放</span>
            </button>
          ))}
        </nav>
        <section className="help-card" aria-labelledby="help-title">
          <span className="help-card__icon">
            <Icon name="help" size={18} />
          </span>
          <strong id="help-title">需要帮助？</strong>
          <span>支持单只 A 股、宽基指数与基础金融知识。</span>
        </section>
      </aside>

      <main className="content">
        <div className="page-heading">
          <div>
            <p className="breadcrumb">投研工作台 / 投研问答</p>
            <h1>投研问答</h1>
            <p className="page-heading__subtitle">
              基于公开信息生成结构化分析，辅助您快速理解市场。
            </p>
          </div>
          <button className="new-chat-button" onClick={onNewChat} type="button">
            <Icon name="plus" size={16} />
            新建对话
          </button>
        </div>
        {children}
      </main>
    </div>
  );
}
