import { useState } from "react";
import { LuFlag } from "react-icons/lu";
import { ApiError, reportGuide } from "../../api/restClient";
import type { Guide } from "../../types";
import { StatusAlert } from "../StatusAlert";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../ui/dialog";
import { Field, FieldDescription, FieldLabel } from "../ui/field";
import { Spinner } from "../ui/spinner";
import { Textarea } from "../ui/textarea";

// Feature 015 (FR-052): "Report an inaccuracy" on a published guide. The note is checked
// against the evidence on the guide's next update and marked fixed or rejected.

const MIN = 5;
const MAX = 500;

export function ReportGuideDialog({ guide, label }: { guide: Guide; label: string }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const length = note.trim().length;
  const valid = length >= MIN && length <= MAX;

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await reportGuide(guide.class_name, guide.spec, guide.content_type, note.trim());
      setDone(true);
      setNote("");
    } catch (e) {
      setErr(
        e instanceof ApiError && e.status === 429
          ? "You're sending reports too quickly — slow down a moment, then try again."
          : "Could not send the report. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setDone(false);
          setErr(null);
        }
      }}
    >
      {/* Radix returns focus to this trigger when the dialog closes. */}
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="self-start text-muted-foreground">
          <LuFlag />
          Report an inaccuracy
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Report an inaccuracy</DialogTitle>
          <DialogDescription>{label}</DialogDescription>
        </DialogHeader>
        {done ? (
          <StatusAlert tone="notice">Thanks — this will be checked on the next update.</StatusAlert>
        ) : (
          <>
            {err && <StatusAlert tone="error">{err}</StatusAlert>}
            <Field>
              <FieldLabel htmlFor="guide-report-note">What is wrong?</FieldLabel>
              <Textarea
                id="guide-report-note"
                value={note}
                maxLength={MAX}
                rows={4}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Combustion's cooldown changed in the latest hotfix."
                aria-describedby="guide-report-count"
              />
              <FieldDescription id="guide-report-count">
                {length} / {MAX} characters{length > 0 && length < MIN ? ` — at least ${MIN}` : ""}
              </FieldDescription>
            </Field>
          </>
        )}
        <DialogFooter>
          {done ? (
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Close
            </Button>
          ) : (
            <Button disabled={!valid || busy} onClick={() => void submit()}>
              {busy && <Spinner />}
              Send report
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
