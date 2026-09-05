import { FormEvent, useState } from "react";

interface UrlInputProps {
  onAnalyze: (url: string) => void;
  loading: boolean;
}

export default function UrlInput({ onAnalyze, loading }: UrlInputProps) {
  const [value, setValue] = useState("");
  const [justPasted, setJustPasted] = useState(false);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onAnalyze(value.trim());
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setValue(text.trim());
        setJustPasted(true);
        setTimeout(() => setJustPasted(false), 1200);
      }
    } catch {
      // Clipboard access denied by the browser; user can paste manually.
    }
  };

  return (
    <form onSubmit={handleSubmit} className="dashboard-url mx-auto w-full max-w-2xl">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Paste YouTube, TikTok, Instagram or Facebook URL"
            className="input-glass w-full px-5 py-4 text-base"
          />
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handlePaste}
            className={`btn-glass px-4 py-4 transition-colors sm:px-5 ${justPasted ? "!border-brand-aqua/50 !text-brand-aqua" : ""}`}
          >
            {justPasted ? "Pasted" : "Paste"}
          </button>
          <button
            type="submit"
            disabled={loading || !value.trim()}
            className="btn-gradient px-5 py-4 sm:px-6"
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
        </div>
      </div>
    </form>
  );
}
