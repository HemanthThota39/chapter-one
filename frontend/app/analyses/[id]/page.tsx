"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import {
  AnalysisDetail,
  fetchAnalysis,
  reportUrl,
  streamUrl,
} from "@/lib/analyses";

type ProgressEvent = { stage: string; percent: number; message: string };

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  classifying: "Classifying idea",
  research: "Running parallel research",
  research_done: "Research complete",
  analysis_1: "Analysing problem + business model",
  analysis_2: "Analysing GTM + risk",
  scoring: "Computing CVF scores",
  compiling: "Generating markdown report",
  done: "Complete",
  error: "Error",
};

export default function AnalysisDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();

  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [current, setCurrent] = useState<ProgressEvent | null>(null);
  const [detailLine, setDetailLine] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const renderTarget = useRef<HTMLDivElement>(null);

  const refreshDetail = useCallback(async () => {
    try {
      const d = await fetchAnalysis(id);
      setDetail(d);
      return d;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, [id]);

  useEffect(() => {
    refreshDetail();
  }, [refreshDetail]);

  useEffect(() => {
    if (!detail) return;
    if (detail.status === "done") {
      // Fetch report markdown
      fetch(reportUrl(id), { credentials: "include" })
        .then((r) => r.text())
        .then((md) => setMarkdown(md))
        .catch((e) => setError((e as Error).message));
      return; // no SSE needed
    }
    if (detail.status === "failed") {
      setError(detail.error_message || "Analysis failed");
      return;
    }

    const es = new EventSource(streamUrl(id), { withCredentials: true });
    es.addEventListener("progress", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as ProgressEvent;
        setEvents((prev) => [...prev, data]);
        setCurrent(data);
        if (data.stage === "done" || data.stage === "error") {
          es.close();
          refreshDetail();
        }
      } catch {/* ignore */}
    });
    es.addEventListener("detail", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data);
        if (data?.message) setDetailLine(data.message);
      } catch {/* ignore */}
    });
    es.addEventListener("ping", () => {/* keepalive */});
    es.addEventListener("close", () => es.close());
    es.onerror = () => {/* browser auto-reconnects; terminal events close first */};
    return () => es.close();
  }, [detail?.status, id, refreshDetail]);

  if (error) {
    return (
      <main className="mx-auto max-w-xl px-6 py-16 text-center">
        <p className="text-sm text-red-600">Error: {error}</p>
        <button
          onClick={() => router.back()}
          className="mt-4 rounded-md border border-neutral-300 px-3 py-1 text-sm hover:bg-neutral-100"
        >
          Go back
        </button>
      </main>
    );
  }
  if (!detail) {
    return <main className="mx-auto max-w-xl px-6 py-16 text-center text-sm text-neutral-500">Loading...</main>;
  }

  const percent = current?.percent ?? (detail.status === "done" ? 100 : 5);
  const running = detail.status === "queued" || detail.status === "running";
  const stageLabel = current
    ? STAGE_LABELS[current.stage] ?? current.stage
    : STAGE_LABELS[detail.status] ?? detail.status;

  return (
    <main className="mx-auto max-w-3xl px-4 py-6 md:px-6">
      <header className="mb-6">
        <button
          onClick={() => router.back()}
          className="text-xs text-neutral-500 hover:text-neutral-800"
        >
          ← Back
        </button>
        <h1 className="mt-2 text-xl font-bold tracking-tight">
          {detail.idea_title || "Analysis in progress..."}
        </h1>
        {detail.verdict && (
          <div className="mt-1 text-sm text-neutral-600">
            <span className="mr-3">Score: <strong>{detail.overall_score_100}/100</strong></span>
            <span className="mr-3">Verdict: <strong>{detail.verdict}</strong></span>
            <span className="text-neutral-400">Confidence: {detail.confidence}</span>
          </div>
        )}
      </header>

      {running && (
        <section className="mb-6 rounded-md border border-neutral-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="pipeline-spinner" aria-hidden />
              <h3 className="text-sm font-semibold text-neutral-800">{stageLabel}</h3>
            </div>
            <span className="text-xs font-medium text-neutral-500">{percent}%</span>
          </div>
          <div className="mb-3 h-2 w-full overflow-hidden rounded-full bg-neutral-100">
            <div
              className="pipeline-shimmer h-full transition-all duration-500"
              style={{ width: `${Math.max(percent, 2)}%` }}
            />
          </div>
          {detailLine && (
            <div key={detailLine} className="pipeline-detail truncate text-xs text-neutral-500">
              <span className="mr-1 text-neutral-400">→</span>
              {detailLine}
            </div>
          )}
          <ul className="mt-3 space-y-1 text-sm text-neutral-600">
            {events.map((e, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-0.5 text-neutral-400">✓</span>
                <span>
                  <span className="font-medium text-neutral-800">
                    {STAGE_LABELS[e.stage] ?? e.stage}
                  </span>
                  {e.message ? <span className="text-neutral-500"> — {e.message}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {markdown && (
        <section className="rounded-md border border-neutral-200 bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between border-b pb-3">
            <h2 className="text-sm font-semibold text-neutral-700">Report</h2>
            <a
              href={reportUrl(id)}
              className="rounded-md bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-200"
            >
              Download .md
            </a>
          </div>
          <div ref={renderTarget} className="prose-report max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
              {markdown}
            </ReactMarkdown>
          </div>
        </section>
      )}
    </main>
  );
}
