"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { logout, useSession } from "@/lib/session";

export default function FeedPage() {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session.status === "unauthenticated") router.replace("/");
    if (session.status === "authenticated" && !session.user.onboarding_complete) {
      router.replace("/onboarding");
    }
  }, [session, router]);

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
          <h1 className="text-xl font-bold tracking-tight">Feed</h1>
          <p className="text-xs text-neutral-500">What your circle is working on</p>
        </div>
        <div className="flex items-center gap-3">
          <a href={`/${user.username}`} className="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-neutral-100">
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

      <div className="rounded-md border-2 border-dashed border-neutral-300 bg-white p-8 text-center text-sm text-neutral-500">
        The feed lights up once someone analyses an idea. M2 wires analyses into posts — coming next.
      </div>
    </main>
  );
}
