import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, generateGuide, getGuide, listGuides } from "../../api/restClient";
import type { Guide, GuideFreshness, GuideListItem, GuideStatus } from "../../types";
import { StreamMarkdown } from "../StreamMarkdown";

// Class Guides tab (feature 008 / US2): the full class/spec roster merged with the shared,
// global library's status. Any signed-in user can request, retry, or refresh a guide, and
// view its content. Generation is best-effort/non-blocking and rate-limited (429 → slow down).

const CHIP_LABEL: Record<GuideStatus, string> = {
  ready: "Downloaded",
  pending: "Generating…",
  failed: "Failed",
  none: "Not downloaded",
};

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

function GuideProvenance({
  it,
}: {
  it: { game_patch: string | null; generated_at: string | null; freshness: GuideFreshness | null };
}) {
  const date = fmtDate(it.generated_at);
  const stale = it.freshness === "possibly_stale" || it.freshness === "unknown";
  return (
    <>
      <span className="guide-meta" title="Patch the guide targets · when it was generated">
        {it.game_patch ? `Patch ${it.game_patch}` : "Patch unknown"}
        {date ? ` · ${date}` : ""}
      </span>
      {stale && (
        <span
          className="guide-badge guide-stale"
          title={
            it.freshness === "unknown"
              ? "This guide does not state a patch; regenerate to refresh it."
              : "This guide targets an older patch; regenerate to refresh it."
          }
        >
          May be out of date
        </span>
      )}
    </>
  );
}

export function ClassGuidesTab({ active }: { active: boolean }) {
  const [items, setItems] = useState<GuideListItem[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Guide | null>(null);
  const [viewBusy, setViewBusy] = useState(false);

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
  const anyPending = items.some((i) => i.status === "pending");
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
    setViewBusy(true);
    setErr(null);
    try {
      setViewing(await getGuide(it.class_name, it.spec));
    } catch {
      setErr("Could not open that guide.");
    } finally {
      setViewBusy(false);
    }
  }, []);

  // Preserve the server ordering (class display, then spec) while grouping by class.
  const groups = useMemo(() => {
    const byClass = new Map<string, GuideListItem[]>();
    for (const it of items) {
      const list = byClass.get(it.class_display) ?? [];
      list.push(it);
      byClass.set(it.class_display, list);
    }
    return [...byClass.entries()];
  }, [items]);

  return (
    <div className="profile-tabpanel">
      {err && <div className="profile-error">{err}</div>}
      {notice && <div className="profile-notice">{notice}</div>}

      <div className="guide-grid">
        {groups.map(([display, specs]) => (
          <section className="guide-class-card" key={display}>
            <h3 className="guide-class-name">{display}</h3>
            <ul className="guide-spec-list">
              {specs.map((it) => {
                const key = keyOf(it);
                const busy = busyKey === key;
                return (
                  <li className="guide-spec-row" key={key}>
                    <span className="guide-spec-name">{it.spec}</span>
                    <span className={`guide-badge guide-${it.status}`}>
                      {CHIP_LABEL[it.status]}
                    </span>
                    {it.status === "ready" && <GuideProvenance it={it} />}
                    <span className="guide-spec-actions">
                      {it.status === "ready" && (
                        <>
                          <button
                            className="guide-btn"
                            disabled={viewBusy}
                            onClick={() => void onView(it)}
                          >
                            View
                          </button>
                          <button
                            className="guide-btn guide-btn-ghost"
                            disabled={busy}
                            onClick={() => void onGenerate(it, true)}
                            title="Regenerate this guide"
                          >
                            {busy ? "…" : "Refresh"}
                          </button>
                        </>
                      )}
                      {it.status === "failed" && (
                        <button
                          className="guide-btn"
                          disabled={busy}
                          onClick={() => void onGenerate(it, true)}
                        >
                          {busy ? "…" : "Retry"}
                        </button>
                      )}
                      {it.status === "none" && (
                        <button
                          className="guide-btn"
                          disabled={busy}
                          onClick={() => void onGenerate(it, false)}
                        >
                          {busy ? "…" : "Generate"}
                        </button>
                      )}
                      {it.status === "pending" && (
                        <span className="guide-spec-hint">working…</span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>

      {viewing && (
        <div
          className="profile-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={`${viewing.class_name} ${viewing.spec} guide`}
          onClick={() => setViewing(null)}
        >
          <div className="guide-view-panel" onClick={(e) => e.stopPropagation()}>
            <header className="profile-header">
              <h2>
                {viewing.class_name} — {viewing.spec}
              </h2>
              <button className="profile-close" onClick={() => setViewing(null)} title="Close">
                ✕
              </button>
            </header>
            {viewing.status === "ready" && (
              <div className="guide-view-meta">
                <GuideProvenance it={viewing} />
              </div>
            )}
            <div className="guide-view-body">
              {viewing.guide_markdown ? (
                <StreamMarkdown content={viewing.guide_markdown} />
              ) : (
                <p className="guide-spec-hint">No content yet.</p>
              )}
              {viewing.sources && viewing.sources.length > 0 && (
                <div className="guide-sources">
                  <h4>Sources</h4>
                  <ul>
                    {viewing.sources.map((s) => (
                      <li key={s.uri}>
                        <a href={s.uri} target="_blank" rel="noreferrer">
                          {s.title || s.uri}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
