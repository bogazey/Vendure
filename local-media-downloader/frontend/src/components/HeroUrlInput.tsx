import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { detectPlatformFromUrl, PLATFORM_ICONS, PLATFORM_LABELS } from "../utils/platform";

/**
 * The hero's focal point: a real, functional URL input - not decorative.
 * Submitting hands the URL forward to signup (or straight to the
 * Downloader if already signed in) via router state, where it's picked up
 * and analyzed automatically (see Signup.tsx / Dashboard.tsx). Actually
 * downloading still requires an account, per the app's existing policy -
 * this just removes the friction of retyping the link after signing up.
 */
export default function HeroUrlInput() {
  const { account } = useAuth();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);

  const platform = useMemo(() => detectPlatformFromUrl(value), [value]);

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setValue(text.trim());
        setError(null);
      }
    } catch {
      // Clipboard access denied by the browser; user can paste manually.
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) {
      setError("Paste a link to get started.");
      return;
    }
    if (!/^https?:\/\/.+\..+/i.test(trimmed)) {
      setError("That doesn't look like a valid URL.");
      return;
    }
    setError(null);
    navigate(account ? "/dashboard" : "/signup", { state: { initialUrl: trimmed } });
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-2xl">
      <div
        className={`glass-panel gradient-border flex flex-col gap-3 p-3 transition-shadow duration-300 sm:flex-row sm:items-center ${
          focused ? "shadow-glow-lg" : ""
        }`}
      >
        <div className="flex flex-1 items-center gap-2 px-2">
          {platform && (
            <span className="hidden shrink-0 items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-1 text-xs font-medium text-slate-300 sm:flex">
              <span>{PLATFORM_ICONS[platform]}</span>
              {platform === "unknown" ? "Link" : PLATFORM_LABELS[platform]}
            </span>
          )}
          <input
            type="text"
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (error) setError(null);
            }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Paste a YouTube, TikTok, Instagram or Facebook link…"
            className="w-full bg-transparent py-3 text-base text-slate-100 placeholder:text-slate-500 focus:outline-none"
          />
        </div>
        <div className="flex gap-2 px-1 pb-1 sm:pb-0">
          <button type="button" onClick={handlePaste} className="btn-glass !px-4 !py-3 text-sm">
            Paste
          </button>
          <button type="submit" className="btn-gradient flex-1 !px-6 !py-3 text-sm sm:flex-none">
            Continue
          </button>
        </div>
      </div>
      {error && <p className="mt-2 px-2 text-sm text-red-400">{error}</p>}
      {!error && platform === "unknown" && value.trim() && (
        <p className="mt-2 px-2 text-sm text-slate-500">
          We support YouTube, TikTok, Instagram, and Facebook - Loady will double-check this link for you.
        </p>
      )}
    </form>
  );
}
