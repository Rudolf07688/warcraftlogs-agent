import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/restClient";
import {
  type RaidSummary,
  type RaidSummaryCharacter,
  type RaidSummaryParticipant,
} from "../../api/raidSummary";
import { Alert, AlertDescription } from "../ui/alert";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";
import { formatDuration, formatWhen } from "./raidFormat";
import { loadRaidSummary } from "./summaryCache";

type State =
  | { kind: "loading" }
  | { kind: "ready"; summary: RaidSummary }
  | { kind: "error"; notFound: boolean; rateLimited: boolean };

const ROLE_ORDER = ["tank", "healer", "dps", "other"] as const;
const ROLE_LABEL: Record<(typeof ROLE_ORDER)[number], string> = {
  tank: "Tanks",
  healer: "Healers",
  dps: "DPS",
  other: "Other",
};

function groupByRole(participants: RaidSummaryParticipant[]) {
  const groups: Record<(typeof ROLE_ORDER)[number], RaidSummaryParticipant[]> = {
    tank: [],
    healer: [],
    dps: [],
    other: [],
  };
  for (const p of participants) groups[p.role ?? "other"].push(p);
  return groups;
}

// Each part may be null (contract:raid-summary): a missing one is left out, never printed.
function classLine(c: { class_name: string | null; spec: string | null }): string {
  return [c.spec, c.class_name].filter(Boolean).join(" ");
}

function Participants({ participants }: { participants: RaidSummaryParticipant[] }) {
  const groups = groupByRole(participants);
  return (
    <section aria-label="Participants" className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">Participants ({participants.length})</h3>
      {ROLE_ORDER.filter((r) => groups[r].length > 0).map((r) => (
        <div key={r} role="group" aria-label={ROLE_LABEL[r]}>
          <div className="text-[0.6875rem] uppercase tracking-wider text-muted-foreground">
            {ROLE_LABEL[r]} ({groups[r].length})
          </div>
          <ul className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            {groups[r].map((p, i) => (
              <li key={`${p.name}-${i}`} className="flex min-w-0 gap-2 text-sm">
                <span className="truncate font-medium">{p.name}</span>
                <span className="truncate text-muted-foreground">{classLine(p)}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function MyCharacters({ characters }: { characters: RaidSummaryCharacter[] }) {
  return (
    <section aria-label="My characters" className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">My characters</h3>
      {characters.map((c, i) => (
        <div key={`${c.name}-${i}`} className="min-w-0">
          <div className="flex min-w-0 gap-2 text-sm">
            <span className="truncate font-medium">{c.name}</span>
            <span className="truncate text-muted-foreground">{classLine(c)}</span>
          </div>
          {c.parses.length === 0 ? (
            <div className="text-sm text-muted-foreground">No parses stored</div>
          ) : (
            <ul>
              {c.parses.map((p, j) => (
                <li key={j} className="flex min-w-0 justify-between gap-3 text-sm">
                  <span className="truncate">
                    {p.encounter ?? "Unknown encounter"}
                    {p.difficulty ? ` (${p.difficulty})` : ""}
                  </span>
                  <span className="shrink-0 tabular-nums">
                    {p.percentile == null ? "n/a" : `${Math.round(p.percentile)}%`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </section>
  );
}

/**
 * The stored data of one tracked raid (contract:raid-summary). Mounted per tab, keyed by the
 * report code, so an answer that arrives after the user moved on is dropped (`cancelled`).
 */
export function RaidSummaryPanel({ reportCode }: { reportCode: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    loadRaidSummary(reportCode).then(
      (summary) => {
        if (!cancelled) setState({ kind: "ready", summary });
      },
      (err: unknown) => {
        if (cancelled) return;
        const status = err instanceof ApiError ? err.status : 0;
        setState({ kind: "error", notFound: status === 404, rateLimited: status === 429 });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [reportCode, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);

  if (state.kind === "loading") {
    return (
      <div role="status" aria-label="Loading raid data" className="flex flex-col gap-2">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <Alert variant="destructive">
        <AlertDescription className="flex flex-wrap items-center gap-2">
          {state.notFound
            ? "Raid not found: it is not one of your tracked raids."
            : state.rateLimited
              ? "Too many requests, try again in a minute."
              : "Could not load the stored data for this raid."}
          {!state.notFound && (
            <Button size="sm" variant="secondary" onClick={retry}>
              Retry
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }
  const s = state.summary;
  if (!s.has_data) {
    return (
      <p className="text-sm text-muted-foreground">
        Nothing stored for this raid yet: analyze it to pull its data.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {s.duration_ms != null && (
        <div className="text-sm">
          <span className="text-muted-foreground">Duration </span>
          <span className="font-medium">{formatDuration(s.duration_ms)}</span>
          {s.fetched_at && (
            <span className="text-muted-foreground"> · stored {formatWhen(s.fetched_at)}</span>
          )}
        </div>
      )}
      {s.participants.length > 0 && <Participants participants={s.participants} />}
      {s.my_characters.length > 0 && <MyCharacters characters={s.my_characters} />}
    </div>
  );
}
