interface Props {
  models: string[];
  value: string;
  onChange: (model: string) => void;
  disabled?: boolean;
  degraded?: boolean;
}

export function ModelSelect({ models, value, onChange, disabled, degraded }: Props) {
  return (
    <span className="model-select-wrap">
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
      {degraded && (
        <span
          className="model-degraded"
          title="Model discovery could not reach Vertex; showing a fallback list."
        >
          ⚠️ fallback list
        </span>
      )}
    </span>
  );
}
