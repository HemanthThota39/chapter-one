"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, useSession } from "@/lib/session";

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
    fetch(`${API_BASE}/api/v1/users/${username}`, { credentials: "include" })
      .then(async (r) => {
        if (r.status === 404) { setError("not_found"); return; }
        if (!r.ok) throw new Error(`status ${r.status}`);
        const data = await r.json();
        setProfile(data.user);
      })
      .catch((e) => setError(e.message));
  }, [username]);

  if (error === "not_found") {
    return (
      <main className="mx-auto max-w-md px-6 py-16 text-center">
        <h1 className="text-xl font-semibold">User not found</h1>
        <p className="mt-2 text-sm text-neutral-500">
          @{username} isn't a Chapter One account.
        </p>
      </main>
    );
  }
  if (error) {
    return (
      <main className="mx-auto max-w-md px-6 py-16 text-center">
        <p className="text-sm text-red-600">Couldn't load profile: {error}</p>
      </main>
    );
  }
  if (!profile) {
    return <main className="mx-auto max-w-md px-6 py-16 text-center text-sm text-neutral-500">Loading profile...</main>;
  }

  const isSelf =
    session.status === "authenticated" &&
    session.user.username === profile.username;

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 md:px-6">
      <header className="mb-8 flex items-start gap-5">
        {profile.avatar_url ? (
          <img
            src={profile.avatar_url}
            alt=""
            className="h-20 w-20 rounded-full object-cover shadow"
          />
        ) : (
          <span className="inline-flex h-20 w-20 items-center justify-center rounded-full bg-neutral-200 text-2xl font-semibold">
            {profile.display_name.slice(0, 1).toUpperCase()}
          </span>
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{profile.display_name}</h1>
          <p className="text-sm text-neutral-500">@{profile.username}</p>
          <p className="mt-1 text-xs text-neutral-400">
            Joined {new Date(profile.joined_at).toLocaleDateString()}
          </p>
        </div>
        {isSelf && (
          <button
            onClick={() => router.push("/settings")}
            className="rounded-md bg-neutral-100 px-3 py-1 text-xs hover:bg-neutral-200"
          >
            Settings
          </button>
        )}
      </header>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Ideas" value={profile.total_analyses} />
        <Stat label="🔥 streak" value={profile.current_streak} highlight={profile.current_streak >= 7} />
        <Stat label="Longest streak" value={profile.longest_streak} />
        <Stat label="🔥 received" value={profile.fires_received} />
      </section>

      <section className="mt-10">
        <h2 className="mb-3 text-sm font-semibold text-neutral-700">Public reports</h2>
        <div className="rounded-md border-2 border-dashed border-neutral-300 bg-white p-6 text-center text-sm text-neutral-500">
          {isSelf ? "You haven't shared anything yet." : "Nothing shared yet."}
        </div>
      </section>
    </main>
  );
}

function Stat({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`rounded-md border p-3 ${highlight ? "border-orange-300 bg-orange-50" : "border-neutral-200 bg-white"}`}>
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}
