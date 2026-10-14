// PERF-011: KaTeX (and its CSS and fonts) is only needed when a reply contains math, so it
// lives in its own chunk that StreamMarkdown loads on first use.
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

// US3: math rendering via Streamdown's first-class `plugins.math` slot. Streamdown runs
// `remarkPlugin` after remark-gfm and `rehypePlugin` after its sanitize step — verified to
// render KaTeX correctly through that ordering.
export const MATH_PLUGIN = {
  name: "katex" as const,
  type: "math" as const,
  remarkPlugin: remarkMath,
  rehypePlugin: rehypeKatex,
};
