import { useNavigate } from "react-router-dom";
import { RaidTab } from "../components/raids/RaidTab";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import type { Raid } from "../types";

interface Props {
  raids: Raid[];
  status: "loading" | "ready" | "error";
  /** The report code from the address; undefined selects the newest raid. */
  reportCode: string | undefined;
  streaming: boolean;
  /** The chat shell's current error (a failed "Analyze this raid" lands here). */
  error: string | null;
  onAnalyze: (reportCode: string) => void;
}

// Most recent first: the raid's own start, else when it was first seen.
function raidTime(r: Raid): number {
  return Date.parse(r.report_started_at ?? r.first_seen_at ?? r.last_asked_at) || 0;
}

export default function RaidsPage({ raids, status, reportCode, streaming, error, onAnalyze }: Props) {
  const navigate = useNavigate();
  const sorted = [...raids].sort((a, b) => raidTime(b) - raidTime(a));

  let body;
  if (status === "loading") {
    body = <p className="text-sm text-muted-foreground">Loading raids…</p>;
  } else if (status === "error" && sorted.length === 0) {
    body = (
      <Alert variant="destructive">
        <AlertDescription>Could not load your raids.</AlertDescription>
      </Alert>
    );
  } else if (sorted.length === 0) {
    body = <p className="text-sm text-muted-foreground">No raids tracked yet</p>;
  } else {
    // A code that is not in the list never reaches the summary call (hostile or stale link).
    const selected = reportCode ?? sorted[0].report_code;
    const known = sorted.some((r) => r.report_code === selected);
    body = (
      <Tabs
        value={known ? selected : ""}
        onValueChange={(code) => navigate(`/app/raids/${encodeURIComponent(code)}`)}
        className="min-w-0"
      >
        <div className="overflow-x-auto pb-2" data-testid="raid-tabs-scroll">
          <TabsList variant="line" aria-label="Tracked raids" className="w-max">
            {sorted.map((r) => (
              <TabsTrigger key={r.report_code} value={r.report_code} className="max-w-56 flex-none">
                <span className="truncate" title={r.label}>
                  {r.label}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        {!known && (
          <Alert>
            <AlertDescription>Raid not found: it is not one of your tracked raids.</AlertDescription>
          </Alert>
        )}
        {sorted.map((r) => (
          <TabsContent key={r.report_code} value={r.report_code}>
            <RaidTab raid={r} analyzeDisabled={streaming} onAnalyze={onAnalyze} />
          </TabsContent>
        ))}
      </Tabs>
    );
  }

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
      <h1 className="text-xl font-semibold">Raids</h1>
      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {body}
    </div>
  );
}
