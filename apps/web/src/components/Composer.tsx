import type { FormEvent, KeyboardEvent } from "react";

import { MAX_QUESTION_CHARS } from "../api";
import { Icon } from "./Icon";

interface ComposerProps {
  active: boolean;
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
  onSubmit: () => void;
}

export function Composer({
  active,
  value,
  onChange,
  onClear,
  onSubmit,
}: ComposerProps) {
  const valid = value.trim().length > 0 && value.length <= MAX_QUESTION_CHARS;
  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (valid && !active) onSubmit();
  };
  const keyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      submit();
    }
  };
  return (
    <form
      className={`composer${active ? " composer--active" : ""}`}
      onSubmit={submit}
    >
      <label className="sr-only" htmlFor="research-question">
        请输入投资研究问题
      </label>
      <textarea
        id="research-question"
        maxLength={MAX_QUESTION_CHARS}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={keyDown}
        placeholder="请输入您的问题（仅支持投资研究相关提问）"
        readOnly={active}
        rows={2}
        value={value}
      />
      <div className="composer__actions">
        <button
          className="composer__clear"
          disabled={active && !value}
          onClick={onClear}
          type="button"
        >
          <Icon name="clear" size={15} />
          清空对话
        </button>
        <span className="composer__count" aria-live="polite">
          {value.length}/{MAX_QUESTION_CHARS}
        </span>
        <button
          className="composer__send"
          disabled={!valid || active}
          type="submit"
          aria-label="发送问题"
        >
          <Icon name="send" size={22} />
        </button>
      </div>
    </form>
  );
}
