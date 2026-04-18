"use client";

import { useState } from "react";

type Props = {
  onStart: (idea: string) => void;
  disabled?: boolean;
};

export default function AnalyzerForm({ onStart, disabled }: Props) {
  const [idea, setIdea] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = idea.trim();
    if (trimmed.length < 20) return;
    onStart(trimmed);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <label htmlFor="idea" className="block text-sm font-medium text-neutral-700">
        Describe your startup idea
      </label>
      <textarea
        id="idea"
        name="idea"
        rows={6}
        required
        minLength={20}
        maxLength={4000}
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="e.g. A compliance copilot that helps Indian CA firms automate GST filings for their SMB clients..."
        className="w-full rounded-md border border-neutral-300 bg-white p-3 text-sm shadow-sm focus:border-neutral-500 focus:outline-none focus:ring-2 focus:ring-neutral-200"
        disabled={disabled}
      />
      <div className="flex items-center justify-between">
        <span className="text-xs text-neutral-500">
          {idea.length}/4000 chars (min 20)
        </span>
        <button
          type="submit"
          disabled={disabled || idea.trim().length < 20}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-400"
        >
          {disabled ? "Analyzing..." : "Analyze"}
        </button>
      </div>
    </form>
  );
}
