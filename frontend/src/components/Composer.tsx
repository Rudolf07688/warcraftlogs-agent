import { useState } from "react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";

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
      <Textarea
        className="flex-1 min-h-0 max-h-40 resize-none bg-secondary/60"
        aria-label="Message"
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
      <Button className="self-stretch h-auto px-5" onClick={submit} disabled={disabled || !text.trim()}>
        Send
      </Button>
    </div>
  );
}
