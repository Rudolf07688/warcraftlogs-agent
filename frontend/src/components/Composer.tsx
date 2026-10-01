import { useState } from "react";

interface Props {
  disabled?: boolean;
  onSend: (text: string) => void;
}

export function Composer({ disabled, onSend }: Props) {
  const [text, setText] = useState("");

  function submit() {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }

  return (
    <div className="composer">
      <textarea
        className="composer-input"
        placeholder="Ask about Warcraft Logs… (e.g. How are hunters performing on Heroic Ula'tek?)"
        value={text}
        rows={2}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <button className="composer-send" onClick={submit} disabled={disabled || !text.trim()}>
        Send
      </button>
    </div>
  );
}
