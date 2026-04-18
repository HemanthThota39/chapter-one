"use client";

import { useEffect, useState } from "react";

export type SessionUser = {
  id: string;
  external_id: string;
  email: string;
  username: string | null;
  display_name: string;
  avatar_url: string | null;
  avatar_kind: "upload" | "library" | "initials";
  avatar_seed: string | null;
  timezone: string;
  default_visibility: "public" | "private";
  total_analyses: number;
  current_streak: number;
  longest_streak: number;
  fires_received: number;
  onboarding_complete: boolean;
};

export type SessionState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "authenticated"; user: SessionUser };

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function fetchSession(): Promise<SessionState> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/session`, {
      credentials: "include",
    });
    if (res.status === 401) return { status: "unauthenticated" };
    if (!res.ok) return { status: "unauthenticated" };
    const { user } = await res.json();
    return { status: "authenticated", user };
  } catch {
    return { status: "unauthenticated" };
  }
}

export function useSession(): SessionState {
  const [state, setState] = useState<SessionState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchSession().then((s) => {
      if (!cancelled) setState(s);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

export function loginUrl(redirect?: string): string {
  const params = redirect
    ? `?redirect=${encodeURIComponent(redirect)}`
    : "";
  return `${API_BASE}/api/v1/auth/login${params}`;
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/v1/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}
