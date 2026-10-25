import { memo, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { LuCalendarClock, LuRefreshCw, LuSkull, LuSwords, LuTimer, LuUsers } from "react-icons/lu";
import { getRecentRaids, refreshRecentRaids } from "../api/restClient";
import type { RecentMplusRun, RecentRaid, RecentRaidsResponse } from "../types";
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "./ui/empty";
import { Item, ItemContent, ItemDescription, ItemTitle } from "./ui/item";
import { Skeleton } from "./ui/skeleton";
import { Spinner } from "./ui/spinner";

// Feature 013 (research R6): poll while a background refresh runs, every 3 s, paused while
// the tab is hidden, giving up after 3 minutes.
const POLL_MS = 3000;
const POLL_GIVE_UP_MS = 180_000;

const DIFFICULTY: Record<number, { label: string; variant: "secondary" | "default" | "warning" }> =
  {
    1: { label: "LFR", variant: "secondary" },
    3: { label: "Normal", variant: "secondary" },
    4: { label: "Heroic", variant: "default" },
    5: { label: "Mythic", variant: "warning" },
  };

// Short server codes → friendly text; a raw code is never shown.
const ERROR_TEXT: Record<string, string> = {
  rate_limited: "Warcraft Logs is busy, try again shortly.",
  wcl_unavailable: "Warcraft Logs couldn't be reached.",
  timeout: "Warcraft Logs took too long to answer.",
};
const errorText = (code: string | null) => (code && ERROR_TEXT[code]) || "Something went wrong.";

function whenText(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function agoText(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "updated just now";
  if (minutes < 60) return `updated ${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `updated ${hours} h ago` : `updated ${Math.round(hours / 24)} d ago`;
}

interface Props {
  onInvestigate: (reportCode: string) => void;
  onInvestigateMplus: (reportCode: string, fightId: number) => void;
  disabled: boolean;
}

const RaidCard = memo(function RaidCard({
  raid,
  disabled,
  onInvestigate,
}: {
  raid: RecentRaid;
  disabled: boolean;
  onInvestigate: (reportCode: string) => void;
}) {
  const difficulty = raid.difficulty != null ? DIFFICULTY[raid.difficulty] : undefined;
  const pulled = raid.bosses_pulled ?? 0;
  return (
    <Item asChild variant="outline" className="raid-card">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onInvestigate(raid.report_code)}
        title="Investigate this raid in a new chat"
      >
        <ItemContent className="raid-card-content">
          <ItemTitle className="raid-card-title">
            <span className="raid-card-zone">{raid.zone_name || raid.title}</span>
            {difficulty && <Badge variant={difficulty.variant}>{difficulty.label}</Badge>}
          </ItemTitle>
          <ItemDescription className="raid-card-meta">
            <span>
              <LuCalendarClock aria-hidden /> {whenText(raid.started_at)}
            </span>
            <span>
              <LuUsers aria-hidden /> {raid.characters.map((c) => c.name).join(", ")}
            </span>
            {pulled > 0 && (
              <span>
                <LuSkull aria-hidden /> {raid.bosses_killed ?? 0}/{pulled} bosses
              </span>
            )}
          </ItemDescription>
        </ItemContent>
      </button>
    </Item>
  );
});

const MplusCard = memo(function MplusCard({
  run,
  disabled,
  onInvestigate,
}: {
  run: RecentMplusRun;
  disabled: boolean;
  onInvestigate: (reportCode: string, fightId: number) => void;
}) {
  return (
    <Item asChild variant="outline" className="raid-card">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onInvestigate(run.report_code, run.fight_id)}
        title="Investigate this Mythic+ run in a new chat"
      >
        <ItemContent className="raid-card-content">
          <ItemTitle className="raid-card-title">
            <span className="raid-card-zone">
              {run.dungeon} +{run.key_level}
            </span>
            <Badge variant={run.timed ? "default" : "secondary"}>
              {run.timed ? "Timed" : "Depleted"}
            </Badge>
          </ItemTitle>
          <ItemDescription className="raid-card-meta">
            <span>
              <LuCalendarClock aria-hidden /> {whenText(run.started_at)}
            </span>
            <span>
              <LuUsers aria-hidden /> {run.characters.map((c) => c.name).join(", ")}
            </span>
          </ItemDescription>
        </ItemContent>
      </button>
    </Item>
  );
});

function MplusSection({
  runs,
  disabled,
  onInvestigate,
}: {
  runs: RecentMplusRun[];
  disabled: boolean;
  onInvestigate: (reportCode: string, fightId: number) => void;
}) {
  if (runs.length === 0) return null;
  return (
    <>
      <header className="welcome-panel-header">
        <h2 className="welcome-panel-title">
          <LuTimer aria-hidden /> Your recent Mythic+ runs
        </h2>
      </header>
      <div className="raid-grid">
        {runs.map((run) => (
          <MplusCard
            key={`${run.report_code}-${run.fight_id}`}
            run={run}
            disabled={disabled}
            onInvestigate={onInvestigate}
          />
        ))}
      </div>
    </>
  );
}

function WelcomePanelImpl({ onInvestigate, onInvestigateMplus, disabled }: Props) {
  const [data, setData] = useState<RecentRaidsResponse | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const alive = useRef(true);
  const pollStart = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await getRecentRaids();
      if (!alive.current) return;
      setData(next);
      setLoadFailed(false);
    } catch {
      if (alive.current) setLoadFailed(true);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
    };
  }, [load]);

  // Poll while a refresh is running (research R6).
  useEffect(() => {
    if (data?.refresh.status !== "running") {
      pollStart.current = null;
      return;
    }
    pollStart.current ??= Date.now();
    if (Date.now() - pollStart.current > POLL_GIVE_UP_MS) return;
    const timer = window.setTimeout(() => {
      if (document.visibilityState !== "hidden") void load();
    }, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        window.clearTimeout(timer);
        void load();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [data, load]);

  const retry = useCallback(async () => {
    setRetrying(true);
    pollStart.current = null;
    try {
      await refreshRecentRaids();
    } catch {
      /* the next load shows the current state */
    }
    await load();
    if (alive.current) setRetrying(false);
  }, [load]);

  if (!data) {
    if (loadFailed) {
      return (
        <section className="welcome-panel" aria-label="Your recent raids">
          <Alert variant="destructive">
            <AlertTitle>Couldn't load your raids</AlertTitle>
            <AlertDescription>
              <Button variant="secondary" size="sm" onClick={() => void load()}>
                <LuRefreshCw aria-hidden /> Retry
              </Button>
            </AlertDescription>
          </Alert>
        </section>
      );
    }
    return <SkeletonGrid />;
  }

  if (!data.has_characters) {
    return (
      <section className="welcome-panel" aria-label="Your recent raids">
        <Empty className="welcome-empty">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <LuSwords />
            </EmptyMedia>
            <EmptyTitle>Add your characters to see your recent raids</EmptyTitle>
            <EmptyDescription>
              Your last raids show up here, ready to investigate in one click.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild size="sm">
              <Link to="/profile">Add characters</Link>
            </Button>
          </EmptyContent>
        </Empty>
      </section>
    );
  }

  const { raids, refresh } = data;
  const mplusRuns = data.mplus_runs ?? [];
  const running = refresh.status === "running";
  const failed = refresh.status === "failed";

  if (raids.length === 0) {
    const waiting = running || refresh.status === "idle";
    // Stored runs show whatever the raid state (FR-010); the skeleton is only for nothing.
    if (waiting && mplusRuns.length === 0) return <SkeletonGrid />;
    return (
      <section className="welcome-panel" aria-label="Your recent raids">
        {waiting ? (
          <header className="welcome-panel-header">
            <h2 className="welcome-panel-title">Your recent raids</h2>
            <span className="welcome-panel-status">
              <Spinner /> checking for new raids…
            </span>
          </header>
        ) : failed ? (
          <Alert variant="destructive">
            <AlertTitle>Couldn't load your raids</AlertTitle>
            <AlertDescription>
              <span>{errorText(refresh.last_error)}</span>
              <Button variant="secondary" size="sm" disabled={retrying} onClick={() => void retry()}>
                <LuRefreshCw aria-hidden /> Retry
              </Button>
            </AlertDescription>
          </Alert>
        ) : (
          <Empty className="welcome-empty">
            <EmptyHeader>
              <EmptyTitle>No recent raids found for your characters</EmptyTitle>
              <EmptyDescription>
                Raids appear here once they're logged publicly on Warcraft Logs.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
        <MplusSection runs={mplusRuns} disabled={disabled} onInvestigate={onInvestigateMplus} />
      </section>
    );
  }

  return (
    <section className="welcome-panel" aria-label="Your recent raids">
      <header className="welcome-panel-header">
        <h2 className="welcome-panel-title">Your recent raids</h2>
        <span className="welcome-panel-status">
          {running ? (
            <>
              <Spinner /> checking for new raids…
            </>
          ) : failed ? (
            <>
              <span title={errorText(refresh.last_error)}>Couldn't refresh</span>
              <Button
                variant="ghost"
                size="sm"
                disabled={retrying}
                onClick={() => void retry()}
              >
                Retry
              </Button>
            </>
          ) : (
            refresh.last_success_at && agoText(refresh.last_success_at)
          )}
        </span>
      </header>
      <div className="raid-grid">
        {raids.map((raid) => (
          <RaidCard
            key={raid.report_code}
            raid={raid}
            disabled={disabled}
            onInvestigate={onInvestigate}
          />
        ))}
      </div>
      <MplusSection runs={mplusRuns} disabled={disabled} onInvestigate={onInvestigateMplus} />
    </section>
  );
}

function SkeletonGrid() {
  return (
    <section className="welcome-panel" aria-label="Your recent raids" aria-busy="true">
      <header className="welcome-panel-header">
        <h2 className="welcome-panel-title">Your recent raids</h2>
      </header>
      <div className="raid-grid">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="raid-card-skeleton" />
        ))}
      </div>
    </section>
  );
}

// Memoized: App re-renders on stream events, the panel only when its props change.
export const WelcomePanel = memo(WelcomePanelImpl);
