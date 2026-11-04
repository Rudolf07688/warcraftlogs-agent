import type { TransportItem } from "@grafana/faro-react";

// Feature 057 (SEC-006): the invite and password-reset links carry a single-use token in the
// URL fragment (`#token=...`) that the page strips only after it mounts, so Faro could start
// first. Nothing may leave the browser with a query or a fragment: this runs as Faro's
// `beforeSend` over every item, and drops them from every string that is a URL (page meta,
// span `http.url`, route events) and from URLs inside longer text (log and error messages).

const WHOLE_URL = /^(?:https?:\/\/|\/)\S*$/;
const URL_IN_TEXT = /(https?:\/\/[^\s?#"'<>]*)[?#][^\s"'<>]*/g;

export function scrubString(value: string): string {
  if (WHOLE_URL.test(value)) return value.replace(/[?#].*$/, "");
  return value.replace(URL_IN_TEXT, "$1");
}

function scrub(value: unknown): unknown {
  if (typeof value === "string") return scrubString(value);
  if (Array.isArray(value)) return value.map(scrub);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, inner]) => [key, scrub(inner)]));
  }
  return value;
}

/** Faro `beforeSend`: the item with the query and fragment removed from every URL in it. */
export function scrubItem(item: TransportItem): TransportItem {
  return scrub(item) as TransportItem;
}
