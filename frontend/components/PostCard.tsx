"use client";

import { useState } from "react";
import { FeedItem, toggleFire } from "@/lib/social";

type Props = {
  item: FeedItem;
  onOpenComments?: (postId: string) => void;
};

export default function PostCard({ item, onOpenComments }: Props) {
  const [fired, setFired] = useState(item.i_fired);
  const [count, setCount] = useState(item.fire_count);
  const [busy, setBusy] = useState(false);

  const handleFire = async () => {
    if (busy) return;
    setBusy(true);
    // Optimistic
    const prev = { fired, count };
    setFired(!fired);
    setCount(fired ? Math.max(0, count - 1) : count + 1);
    try {
      const r = await toggleFire(item.post_id);
      setFired(r.fired);
      setCount(r.fire_count);
    } catch {
      setFired(prev.fired);
      setCount(prev.count);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="card p-4">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <a href={`/${item.owner.username}`} className="shrink-0">
            {item.owner.avatar_url ? (
              <img src={item.owner.avatar_url} alt="" className="h-10 w-10 rounded-full object-cover" />
            ) : (
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-neutral-200 font-semibold text-neutral-700">
                {item.owner.display_name.slice(0, 1).toUpperCase()}
              </span>
            )}
          </a>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">
              <a href={`/${item.owner.username}`} className="hover:underline">
                {item.owner.display_name}
              </a>{" "}
              <span className="text-neutral-500">@{item.owner.username}</span>
            </div>
            <div className="text-xs text-neutral-500">
              {item.published_at && timeago(item.published_at)}
            </div>
          </div>
        </div>
      </header>

      <h3 className="mb-2 text-base font-semibold tracking-tight text-neutral-900 break-anywhere">
        <a href={`/analyses/${item.analysis_id}`} className="hover:underline">
          {item.idea_title ?? "Untitled analysis"}
        </a>
      </h3>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        {item.verdict && (
          <span className={`rounded-full px-2.5 py-0.5 font-semibold ${verdictColor(item.verdict)}`}>
            {item.verdict}
          </span>
        )}
        {item.overall_score_100 != null && (
          <span className="rounded-full bg-neutral-100 px-2.5 py-0.5 font-semibold text-neutral-800">
            {item.overall_score_100}/100
          </span>
        )}
      </div>

      {item.caption && (
        <p className="mb-3 text-sm text-neutral-700 break-anywhere">{item.caption}</p>
      )}

      <footer className="flex items-center gap-2 border-t border-neutral-100 pt-3 text-sm">
        <button
          onClick={handleFire}
          disabled={busy}
          className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs transition active:scale-95 ${fired ? "bg-orange-50 text-orange-700" : "text-neutral-600 hover:bg-neutral-100"}`}
          aria-pressed={fired}
        >
          <span className={fired ? "animate-pop" : ""}>🔥</span>
          <span className="font-semibold">{count}</span>
        </button>
        <button
          onClick={() => onOpenComments?.(item.post_id)}
          className="flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-neutral-600 transition hover:bg-neutral-100"
        >
          💬 <span className="font-semibold">{item.comment_count}</span>
        </button>
        <a
          href={`/analyses/${item.analysis_id}`}
          className="ml-auto text-xs font-medium text-neutral-700 hover:underline"
        >
          View report →
        </a>
      </footer>
    </article>
  );
}

function verdictColor(v: string): string {
  if (v === "STRONG INVEST") return "bg-green-100 text-green-800";
  if (v === "CONDITIONAL") return "bg-blue-100 text-blue-800";
  if (v === "WATCH") return "bg-yellow-100 text-yellow-800";
  if (v === "PASS" || v === "HARD PASS") return "bg-red-100 text-red-800";
  return "bg-neutral-100 text-neutral-700";
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
