"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import {
  AnalysisDetail,
  fetchAnalysis,
  reportPdfUrl,
  reportUrl,
  streamUrl,
} from "@/lib/analyses";
import AppShell from "@/components/AppShell";

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

  useEffect(() => { refreshDetail(); }, [refreshDetail]);

  useEffect(() => {
    if (!detail) return;
    if (detail.status === "done") {
      fetch(reportUrl(id), { credentials: "include" })
        .then((r) => r.text())
        .then((md) => setMarkdown(md))
        .catch((e) => setError((e as Error).message));
      return;
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
    es.onerror = () => {/* browser auto-reconnects */};
    return () => es.close();
  }, [detail?.status, id, refreshDetail]);

  if (error) {
    return (
      <AppShell title="Analysis" width="wide">
        <div className="card p-6 text-center">
          <p className="text-sm text-red-600">{error}</p>
          <button onClick={() => router.back()} className="btn-secondary mt-4">← Go back</button>
        </div>
      </AppShell>
    );
  }
  if (!detail) {
    return (
      <AppShell title="Analysis" width="wide">
        <div className="py-10 text-center text-sm text-neutral-500">Loading…</div>
      </AppShell>
    );
  }

  const percent = current?.percent ?? (detail.status === "done" ? 100 : 5);
  const running = detail.status === "queued" || detail.status === "running";
  const stageLabel = current
    ? STAGE_LABELS[current.stage] ?? current.stage
    : STAGE_LABELS[detail.status] ?? detail.status;

  return (
    <AppShell title="Analysis" width="wide">
      <header className="mb-5">
        <button onClick={() => router.back()} className="btn-ghost -ml-2 !px-2 !py-1 text-xs">← Back</button>
        <h1 className="mt-2 text-xl font-bold tracking-tight break-anywhere">
          {detail.idea_title || "Analysis in progress…"}
        </h1>
        {/* Show the user their original submission while we don't have a title
            yet — otherwise they'd stare at "Analysis in progress…" with no
            indication which idea this is. */}
        {!detail.idea_title && detail.idea_text && (
          <blockquote className="mt-3 border-l-2 border-neutral-200 pl-3 text-sm italic text-neutral-600 break-anywhere line-clamp-6">
            {detail.idea_text}
          </blockquote>
        )}
        {detail.verdict && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded-full px-2.5 py-0.5 font-semibold ${verdictBadge(detail.verdict)}`}>
              {detail.verdict}
            </span>
            {detail.overall_score_100 != null && (
              <span className="rounded-full bg-neutral-100 px-2.5 py-0.5 font-semibold text-neutral-800">
                {detail.overall_score_100}/100
              </span>
            )}
            {detail.confidence && (
              <span className="text-neutral-500">· Confidence {detail.confidence}</span>
            )}
          </div>
        )}
      </header>

      {running && (
        <section className="card mb-5 overflow-hidden p-5 md:p-6">
          {/* Mobile: ring on top center, then left-aligned text block below.
              Desktop: ring on the left, text block flows beside it. */}
          <div className="flex flex-col items-start gap-4 md:flex-row md:gap-6">
            <div className="mx-auto md:mx-0"><ProgressRing percent={percent} /></div>
            <div className="min-w-0 w-full flex-1 text-left">
              <h3 className="text-base font-semibold text-neutral-900 break-anywhere">
                {stageLabel}
              </h3>
              {detailLine && (
                <p
                  key={detailLine}
                  className="pipeline-detail mt-1 text-xs text-neutral-500 break-anywhere"
                >
                  {detailLine}
                </p>
              )}
              {events.length > 0 && (
                <ul className="mt-4 space-y-1.5 text-xs text-neutral-600">
                  {events.map((e, i) => {
                    const isLast = i === events.length - 1;
                    return (
                      <li
                        key={i}
                        className="flex min-w-0 items-start gap-2 break-anywhere"
                      >
                        <span
                          className={`mt-0.5 shrink-0 ${isLast ? "text-blue-600" : "text-neutral-400"}`}
                        >
                          {isLast ? "•" : "✓"}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span
                            className={`font-medium ${isLast ? "text-neutral-900" : "text-neutral-700"}`}
                          >
                            {STAGE_LABELS[e.stage] ?? e.stage}
                          </span>
                          {e.message ? (
                            <span className="text-neutral-500"> — {e.message}</span>
                          ) : null}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </section>
      )}

      {markdown && (
        <section className="card p-5 md:p-6">
          <div className="mb-4 flex items-center justify-between gap-3 border-b border-neutral-100 pb-3">
            <h2 className="text-sm font-semibold text-neutral-700">Report</h2>
            <a
              href={reportPdfUrl(id)}
              className="btn-secondary !py-1.5 text-xs"
              target="_blank"
              rel="noopener noreferrer"
            >
              <DownloadIcon /> Download PDF
            </a>
          </div>
          <div ref={renderTarget} className="prose-report max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={{
                table: ({ node, ...props }) => (
                  <div className="table-scroll">
                    <table {...props} />
                  </div>
                ),
              }}
            >
              {markdown}
            </ReactMarkdown>
          </div>
        </section>
      )}
    </AppShell>
  );
}

function verdictBadge(v: string): string {
  if (v === "STRONG INVEST") return "bg-green-100 text-green-800";
  if (v === "CONDITIONAL") return "bg-blue-100 text-blue-800";
  if (v === "WATCH") return "bg-yellow-100 text-yellow-800";
  if (v === "PASS" || v === "HARD PASS") return "bg-red-100 text-red-800";
  return "bg-neutral-100 text-neutral-700";
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  );
}

function ProgressRing({ percent }: { percent: number }) {
  // Clamp for safety; show at least 2% so the ring has a visible arc.
  const p = Math.max(2, Math.min(100, percent));
  const size = 112;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (p / 100) * c;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="#e5e7eb" strokeWidth={stroke}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke="#111827"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 600ms cubic-bezier(0.2, 0.7, 0.2, 1)" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold tabular-nums tracking-tight">{Math.round(p)}%</span>
        <span className="text-[10px] uppercase tracking-wider text-neutral-500">Running</span>
      </div>
    </div>
  );
}
