"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_BASE, useSession } from "@/lib/session";
import { AnalysisSummary, deleteAnalysis, fetchMyAnalyses } from "@/lib/analyses";
import AppShell from "@/components/AppShell";

type PublicProfile = {
  username: string;
  display_name: string;
  avatar_url: string | null;
  avatar_kind: string;
  avatar_seed: string | null;
  joined_at: string;
  total_analyses: number;
  current_streak: number;
  longest_streak: number;
  fires_received: number;
};

type PublicAnalysis = {
  id: string;
  idea_title: string | null;
  slug: string | null;
  verdict: string | null;
  overall_score_100: number | null;
  completed_at: string | null;
  post_id: string | null;
  fire_count: number;
  comment_count: number;
};

const RESERVED_PATHS = new Set([
  "settings", "onboarding", "feed", "new", "analyses",
  "api", "login", "logout", "signup", "me",
  "favicon.ico", "robots.txt", "sitemap.xml",
]);

export default function ProfilePage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = use(params);
  const session = useSession();
  const router = useRouter();

  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mine, setMine] = useState<AnalysisSummary[] | null>(null);
  const [theirs, setTheirs] = useState<PublicAnalysis[] | null>(null);
  const [showFailed, setShowFailed] = useState(false);

  useEffect(() => {
    if (RESERVED_PATHS.has(username.toLowerCase())) {
      router.replace("/feed");
      return;
    }
    let alive = true;
    fetch(`${API_BASE}/api/v1/users/${username}`, { credentials: "include" })
      .then(async (r) => {
        if (!alive) return;
        if (r.status === 404) { setError("not_found"); return; }
        if (!r.ok) throw new Error(`status ${r.status}`);
        const data = await r.json();
        setProfile(data.user);
      })
      .catch((e) => { if (alive) setError((e as Error).message); });
    return () => { alive = false; };
  }, [username, router]);

  const isSelf =
    session.status === "authenticated" &&
    !!profile &&
    session.user.username === profile.username;

  // Load own analyses (all statuses) when viewing self; public ones otherwise.
  useEffect(() => {
    if (!profile) return;
    let alive = true;
    if (isSelf) {
      fetchMyAnalyses()
        .then((items) => { if (alive) setMine(items); })
        .catch(() => { if (alive) setMine([]); });
    } else {
      fetch(`${API_BASE}/api/v1/users/${profile.username}/analyses`, { credentials: "include" })
        .then(async (r) => r.ok ? r.json() : { items: [] })
        .then((d) => { if (alive) setTheirs(d.items); })
        .catch(() => { if (alive) setTheirs([]); });
    }
    return () => { alive = false; };
  }, [profile, isSelf]);

  // Poll while any of my analyses are still running — every 5s.
  const hasRunning = (mine ?? []).some((a) => a.status === "queued" || a.status === "running");
  useEffect(() => {
    if (!isSelf || !hasRunning) return;
    const t = setInterval(() => {
      fetchMyAnalyses().then((items) => setMine(items)).catch(() => {/* keep old */});
    }, 5000);
    return () => clearInterval(t);
  }, [isSelf, hasRunning]);

  if (error === "not_found") {
    return (
      <AppShell title="Profile">
        <div className="card p-8 text-center">
          <h1 className="text-lg font-semibold">User not found</h1>
          <p className="mt-2 text-sm text-neutral-500 break-anywhere">
            @{username} isn't a Chapter One account.
          </p>
        </div>
      </AppShell>
    );
  }
  if (error) {
    return (
      <AppShell title="Profile">
        <div className="card p-8 text-center">
          <p className="text-sm text-red-600 break-anywhere">Couldn't load profile: {error}</p>
        </div>
      </AppShell>
    );
  }
  if (!profile) {
    return (
      <AppShell title="Profile">
        <ProfileSkeleton />
      </AppShell>
    );
  }

  const running = (mine ?? []).filter((a) => a.status === "queued" || a.status === "running");
  const done = (mine ?? []).filter((a) => a.status === "done");
  const failed = (mine ?? []).filter((a) => a.status === "failed");

  return (
    <AppShell title={profile.display_name}>
      <header className="mb-5 flex items-start gap-4">
        {profile.avatar_url ? (
          <img src={profile.avatar_url} alt="" className="h-20 w-20 shrink-0 rounded-full object-cover shadow" />
        ) : (
          <span className="inline-flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-neutral-200 text-2xl font-semibold">
            {profile.display_name.slice(0, 1).toUpperCase()}
          </span>
        )}
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold tracking-tight break-anywhere">{profile.display_name}</h1>
          <p className="text-sm text-neutral-500 break-anywhere">@{profile.username}</p>
          <p className="mt-1 text-xs text-neutral-400">
            Joined {new Date(profile.joined_at).toLocaleDateString()}
          </p>
        </div>
      </header>

      <section className="grid grid-cols-4 gap-2.5">
        <Stat label="Ideas" value={profile.total_analyses} />
        <Stat label="🔥 Streak" value={profile.current_streak} highlight={profile.current_streak >= 7} />
        <Stat label="Longest" value={profile.longest_streak} />
        <Stat label="🔥 Got" value={profile.fires_received} />
      </section>

      <section className="mt-8">
        {isSelf && running.length > 0 && (
          <InProgressStrip items={running} />
        )}

        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-700">
            {isSelf ? "Your ideas" : "Public ideas"}{" "}
            <span className="text-neutral-400">·</span>{" "}
            <span className="text-neutral-500">
              {isSelf ? done.length : theirs?.length ?? 0}
            </span>
          </h2>
        </div>

        {isSelf ? (
          mine === null ? <GridSkeleton /> : (
            <MineGrid
              items={done}
              onDelete={async (id) => {
                await deleteAnalysis(id);
                setMine((prev) => (prev ?? []).filter((a) => a.id !== id));
              }}
            />
          )
        ) : (
          theirs === null ? <GridSkeleton /> : <PublicGrid items={theirs} />
        )}

        {isSelf && failed.length > 0 && (
          <div className="mt-6">
            <button
              onClick={() => setShowFailed((x) => !x)}
              className="btn-ghost text-xs text-neutral-500"
            >
              {showFailed ? "Hide" : "Show"} {failed.length} failed {failed.length === 1 ? "analysis" : "analyses"}
            </button>
            {showFailed && (
              <div className="mt-2">
                <MineGrid
                  items={failed}
                  onDelete={async (id) => {
                    await deleteAnalysis(id);
                    setMine((prev) => (prev ?? []).filter((a) => a.id !== id));
                  }}
                />
              </div>
            )}
          </div>
        )}
      </section>
    </AppShell>
  );
}

