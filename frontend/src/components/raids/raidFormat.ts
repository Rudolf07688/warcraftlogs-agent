import type { Raid } from "../../types";

export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// US2: show the raid's own date/time, falling back when the report start is unknown
// (older rows predating the column, or raids captured via a non-fight tool).
export function raidWhen(r: Raid): string {
  return formatWhen(r.report_started_at ?? r.first_seen_at ?? r.last_asked_at);
}

// US2: a compact boss summary (kills marked).
export function bossSummary(r: Raid, max = 3): string {
  const bosses = r.encounters ?? [];
  if (bosses.length === 0) return "";
  const names = bosses.map((e) => (e.kill ? `${e.name} ✓` : e.name));
  const shown = names.slice(0, max).join(", ");
  return names.length > max ? `${shown} +${names.length - max}` : shown;
}

// 9_876_000 ms -> "2h 44m"; under an hour -> "44m 36s".
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`;
}
