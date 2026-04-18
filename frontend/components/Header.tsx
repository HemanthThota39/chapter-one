"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { logout, useSession } from "@/lib/session";
import { notificationsStreamUrl } from "@/lib/social";

type Props = {
  title?: string;
  subtitle?: string;
};

export default function Header({ title, subtitle }: Props) {
  const session = useSession();
  const router = useRouter();
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
    es.addEventListener("new", () => {
      // The 'unread_count' event will follow; no-op here.
    });
    es.onerror = () => {/* browser auto-reconnects */};
    return () => es.close();
  }, [session.status]);

  if (session.status !== "authenticated") return null;
  const user = session.user;

  return (
    <header className="mb-6 flex items-center justify-between border-b border-neutral-200 pb-4">
      <div>
        <h1 className="text-xl font-bold tracking-tight">
          <a href="/feed" className="hover:underline">{title ?? "Feed"}</a>
        </h1>
        {subtitle && <p className="text-xs text-neutral-500">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-3">
        <a
          href="/new"
          className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700"
        >
          + New idea
        </a>
        <a
          href="/notifications"
          className="relative rounded-md px-2 py-1 text-sm hover:bg-neutral-100"
          aria-label="Notifications"
        >
          🔔
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </a>
        <a
          href={`/${user.username}`}
          className="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-neutral-100"
        >
          {user.avatar_url ? (
            <img src={user.avatar_url} alt="" className="h-7 w-7 rounded-full object-cover" />
          ) : (
            <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-neutral-200 text-xs font-semibold">
              {user.display_name.slice(0, 1).toUpperCase()}
            </span>
          )}
          <span className="hidden text-xs sm:inline">@{user.username}</span>
        </a>
        <button
          onClick={async () => { await logout(); router.replace("/"); }}
          className="text-xs text-neutral-500 hover:text-neutral-800"
        >
          Log out
        </button>
      </div>
    </header>
  );
}
