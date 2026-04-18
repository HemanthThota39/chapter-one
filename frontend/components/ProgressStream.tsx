"use client";

import { memo, useEffect, useRef, useState } from "react";
import { streamUrl } from "@/lib/api";

export type ProgressEvent = {
  stage: string;
  percent: number;
  message: string;
};

type Props = {
  analysisId: string | null;
  onComplete: () => void;
  onError: (message: string) => void;
};

const STAGE_LABELS: Record<string, string> = {
  classifying: "Classifying idea",
  research: "Running parallel research",
  research_done: "Research complete",
  analysis_1: "Analysing problem + business model",
  analysis_2: "Analysing GTM + risk",
  scoring: "Computing CVF scores",
  compiling: "Generating report",
  done: "Complete",
  error: "Error",
};

export default function ProgressStream({ analysisId, onComplete, onError }: Props) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [current, setCurrent] = useState<ProgressEvent | null>(null);
  const [running, setRunning] = useState(false);
  // Detail lives in a separate ref-backed state so it re-renders only the <DetailLine />,
  // never the stage list — keeps updates cheap even if we stream hundreds of detail events.
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    if (!analysisId) return;
    setEvents([]);
    setCurrent(null);
    setDetail("");
    setRunning(true);

    const es = new EventSource(streamUrl(analysisId));

    es.addEventListener("progress", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as ProgressEvent;
        setEvents((prev) => [...prev, data]);
        setCurrent(data);
        if (data.stage === "done") {
          setRunning(false);
          es.close();
          onComplete();
        }
        if (data.stage === "error") {
          setRunning(false);
          es.close();
          onError(data.message || "Analysis failed");
        }
      } catch (e) {
        console.error("bad progress payload", e);
      }
    });

    es.addEventListener("detail", (ev) => {
      try {
        const data = JSON.parse((ev as MessageEvent).data) as { message: string };
        if (data.message) setDetail(data.message);
      } catch {
        /* ignore malformed detail */
      }
    });

    es.addEventListener("close", () => es.close());
    es.onerror = () => {
      /* browser auto-reconnects; terminal events close us first */
    };

    return () => es.close();
  }, [analysisId, onComplete, onError]);

  if (!analysisId) return null;

  const percent = current?.percent ?? 0;
  const stageLabel = current ? STAGE_LABELS[current.stage] ?? current.stage : "Starting...";

  return (
    <div className="rounded-md border border-neutral-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {running && <span className="pipeline-spinner" aria-hidden />}
          <h3 className="text-sm font-semibold text-neutral-800">
            {stageLabel}
          </h3>
        </div>
        <span className="text-xs font-medium text-neutral-500">{percent}%</span>
      </div>

      {/* Two-layer bar: deterministic progress fill + optional shimmer so users
          see continuous motion even between stage updates. */}
      <div className="mb-3 h-2 w-full overflow-hidden rounded-full bg-neutral-100">
        <div
          className={`h-full ${running ? "pipeline-shimmer" : "bg-neutral-900"} transition-all duration-500`}
          style={{ width: `${Math.max(percent, 2)}%` }}
        />
      </div>

      <DetailLine detail={detail} />

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
    </div>
  );
}

// Isolated, memoized so detail updates never force the stage list to re-render.
// Key on the detail text so the fade-in animation re-plays on each change.
const DetailLine = memo(function DetailLine({ detail }: { detail: string }) {
  if (!detail) return null;
  return (
    <div
      key={detail}
      className="pipeline-detail truncate text-xs text-neutral-500"
      title={detail}
    >
      <span className="mr-1 text-neutral-400">→</span>
      {detail}
    </div>
  );
});
