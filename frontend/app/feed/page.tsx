"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import { FeedItem, fetchFeed } from "@/lib/social";
import { setCached, useSWR } from "@/lib/cache";
import AppShell from "@/components/AppShell";
import PostCard from "@/components/PostCard";
import CommentThread from "@/components/CommentThread";

export default function FeedPage() {
  const session = useSession();
  const router = useRouter();
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [extra, setExtra] = useState<FeedItem[]>([]);
  const [openComments, setOpenComments] = useState<Set<string>>(new Set());
  const [loadMoreErr, setLoadMoreErr] = useState<string | null>(null);

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
    if (session.status === "authenticated" && !session.user.onboarding_complete) {
      router.replace("/onboarding");
    }
  }, [session, router]);

  const {
    data, error, loading, mutate,
  } = useSWR<{ items: FeedItem[]; next_cursor: string | null }>(
    session.status === "authenticated" ? "feed:first" : null,
    fetchFeed,
  );

  useEffect(() => {
    if (data?.next_cursor !== undefined) setNextCursor(data.next_cursor);
  }, [data?.next_cursor]);

  const items = [...(data?.items ?? []), ...extra];

  const loadMore = useCallback(async () => {
    if (!nextCursor) return;
    try {
      const { items: more, next_cursor } = await fetchFeed(nextCursor);
      setExtra((prev) => [...prev, ...more]);
      setNextCursor(next_cursor);
    } catch (e) {
      setLoadMoreErr((e as Error).message || "Failed to load more");
    }
  }, [nextCursor]);

  const refresh = useCallback(async () => {
    try {
      const fresh = await fetchFeed();
      setCached("feed:first", fresh);
      mutate(fresh);
      setExtra([]);
      setNextCursor(fresh.next_cursor);
    } catch {/* ignore */}
  }, [mutate]);
  // Background refresh on tab focus — makes the feed feel live.
  useEffect(() => {
    const onFocus = () => { if (session.status === "authenticated") refresh(); };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh, session.status]);

  const toggleCommentsFor = useCallback((postId: string) => {
    setOpenComments((prev) => {
      const next = new Set(prev);
      if (next.has(postId)) next.delete(postId);
      else next.add(postId);
      return next;
    });
  }, []);

  if (session.status !== "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-neutral-500">Loading...</div>
      </main>
    );
  }

  return (
    <AppShell title="Feed">
      {loading && items.length === 0 ? (
        <FeedSkeleton />
      ) : error && items.length === 0 ? (
        <div className="card flex flex-col items-center gap-3 p-8 text-center">
          <p className="text-sm text-red-600 break-anywhere">{error.message}</p>
          <button onClick={refresh} className="btn-secondary">Retry</button>
        </div>
      ) : items.length === 0 ? (
        <div className="card flex flex-col items-center gap-3 p-8 text-center">
          <p className="text-sm text-neutral-700">The feed is quiet right now.</p>
          <Link href="/new" className="btn-primary">Submit the first idea</Link>
        </div>
      ) : (
        <ul className="space-y-4">
          {items.map((item) => (
            <li key={item.post_id}>
              <PostCard item={item} onOpenComments={toggleCommentsFor} />
              {openComments.has(item.post_id) && <CommentThread postId={item.post_id} />}
            </li>
          ))}
        </ul>
      )}

      {nextCursor && (
        <div className="mt-6 flex flex-col items-center gap-2">
          <button onClick={loadMore} className="btn-secondary">Load more</button>
          {loadMoreErr && <p className="text-xs text-red-600">{loadMoreErr}</p>}
        </div>
      )}
    </AppShell>
  );
}

function FeedSkeleton() {
  return (
    <ul className="space-y-4">
      {[0, 1, 2].map((i) => (
        <li key={i} className="card animate-pulse p-4">
          <div className="mb-3 flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-neutral-200" />
            <div className="flex-1">
              <div className="mb-1 h-3 w-32 rounded bg-neutral-200" />
              <div className="h-2.5 w-20 rounded bg-neutral-100" />
            </div>
          </div>
          <div className="mb-2 h-4 w-4/5 rounded bg-neutral-200" />
          <div className="mb-1 h-3 w-3/5 rounded bg-neutral-100" />
          <div className="mt-4 flex gap-3">
            <div className="h-6 w-14 rounded-full bg-neutral-100" />
            <div className="h-6 w-14 rounded-full bg-neutral-100" />
          </div>
        </li>
      ))}
    </ul>
  );
}
