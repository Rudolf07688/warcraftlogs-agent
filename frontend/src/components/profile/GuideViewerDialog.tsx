import { type ReactNode, useCallback, useEffect, useState } from "react";
import { LuExternalLink } from "react-icons/lu";
import { ApiError, generateGuide, getGuide } from "../../api/restClient";
import { classColor, classDisplayName } from "../../lib/classColors";
import type { ContentType, Guide, GuideFreshness } from "../../types";
import { StatusAlert } from "../StatusAlert";
import { StatusBadge } from "../StatusBadge";
import { StreamMarkdown } from "../StreamMarkdown";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../ui/dialog";
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemTitle } from "../ui/item";
import { Spinner } from "../ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";

// Feature 015: the guide viewer, extracted from the Class Guides tab. One dialog per spec
// with Raid | Mythic+ tabs; it opens on the content type the user clicked and fetches each
// tab once. Shows the published guide, an unverified draft (with a warning), or an empty
// state with an inline Generate button (contracts/ui-guides.md §Viewer).

export const CONTENT_LABEL: Record<ContentType, string> = { raid: "Raid", mplus: "Mythic+" };

const TIER_LABEL: Record<number, string> = { 1: "Official", 2: "Warcraft Logs", 3: "Guide site" };

export interface GuideTarget {
  class_name: string;
  spec: string;
  spec_display: string;
  contentType: ContentType;
}

export function fmtDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString();
}

type ProvenanceSource = {
  content_type: ContentType;
  game_patch: string | null;
  season: string | null;
  generated_at: string | null;
  freshness: GuideFreshness | null;
  stale_reason: string | null;
};

// "Patch 12.1 · 18 Oct" for Raid, "Mythic+ Season 2 · 18 Oct" for Mythic+.
export function provenanceText(it: ProvenanceSource): string {
  const date = fmtDate(it.generated_at);
  const where =
    it.content_type === "mplus" && it.season
      ? it.season
      : it.game_patch
        ? `Patch ${it.game_patch}`
        : "Patch unknown";
  return `${where}${date ? ` · ${date}` : ""}`;
}

const STALE_WHY: Record<string, string> = {
  patch_changed: "A new patch is live since this guide was written.",
  season_changed: "A new Mythic+ season started since this guide was written.",
  hotfix: "Blizzard hotfixed this class since this guide was written.",
  legacy: "This guide predates the verified-guide pipeline.",
};

export function StaleBadge({ it }: { it: ProvenanceSource }) {
  if (it.freshness !== "possibly_stale" && it.freshness !== "unknown") return null;
  const why =
    (it.stale_reason && STALE_WHY[it.stale_reason]) ||
    (it.freshness === "unknown"
      ? "This guide does not state a patch."
      : "This guide targets an older patch or season.");
  return (
    <StatusBadge tone="warn" title={`${why} It refreshes automatically when in use, or regenerate it now.`}>
      May be out of date
    </StatusBadge>
  );
}

function GuideSources({ guide }: { guide: Guide }) {
  if (guide.sources.length === 0) return null;
  return (
    <section className="flex flex-col gap-2 border-t border-border pt-4">
      <h4 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Sources</h4>
      <ItemGroup className="gap-1">
        {guide.sources.map((s) => {
          const meta = [s.tier ? TIER_LABEL[s.tier] : null, fmtDate(s.date)].filter(Boolean).join(" · ");
          return (
            <Item key={s.uri} role="listitem" size="sm" asChild className="px-2 py-1.5">
              <a href={s.uri} target="_blank" rel="noreferrer">
                <ItemContent className="min-w-0">
                  <ItemTitle className="w-full">
                    <span className="truncate">{s.title || s.uri}</span>
                  </ItemTitle>
                  {meta && <ItemDescription className="text-xs">{meta}</ItemDescription>}
                </ItemContent>
                <ItemActions>
                  <LuExternalLink className="size-4 text-muted-foreground" />
                </ItemActions>
              </a>
            </Item>
          );
        })}
      </ItemGroup>
    </section>
  );
}

