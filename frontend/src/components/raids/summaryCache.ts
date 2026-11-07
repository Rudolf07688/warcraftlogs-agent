import { getRaidSummary, type RaidSummary } from "../../api/raidSummary";

// PERF-001: the tabs unmount when inactive, so every switch asked for the summary again and
// quick browsing could trip the backend's 60/min limit. A short in-memory cache per report code,
// holding the promise so two quick mounts share one request. Failures are never kept.
const TTL_MS = 60_000;

const cache = new Map<string, { at: number; promise: Promise<RaidSummary> }>();

export function loadRaidSummary(reportCode: string): Promise<RaidSummary> {
  const hit = cache.get(reportCode);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.promise;
  const entry = { at: Date.now(), promise: getRaidSummary(reportCode) };
  cache.set(reportCode, entry);
  entry.promise.catch(() => {
    if (cache.get(reportCode) === entry) cache.delete(reportCode);
  });
  return entry.promise;
}

/** Forget one raid (its data is about to change) or, without a code, all of them. */
export function clearRaidSummaryCache(reportCode?: string): void {
  if (reportCode === undefined) cache.clear();
  else cache.delete(reportCode);
}
