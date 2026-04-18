"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import { FeedItem, fetchFeed } from "@/lib/social";
import AppShell from "@/components/AppShell";
import PostCard from "@/components/PostCard";
import CommentThread from "@/components/CommentThread";

export default function FeedPage() {
  const session = useSession();
  const router = useRouter();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openComments, setOpenComments] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
    if (session.status === "authenticated" && !session.user.onboarding_complete) {
      router.replace("/onboarding");
    }
  }, [session, router]);

  useEffect(() => {
    if (session.status !== "authenticated") return;
    fetchFeed().then(({ items, next_cursor }) => {
      setItems(items);
      setNextCursor(next_cursor);
      setLoading(false);
    });
  }, [session.status]);

  const loadMore = useCallback(async () => {
    if (!nextCursor) return;
    const { items: more, next_cursor } = await fetchFeed(nextCursor);
    setItems((prev) => [...prev, ...more]);
    setNextCursor(next_cursor);
  }, [nextCursor]);

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
      {loading ? (
        <div className="py-10 text-center text-sm text-neutral-500">Loading feed…</div>
      ) : items.length === 0 ? (
        <div className="card flex flex-col items-center gap-3 p-8 text-center">
          <p className="text-sm text-neutral-700">The feed is quiet right now.</p>
          <a href="/new" className="btn-primary">Submit the first idea</a>
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
        <div className="mt-6 flex justify-center">
          <button onClick={loadMore} className="btn-secondary">Load more</button>
        </div>
      )}
    </AppShell>
  );
}
