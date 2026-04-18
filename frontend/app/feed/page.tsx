"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import { FeedItem, fetchFeed } from "@/lib/social";
import Header from "@/components/Header";
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
    <main className="mx-auto max-w-2xl px-4 py-6 md:px-6">
      <Header title="Feed" subtitle="Ideas from your circle" />

      {loading ? (
        <div className="text-sm text-neutral-500">Loading feed...</div>
      ) : items.length === 0 ? (
        <div className="rounded-md border-2 border-dashed border-neutral-300 bg-white p-8 text-center">
          <p className="text-sm text-neutral-700">The feed is quiet right now.</p>
          <a
            href="/new"
            className="mt-3 inline-block rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
          >
            Submit the first idea
          </a>
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
          <button
            onClick={loadMore}
            className="rounded-md border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100"
          >
            Load more
          </button>
        </div>
      )}
    </main>
  );
}
