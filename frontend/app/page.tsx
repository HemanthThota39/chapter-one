"use client";

import { useCallback, useState } from "react";
import AnalyzerForm from "@/components/AnalyzerForm";
import ProgressStream from "@/components/ProgressStream";
import ReportViewer from "@/components/ReportViewer";
import { startAnalysis } from "@/lib/api";

export default function HomePage() {
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleStart = useCallback(async (idea: string) => {
    setRunning(true);
    setCompleted(false);
    setErrorMsg(null);
    setAnalysisId(null);
    try {
      const { analysis_id } = await startAnalysis(idea);
      setAnalysisId(analysis_id);
    } catch (e) {
      setErrorMsg((e as Error).message);
      setRunning(false);
    }
  }, []);

  const handleComplete = useCallback(() => {
    setCompleted(true);
    setRunning(false);
  }, []);

  const handleError = useCallback((msg: string) => {
    setErrorMsg(msg);
    setRunning(false);
  }, []);

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-neutral-900">
          Startup Analyzer
        </h1>
        <p className="mt-1 text-sm text-neutral-600">
          Composite VC Framework · 10 dimensions · grounded in live web search
        </p>
      </header>

      <section className="mb-6 rounded-md border border-neutral-200 bg-white p-6 shadow-sm">
        <AnalyzerForm onStart={handleStart} disabled={running} />
      </section>

      {errorMsg && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      {analysisId && (
        <section className="mb-6">
          <ProgressStream
            analysisId={analysisId}
            onComplete={handleComplete}
            onError={handleError}
          />
        </section>
      )}

      {completed && analysisId && (
        <section>
          <ReportViewer analysisId={analysisId} />
        </section>
      )}

      <footer className="mt-12 text-center text-xs text-neutral-500">
        Powered by gpt-5.3-chat on Azure AI Foundry · Native web_search tool
      </footer>
    </main>
  );
}