function InProgressStrip({ items }: { items: AnalysisSummary[] }) {
  return (
    <div className="mb-5 rounded-2xl border border-blue-200 bg-blue-50/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-blue-900">
        <span className="pipeline-spinner" aria-hidden style={{ borderTopColor: "#1e40af", borderColor: "#bfdbfe" }} />
        {items.length === 1 ? "1 analysis running" : `${items.length} analyses running`}
      </div>
      <ul className="space-y-1.5">
        {items.map((a) => (
          <li key={a.id}>
            <Link
              href={`/analyses/${a.id}`}
              className="flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2 text-sm shadow-sm transition hover:shadow-md"
            >
              <span className="truncate font-medium text-neutral-800 break-anywhere">
                {a.idea_title || "Analysis starting…"}
              </span>
              <span className="shrink-0 text-[11px] font-medium text-blue-700">
                {a.status === "queued" ? "Queued" : "Running"} →
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MineGrid({
  items,
  onDelete,
}: {
  items: AnalysisSummary[];
  onDelete: (id: string) => Promise<void>;
}) {
  if (items.length === 0) {
    return (
      <div className="card p-8 text-center">
        <p className="text-sm text-neutral-600">Nothing here yet.</p>
        <Link href="/new" className="btn-primary mt-3 text-sm">+ New idea</Link>
      </div>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((a) => (
        <li key={a.id} className="relative">
          <Link href={`/analyses/${a.id}`} className="card block p-4 transition hover:shadow-md">
            <div className="mb-2 flex flex-wrap items-center gap-2 pr-8 text-[11px] font-medium">
              <StatusBadge status={a.status} />
              {a.visibility === "private" && (
                <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-600">Private</span>
              )}
              {a.verdict && (
                <span className={`rounded-full px-2 py-0.5 ${verdictColor(a.verdict)}`}>{a.verdict}</span>
              )}
              {a.overall_score_100 != null && (
                <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-800">{a.overall_score_100}/100</span>
              )}
            </div>
            <h3 className="line-clamp-2 text-sm font-semibold text-neutral-900 break-anywhere">
              {a.idea_title ?? "Untitled analysis"}
            </h3>
            <p className="mt-2 text-[11px] text-neutral-500">
              {a.completed_at
                ? `Completed ${new Date(a.completed_at).toLocaleDateString()}`
                : a.submitted_at
                  ? `Submitted ${new Date(a.submitted_at).toLocaleDateString()}`
                  : ""}
            </p>
          </Link>
          <CardMenu id={a.id} title={a.idea_title} onDelete={onDelete} />
        </li>
      ))}
    </ul>
  );
}

function CardMenu({
  id, title, onDelete,
}: {
  id: string;
  title: string | null;
  onDelete: (id: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  // Close the popover on outside click.
  useEffect(() => {
    if (!open) return;
    const onClick = () => setOpen(false);
    // Register after the current event so the click that opened us isn't caught.
    const t = setTimeout(() => window.addEventListener("click", onClick), 0);
    return () => { clearTimeout(t); window.removeEventListener("click", onClick); };
  }, [open]);

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    const label = title ? `"${title}"` : "this analysis";
    if (!window.confirm(`Delete ${label}? This removes the report, post, comments, and fires. Cannot be undone.`)) return;
    setBusy(true);
    try {
      await onDelete(id);
    } catch (err) {
      alert((err as Error).message || "Delete failed");
      setBusy(false);
    }
  };

  return (
    <div className="absolute right-2 top-2">
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((x) => !x); }}
        className="flex h-7 w-7 items-center justify-center rounded-full text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-800"
        aria-label="More actions"
      >
        <DotsIcon />
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute right-0 top-8 z-10 w-40 overflow-hidden rounded-xl border border-neutral-200 bg-white text-sm shadow-lg"
        >
          <button
            onClick={handleDelete}
            disabled={busy}
            className="block w-full px-3 py-2 text-left text-red-600 transition hover:bg-red-50 disabled:opacity-50"
          >
            {busy ? "Deleting…" : "Delete"}
          </button>
        </div>
      )}
    </div>
  );
}

function DotsIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <circle cx="5" cy="12" r="1.6" />
      <circle cx="12" cy="12" r="1.6" />
      <circle cx="19" cy="12" r="1.6" />
    </svg>
  );
}

