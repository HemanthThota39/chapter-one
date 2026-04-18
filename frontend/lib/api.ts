export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type StartResponse = { analysis_id: string; status: string };

export async function startAnalysis(idea: string): Promise<StartResponse> {
  const res = await fetch(`${API_BASE}/api/analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea }),
  });
  if (!res.ok) throw new Error(`Start failed: ${res.status}`);
  return res.json();
}

export function streamUrl(analysisId: string): string {
  return `${API_BASE}/api/analysis/${analysisId}/stream`;
}

export function reportUrl(analysisId: string): string {
  return `${API_BASE}/api/analysis/${analysisId}/report`;
}

export async function reportRenderError(
  analysisId: string,
  chartIndex: number,
  error: string,
  code: string,
  kind: "mermaid" | "markdown" = "mermaid"
): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/telemetry/render-error`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        analysis_id: analysisId,
        chart_index: chartIndex,
        error,
        code,
        kind,
      }),
    });
  } catch {
    /* best-effort; swallow */
  }
}
