"use client";

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

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

async function fetchSessionOnce(timeoutMs: number): Promise<SessionState> {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/session`, {
      credentials: "include",
      signal: ac.signal,
    });
    if (res.status === 401) return { status: "unauthenticated" };
    if (!res.ok) return { status: "unauthenticated" };
    const { user } = await res.json();
    return { status: "authenticated", user };
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchSession(): Promise<SessionState> {
  // Try once with a short timeout; if it stalls (typical during a rolling
  // backend deploy), retry once with a longer window. Only after both
  // attempts fail do we fall through to "unauthenticated" — stalling
  // forever in "loading" would trap the whole UI.
  try {
    return await fetchSessionOnce(6000);
  } catch {
    try {
      return await fetchSessionOnce(12000);
    } catch {
      return { status: "unauthenticated" };
    }
  }
}

type SessionContextValue = {
  session: SessionState;
  refresh: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

/** Root-level provider: fetches the session ONCE for the whole tree and
 *  exposes a refresh() so pages can pull fresh profile data after mutations. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionState>({ status: "loading" });

  const refresh = useCallback(async () => {
    const s = await fetchSession();
    setSession(s);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchSession().then((s) => { if (!cancelled) setSession(s); });
    return () => { cancelled = true; };
  }, []);

  return React.createElement(
    SessionContext.Provider,
    { value: { session, refresh } },
    children,
  );
}

/** Access the shared session state. Must be used under <SessionProvider>. */
export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    // Provider always mounted in app/layout.tsx, so this only hits in tests /
    // storybook — yield a safe default to avoid crashing the whole tree.
    return { status: "loading" };
  }
  return ctx.session;
}

/** Access the session refresher. Returns a no-op if no provider is mounted. */
export function useSessionRefresh(): () => Promise<void> {
  const ctx = useContext(SessionContext);
  return ctx?.refresh ?? (async () => {/* no provider */});
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
