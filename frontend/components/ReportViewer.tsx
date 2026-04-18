"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import mermaid from "mermaid";
import { reportRenderError, reportUrl } from "@/lib/api";

type Props = { analysisId: string };

export default function ReportViewer({ analysisId }: Props) {
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mermaid.initialize({ startOnLoad: false, theme: "default", securityLevel: "loose" });
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(reportUrl(analysisId));
        if (!res.ok) throw new Error(`Report fetch ${res.status}`);
        const text = await res.text();
        if (!cancelled) setMarkdown(text);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [analysisId]);

  useEffect(() => {
    if (!markdown || !ref.current) return;
    const nodes = ref.current.querySelectorAll<HTMLElement>("code.language-mermaid");
    nodes.forEach(async (node, idx) => {
      const id = `mermaid-${analysisId}-${idx}`;
      const code = node.textContent || "";
      try {
        const { svg } = await mermaid.render(id, code);
        const wrapper = document.createElement("div");
        wrapper.className = "my-4";
        wrapper.innerHTML = svg;
        node.parentElement?.replaceWith(wrapper);
      } catch (e) {
        const msg = (e as Error).message || String(e);
        console.error(`mermaid chart ${idx} failed:`, msg);
        reportRenderError(analysisId, idx, msg, code, "mermaid");
        // Graceful fallback: show the broken code with a warning rather than crash the page.
        const fallback = document.createElement("div");
        fallback.className =
          "my-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm";
        fallback.innerHTML = `
          <div class="mb-2 font-semibold text-amber-900">
            Chart ${idx + 1} could not be rendered (reported to backend)
          </div>
          <pre class="whitespace-pre-wrap overflow-x-auto text-xs text-amber-900">${escapeHtml(
            code
          )}</pre>
        `;
        node.parentElement?.replaceWith(fallback);
      }
    });
  }, [markdown, analysisId]);

  if (error) {
    return <div className="text-sm text-red-600">Failed to load report: {error}</div>;
  }
  if (markdown === null) {
    return <div className="text-sm text-neutral-500">Loading report...</div>;
  }

  return (
    <div className="rounded-md border border-neutral-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between border-b pb-3">
        <h2 className="text-sm font-semibold text-neutral-700">Analysis Report</h2>
        <a
          href={reportUrl(analysisId)}
          className="rounded-md bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-200"
        >
          Download .md
        </a>
      </div>
      <div ref={ref} className="prose-report max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
        >
          {markdown}
        </ReactMarkdown>
      </div>
    </div>
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
