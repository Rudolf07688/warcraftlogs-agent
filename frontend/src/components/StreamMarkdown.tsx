import { memo } from "react";
import { Streamdown, defaultRehypePlugins } from "streamdown";
import type { Components } from "streamdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { rehypeWordSpans } from "../lib/rehypeWordSpans";
import { useSmoothText } from "../hooks/useSmoothText";

/**
 * US6 streaming renderer (replaces the old react-markdown `Markdown`).
 *
 * Streamdown renders streaming-safe GFM markdown (no flashing `**`/broken tables
 * mid-stream) and memoizes completed blocks. We layer on:
 *  - `useSmoothText` so text inks in at a steady adaptive rate (FR-029),
 *  - `rehypeWordSpans` for the per-word ink-in reveal (CSS-only),
 *  - an ember caret trailing the stream,
 *  - new-tab links (US1/FR-003) so clicking a Warcraft Logs source never loses chat state.
 */

// Append our word-span plugin to Streamdown's defaults (passing rehypePlugins replaces them).
const REHYPE_PLUGINS = [...Object.values(defaultRehypePlugins), rehypeWordSpans];

// US3: math rendering via Streamdown's first-class `plugins.math` slot. Streamdown
// runs `remarkPlugin` after remark-gfm and `rehypePlugin` after its sanitize step —
// verified to render KaTeX correctly through that ordering. KaTeX CSS is imported in
// index.css (T036). This is additive: code highlighting and other defaults are kept.
const MATH_PLUGIN = {
  name: "katex" as const,
  type: "math" as const,
  remarkPlugin: remarkMath,
  rehypePlugin: rehypeKatex,
};

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
  return (
    <div className={`markdown stream${streaming ? " is-streaming" : ""}`}>
      <Streamdown
        mode={streaming ? "streaming" : "static"}
        parseIncompleteMarkdown={streaming}
        rehypePlugins={REHYPE_PLUGINS}
        plugins={{ math: MATH_PLUGIN }}
        components={COMPONENTS}
      >
        {shown}
      </Streamdown>
      {streaming && <span className="ember-caret" aria-hidden="true" />}
    </div>
  );
}

export const StreamMarkdown = memo(StreamMarkdownImpl);
