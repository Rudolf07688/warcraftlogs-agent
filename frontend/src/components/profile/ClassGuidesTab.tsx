import { useCallback, useEffect, useMemo, useState } from "react";
import { LuBookOpen, LuRefreshCw, LuSearch, LuSearchX } from "react-icons/lu";
import { ApiError, generateGuide, listGuides } from "../../api/restClient";
import { classColor, classDisplayName } from "../../lib/classColors";
import { cn } from "../../lib/utils";
import type { ContentType, GuideListItem, GuideSummary } from "../../types";
import { getGuideContentType, setGuideContentType } from "../../uiPrefs";
import { StatusAlert } from "../StatusAlert";
import { GUIDE_LABEL_LIBRARY, GUIDE_TONE, StatusBadge } from "../StatusBadge";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "../ui/empty";
import { InputGroup, InputGroupAddon, InputGroupInput } from "../ui/input-group";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemTitle } from "../ui/item";
import { Skeleton } from "../ui/skeleton";
import { Spinner } from "../ui/spinner";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { CONTENT_LABEL, GuideViewerDialog, type GuideTarget, StaleBadge, provenanceText } from "./GuideViewerDialog";
import { ReportGuideDialog } from "./ReportGuideDialog";

// Class Guides tab (features 008, 015): the full class/spec roster merged with the shared,
// global library. Each spec has two independent guides — Raid and Mythic+. A toolbar switch
// picks which one the rows show; a small dot beside each spec shows the other type's state.
// Any signed-in user can request, retry, refresh or view a guide. Generation is
// best-effort/non-blocking and rate-limited (429 → slow down).

const POLL_MS = 4000;

const OTHER: Record<ContentType, ContentType> = { raid: "mplus", mplus: "raid" };

function keyOf(it: { class_name: string; spec: string }, ct: ContentType): string {
  return `${it.class_name}/${it.spec}/${ct}`;
}

function isStale(s: GuideSummary): boolean {
  return s.has_published && (s.freshness === "possibly_stale" || s.freshness === "unknown");
}

type Filter = "all" | "ready" | "none" | "attention";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "ready", label: "Ready" },
  { value: "none", label: "Not generated" },
  { value: "attention", label: "Needs attention" },
];

function matchesFilter(s: GuideSummary, f: Filter): boolean {
  switch (f) {
    case "all":
      return true;
    case "ready":
      return s.has_published;
    case "none":
      return s.status === "none";
    case "attention":
      return s.status === "failed" || s.status === "needs_review" || isStale(s);
  }
}

// The other content type's state, for the dot's colour and its accessible name.
function otherState(s: GuideSummary): { label: string; className: string } {
  if (s.has_published) return { label: "ready", className: "bg-success" };
  switch (s.status) {
    case "pending":
      return { label: "generating", className: "animate-pulse bg-muted-foreground" };
    case "needs_review":
      return { label: "unverified draft", className: "bg-warning" };
    case "failed":
      return { label: "failed", className: "bg-warning" };
    default:
      return { label: "not generated", className: "border border-muted-foreground bg-transparent" };
  }
}

function OtherTypeDot({ it, contentType, onSwitch }: { it: GuideListItem; contentType: ContentType; onSwitch: () => void }) {
  const other = OTHER[contentType];
  const state = otherState(it[other]);
  const label = `${CONTENT_LABEL[other]} guide: ${state.label}`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`${label} — show ${CONTENT_LABEL[other]} guides`}
          onClick={onSwitch}
          className="inline-flex size-5 items-center justify-center rounded-full focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {/* The only hand-built piece: an 8 px status dot (no registry item is a bare dot). */}
          <span aria-hidden className={cn("block size-2 rounded-full", state.className)} />
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function rowDescription(s: GuideSummary): string {
  if (s.has_published) return provenanceText(s);
  switch (s.status) {
    case "none":
      return "Not generated yet";
    case "pending":
      return "Researching the latest sources…";
    case "needs_review":
      return "Could not be fully verified — view the draft";
    default:
      return "Generation failed — try again.";
  }
}

