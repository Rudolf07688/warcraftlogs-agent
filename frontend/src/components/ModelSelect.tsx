interface Props {
  models: string[];
  value: string;
  onChange: (model: string) => void;
  disabled?: boolean;
}

export function ModelSelect({ models, value, onChange, disabled }: Props) {
  return (
    <select
      className="model-select"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      title="Model"
    >
      {models.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
    </select>
  );
}
