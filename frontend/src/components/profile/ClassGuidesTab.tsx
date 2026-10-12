import { useCallback, useEffect, useMemo, useState } from "react";
import { LuBookOpen, LuExternalLink, LuRefreshCw, LuSearch, LuSearchX } from "react-icons/lu";
import { ApiError, generateGuide, getGuide, listGuides } from "../../api/restClient";
import { classColor, classDisplayName } from "../../lib/classColors";
import type { Guide, GuideFreshness, GuideListItem } from "../../types";
import { StatusAlert } from "../StatusAlert";
import { GUIDE_LABEL_LIBRARY, GUIDE_TONE, StatusBadge } from "../StatusBadge";
import { StreamMarkdown } from "../StreamMarkdown";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "../ui/empty";
import { InputGroup, InputGroupAddon, InputGroupInput } from "../ui/input-group";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemTitle } from "../ui/item";
import { Skeleton } from "../ui/skeleton";
import { Spinner } from "../ui/spinner";
import { ToggleGroup, ToggleGroupItem } from "../ui/toggle-group";

// Class Guides tab (feature 008 / US2): the full class/spec roster merged with the shared,
// global library's status. Any signed-in user can request, retry, or refresh a guide, and
// view its content. Generation is best-effort/non-blocking and rate-limited (429 → slow down).
// Profile revamp: search + status filter, one class-coloured card per class.

const POLL_MS = 4000;

function keyOf(it: { class_name: string; spec: string }): string {
  return `${it.class_name}/${it.spec}`;
}

// Feature 009 / US5: patch + generated date for a ready guide, and a visible
// "May be out of date" badge when the guide's patch is older than the live one or unknown.
function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString();
}

type ProvenanceSource = { game_patch: string | null; generated_at: string | null; freshness: GuideFreshness | null };

function isStale(it: ProvenanceSource): boolean {
  return it.freshness === "possibly_stale" || it.freshness === "unknown";
}

function provenanceText(it: ProvenanceSource): string {
  const date = fmtDate(it.generated_at);
  return `${it.game_patch ? `Patch ${it.game_patch}` : "Patch unknown"}${date ? ` · ${date}` : ""}`;
}

function StaleBadge({ it }: { it: ProvenanceSource }) {
  if (!isStale(it)) return null;
  return (
    <StatusBadge
      tone="warn"
      title={
        it.freshness === "unknown"
          ? "This guide does not state a patch; regenerate to refresh it."
          : "This guide targets an older patch; regenerate to refresh it."
      }
    >
      May be out of date
    </StatusBadge>
  );
}

type Filter = "all" | "ready" | "none" | "attention";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "ready", label: "Ready" },
  { value: "none", label: "Not generated" },
  { value: "attention", label: "Needs attention" },
];

