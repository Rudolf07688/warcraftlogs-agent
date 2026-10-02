// US4: a themed checkbox group of a report's distinct bosses. Selecting bosses folds
// their names into the next user message (handled in App). Readable on narrow + wide.
import type { Encounter } from "../types";

interface Props {
  encounters: Encounter[];
  selected: number[];
  onChange: (ids: number[]) => void;
  disabled?: boolean;
}

export function EncounterPicker({ encounters, selected, onChange, disabled }: Props) {
  if (encounters.length === 0) return null;

  function toggle(id: number) {
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  }

  return (
    <div className="encounter-picker">
      <div className="encounter-picker-label">Focus the next question on…</div>
      <div className="encounter-options">
        {encounters.map((e) => {
          const isSel = selected.includes(e.encounter_id);
          return (
            <label
              key={e.encounter_id}
              className={`encounter-option${isSel ? " selected" : ""}`}
            >
              <input
                type="checkbox"
                checked={isSel}
                disabled={disabled}
                onChange={() => toggle(e.encounter_id)}
              />
              <span>{e.name}</span>
              {e.kill && <span className="encounter-kill" title="Killed">✓</span>}
            </label>
          );
        })}
      </div>
    </div>
  );
}
