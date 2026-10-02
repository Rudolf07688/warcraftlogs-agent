import { visit } from "unist-util-visit";

/**
 * US6 (FR-029): wrap each word in a `<span class="ink">` so a CSS mount animation
 * plays once per newly-revealed word while streaming (see `.is-streaming .ink` in
 * index.css). Skips code/pre so source stays intact. CSS-only — thousands of words
 * stay cheap. Appended to Streamdown's default rehype plugins.
 */
export function rehypeWordSpans() {
  return (tree: unknown) => {
    visit(tree as never, "text", (node: any, index: number | null, parent: any) => {
      if (!parent || index == null) return;
      const tag = parent.tagName;
      if (tag === "code" || tag === "pre") return;
      const parts = String(node.value).split(/(\s+)/).filter(Boolean);
      if (parts.length === 0) return;
      parent.children.splice(
        index,
        1,
        ...parts.map((p: string) =>
          /^\s+$/.test(p)
            ? { type: "text", value: p }
            : {
                type: "element",
                tagName: "span",
                properties: { className: ["ink"] },
                children: [{ type: "text", value: p }],
              },
        ),
      );
      return index + parts.length;
    });
  };
}
