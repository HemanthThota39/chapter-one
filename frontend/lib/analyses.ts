import { API_BASE } from "@/lib/session";

async function fetchWithTimeout(url: string, init: RequestInit, ms: number): Promise<Response> {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ac.signal });
  } finally {
    clearTimeout(timer);
  }
}

function wrapNetworkError(url: string, e: unknown): Error {
  const err = e as Error;
  const name = err?.name ?? "Error";
  if (name === "AbortError") return new Error("Request timed out. Check your connection and try again.");
  // eslint-disable-next-line no-console
  console.error("[chapter-one] request failed", { url, name, message: err?.message, err });
  return new Error(`Couldn't reach the server (${name}).`);
}

export type AnalysisSummary = {
  id: string;
  idea_title: string | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  visibility: "public" | "private";
  overall_score_100: number | null;
  verdict: string | null;
  submitted_at: string | null;
  completed_at: string | null;
  post_id: string | null;
  fire_count: number;
  comment_count: number;
  i_fired: boolean;
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

export function reportPdfUrl(id: string): string {
  return `${API_BASE}/api/v1/analyses/${id}/report.pdf`;
}

export async function retryAnalysis(id: string): Promise<void> {
  const url = `${API_BASE}/api/v1/analyses/${id}/retry`;
  let res: Response;
  try {
    res = await fetchWithTimeout(url, { method: "POST", credentials: "include" }, 30000);
  } catch (e) {
    throw wrapNetworkError(url, e);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Retry failed (${res.status})`);
  }
}

export async function deleteAnalysis(id: string): Promise<void> {
  const url = `${API_BASE}/api/v1/analyses/${id}`;
  let res: Response;
  try {
    res = await fetchWithTimeout(url, { method: "DELETE", credentials: "include" }, 30000);
  } catch (e) {
    throw wrapNetworkError(url, e);
  }
  if (!res.ok && res.status !== 204) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Delete failed (${res.status})`);
  }
}

export async function setVisibility(id: string, visibility: "public" | "private"): Promise<void> {
  const url = `${API_BASE}/api/v1/analyses/${id}`;
  let res: Response;
  try {
    res = await fetchWithTimeout(
      url,
      {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ visibility }),
      },
      30000,
    );
  } catch (e) {
    throw wrapNetworkError(url, e);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Visibility change failed (${res.status})`);
  }
}
