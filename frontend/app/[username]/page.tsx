"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_BASE, useSession, useSessionRefresh } from "@/lib/session";
import { AnalysisSummary, deleteAnalysis, fetchMyAnalyses, reportPdfUrl, retryAnalysis } from "@/lib/analyses";
import { toggleFire } from "@/lib/social";
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
  const refreshSession = useSessionRefresh();
  const router = useRouter();

  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mine, setMine] = useState<AnalysisSummary[] | null>(null);
  const [theirs, setTheirs] = useState<PublicAnalysis[] | null>(null);
  const [showFailed, setShowFailed] = useState(false);

  const refetchProfile = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/api/v1/users/${username}`, { credentials: "include" });
      if (r.ok) {
        const data = await r.json();
        setProfile(data.user);
      }
    } catch {/* keep previous profile on transient error */}
  }, [username]);

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

      <section className="grid grid-cols-2 gap-3">
        <Stat label="Ideas" value={profile.total_analyses} />
        <Stat label="🔥 Fires" value={profile.fires_received} highlight={profile.fires_received >= 5} />
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
                const backup = mine;
                setMine((prev) => (prev ?? []).filter((a) => a.id !== id));
                try {
                  await deleteAnalysis(id);
                  // Fire-and-forget: refresh counts in the background, don't
                  // block the UI on them.
                  refetchProfile();
                  refreshSession();
                } catch (e) {
                  setMine(backup);
                  alert((e as Error).message || "Delete failed");
                }
              }}
              onFireToggle={(id, fired, fc) => {
                setMine((prev) => (prev ?? []).map((a) => a.id === id ? { ...a, i_fired: fired, fire_count: fc } : a));
              }}
              onRetry={async (id) => {
                await retryAnalysis(id);
                setMine((prev) => (prev ?? []).map((a) => a.id === id ? { ...a, status: "queued" } : a));
                router.push(`/analyses/${id}`);
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
                  onFireToggle={() => {/* failed items have no post, footer doesn't render */}}
                  onRetry={async (id) => {
                    await retryAnalysis(id);
                    setMine((prev) => (prev ?? []).map((a) => a.id === id ? { ...a, status: "queued" } : a));
                    router.push(`/analyses/${id}`);
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

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  classifying: "Classifying idea",
  research: "Running parallel research",
  research_done: "Research complete",
  analysis_1: "Analysing problem + business model",
  analysis_2: "Analysing GTM + risk",
  scoring: "Computing CVF scores",
  compiling: "Generating report",
  done: "Complete",
  error: "Error",
};

function currentStepLabel(a: AnalysisSummary): string {
  if (a.latest_stage && STAGE_LABELS[a.latest_stage]) return STAGE_LABELS[a.latest_stage];
  if (a.latest_message) return a.latest_message;
  if (a.status === "queued") return "Queued — worker will pick this up shortly";
  return "Starting…";
}

function InProgressStrip({ items }: { items: AnalysisSummary[] }) {
  return (
    <div className="mb-5 rounded-2xl border border-blue-200 bg-blue-50/50 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-blue-900">
        <span className="pipeline-spinner" aria-hidden style={{ borderTopColor: "#1e40af", borderColor: "#bfdbfe" }} />
        {items.length === 1 ? "1 analysis running" : `${items.length} analyses running`}
      </div>
      <ul className="space-y-1.5">
        {items.map((a) => {
          const pct = a.latest_percent ?? 0;
          const step = currentStepLabel(a);
          return (
            <li key={a.id}>
              <Link
                href={`/analyses/${a.id}`}
                className="flex items-center justify-between gap-3 rounded-lg bg-white px-3 py-2 text-sm shadow-sm transition hover:shadow-md"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-neutral-800 break-anywhere">
                    {a.idea_title || step}
                  </div>
                  {a.idea_title && (
                    <div className="truncate text-[11px] text-neutral-500">{step}</div>
                  )}
                  <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-neutral-100">
                    <div
                      className="h-full bg-blue-600 transition-all duration-500"
                      style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
                    />
                  </div>
                </div>
                <span className="shrink-0 text-[11px] font-semibold tabular-nums text-blue-700">
                  {pct}%
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function MineGrid({
  items,
  onDelete,
  onFireToggle,
  onRetry,
}: {
  items: AnalysisSummary[];
  onDelete: (id: string) => Promise<void>;
  onFireToggle: (id: string, fired: boolean, count: number) => void;
  onRetry: (id: string) => Promise<void>;
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
        <IdeaCard key={a.id} a={a} onDelete={onDelete} onFireToggle={onFireToggle} onRetry={onRetry} />
      ))}
    </ul>
  );
}

function IdeaCard({
  a, onDelete, onFireToggle, onRetry,
}: {
  a: AnalysisSummary;
  onDelete: (id: string) => Promise<void>;
  onFireToggle: (id: string, fired: boolean, count: number) => void;
  onRetry: (id: string) => Promise<void>;
}) {
  const isDone = a.status === "done";
  const isFailed = a.status === "failed" || a.status === "cancelled";
  return (
    <li className="relative">
      <Link href={`/analyses/${a.id}`} className="card block p-4 pb-3 transition hover:shadow-md">
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
          {timestampLabel(a)}
        </p>
      </Link>

      {/* Card footer — reserved for social signals. Only rendered when the
          analysis actually has a post (i.e. it's public + done). */}
      {isDone && a.visibility === "public" && a.post_id && (
        <CardFooter a={a} onFireToggle={onFireToggle} />
      )}

      <CardMenu
        id={a.id}
        title={a.idea_title}
        canDownload={isDone}
        canRetry={isFailed}
        onDelete={onDelete}
        onRetry={onRetry}
      />
    </li>
  );
}

function CardFooter({
  a, onFireToggle,
}: {
  a: AnalysisSummary;
  onFireToggle: (id: string, fired: boolean, count: number) => void;
}) {
  const [fired, setFired] = useState(a.i_fired);
  const [count, setCount] = useState(a.fire_count);
  const [busy, setBusy] = useState(false);

  const handleFire = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy || !a.post_id) return;
    setBusy(true);
    const prev = { fired, count };
    setFired(!fired);
    setCount(fired ? Math.max(0, count - 1) : count + 1);
    try {
      const r = await toggleFire(a.post_id);
      setFired(r.fired);
      setCount(r.fire_count);
      onFireToggle(a.id, r.fired, r.fire_count);
    } catch {
      setFired(prev.fired);
      setCount(prev.count);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card border-t-0 rounded-t-none -mt-[1px] flex items-center gap-3 px-4 py-2 text-xs">
      <button
        onClick={handleFire}
        disabled={busy}
        aria-pressed={fired}
        className={`flex items-center gap-1 rounded-full px-2 py-0.5 transition active:scale-95 ${fired ? "bg-orange-50 text-orange-700" : "text-neutral-600 hover:bg-neutral-100"}`}
      >
        <span className={fired ? "animate-pop" : ""}>🔥</span>
        <span className="font-semibold tabular-nums">{count}</span>
      </button>
      <span className="flex items-center gap-1 rounded-full px-2 py-0.5 text-neutral-600">
        💬 <span className="font-semibold tabular-nums">{a.comment_count}</span>
      </span>
    </div>
  );
}

function CardMenu({
  id, title, canDownload, canRetry, onDelete, onRetry,
}: {
  id: string;
  title: string | null;
  canDownload: boolean;
  canRetry: boolean;
  onDelete: (id: string) => Promise<void>;
  onRetry: (id: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<false | "delete" | "retry">(false);

  useEffect(() => {
    if (!open) return;
    const onClick = () => setOpen(false);
    const t = setTimeout(() => window.addEventListener("click", onClick), 0);
    return () => { clearTimeout(t); window.removeEventListener("click", onClick); };
  }, [open]);

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    const label = title ? `"${title}"` : "this analysis";
    if (!window.confirm(`Delete ${label}? This removes the report, post, comments, and fires. Cannot be undone.`)) return;
    setBusy("delete");
    try {
      await onDelete(id);
    } catch (err) {
      alert((err as Error).message || "Delete failed");
      setBusy(false);
    }
  };

  const handleRetry = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    setBusy("retry");
    setOpen(false);
    try {
      await onRetry(id);
    } catch (err) {
      alert((err as Error).message || "Retry failed");
      setBusy(false);
    }
  };

  return (
    <div className="absolute right-2 top-2">
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen((x) => !x); }}
        className="flex h-7 w-7 items-center justify-center rounded-full bg-white/80 text-neutral-600 shadow-sm ring-1 ring-neutral-200 backdrop-blur transition hover:bg-white hover:text-neutral-900"
        aria-label="More actions"
      >
        <DotsIcon />
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute right-0 top-9 z-10 w-44 overflow-hidden rounded-xl border border-neutral-200 bg-white text-sm shadow-lg"
        >
          {canRetry && (
            <button
              onClick={handleRetry}
              disabled={!!busy}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-neutral-800 transition hover:bg-neutral-50 disabled:opacity-50"
            >
              <RetryIcon /> {busy === "retry" ? "Retrying…" : "Retry analysis"}
            </button>
          )}
          {canDownload && (
            <a
              href={reportPdfUrl(id)}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => { e.stopPropagation(); setOpen(false); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-neutral-800 transition hover:bg-neutral-50"
            >
              <MenuDownloadIcon /> Download PDF
            </a>
          )}
          <button
            onClick={handleDelete}
            disabled={!!busy}
            className="flex w-full items-center gap-2 border-t border-neutral-100 px-3 py-2 text-left text-red-600 transition hover:bg-red-50 disabled:opacity-50"
          >
            <TrashIcon /> {busy === "delete" ? "Deleting…" : "Delete"}
          </button>
        </div>
      )}
    </div>
  );
}

function MenuDownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6 18 20a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
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

function timestampLabel(a: AnalysisSummary): string {
  const fmt = (iso: string) => new Date(iso).toLocaleDateString();
  if (a.status === "failed") return a.completed_at ? `Failed ${fmt(a.completed_at)}` : "Failed";
  if (a.status === "cancelled") return a.completed_at ? `Cancelled ${fmt(a.completed_at)}` : "Cancelled";
  if (a.status === "done" && a.completed_at) return `Completed ${fmt(a.completed_at)}`;
  if (a.submitted_at) return `Submitted ${fmt(a.submitted_at)}`;
  return "";
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
