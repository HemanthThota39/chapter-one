"use client";

import { useEffect, useState } from "react";
import {
  Comment,
  deleteComment,
  fetchComments,
  postComment,
} from "@/lib/social";
import { useSession } from "@/lib/session";

const URL_RE = /(https?:\/\/[^\s]+)/g;

function linkify(text: string): (string | JSX.Element)[] {
  const parts: (string | JSX.Element)[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  const regex = new RegExp(URL_RE);
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    parts.push(
      <a
        key={match.index}
        href={match[0]}
        target="_blank"
        rel="noopener noreferrer"
        className="text-blue-600 underline hover:text-blue-800"
      >
        {match[0]}
      </a>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));
  return parts;
}

type Props = { postId: string };

export default function CommentThread({ postId }: Props) {
  const session = useSession();
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchComments(postId).then((data) => {
      if (alive) {
        setComments(data);
        setLoading(false);
      }
    });
    return () => { alive = false; };
  }, [postId]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!body.trim() || posting) return;
    setPosting(true);
    try {
      const c = await postComment(postId, body.trim(), replyTo);
      setComments((prev) => [...prev, c]);
      setBody("");
      setReplyTo(null);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setPosting(false);
    }
  };

  const onDelete = async (id: string) => {
    await deleteComment(id);
    setComments((prev) =>
      prev.map((c) =>
        c.id === id ? { ...c, body: "[deleted]", is_deleted: true } : c,
      ),
    );
  };

  // Build parent → children map for flat-with-parent rendering
  const tops = comments.filter((c) => !c.parent_id);
  const children: Record<string, Comment[]> = {};
  for (const c of comments) {
    if (c.parent_id) {
      (children[c.parent_id] ??= []).push(c);
    }
  }

  return (
    <section className="mt-4 border-t border-neutral-100 pt-4">
      <h4 className="mb-3 text-sm font-semibold text-neutral-700">
        Comments
        {comments.length > 0 && ` (${comments.length})`}
      </h4>

      {loading ? (
        <div className="text-xs text-neutral-500">Loading comments...</div>
      ) : tops.length === 0 ? (
        <div className="text-xs text-neutral-500">No comments yet. Be the first.</div>
      ) : (
        <ul className="space-y-3">
          {tops.map((c) => (
            <li key={c.id}>
              <CommentRow
                c={c}
                sessionUserId={session.status === "authenticated" ? session.user.id : null}
                onReply={() => setReplyTo(c.id)}
                onDelete={() => onDelete(c.id)}
              />
              {children[c.id] && children[c.id].length > 0 && (
                <ul className="ml-8 mt-2 space-y-2 border-l border-neutral-200 pl-3">
                  {children[c.id].map((r) => (
                    <li key={r.id}>
                      <CommentRow
                        c={r}
                        sessionUserId={session.status === "authenticated" ? session.user.id : null}
                        onReply={() => setReplyTo(c.id)}
                        onDelete={() => onDelete(r.id)}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}

      {session.status === "authenticated" && (
        <form onSubmit={submit} className="mt-4 space-y-2">
          {replyTo && (
            <div className="flex items-center justify-between rounded-md bg-neutral-50 px-2 py-1 text-xs text-neutral-600">
              <span>Replying to a comment</span>
              <button
                type="button"
                onClick={() => setReplyTo(null)}
                className="text-neutral-400 hover:text-neutral-700"
              >
                Cancel
              </button>
            </div>
          )}
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Add a comment..."
            maxLength={1000}
            rows={2}
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-200"
          />
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-neutral-400">URLs auto-linkify. No markdown.</span>
            <button
              type="submit"
              disabled={posting || !body.trim()}
              className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white disabled:bg-neutral-400"
            >
              {posting ? "Posting..." : replyTo ? "Reply" : "Comment"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function CommentRow({
  c,
  sessionUserId,
  onReply,
  onDelete,
}: {
  c: Comment;
  sessionUserId: string | null;
  onReply: () => void;
  onDelete: () => void;
}) {
  const isMine = sessionUserId && sessionUserId === c.author.id;
  return (
    <div className="flex items-start gap-2">
      <a href={`/${c.author.username}`} className="shrink-0">
        {c.author.avatar_url ? (
          <img src={c.author.avatar_url} alt="" className="h-7 w-7 rounded-full object-cover" />
        ) : (
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-neutral-200 text-xs font-semibold">
            {c.author.display_name?.slice(0, 1).toUpperCase() ?? "?"}
          </span>
        )}
      </a>
      <div className="flex-1">
        <div className="text-xs text-neutral-500">
          <a href={`/${c.author.username}`} className="font-medium text-neutral-800 hover:underline">
            {c.author.display_name}
          </a>{" "}
          · <span>@{c.author.username}</span> · {timeago(c.created_at)}
          {c.is_edited && " · edited"}
        </div>
        <div className={`mt-1 text-sm ${c.is_deleted ? "italic text-neutral-400" : "text-neutral-800"}`}>
          {c.is_deleted ? "[deleted]" : linkify(c.body)}
        </div>
        {!c.is_deleted && (
          <div className="mt-1 flex items-center gap-3 text-[11px]">
            <button onClick={onReply} className="text-neutral-500 hover:text-neutral-800">
              Reply
            </button>
            {isMine && (
              <button onClick={onDelete} className="text-neutral-500 hover:text-red-600">
                Delete
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function timeago(iso: string): string {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d`;
  return d.toLocaleDateString();
}
