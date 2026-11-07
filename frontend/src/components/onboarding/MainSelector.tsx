import { useEffect, useId, useMemo, useState } from "react";
import { ApiError, listGuides, saveProfileSettings } from "../../api/restClient";
import type { GuideListItem, MainContent, ProfileSettings, ProfileSettingsInput } from "../../types";
import { Button } from "../ui/button";
import { Field, FieldError, FieldLabel, FieldTitle } from "../ui/field";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";

// Feature 074 (sc-167): pick a main class, optionally one of its specs, and the main content.
// The classes and specs are the app's one roster (the Class Guides list); the server checks
// the values again. Saving replaces all three; an empty choice clears it.

const CONTENT: { value: MainContent; label: string }[] = [
  { value: "raid", label: "Raid" },
  { value: "mplus", label: "Mythic+" },
  { value: "both", label: "Both" },
];

type RosterClass = { display: string; specs: { spec: string; display: string }[] };

function byClass(items: GuideListItem[]): Map<string, RosterClass> {
  const out = new Map<string, RosterClass>();
  for (const it of items) {
    const entry = out.get(it.class_name) ?? { display: it.class_display, specs: [] };
    entry.specs.push({ spec: it.spec, display: it.spec_display });
    out.set(it.class_name, entry);
  }
  return out;
}

export function MainSelector({
  value,
  onSaved,
}: {
  value: ProfileSettingsInput;
  onSaved: (settings: ProfileSettings) => void;
}) {
  const ids = { cls: useId(), spec: useId() };
  const [roster, setRoster] = useState<Map<string, RosterClass> | null>(null);
  // Only the three saved fields: the PUT rejects any other key.
  const saved: ProfileSettingsInput = {
    main_class: value.main_class,
    main_spec: value.main_spec,
    main_content: value.main_content,
  };
  const [draft, setDraft] = useState<ProfileSettingsInput>(saved);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(
    () => setDraft({ main_class: value.main_class, main_spec: value.main_spec, main_content: value.main_content }),
    [value.main_class, value.main_spec, value.main_content],
  );

  useEffect(() => {
    let live = true;
    listGuides().then(
      (r) => live && setRoster(byClass(r.guides)),
      () => live && setError("Couldn't load the class list. Try again later."),
    );
    return () => {
      live = false;
    };
  }, []);

  const specs = useMemo(
    () => (draft.main_class ? (roster?.get(draft.main_class)?.specs ?? []) : []),
    [roster, draft.main_class],
  );
  const changed =
    draft.main_class !== saved.main_class ||
    draft.main_spec !== saved.main_spec ||
    draft.main_content !== saved.main_content;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onSaved(await saveProfileSettings(draft));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <Field className="w-auto">
          <FieldLabel htmlFor={ids.cls}>Main class</FieldLabel>
          <NativeSelect
            id={ids.cls}
            value={draft.main_class ?? ""}
            disabled={!roster}
            // A new class drops a spec that belongs to the old one.
            onChange={(e) => setDraft({ ...draft, main_class: e.target.value || null, main_spec: null })}
          >
            <NativeSelectOption value="">No main class</NativeSelectOption>
            {[...(roster ?? new Map<string, RosterClass>())].map(([cls, info]) => (
              <NativeSelectOption key={cls} value={cls}>
                {info.display}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <Field className="w-auto">
          <FieldLabel htmlFor={ids.spec}>Main spec</FieldLabel>
          <NativeSelect
            id={ids.spec}
            value={draft.main_spec ?? ""}
            disabled={!draft.main_class || specs.length === 0}
            onChange={(e) => setDraft({ ...draft, main_spec: e.target.value || null })}
          >
            <NativeSelectOption value="">Any spec</NativeSelectOption>
            {specs.map((s) => (
              <NativeSelectOption key={s.spec} value={s.spec}>
                {s.display}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <Field className="w-auto">
          <FieldTitle>Main content</FieldTitle>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            aria-label="Main content"
            value={draft.main_content ?? ""}
            onValueChange={(v) => setDraft({ ...draft, main_content: (v || null) as MainContent | null })}
          >
            {CONTENT.map((c) => (
              <ToggleGroupItem
                key={c.value}
                value={c.value}
                className="dark:data-[state=on]:bg-primary/15 dark:data-[state=on]:text-glow"
              >
                {c.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
        <Button onClick={save} disabled={!changed || saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
      </div>
      <FieldError>{error}</FieldError>
    </div>
  );
}
