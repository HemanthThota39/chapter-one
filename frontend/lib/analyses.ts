import { API_BASE } from "@/lib/session";

export type AnalysisSummary = {
  id: string;
  idea_title: string | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  visibility: "public" | "private";
  overall_score_100: number | null;
  verdict: string | null;
  submitted_at: string | null;
  completed_at: string | null;
};

export type AnalysisDetail = AnalysisSummary & {
  owner: { username: string | null; display_name: string; avatar_url: string | null };
  slug: string | null;
  confidence: string | null;
  error_message: string | null;
  current_version_id: string | null;
  is_own: boolean;
};

export async function submitAnalysis(
  idea_text: string,
  visibility: "public" | "private" = "public"
): Promise<{ analysis_id: string }> {
  const res = await fetch(`${API_BASE}/api/v1/analyses`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea_text, visibility }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Submit failed (${res.status})`);
  }
  return res.json();
}

export async function fetchAnalysis(id: string): Promise<AnalysisDetail> {
  const res = await fetch(`${API_BASE}/api/v1/analyses/${id}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(`Fetch failed (${res.status})`);
  return res.json();
}

export async function fetchMyAnalyses(): Promise<AnalysisSummary[]> {
  const res = await fetch(`${API_BASE}/api/v1/analyses`, {
    credentials: "include",
  });
  if (!res.ok) return [];
  const { items } = await res.json();
  return items;
}

export function streamUrl(id: string): string {
  return `${API_BASE}/api/v1/analyses/${id}/stream`;
}

export function reportUrl(id: string): string {
  return `${API_BASE}/api/v1/analyses/${id}/report`;
}
