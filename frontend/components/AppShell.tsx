"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import { notificationsStreamUrl } from "@/lib/social";

type Props = {
  children: React.ReactNode;
  title?: string;
  /** "narrow" (default) is a tight 672px column for social/feed content.
   *  "wide" uses ~1120px so long-form reports can breathe on desktop. */
  width?: "narrow" | "wide";
};

export default function AppShell({ children, title, width = "narrow" }: Props) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname() || "/";
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (session.status !== "authenticated") return;
    const es = new EventSource(notificationsStreamUrl(), { withCredentials: true });
    es.addEventListener("unread_count", (ev) => {
      try {
        const { unread_count } = JSON.parse((ev as MessageEvent).data);
        setUnread(unread_count);
      } catch {/* ignore */}
    });
    es.onerror = () => {/* browser auto-reconnects */};
    return () => es.close();
  }, [session.status]);

  if (session.status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center text-sm text-neutral-500">
        Loading…
      </main>
    );
  }

  if (session.status !== "authenticated") {
    // Auth-gated pages handle redirects themselves — this path shouldn't normally hit.
    return <>{children}</>;
  }

  const user = session.user;
  const streak = user.current_streak ?? 0;
  const maxW = width === "wide" ? "max-w-5xl" : "max-w-2xl";
  const isActive = (href: string) => {
    if (href === "/feed") return pathname === "/feed";
    if (href === "/notifications") return pathname.startsWith("/notifications");
    if (href === `/${user.username}`) return pathname === `/${user.username}`;
    return false;
  };

  return (
    <div className="min-h-screen bg-neutral-50 pb-24">
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-neutral-200 bg-white/85 backdrop-blur supports-[backdrop-filter]:bg-white/70">
        <div className={`mx-auto flex h-14 ${maxW} items-center justify-between px-4 md:px-6`}>
          <button
            onClick={() => router.push(user.username ? `/${user.username}` : "/feed")}
            className="flex items-center gap-2 rounded-full py-1 pr-2 transition hover:bg-neutral-100"
            aria-label="Profile"
          >
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" className="h-8 w-8 rounded-full object-cover" />
            ) : (
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-neutral-200 text-xs font-semibold text-neutral-700">
                {user.display_name.slice(0, 1).toUpperCase()}
              </span>
            )}
            {streak > 0 && (
              <span
                className="flex items-center gap-0.5 rounded-full bg-orange-50 px-2 py-0.5 text-[11px] font-semibold text-orange-700 ring-1 ring-orange-200"
                title={`${streak}-day streak`}
              >
                <span aria-hidden>🔥</span>
                <span>{streak}</span>
              </span>
            )}
          </button>

          {title && (
            <h1 className="truncate text-sm font-semibold tracking-tight text-neutral-800">
              {title}
            </h1>
          )}

          <button
            onClick={() => router.push("/settings")}
            className="rounded-full p-2 text-neutral-600 transition hover:bg-neutral-100 hover:text-neutral-900"
            aria-label="Settings"
          >
            <SettingsIcon />
          </button>
        </div>
      </header>

      {/* Content */}
      <div className={`mx-auto w-full ${maxW} px-4 py-5 md:px-6`}>
        {children}
      </div>

      {/* Bottom nav (Instagram-style) — fixed, safe-area aware */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 border-t border-neutral-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/85"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="mx-auto grid max-w-xl grid-cols-5 items-end">
          <NavTab
            href="/feed"
            active={isActive("/feed")}
            label="Feed"
            icon={<HomeIcon active={isActive("/feed")} />}
            onClick={() => router.push("/feed")}
          />
          <NavTab
            href="/notifications"
            active={isActive("/notifications")}
            label="Alerts"
            badge={unread}
            icon={<BellIcon active={isActive("/notifications")} />}
            onClick={() => router.push("/notifications")}
          />
          {/* Hero "+" — visually centered, elevated, rounded */}
          <div className="relative flex items-start justify-center">
            <button
              onClick={() => router.push("/new")}
              aria-label="New idea"
              className="-translate-y-4 rounded-full bg-neutral-900 p-4 text-white shadow-lg shadow-neutral-900/25 ring-4 ring-white transition active:scale-95 hover:bg-neutral-700"
            >
              <PlusIcon />
            </button>
          </div>
          <NavTab
            href={`/${user.username ?? ""}`}
            active={isActive(`/${user.username}`)}
            label="Profile"
            icon={<UserIcon active={isActive(`/${user.username}`)} />}
            onClick={() => router.push(`/${user.username ?? ""}`)}
          />
          <NavTab
            href="/settings"
            active={pathname === "/settings"}
            label="Settings"
            icon={<SettingsIcon active={pathname === "/settings"} />}
            onClick={() => router.push("/settings")}
          />
        </div>
      </nav>
    </div>
  );
}

function NavTab({
  active,
  label,
  icon,
  badge,
  onClick,
}: {
  href: string;
  active: boolean;
  label: string;
  icon: React.ReactNode;
  badge?: number;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative flex h-16 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition ${
        active ? "text-neutral-900" : "text-neutral-500 hover:text-neutral-800"
      }`}
    >
      <div className="relative">
        {icon}
        {badge != null && badge > 0 && (
          <span className="absolute -right-2 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white">
            {badge > 99 ? "99+" : badge}
          </span>
        )}
      </div>
      <span>{label}</span>
    </button>
  );
}

/* -- Icons (stroke = 1.75, size = 22 for tabs, 20 for top bar) ------------ */

function HomeIcon({ active }: { active?: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={active ? 2.25 : 1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
    </svg>
  );
}

function BellIcon({ active }: { active?: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={active ? 2.25 : 1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 16v-5a6 6 0 1 0-12 0v5l-2 2h16l-2-2Z" />
      <path d="M10 21a2 2 0 0 0 4 0" />
    </svg>
  );
}

function UserIcon({ active }: { active?: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={active ? 2.25 : 1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" />
    </svg>
  );
}

function SettingsIcon({ active }: { active?: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={active ? 2.25 : 1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.36.15.68.38.95.66.26.27.48.59.61.94.13.35.17.72.13 1.08Z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}
