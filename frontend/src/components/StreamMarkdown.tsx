import { memo, useEffect, useMemo, useState } from "react";
import { Streamdown, defaultRehypePlugins } from "streamdown";
import type { Components } from "streamdown";
import { rehypeWordSpans } from "../lib/rehypeWordSpans";
import { useSmoothText } from "../hooks/useSmoothText";

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

// Streamdown's defaults, plus our word-span plugin for the live reply (passing
// rehypePlugins replaces the defaults). Finished messages skip the per-word spans: the
// ink-in has already played, and a span per word is costly on long answers (PERF-010).
const STATIC_REHYPE_PLUGINS = Object.values(defaultRehypePlugins);
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