function PublicGrid({ items }: { items: PublicAnalysis[] }) {
  if (items.length === 0) {
    return (
      <div className="card p-8 text-center text-sm text-neutral-500">
        Nothing shared yet.
      </div>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((a) => (
        <li key={a.id}>
          <Link href={`/analyses/${a.id}`} className="card block p-4 transition hover:shadow-md">
            <div className="mb-2 flex items-center gap-2 text-[11px] font-medium">
              {a.verdict && (
                <span className={`rounded-full px-2 py-0.5 ${verdictColor(a.verdict)}`}>{a.verdict}</span>
              )}
              {a.overall_score_100 != null && (
                <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-800">{a.overall_score_100}/100</span>
              )}
            </div>
            <h3 className="line-clamp-2 text-sm font-semibold text-neutral-900 break-anywhere">
              {a.idea_title ?? "Untitled analysis"}
            </h3>
            <div className="mt-3 flex items-center gap-3 text-[11px] text-neutral-500">
              <span>🔥 {a.fire_count}</span>
              <span>💬 {a.comment_count}</span>
              {a.completed_at && <span className="ml-auto">{new Date(a.completed_at).toLocaleDateString()}</span>}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "done") return <span className="rounded-full bg-green-100 px-2 py-0.5 text-green-800">Done</span>;
  if (status === "running" || status === "queued") return <span className="rounded-full bg-blue-100 px-2 py-0.5 text-blue-800">In progress</span>;
  if (status === "failed") return <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-800">Failed</span>;
  if (status === "cancelled") return <span className="rounded-full bg-neutral-200 px-2 py-0.5 text-neutral-700">Cancelled</span>;
  return <span className="rounded-full bg-neutral-100 px-2 py-0.5 text-neutral-700">{status}</span>;
}

function verdictColor(v: string): string {
  if (v === "STRONG INVEST") return "bg-green-100 text-green-800";
  if (v === "CONDITIONAL") return "bg-blue-100 text-blue-800";
  if (v === "WATCH") return "bg-yellow-100 text-yellow-800";
  if (v === "PASS" || v === "HARD PASS") return "bg-red-100 text-red-800";
  return "bg-neutral-100 text-neutral-700";
}

function Stat({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`rounded-xl border p-3 text-center ${highlight ? "border-orange-300 bg-orange-50" : "border-neutral-200 bg-white"}`}>
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-0.5 text-xl font-bold">{value}</div>
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="mb-5 flex items-start gap-4">
        <div className="h-20 w-20 rounded-full bg-neutral-200" />
        <div className="flex-1 space-y-2">
          <div className="h-5 w-40 rounded bg-neutral-200" />
          <div className="h-3 w-24 rounded bg-neutral-100" />
        </div>
      </div>
      <div className="grid grid-cols-4 gap-2.5">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-16 rounded-xl bg-neutral-100" />
        ))}
      </div>
    </div>
  );
}

function GridSkeleton() {
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="card h-32 animate-pulse bg-neutral-50" />
      ))}
    </ul>
  );
}