// Badges beside the spec name for the selected type (guides-api.md status table).
function RowBadges({ s }: { s: GuideSummary }) {
  if (!s.has_published) {
    return s.status === "none" ? null : (
      <StatusBadge tone={GUIDE_TONE[s.status]}>{GUIDE_LABEL_LIBRARY[s.status]}</StatusBadge>
    );
  }
  return (
    <>
      <StaleBadge it={s} />
      {s.refreshing && <StatusBadge tone="pending">Refreshing</StatusBadge>}
      {s.status === "needs_review" && <StatusBadge tone="warn">Update held for review</StatusBadge>}
      {s.status === "failed" && <StatusBadge tone="warn">Update failed</StatusBadge>}
    </>
  );
}

function GridSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true" aria-label="Loading class guides">
      {Array.from({ length: 6 }, (_, i) => (
        <Card key={i} className="gap-4">
          <CardHeader>
            <Skeleton className="h-5 w-32" />
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function ClassGuidesTab({ active }: { active: boolean }) {
  const [items, setItems] = useState<GuideListItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [viewing, setViewing] = useState<GuideTarget | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [contentType, setContentTypeState] = useState<ContentType>(getGuideContentType);

  const setContentType = useCallback((ct: ContentType) => {
    setContentTypeState(ct);
    setGuideContentType(ct);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setItems((await listGuides()).guides);
      setErr(null);
    } catch {
      setErr("Could not load the class guides.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll while either content type of any spec is generating, only while the tab is visible.
  const anyPending = (items ?? []).some((i) => i.raid.status === "pending" || i.mplus.status === "pending");
  useEffect(() => {
    if (!active || !anyPending) return;
    const t = setTimeout(() => void refresh(), POLL_MS);
    return () => clearTimeout(t);
  }, [active, anyPending, refresh]);

  const onGenerate = useCallback(
    async (it: GuideListItem, force: boolean) => {
      const key = keyOf(it, contentType);
      setBusyKey(key);
      setNotice(null);
      setErr(null);
      try {
        await generateGuide(it.class_name, it.spec, contentType, force);
        await refresh();
      } catch (e) {
        if (e instanceof ApiError && e.status === 429) {
          setNotice("You're requesting guides too quickly — slow down a moment, then try again.");
        } else {
          setErr("Could not start that guide. Please try again.");
        }
      } finally {
        setBusyKey(null);
      }
    },
    [contentType, refresh],
  );

  const total = items?.length ?? 0;
  const readyCount = (items ?? []).filter((i) => i[contentType].has_published).length;

  // Preserve the server ordering (class display, then spec) while grouping by class,
  // after applying the search text and the status filter for the selected content type.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const byClass = new Map<string, GuideListItem[]>();
    for (const it of items ?? []) {
      if (!matchesFilter(it[contentType], filter)) continue;
      if (q && !`${it.class_display} ${it.spec_display}`.toLowerCase().includes(q)) continue;
      const list = byClass.get(it.class_display) ?? [];
      list.push(it);
      byClass.set(it.class_display, list);
    }
    return [...byClass.entries()];
  }, [items, query, filter, contentType]);

  // Ready-count per class over the unfiltered roster, for the card descriptions.
  const classTotals = useMemo(() => {
    const m = new Map<string, { ready: number; total: number }>();
    for (const it of items ?? []) {
      const t = m.get(it.class_display) ?? { ready: 0, total: 0 };
      t.total += 1;
      if (it[contentType].has_published) t.ready += 1;
      m.set(it.class_display, t);
    }
    return m;
  }, [items, contentType]);

  const label = CONTENT_LABEL[contentType];

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-col gap-4">
        {err && (
          <StatusAlert tone="error" onDismiss={() => setErr(null)}>
            {err}
          </StatusAlert>
        )}
        {notice && (
          <StatusAlert tone="notice" onDismiss={() => setNotice(null)}>
            {notice}
          </StatusAlert>
        )}

        <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
          <InputGroup className="md:max-w-xs">
            <InputGroupInput
              aria-label="Search classes and specs"
              placeholder="Search classes and specs…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <InputGroupAddon>
              <LuSearch />
            </InputGroupAddon>
          </InputGroup>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            aria-label="Content type"
            value={contentType}
            onValueChange={(v) => {
              if (v) setContentType(v as ContentType);
            }}
          >
            {(["raid", "mplus"] as const).map((ct) => (
              <ToggleGroupItem
                key={ct}
                value={ct}
                className="dark:data-[state=on]:bg-primary/15 dark:data-[state=on]:text-glow"
              >
                {CONTENT_LABEL[ct]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            aria-label="Filter by status"
            value={filter}
            onValueChange={(v) => {
              if (v) setFilter(v as Filter);
            }}
            className="flex-wrap"
          >
            {FILTERS.map((f) => (
              <ToggleGroupItem
                key={f.value}
                value={f.value}
                className="dark:data-[state=on]:bg-primary/15 dark:data-[state=on]:text-glow"
              >
                {f.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {items && (
            <span className="text-sm text-muted-foreground md:ml-auto" aria-live="polite">
              <span className="font-semibold text-foreground">{readyCount}</span> of {total} {label} guides ready
            </span>
          )}
        </div>

        {items === null && !err ? (
          <GridSkeleton />
        ) : groups.length === 0 ? (
          <Empty className="border border-dashed">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <LuSearchX />
              </EmptyMedia>
              <EmptyTitle>No guides match</EmptyTitle>
              <EmptyDescription>Try a different search, content type or status filter.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <div className="grid items-start gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {groups.map(([display, specs]) => {
              const color = classColor(specs[0]?.class_name);
              const counts = classTotals.get(display);
              return (
                <Card
                  key={display}
                  className="gap-3 overflow-hidden border-t-2 pt-4 pb-2"
                  style={color ? { borderTopColor: color } : undefined}
                >
                  <CardHeader className="px-4">
                    <CardTitle
                      className="font-display text-base tracking-wide"
                      style={color ? { color } : undefined}
                    >
                      <h3>{display}</h3>
                    </CardTitle>
                    {counts && (
                      <CardDescription>
                        {counts.ready} of {counts.total} {label} ready
                      </CardDescription>
                    )}
                  </CardHeader>
                  <CardContent className="px-2">
                    <ItemGroup className="gap-1">
                      {specs.map((it) => {
                        const s = it[contentType];
                        const key = keyOf(it, contentType);
                        const busy = busyKey === key;
                        const name = `${it.spec_display} ${classDisplayName(it.class_name)} ${label} guide`;
                        const view = () =>
                          setViewing({
                            class_name: it.class_name,
                            spec: it.spec,
                            spec_display: it.spec_display,
                            contentType,
                          });
                        return (
                          <Item key={key} role="listitem" size="sm" className="px-2 py-2 hover:bg-accent/40">
                            <ItemContent className="min-w-0">
                              <ItemTitle className="flex-wrap">
                                {it.spec_display}
                                <OtherTypeDot
                                  it={it}
                                  contentType={contentType}
                                  onSwitch={() => setContentType(OTHER[contentType])}
                                />
                                <RowBadges s={s} />
                              </ItemTitle>
                              <ItemDescription className="text-xs">{rowDescription(s)}</ItemDescription>
                            </ItemContent>
                            <ItemActions>
                              {(s.has_published || s.status === "needs_review") && (
                                <Button size="sm" variant="secondary" onClick={view} aria-label={`View ${name}`}>
                                  <LuBookOpen />
                                  View
                                </Button>
                              )}
                              {s.has_published && (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="size-8 text-muted-foreground"
                                  disabled={busy || s.refreshing}
                                  onClick={() => void onGenerate(it, true)}
                                  aria-label={`Refresh ${name}`}
                                  title="Regenerate this guide"
                                >
                                  {busy || s.refreshing ? <Spinner /> : <LuRefreshCw />}
                                </Button>
                              )}
                              {!s.has_published && (s.status === "failed" || s.status === "needs_review") && (
                                <Button size="sm" disabled={busy} onClick={() => void onGenerate(it, true)}>
                                  {busy && <Spinner />}
                                  Retry
                                </Button>
                              )}
                              {s.status === "none" && (
                                <Button
                                  size="sm"
                                  disabled={busy}
                                  onClick={() => void onGenerate(it, false)}
                                  aria-label={`Generate ${name}`}
                                >
                                  {busy && <Spinner />}
                                  Generate
                                </Button>
                              )}
                              {s.status === "pending" && !s.has_published && (
                                <Spinner className="text-muted-foreground" />
                              )}
                            </ItemActions>
                          </Item>
                        );
                      })}
                    </ItemGroup>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        <GuideViewerDialog
          target={viewing}
          onClose={() => setViewing(null)}
          onChanged={() => void refresh()}
          renderFooter={(g) => (
            <ReportGuideDialog
              guide={g}
              label={`${viewing?.spec_display ?? g.spec} ${classDisplayName(g.class_name)} — ${CONTENT_LABEL[g.content_type]}`}
            />
          )}
        />
      </div>
    </TooltipProvider>
  );
}
