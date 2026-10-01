import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders agent output as GitHub-flavored Markdown (tables, lists, code, etc.).
 * Memoized so re-rendering the message list during streaming stays cheap.
 */
export const Markdown = memo(function Markdown({ content }: { content: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
});
