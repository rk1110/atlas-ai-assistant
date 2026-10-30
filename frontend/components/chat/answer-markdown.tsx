"use client";

import type { ComponentProps } from "react";
import ReactMarkdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CitationChip } from "@/components/chat/citation-chip";
import type { CitationEvent } from "@/lib/events";

// Same pattern as the backend (services/grounding.py): [1], [2][3], [1, 3], and gpt-oss's 【1】.
const MARKER = /[[【](\d+(?:\s*,\s*\d+)*)(?:†[^\]】]*)?[\]】]/g;
const CITE_PREFIX = "#cite-";

/**
 * An assistant answer rendered as Markdown, with its [n] markers turned into clickable chips.
 *
 * How: before rendering, "[1]" becomes the Markdown link "[1](#cite-1)", and the link renderer
 * below draws a CitationChip for those links. Only numbers with a citation event get a chip;
 * while the answer is still streaming there are none yet, so markers show as plain "[1]" and
 * become chips when the citations arrive at the end.
 */
export function AnswerMarkdown({ content, citations }: { content: string; citations: CitationEvent[] }) {
  const byId = new Map(citations.map((c) => [c.citation_id, c]));
  const components: Components = {
    // Only the attributes Markdown links have; `node` (the syntax tree) must not reach the DOM.
    a: ({ href, title, children }: ComponentProps<"a"> & ExtraProps) => {
      const citation = href?.startsWith(CITE_PREFIX) ? byId.get(href.slice(CITE_PREFIX.length)) : undefined;
      if (citation) return <CitationChip citation={citation} inline />;
      return (
        <a href={href} title={title}>
          {children}
        </a>
      );
    },
  };
  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {byId.size > 0 ? linkMarkers(content, byId) : content}
      </ReactMarkdown>
    </div>
  );
}

function linkMarkers(text: string, byId: Map<string, CitationEvent>): string {
  return text.replace(MARKER, (_match, numbers: string) =>
    numbers
      .split(",")
      .map((n) => n.trim())
      .map((n) => (byId.has(n) ? `[${n}](${CITE_PREFIX}${n})` : `[${n}]`))
      .join(""),
  );
}
