"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { loginUrl, useSession } from "@/lib/session";

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  idp_error: "Microsoft sign-in returned an error. Please try again.",
  missing_params: "Sign-in was incomplete. Please start over.",
  session_lost: "Your browser dropped the sign-in session (third-party cookies may be blocked). Please try again — if it persists, allow cookies for this site.",
  state_mismatch: "Sign-in state check failed. Please try again.",
  token_exchange_failed: "We couldn't complete sign-in with Microsoft. Please try again in a moment.",
  no_id_token: "Microsoft didn't return a valid identity token. Please try again.",
  token_invalid: "Your identity token failed validation. Please try again.",
};

export default function LandingPage() {
  const session = useSession();
  const router = useRouter();
  const [authError, setAuthError] = useState<string | null>(null);
  const [errorDismissed, setErrorDismissed] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setAuthError(params.get("auth_error"));
  }, []);

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
      <div className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center px-6 py-12 md:py-16">
        <div className="mb-10">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-neutral-900 px-3 py-1 text-xs font-medium text-white">
            <span>Chapter One</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-neutral-900 sm:text-4xl md:text-5xl">
            It all starts with Chapter One.
          </h1>
          <p className="mt-4 text-base text-neutral-600 md:text-lg">
            A place for you and your friends to brainstorm startup ideas, get
            rigorous AI-grounded analysis, debate the verdict with facts, and
            share what you build.
          </p>
        </div>

        {authError && !errorDismissed && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <div className="flex items-start justify-between gap-3">
              <p className="break-anywhere">
                {AUTH_ERROR_MESSAGES[authError] || "Sign-in failed. Please try again."}
              </p>
              <button onClick={() => setErrorDismissed(true)} className="shrink-0 text-red-400 hover:text-red-700" aria-label="Dismiss">×</button>
            </div>
          </div>
        )}

        <div className="space-y-3">
          <a href={loginUrl()} className="btn-primary w-full !py-3 text-base">
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
        Chapter One · built for friends · MIT licensed
      </footer>
    </main>
  );
}
