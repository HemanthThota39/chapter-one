"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import {
  Notification,
  clearAllNotifications,
  clearNotification,
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/social";
import Header from "@/components/Header";

export default function NotificationsPage() {
  const session = useSession();
  const router = useRouter();
  const [items, setItems] = useState<Notification[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
  }, [session.status, router]);

  const load = async (f: "all" | "unread") => {
    setLoading(true);
    const data = await fetchNotifications(f);
    setItems(data.items);
    setUnread(data.unread_count);
    setLoading(false);
  };

  useEffect(() => {
    if (session.status === "authenticated") load(filter);
  }, [session.status, filter]);

  if (session.status !== "authenticated") {
    return <main className="flex min-h-screen items-center justify-center text-sm text-neutral-500">Loading...</main>;
  }

  const onOpen = async (n: Notification) => {
    if (!n.read_at) await markNotificationRead(n.id);
    setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)));
    setUnread((u) => Math.max(0, u - (n.read_at ? 0 : 1)));
    const target = destinationUrl(n);
    if (target) router.push(target);
  };

  const onClear = async (id: string) => {
    await clearNotification(id);
    setItems((prev) => prev.filter((x) => x.id !== id));
  };

  return (
    <main className="mx-auto max-w-2xl px-4 py-6 md:px-6">
      <Header title="Notifications" subtitle={`${unread} unread`} />

      <div className="mb-4 flex items-center justify-between">
        <div className="flex gap-2 text-xs">
          <button
            onClick={() => setFilter("all")}
            className={`rounded-md px-3 py-1 ${filter === "all" ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-700"}`}
          >
            All
          </button>
          <button
            onClick={() => setFilter("unread")}
            className={`rounded-md px-3 py-1 ${filter === "unread" ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-700"}`}
          >
            Unread
          </button>
        </div>
        <div className="flex gap-2 text-xs">
          <button
            onClick={async () => { await markAllNotificationsRead(); await load(filter); }}
            className="rounded-md border border-neutral-300 px-3 py-1 hover:bg-neutral-100"
          >
            Mark all read
          </button>
          <button
            onClick={async () => { await clearAllNotifications(); await load(filter); }}
            className="rounded-md border border-neutral-300 px-3 py-1 hover:bg-neutral-100"
          >
            Clear all
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-sm text-neutral-500">Loading...</div>
      ) : items.length === 0 ? (
        <div className="rounded-md border-2 border-dashed border-neutral-300 bg-white p-8 text-center text-sm text-neutral-500">
          {filter === "unread" ? "All caught up." : "No notifications yet."}
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map((n) => (
            <li
              key={n.id}
              onClick={() => onOpen(n)}
              className={`cursor-pointer rounded-md border p-3 transition hover:bg-neutral-50 ${n.read_at ? "border-neutral-200 bg-white" : "border-blue-300 bg-blue-50"}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="text-lg">{kindIcon(n.kind)}</span>
                  <div>
                    <div className="text-sm">
                      {describe(n)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-neutral-400">
                      {timeago(n.created_at)}
                    </div>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); onClear(n.id); }}
                  className="text-[11px] text-neutral-400 hover:text-red-600"
                >
                  Clear
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function kindIcon(k: Notification["kind"]): string {
  switch (k) {
    case "fire": return "🔥";
    case "comment": return "💬";
    case "reply": return "↪️";
    case "debate_turn": return "🗣️";
    case "patch_pending": return "✏️";
    case "streak_warning": return "⚠️";
    case "streak_broken": return "💔";
    case "analysis_done": return "✅";
  }
}

function describe(n: Notification): string {
  const p = n.payload as any;
  const actor = p?.actor_username ? `@${p.actor_username}` : "Someone";
  switch (n.kind) {
    case "fire": return `${actor} dropped a 🔥 on your idea`;
    case "comment": return `${actor} commented: "${(p?.preview ?? "").slice(0, 80)}"`;
    case "reply": return `${actor} replied: "${(p?.preview ?? "").slice(0, 80)}"`;
    case "debate_turn": return `${actor} debated your report`;
    case "patch_pending": return `${actor} proposed a change to your report`;
    case "streak_warning": return `Your streak expires in ${p?.hours_remaining ?? "a few"}h`;
    case "streak_broken": return `Your ${p?.previous_streak ?? ""}-day streak ended`;
    case "analysis_done": return `Your analysis finished · ${p?.verdict ?? ""}`;
  }
}

function destinationUrl(n: Notification): string | null {
  const p = n.payload as any;
  if (p?.analysis_id) return `/analyses/${p.analysis_id}`;
  return null;
}

function timeago(iso: string): string {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}
