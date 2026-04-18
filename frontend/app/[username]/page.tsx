"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, useSession } from "@/lib/session";
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

// Paths reserved by the app — accidental collisions here should show a
// proper 404 rather than a "user not found" (confusing).
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

  useEffect(() => {
    // Reserved paths: bounce to /feed so we don't look up "settings" etc. as a user.
    if (RESERVED_PATHS.has(username.toLowerCase())) {
      router.replace("/feed");
      return;
    }
    fetch(`${API_BASE}/api/v1/users/${username}`, { credentials: "include" })
      .then(async (r) => {
        if (r.status === 404) { setError("not_found"); return; }
        if (!r.ok) throw new Error(`status ${r.status}`);
        const data = await r.json();
        setProfile(data.user);
      })
      .catch((e) => setError(e.message));
  }, [username, router]);

  if (error === "not_found") {
    return (
      <AppShell title="Profile">
        <div className="card p-8 text-center">
          <h1 className="text-lg font-semibold">User not found</h1>
          <p className="mt-2 text-sm text-neutral-500">@{username} isn't a Chapter One account.</p>
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
        <div className="py-10 text-center text-sm text-neutral-500">Loading profile…</div>
      </AppShell>
    );
  }

  const isSelf =
    session.status === "authenticated" &&
    session.user.username === profile.username;

  return (
    <AppShell title={profile.display_name}>
      <header className="mb-6 flex items-start gap-4">
        {profile.avatar_url ? (
          <img
            src={profile.avatar_url}
            alt=""
            className="h-20 w-20 shrink-0 rounded-full object-cover shadow"
          />
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

      <section className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Stat label="Ideas" value={profile.total_analyses} />
        <Stat label="🔥 Streak" value={profile.current_streak} highlight={profile.current_streak >= 7} />
        <Stat label="Longest" value={profile.longest_streak} />
        <Stat label="🔥 Received" value={profile.fires_received} />
      </section>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-semibold text-neutral-700">Public reports</h2>
        <div className="card p-6 text-center text-sm text-neutral-500">
          {isSelf ? "You haven't shared anything yet." : "Nothing shared yet."}
        </div>
      </section>
    </AppShell>
  );
}

function Stat({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`rounded-xl border p-3 ${highlight ? "border-orange-300 bg-orange-50" : "border-neutral-200 bg-white"}`}>
      <div className="text-[11px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-0.5 text-2xl font-bold">{value}</div>
    </div>
  );
}
