"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, logout, useSession } from "@/lib/session";
import AppShell from "@/components/AppShell";

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
      <AppShell title="Settings">
        <div className="space-y-4">
          <div className="h-6 w-48 animate-pulse rounded bg-neutral-200" />
          <div className="card animate-pulse space-y-4 p-5">
            <div className="h-4 w-32 rounded bg-neutral-200" />
            <div className="h-9 rounded-xl bg-neutral-100" />
            <div className="h-4 w-32 rounded bg-neutral-200" />
            <div className="h-9 rounded-xl bg-neutral-100" />
            <div className="h-9 w-28 rounded-full bg-neutral-200" />
          </div>
        </div>
      </AppShell>
    );
  }

  const user = session.user;

  return (
    <AppShell title="Settings">
      <header className="mb-5">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-neutral-600 break-anywhere">@{user.username} · {user.email}</p>
      </header>

      <form onSubmit={handleSave} className="card space-y-5 p-5">
        <div>
          <label className="block text-sm font-medium text-neutral-800">Username</label>
          <input
            type="text"
            value={user.username ?? ""}
            readOnly
            className="mt-1 w-full cursor-not-allowed rounded-xl border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-500"
          />
          <p className="mt-1 text-xs text-neutral-500">Usernames are immutable. Email support if you need a change.</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-neutral-800">Display name</label>
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            maxLength={40}
            className="input mt-1"
          />
        </div>

        <fieldset>
          <legend className="block text-sm font-medium text-neutral-800">Default visibility for new analyses</legend>
          <div className="mt-2 space-y-2 text-sm">
            <label className="flex items-start gap-2">
              <input
                type="radio"
                className="mt-1 accent-neutral-900"
                checked={defaultVisibility === "public"}
                onChange={() => setDefaultVisibility("public")}
              />
              <span><strong>Public</strong> — analyses show in the feed by default.</span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                className="mt-1 accent-neutral-900"
                checked={defaultVisibility === "private"}
                onChange={() => setDefaultVisibility("private")}
              />
              <span><strong>Private</strong> — only you can see new analyses by default.</span>
            </label>
          </div>
        </fieldset>

        <div>
          <label className="block text-sm font-medium text-neutral-800">Timezone</label>
          <input
            type="text"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            placeholder="Asia/Kolkata"
            className="input mt-1"
          />
          <p className="mt-1 text-xs text-neutral-500">IANA zone name. Used for streak day-boundary math.</p>
        </div>

        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "Saving…" : "Save changes"}
          </button>
          {saved && <span className="text-xs font-medium text-green-700">Saved ✓</span>}
        </div>
      </form>

      <section className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5">
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
            className="w-full rounded-xl border border-red-300 bg-white px-3 py-2 text-sm focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
            disabled={deleting}
          />
          <button
            onClick={handleDelete}
            disabled={deleting || confirmInput !== "delete my account"}
            className="btn-danger"
          >
            {deleting ? "Deleting…" : "Delete my account"}
          </button>
        </div>
      </section>

      <div className="mt-6 flex justify-center">
        <button
          onClick={async () => { await logout(); router.replace("/"); }}
          className="btn-ghost text-xs"
        >
          Log out
        </button>
      </div>
    </AppShell>
  );
}
