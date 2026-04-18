"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, logout, useSession } from "@/lib/session";

export default function SettingsPage() {
  const session = useSession();
  const router = useRouter();

  const [displayName, setDisplayName] = useState("");
  const [defaultVisibility, setDefaultVisibility] = useState<"public" | "private">("public");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [deleting, setDeleting] = useState(false);
  const [confirmInput, setConfirmInput] = useState("");

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
    if (session.status === "authenticated" && !session.user.onboarding_complete) {
      router.replace("/onboarding");
    }
    if (session.status === "authenticated") {
      setDisplayName(session.user.display_name);
      setDefaultVisibility(session.user.default_visibility);
      setTimezone(session.user.timezone);
    }
  }, [session, router]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch(`${API_BASE}/api/v1/users/me`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: displayName,
          default_visibility: defaultVisibility,
          timezone,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Save failed (${res.status})`);
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (confirmInput !== "delete my account") {
      setError('Type "delete my account" exactly to confirm.');
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/v1/users/me?confirmation=${encodeURIComponent("delete my account")}`,
        { method: "DELETE", credentials: "include" },
      );
      if (!res.ok && res.status !== 202 && res.status !== 204) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Delete failed (${res.status})`);
      }
      // Log out locally + go home
      await logout();
      router.replace("/");
    } catch (e) {
      setError((e as Error).message);
      setDeleting(false);
    }
  };

  if (session.status !== "authenticated" || !session.user.onboarding_complete) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-neutral-500">Loading...</div>
      </main>
    );
  }

  const user = session.user;

  return (
    <main className="mx-auto max-w-xl px-4 py-8 md:px-6">
      <header className="mb-6">
        <button
          onClick={() => router.back()}
          className="text-xs text-neutral-500 hover:text-neutral-800"
        >
          ← Back
        </button>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-neutral-600">
          @{user.username} · {user.email}
        </p>
      </header>

      <form onSubmit={handleSave} className="space-y-5">
        <div>
          <label className="block text-sm font-medium">Username</label>
          <input
            type="text"
            value={user.username ?? ""}
            readOnly
            className="mt-1 w-full cursor-not-allowed rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-500"
          />
          <p className="mt-1 text-xs text-neutral-500">Usernames are immutable. Email support if you need a change.</p>
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
          <legend className="block text-sm font-medium">Default visibility for new analyses</legend>
          <div className="mt-2 space-y-2 text-sm">
            <label className="flex gap-2">
              <input
                type="radio"
                checked={defaultVisibility === "public"}
                onChange={() => setDefaultVisibility("public")}
              />
              <span><strong>Public</strong> — analyses show in the feed by default.</span>
            </label>
            <label className="flex gap-2">
              <input
                type="radio"
                checked={defaultVisibility === "private"}
                onChange={() => setDefaultVisibility("private")}
              />
              <span><strong>Private</strong> — only you can see new analyses by default.</span>
            </label>
          </div>
        </fieldset>

        <div>
          <label className="block text-sm font-medium">Timezone</label>
          <input
            type="text"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="Asia/Kolkata"
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-200"
          />
          <p className="mt-1 text-xs text-neutral-500">
            IANA zone name. Used for streak day-boundary math.
          </p>
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:bg-neutral-400"
          >
            {saving ? "Saving..." : "Save changes"}
          </button>
          {saved && <span className="text-xs text-green-700">Saved ✓</span>}
        </div>
      </form>

      <hr className="my-10 border-neutral-200" />

      <section className="rounded-md border border-red-200 bg-red-50 p-4">
        <h2 className="text-sm font-semibold text-red-900">Danger zone</h2>
        <p className="mt-1 text-xs text-red-800">
          Delete your account and all data: analyses, debates, comments, fires, avatars.
          This action is immediate and irreversible.
        </p>
        <div className="mt-3 space-y-2">
          <input
            type="text"
            value={confirmInput}
            onChange={(e) => setConfirmInput(e.target.value)}
            placeholder='Type "delete my account" to confirm'
            className="w-full rounded-md border border-red-300 bg-white px-3 py-2 text-sm"
            disabled={deleting}
          />
          <button
            onClick={handleDelete}
            disabled={deleting || confirmInput !== "delete my account"}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
          >
            {deleting ? "Deleting..." : "Delete my account"}
          </button>
        </div>
      </section>
    </main>
  );
}
