import { API_BASE } from "@/lib/session";

export type FeedOwner = {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  avatar_kind: "initials" | "library" | "upload";
  avatar_seed: string | null;
};

export type FeedItem = {
  post_id: string;
  analysis_id: string;
  owner: FeedOwner;
  idea_title: string | null;
  slug: string | null;
  verdict: string | null;
  overall_score_100: number | null;
  caption: string | null;
  published_at: string | null;
  fire_count: number;
  comment_count: number;
  i_fired: boolean;
};

export type Comment = {
  id: string;
  post_id: string;
  parent_id: string | null;
  body: string;
  is_edited: boolean;
  is_deleted: boolean;
  created_at: string;
  edited_at: string | null;
  author: {
    id: string;
    username: string;
    display_name: string;
    avatar_url: string | null;
    avatar_kind: string;
    avatar_seed: string | null;
  };
};

export type Notification = {
  id: string;
  kind:
    | "fire"
    | "comment"
    | "reply"
    | "debate_turn"
    | "patch_pending"
    | "streak_warning"
    | "streak_broken"
    | "analysis_done";
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
};

export async function fetchFeed(cursor?: string): Promise<{ items: FeedItem[]; next_cursor: string | null }> {
  const q = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  const res = await fetch(`${API_BASE}/api/v1/feed${q}`, { credentials: "include" });
  if (!res.ok) return { items: [], next_cursor: null };
  return res.json();
}

export async function toggleFire(postId: string): Promise<{ fired: boolean; fire_count: number }> {
  const res = await fetch(`${API_BASE}/api/v1/posts/${postId}/fires`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) throw new Error("fire failed");
  return res.json();
}

export async function fetchComments(postId: string): Promise<Comment[]> {
  const res = await fetch(`${API_BASE}/api/v1/posts/${postId}/comments`, { credentials: "include" });
  if (!res.ok) return [];
  const data = await res.json();
  return data.items;
}

export async function postComment(
  postId: string,
  body: string,
  parentId?: string | null,
): Promise<Comment> {
  const res = await fetch(`${API_BASE}/api/v1/posts/${postId}/comments`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body, parent_id: parentId ?? null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(err?.detail || `Comment failed (${res.status})`);
  }
  const data = await res.json();
  return data.comment;
}

export async function deleteComment(commentId: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/comments/${commentId}`, {
    method: "DELETE",
    credentials: "include",
  });
}

export async function fetchNotifications(
  filter: "all" | "unread" = "all",
  cursor?: string,
): Promise<{ items: Notification[]; unread_count: number; next_cursor: string | null }> {
  const params = new URLSearchParams({ filter, ...(cursor ? { cursor } : {}) });
  const res = await fetch(`${API_BASE}/api/v1/notifications?${params}`, {
    credentials: "include",
  });
  if (!res.ok) return { items: [], unread_count: 0, next_cursor: null };
  return res.json();
}

export async function markNotificationRead(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/notifications/${id}/read`, {
    method: "PATCH",
    credentials: "include",
  });
}

export async function markAllNotificationsRead(): Promise<void> {
  await fetch(`${API_BASE}/api/v1/notifications/read-all`, {
    method: "POST",
    credentials: "include",
  });
}

export async function clearNotification(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/v1/notifications/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
}

export async function clearAllNotifications(): Promise<void> {
  await fetch(`${API_BASE}/api/v1/notifications`, {
    method: "DELETE",
    credentials: "include",
  });
}

export function notificationsStreamUrl(): string {
  return `${API_BASE}/api/v1/notifications/stream`;
}
