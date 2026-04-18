"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AnalysisSummary, fetchMyAnalyses } from "@/lib/analyses";
import { logout, useSession } from "@/lib/session";

export default function FeedPage() {
  const session = useSession();
  const router = useRouter();
  const [analyses, setAnalyses] = useState<AnalysisSummary[] | null>(null);

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
    if (session.status === "authenticated" && !session.user.onboarding_complete) {
      router.replace("/onboarding");
    }
  }, [session, router]);

  useEffect(() => {
    if (session.status !== "authenticated") return;
    fetchMyAnalyses().then(setAnalyses);
  }, [session.status]);

  if (session.status !== "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-neutral-500">Loading...</div>
      </main>
    );
  }

  const user = session.user;

  return (
    <main className="mx-auto max-w-3xl px-4 py-6 md:px-6">
      <header className="mb-6 flex items-center justify-between border-b border-neutral-200 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Your ideas</h1>
          <p className="text-xs text-neutral-500">Global feed lands in M3. For now: your own analyses.</p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/new"
            className="rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-neutral-700"
          >
            + New idea
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

      {analyses === null ? (
        <div className="text-sm text-neutral-500">Loading your analyses...</div>
      ) : analyses.length === 0 ? (
        <div className="rounded-md border-2 border-dashed border-neutral-300 bg-white p-8 text-center">
          <p className="text-sm text-neutral-700">No analyses yet.</p>
          <a
            href="/new"
            className="mt-3 inline-block rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
          >
            Submit your first idea
          </a>
        </div>
      ) : (
        <ul className="space-y-3">
          {analyses.map((a) => (
            <li key={a.id}>
              <a
                href={`/analyses/${a.id}`}
                className="block rounded-md border border-neutral-200 bg-white p-4 hover:border-neutral-300 hover:bg-neutral-50"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold text-neutral-900">
                      {a.idea_title || "Untitled"}
                    </h3>
                    <div className="mt-1 flex items-center gap-3 text-xs text-neutral-500">
                      <span className={`inline-flex rounded-full px-2 py-0.5 ${statusColor(a.status)}`}>
                        {a.status}
                      </span>
                      {a.verdict && <span className="font-medium text-neutral-700">{a.verdict}</span>}
                      {a.overall_score_100 != null && <span>{a.overall_score_100}/100</span>}
                      <span>· {a.visibility}</span>
                    </div>
                  </div>
                  <span className="text-xs text-neutral-400">
                    {a.submitted_at && new Date(a.submitted_at).toLocaleDateString()}
                  </span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

function statusColor(status: string): string {
  switch (status) {
    case "done": return "bg-green-100 text-green-800";
    case "failed": return "bg-red-100 text-red-800";
    case "running":
    case "queued": return "bg-blue-100 text-blue-800";
    default: return "bg-neutral-100 text-neutral-700";
  }
}
