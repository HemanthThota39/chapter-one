"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { loginUrl, useSession } from "@/lib/session";

export default function LandingPage() {
  const session = useSession();
  const router = useRouter();

  useEffect(() => {
    if (session.status === "authenticated") {
      if (!session.user.onboarding_complete) router.replace("/onboarding");
      else router.replace("/feed");
    }
  }, [session, router]);

  if (session.status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-neutral-500">Loading...</div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col">
      <div className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center px-6 py-16">
        <div className="mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-neutral-900 px-3 py-1 text-xs font-medium text-white">
            <span>Chapter One</span>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-neutral-900 md:text-5xl">
            It all starts with Chapter One.
          </h1>
          <p className="mt-4 text-base text-neutral-600 md:text-lg">
            A place for you and your friends to brainstorm startup ideas, get
            rigorous AI-grounded analysis, debate the verdict with facts, and
            share what you build.
          </p>
        </div>

        <div className="space-y-3">
          <a
            href={loginUrl()}
            className="block w-full rounded-md bg-neutral-900 px-5 py-3 text-center text-sm font-medium text-white shadow-sm hover:bg-neutral-700"
          >
            Continue with Google
          </a>
          <p className="text-center text-xs text-neutral-500">
            By continuing you agree to the idea that half-baked ideas are the best kind.
          </p>
        </div>

        <ul className="mt-12 space-y-3 text-sm text-neutral-600">
          <li>
            <span className="font-semibold text-neutral-800">Grounded research.</span>{" "}
            Every report cites real, recent sources. No hallucinated markets.
          </li>
          <li>
            <span className="font-semibold text-neutral-800">Debatable.</span>{" "}
            Push back on a verdict. If you're right, the report updates.
          </li>
          <li>
            <span className="font-semibold text-neutral-800">Shareable.</span>{" "}
            PDF exports, public links, friend-feed reactions.
          </li>
        </ul>
      </div>

      <footer className="border-t border-neutral-200 py-6 text-center text-xs text-neutral-400">
        Chapter One · built for 5 friends · open source · MIT licensed
      </footer>
    </main>
  );
}