function matchesFilter(it: GuideListItem, f: Filter): boolean {
  switch (f) {
    case "all":
      return true;
    case "ready":
      return it.status === "ready";
    case "none":
      return it.status === "none";
    case "attention":
      return it.status === "failed" || (it.status === "ready" && isStale(it));
  }
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
  const [viewing, setViewing] = useState<Guide | null>(null);
  const [viewBusyKey, setViewBusyKey] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

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

  // Poll while any guide is still generating, but only while this tab is visible.
  const anyPending = (items ?? []).some((i) => i.status === "pending");
  useEffect(() => {
    if (!active || !anyPending) return;
    const t = setTimeout(() => void refresh(), POLL_MS);
    return () => clearTimeout(t);
  }, [active, anyPending, refresh]);

  const onGenerate = useCallback(
    async (it: GuideListItem, force: boolean) => {
      const key = keyOf(it);
      setBusyKey(key);
      setNotice(null);
      setErr(null);
      try {
        await generateGuide(it.class_name, it.spec, force);
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
    [refresh],
  );

  const onView = useCallback(async (it: GuideListItem) => {
    setViewBusyKey(keyOf(it));
    setErr(null);
    try {
      setViewing(await getGuide(it.class_name, it.spec));
    } catch {
      setErr("Could not open that guide.");
    } finally {
      setViewBusyKey(null);
    }
  }, []);

  const total = items?.length ?? 0;
  const readyCount = (items ?? []).filter((i) => i.status === "ready").length;

  // Preserve the server ordering (class display, then spec) while grouping by class,
  // after applying the search text and status filter.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const byClass = new Map<string, GuideListItem[]>();
    for (const it of items ?? []) {
      if (!matchesFilter(it, filter)) continue;
      if (q && !`${it.class_display} ${it.spec}`.toLowerCase().includes(q)) continue;
      const list = byClass.get(it.class_display) ?? [];
      list.push(it);
      byClass.set(it.class_display, list);
    }
    return [...byClass.entries()];
  }, [items, query, filter]);

  // Ready-count per class over the unfiltered roster, for the card descriptions.
  const classTotals = useMemo(() => {
    const m = new Map<string, { ready: number; total: number }>();
    for (const it of items ?? []) {
      const t = m.get(it.class_display) ?? { ready: 0, total: 0 };
      t.total += 1;
      if (it.status === "ready") t.ready += 1;
      m.set(it.class_display, t);
    }
    return m;
  }, [items]);

  const viewingColor = viewing ? classColor(viewing.class_name) : null;

  return (
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

      <div className="flex flex-col gap-3 md:flex-row md:items-center">
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
          <span className="text-sm text-muted-foreground md:ml-auto">
            <span className="font-semibold text-foreground">{readyCount}</span> of {total} guides ready
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
            <EmptyDescription>Try a different search or status filter.</EmptyDescription>
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
                      {counts.ready} of {counts.total} ready
                    </CardDescription>
                  )}
                </CardHeader>
                <CardContent className="px-2">
                  <ItemGroup className="gap-1">
                    {specs.map((it) => {
                      const key = keyOf(it);
                      const busy = busyKey === key;
                      return (
                        <Item key={key} role="listitem" size="sm" className="px-2 py-2 hover:bg-accent/40">
                          <ItemContent className="min-w-0">
                            <ItemTitle className="flex-wrap">
                              {it.spec}
                              {it.status !== "ready" && it.status !== "none" && (
                                <StatusBadge tone={GUIDE_TONE[it.status]}>{GUIDE_LABEL_LIBRARY[it.status]}</StatusBadge>
                              )}
                              {it.status === "ready" && <StaleBadge it={it} />}
                            </ItemTitle>
                            <ItemDescription className="text-xs">
                              {it.status === "ready"
                                ? provenanceText(it)
                                : it.status === "none"
                                  ? "Not generated yet"
                                  : it.status === "pending"
                                    ? "Researching the latest sources…"
                                    : "Generation failed — try again."}
                            </ItemDescription>
                          </ItemContent>
                          <ItemActions>
                            {it.status === "ready" && (
                              <>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  disabled={viewBusyKey !== null}
                                  onClick={() => void onView(it)}
                                >
                                  {viewBusyKey === key ? <Spinner /> : <LuBookOpen />}
                                  View
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="size-8 text-muted-foreground"
                                  disabled={busy}
                                  onClick={() => void onGenerate(it, true)}
                                  aria-label={`Refresh ${it.spec} ${classDisplayName(it.class_name)} guide`}
                                  title="Regenerate this guide"
                                >
                                  {busy ? <Spinner /> : <LuRefreshCw />}
                                </Button>
                              </>
                            )}
                            {it.status === "failed" && (
                              <Button size="sm" disabled={busy} onClick={() => void onGenerate(it, true)}>
                                {busy && <Spinner />}
                                Retry
                              </Button>
                            )}
                            {it.status === "none" && (
                              <Button size="sm" disabled={busy} onClick={() => void onGenerate(it, false)}>
                                {busy && <Spinner />}
                                Generate
                              </Button>
                            )}
                            {it.status === "pending" && <Spinner className="text-muted-foreground" />}
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

      <Dialog
        open={viewing !== null}
        onOpenChange={(open) => {
          if (!open) setViewing(null);
        }}
      >
        {/* Radix supplies focus trap, Escape, backdrop close, scroll lock and focus return
            (FR-005). `viewing` is independent of `items`, so a background poll never
            disturbs an open guide. */}
        <DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-3xl">
          {viewing && (
            <>
              <DialogHeader className="border-b border-border pb-4">
                <DialogTitle className="font-display text-lg tracking-wide">
                  <span style={viewingColor ? { color: viewingColor } : undefined}>
                    {viewing.spec} {classDisplayName(viewing.class_name)}
                  </span>
                </DialogTitle>
                <DialogDescription className="flex flex-wrap items-center gap-2">
                  {viewing.status === "ready" ? provenanceText(viewing) : "Class guide"}
                  {viewing.status === "ready" && <StaleBadge it={viewing} />}
                </DialogDescription>
              </DialogHeader>
              <div className="text-sm leading-relaxed">
                {viewing.guide_markdown ? (
                  <StreamMarkdown content={viewing.guide_markdown} />
                ) : (
                  <p className="text-muted-foreground italic">No content yet.</p>
                )}
              </div>
              {viewing.sources && viewing.sources.length > 0 && (
                <section className="flex flex-col gap-2 border-t border-border pt-4">
                  <h4 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Sources</h4>
                  <ItemGroup className="gap-1">
                    {viewing.sources.map((s) => (
                      <Item key={s.uri} role="listitem" size="sm" asChild className="px-2 py-1.5">
                        <a href={s.uri} target="_blank" rel="noreferrer">
                          <ItemContent className="min-w-0">
                            <ItemTitle className="w-full">
                              <span className="truncate">{s.title || s.uri}</span>
                            </ItemTitle>
                          </ItemContent>
                          <ItemActions>
                            <LuExternalLink className="size-4 text-muted-foreground" />
                          </ItemActions>
                        </a>
                      </Item>
                    ))}
                  </ItemGroup>
                </section>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
