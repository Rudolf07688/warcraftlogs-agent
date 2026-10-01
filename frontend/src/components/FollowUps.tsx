// US1: up to three clickable follow-up question buttons rendered under the latest
// agent answer. The full question text is submitted on click; long labels are
// truncated for display only (via CSS). Buttons are disabled while a turn streams.

interface Props {
  suggestions: string[];
  disabled: boolean;
  onPick: (text: string) => void;
}

export function FollowUps({ suggestions, disabled, onPick }: Props) {
  if (!suggestions.length) return null;
  return (
    <div className="followups" role="group" aria-label="Suggested follow-up questions">
      {suggestions.slice(0, 3).map((s, i) => (
        <button
          key={`${i}-${s}`}
          className="followup-chip"
          disabled={disabled}
          title={s}
          onClick={() => onPick(s)}
        >
          {s}
        </button>
      ))}
    </div>
  );
}
