"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
import { submitAnalysis } from "@/lib/analyses";

export default function NewIdeaPage() {
  const session = useSession();
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [visibility, setVisibility] = useState<"public" | "private">("public");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
    if (session.status === "authenticated" && !session.user.onboarding_complete) {
      router.replace("/onboarding");
    }
  }, [session, router]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = idea.trim();
    if (trimmed.length < 20) return;
    setSubmitting(true);
    setError(null);
    try {
      const { analysis_id } = await submitAnalysis(trimmed, visibility);
      router.push(`/analyses/${analysis_id}`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  };

  if (session.status !== "authenticated" || !session.user.onboarding_complete) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-neutral-500">Loading...</div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 md:px-6">
      <header className="mb-6">
        <button
          onClick={() => router.back()}
          className="text-xs text-neutral-500 hover:text-neutral-800"
        >
          ← Back
        </button>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">New idea</h1>
        <p className="mt-1 text-sm text-neutral-600">
          Describe your startup idea. The deeper the description, the richer the report.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-5">
        <div>
          <label className="block text-sm font-medium">Your idea</label>
          <textarea
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            required
            minLength={20}
            maxLength={4000}
            rows={8}
            placeholder="e.g. A compliance copilot that helps Indian CA firms automate GST filings for their SMB clients, with..."
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white p-3 text-sm shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-200"
            disabled={submitting}
          />
          <div className="mt-1 flex justify-between text-xs text-neutral-500">
            <span>{idea.length} / 4000</span>
            <span>Minimum 20 characters</span>
          </div>
        </div>

        <fieldset>
          <legend className="block text-sm font-medium">Visibility</legend>
          <div className="mt-2 space-y-2 text-sm">
            <label className="flex gap-2">
              <input
                type="radio"
                checked={visibility === "public"}
                onChange={() => setVisibility("public")}
                disabled={submitting}
              />
              <span>
                <strong>Public</strong> — shows in the feed; anyone with the share link can read.
              </span>
            </label>
            <label className="flex gap-2">
              <input
                type="radio"
                checked={visibility === "private"}
                onChange={() => setVisibility("private")}
                disabled={submitting}
              />
              <span>
                <strong>Private</strong> — only you can see it. Toggle later anytime.
              </span>
            </label>
          </div>
        </fieldset>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || idea.trim().length < 20}
          className="rounded-md bg-neutral-900 px-5 py-2 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-400"
        >
          {submitting ? "Submitting..." : "Analyse idea"}
        </button>
      </form>

      <p className="mt-8 text-xs text-neutral-500">
        Analysis takes ~3-5 minutes. You can leave this page; we'll keep going.
      </p>
    </main>
  );
}
