import { FormEvent, useState } from "react";

interface UrlInputProps {
  onAnalyze: (url: string) => void;
  loading: boolean;
}

export default function UrlInput({ onAnalyze, loading }: UrlInputProps) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onAnalyze(value.trim());
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setValue(text.trim());
    } catch {
      // Clipboard access denied by the browser; user can paste manually.
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-2xl">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Paste YouTube, TikTok, Instagram or Facebook URL"
            className="w-full rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-base text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handlePaste}
            className="rounded-xl border border-surface-border bg-surface-raised px-4 py-4 text-sm font-medium text-slate-300 hover:bg-surface-border sm:px-5"
          >
            Paste
          </button>
          <button
            type="submit"
            disabled={loading || !value.trim()}
            className="rounded-xl bg-indigo-600 px-5 py-4 text-sm font-semibold text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 sm:px-6"
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>
      </div>
    </form>
  );
}
