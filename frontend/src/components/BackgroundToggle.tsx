// US6: switch the app background at runtime. Backed by the config registry and
// persisted via uiPrefs (through App's changeBackground handler).
import { BACKGROUNDS } from "../config";

interface Props {
  value: string;
  onChange: (id: string) => void;
}

export function BackgroundToggle({ value, onChange }: Props) {
  return (
    <label className="bg-toggle" title="Change the background">
      <span className="bg-toggle-label">Background</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {BACKGROUNDS.map((b) => (
          <option key={b.id} value={b.id}>
            {b.label}
          </option>
        ))}
      </select>
    </label>
  );
}
