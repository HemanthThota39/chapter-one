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
  unreadCount: number;
};

const SessionContext = createContext<SessionContextValue | null>(null);

function notificationsStreamUrl(): string {
  return `${API_BASE}/api/v1/notifications/stream`;
}

/** Root-level provider: fetches the session ONCE for the whole tree,
 *  opens exactly ONE notifications EventSource for the whole session,
 *  and exposes a refresh() so pages can pull fresh profile data after
 *  mutations. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<SessionState>({ status: "loading" });
  const [unreadCount, setUnreadCount] = useState<number>(0);

  const refresh = useCallback(async () => {
    const s = await fetchSession();
    setSession(s);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchSession().then((s) => { if (!cancelled) setSession(s); });
    return () => { cancelled = true; };
  }, []);

  // Background revalidation: when the user returns to the tab after being
  // away (SSE torn down, cookie possibly rotated on the server, or tab
  // suspended), quietly re-fetch session. We intentionally don't reset the
  // existing session to "loading" — if the refresh succeeds we swap to the
  // newer payload without any UI flicker.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        fetchSession().then((s) => {
          // Only apply if we actually got a resolved state back.
          if (s.status !== "loading") setSession(s);
        }).catch(() => {/* keep previous session */});
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, []);

  // Single notifications SSE for the entire app lifetime. Previously lived
  // inside <AppShell> which remounts on every page navigation — that was
  // opening a new SSE stream each time and accumulating ghost connections
  // that throttled further fetches.
  useEffect(() => {
    if (session.status !== "authenticated") return;
    const es = new EventSource(notificationsStreamUrl(), { withCredentials: true });
    es.addEventListener("unread_count", (ev) => {
      try {
        const { unread_count } = JSON.parse((ev as MessageEvent).data);
        setUnreadCount(unread_count);
      } catch {/* ignore */}
    });
    es.onerror = () => {/* browser auto-reconnects */};
    return () => es.close();
  }, [session.status]);

  return React.createElement(
    SessionContext.Provider,
    { value: { session, refresh, unreadCount } },
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

/** Read the live unread-notifications count driven by the single
 *  SessionProvider-owned EventSource. Returns 0 if no provider is mounted. */
export function useUnreadCount(): number {
  const ctx = useContext(SessionContext);
  return ctx?.unreadCount ?? 0;
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
