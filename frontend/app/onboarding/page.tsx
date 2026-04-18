"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, useSession } from "@/lib/session";

type AvatarKind = "initials" | "library" | "upload";

const LIBRARY_OPTIONS = [
  "geo-01", "geo-02", "geo-03", "geo-04",
  "geo-05", "geo-06", "geo-07", "geo-08",
  "geo-09", "geo-10", "geo-11", "geo-12",
];

export default function OnboardingPage() {
  const session = useSession();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [avatarKind, setAvatarKind] = useState<AvatarKind>("initials");
  const [libraryId, setLibraryId] = useState<string>("geo-01");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
    if (session.status === "authenticated" && session.user.onboarding_complete) {
      router.replace("/feed");
    }
    if (session.status === "authenticated" && !displayName) {
      setDisplayName(session.user.display_name || "");
    }
  }, [session, router, displayName]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const form = new FormData();
      form.set("username", username.toLowerCase());
      form.set("display_name", displayName);
      form.set("avatar_kind", avatarKind);
      if (avatarKind === "library") form.set("avatar_library_id", libraryId);
      if (avatarKind === "upload" && file) form.set("avatar_file", file);

      const res = await fetch(`${API_BASE}/api/v1/users/onboard`, {
        method: "POST",
        body: form,
        credentials: "include",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Onboard failed: ${res.status}`);
      }
      router.replace("/feed");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (session.status !== "authenticated") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-neutral-500">Loading...</div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-md px-6 py-10">
      <h1 className="text-2xl font-bold tracking-tight">Welcome 👋</h1>
      <p className="mt-1 text-sm text-neutral-600">
        Pick a username and how you'd like to show up.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-5">
        <div>
          <label className="block text-sm font-medium">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
            pattern="[a-z0-9_]{3,20}"
            required
            minLength={3}
            maxLength={20}
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-200"
            placeholder="hemanth"
          />
          <p className="mt-1 text-xs text-neutral-500">3-20 chars. Lowercase letters, digits, _ only. Immutable.</p>
        </div>

        <div>
          <label className="block text-sm font-medium">Display name</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            maxLength={40}
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-200"
          />
        </div>

        <fieldset>
          <legend className="block text-sm font-medium">Avatar</legend>
          <div className="mt-2 space-y-3">
            {(["initials", "library", "upload"] as AvatarKind[]).map((k) => (
              <label key={k} className="flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="avatar_kind"
                  value={k}
                  checked={avatarKind === k}
                  onChange={() => setAvatarKind(k)}
                  className="mt-0.5"
                />
                <span className="flex-1">
                  {k === "initials" && (
                    <><strong>Initials</strong> — auto-generated from your name.</>
                  )}
                  {k === "library" && (
                    <><strong>Library</strong> — pick a preset geometric avatar.</>
                  )}
                  {k === "upload" && (
                    <><strong>Upload</strong> — your own image (max 2MB).</>
                  )}
                </span>
              </label>
            ))}
          </div>

          {avatarKind === "library" && (
            <div className="mt-3 grid grid-cols-6 gap-2">
              {LIBRARY_OPTIONS.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setLibraryId(id)}
                  className={`aspect-square rounded-md border-2 text-xs ${libraryId === id ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-200 bg-white"}`}
                  aria-label={id}
                >
                  {id}
                </button>
              ))}
            </div>
          )}

          {avatarKind === "upload" && (
            <div className="mt-3">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-sm"
              />
            </div>
          )}
        </fieldset>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting || username.length < 3 || !displayName}
          className="w-full rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-400"
        >
          {submitting ? "Creating..." : "Create profile"}
        </button>
      </form>
    </main>
  );
}
