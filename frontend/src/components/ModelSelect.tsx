import { memo } from "react";
import { StatusBadge } from "./StatusBadge";
import { NativeSelect, NativeSelectOption } from "./ui/native-select";

interface Props {
  models: string[];
  value: string;
  onChange: (model: string) => void;
  disabled?: boolean;
  degraded?: boolean;
}

function ModelSelectImpl({ models, value, onChange, disabled, degraded }: Props) {
  return (
    <span className="ml-auto inline-flex items-center gap-1.5">
      <NativeSelect
        size="sm"
        aria-label="Model"
        title="Model"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {models.map((m) => (
          <NativeSelectOption key={m} value={m}>
            {m}
          </NativeSelectOption>
        ))}
      </NativeSelect>
      {degraded && (
        <StatusBadge
          tone="warn"
          title="Model discovery could not reach Vertex; showing a fallback list."
        >
          ⚠️ fallback list
        </StatusBadge>
      )}
    </span>
  );
}

// PERF-010: skip re-rendering while a reply streams (its props don't change per token).
export const ModelSelect = memo(ModelSelectImpl);