function GuideBody({
  guide,
  target,
  busy,
  onGenerate,
  footer,
}: {
  guide: Guide;
  target: GuideTarget;
  busy: boolean;
  onGenerate: () => void;
  footer?: ReactNode;
}) {
  const label = CONTENT_LABEL[guide.content_type];
  if (guide.display === "none") {
    if (guide.status === "pending") {
      return (
        <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Spinner /> Researching the latest sources…
        </p>
      );
    }
    return (
      <div className="flex flex-col items-start gap-3 py-6">
        <p className="text-sm text-muted-foreground">
          {guide.status === "failed"
            ? `The last ${label} guide run failed. Try again.`
            : `No ${label} guide for ${target.spec_display} yet.`}
        </p>
        <Button size="sm" disabled={busy} onClick={onGenerate}>
          {busy && <Spinner />}
          {guide.status === "failed" ? "Retry" : "Generate"}
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      {guide.display === "draft" && (
        <StatusAlert tone="warn">
          <p className="font-medium">Unverified draft — these areas could not be confirmed:</p>
          {guide.review_issues.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {guide.review_issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          )}
        </StatusAlert>
      )}
      {guide.display === "published" && guide.status === "needs_review" && (
        <StatusAlert tone="warn">An update was held for review; showing the last verified guide.</StatusAlert>
      )}
      {guide.display === "published" && guide.status === "failed" && (
        <StatusAlert tone="warn">The latest update failed; showing the last verified guide.</StatusAlert>
      )}
      <div className="text-sm leading-relaxed">
        {guide.guide_markdown ? (
          <StreamMarkdown content={guide.guide_markdown} />
        ) : (
          <p className="text-muted-foreground italic">No content yet.</p>
        )}
      </div>
      {guide.unconfirmed.length > 0 && (
        <section className="flex flex-col gap-1 text-sm text-muted-foreground">
          <h4 className="text-xs font-semibold tracking-wider uppercase">Not covered</h4>
          <p>Left out because no current source confirmed it:</p>
          <ul className="list-disc pl-5">
            {guide.unconfirmed.map((area) => (
              <li key={area}>{area}</li>
            ))}
          </ul>
        </section>
      )}
      {guide.display === "published" && <GuideSources guide={guide} />}
      {footer}
    </div>
  );
}

export function GuideViewerDialog({
  target,
  onClose,
  onChanged,
  renderFooter,
}: {
  target: GuideTarget | null;
  onClose: () => void;
  /** Called after a generate request so the library can refresh its rows. */
  onChanged?: () => void;
  /** Extra actions under a published guide (e.g. "Report an inaccuracy"). */
  renderFooter?: (guide: Guide) => ReactNode;
}) {
  const [tab, setTab] = useState<ContentType>("raid");
  const [guides, setGuides] = useState<Partial<Record<ContentType, Guide>>>({});
  const [loading, setLoading] = useState<ContentType | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(
    async (ct: ContentType) => {
      if (!target) return;
      setLoading(ct);
      setErr(null);
      try {
        const g = await getGuide(target.class_name, target.spec, ct);
        setGuides((prev) => ({ ...prev, [ct]: g }));
      } catch {
        setErr("Could not open that guide.");
      } finally {
        setLoading((cur) => (cur === ct ? null : cur));
      }
    },
    [target],
  );

  // A new target resets the cache and opens on the content type that was clicked.
  useEffect(() => {
    setGuides({});
    setErr(null);
    if (target) {
      setTab(target.contentType);
      void load(target.contentType);
    }
  }, [target, load]);

  const onTab = (value: string) => {
    const ct = value as ContentType;
    setTab(ct);
    if (!guides[ct]) void load(ct);
  };

  const onGenerate = async (ct: ContentType) => {
    if (!target) return;
    setBusy(true);
    setErr(null);
    try {
      const g = await generateGuide(target.class_name, target.spec, ct, false);
      setGuides((prev) => ({ ...prev, [ct]: g }));
      onChanged?.();
    } catch (e) {
      setErr(
        e instanceof ApiError && e.status === 429
          ? "You're requesting guides too quickly — slow down a moment, then try again."
          : "Could not start that guide. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  const color = target ? classColor(target.class_name) : null;
  const current = guides[tab];

  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      {/* Radix supplies focus trap, Escape, backdrop close, scroll lock and focus return. */}
      <DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-3xl">
        {target && (
          <>
            <DialogHeader className="border-b border-border pb-4">
              <DialogTitle className="font-display text-lg tracking-wide">
                <span style={color ? { color } : undefined}>
                  {target.spec_display} {classDisplayName(target.class_name)}
                </span>
              </DialogTitle>
              <DialogDescription className="flex flex-wrap items-center gap-2">
                {current?.has_published ? provenanceText(current) : "Class guide"}
                {current?.has_published && <StaleBadge it={current} />}
                {current?.refreshing && <StatusBadge tone="pending">Refreshing</StatusBadge>}
              </DialogDescription>
            </DialogHeader>
            {err && (
              <StatusAlert tone="error" onDismiss={() => setErr(null)}>
                {err}
              </StatusAlert>
            )}
            <Tabs value={tab} onValueChange={onTab}>
              <TabsList aria-label="Content type">
                {(["raid", "mplus"] as const).map((ct) => (
                  <TabsTrigger key={ct} value={ct}>
                    {CONTENT_LABEL[ct]}
                  </TabsTrigger>
                ))}
              </TabsList>
              {(["raid", "mplus"] as const).map((ct) => (
                <TabsContent key={ct} value={ct} className="pt-2">
                  {loading === ct && !guides[ct] ? (
                    <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                      <Spinner /> Loading…
                    </p>
                  ) : guides[ct] ? (
                    <GuideBody
                      guide={guides[ct]}
                      target={target}
                      busy={busy}
                      onGenerate={() => void onGenerate(ct)}
                      footer={guides[ct].display === "published" ? renderFooter?.(guides[ct]) : undefined}
                    />
                  ) : null}
                </TabsContent>
              ))}
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
