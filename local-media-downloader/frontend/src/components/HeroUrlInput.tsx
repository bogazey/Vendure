import { useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const { account } = useAuth();
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const [justPasted, setJustPasted] = useState(false);

  const platform = useMemo(() => detectPlatformFromUrl(value), [value]);

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        setValue(text.trim());
        setError(null);
        setJustPasted(true);
        setTimeout(() => setJustPasted(false), 1200);
      }
    } catch {
      // Clipboard access denied by the browser; user can paste manually.
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) {
      setError(t("downloader.required"));
      return;
    }
    if (!/^https?:\/\/.+\..+/i.test(trimmed)) {
      setError(t("downloader.invalid"));
      return;
    }
    setError(null);
    navigate(account ? "/dashboard" : "/signup", { state: { initialUrl: trimmed } });
  };

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-3xl">
      <div
        className={`url-console flex flex-col gap-3 p-2.5 transition-all duration-300 sm:flex-row sm:items-center ${
          focused ? "url-console-focused" : ""
        }`}
      >
        <div className="flex flex-1 items-center gap-2 px-2">
          {!platform && (
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              width={16}
              height={16}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.75}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="hidden shrink-0 text-slate-500 sm:block"
            >
              <path d="M9.5 14.5 14.5 9.5" />
              <path d="M11 6.5 12.5 5a3.5 3.5 0 0 1 5 5L16 11.5" />
              <path d="M13 17.5 11.5 19a3.5 3.5 0 0 1-5-5L8 12.5" />
            </svg>
          )}
          {platform && (
            <span className="hidden shrink-0 items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-1 text-xs font-medium text-slate-300 sm:flex">
              <span>{PLATFORM_ICONS[platform]}</span>
              {platform === "unknown" ? t("downloader.link") : PLATFORM_LABELS[platform]}
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
            placeholder={t("downloader.placeholder")}
            dir="ltr"
            className="w-full bg-transparent py-3.5 text-[15px] text-slate-100 placeholder:text-slate-500 focus:outline-none sm:text-base"
          />
        </div>
        <div className="flex gap-2 px-1 pb-1 sm:pb-0">
          <button
            type="button"
            onClick={handlePaste}
            className={`paste-button ${justPasted ? "!border-brand-aqua/50 !text-brand-aqua" : ""}`}
          >
            {justPasted ? t("downloader.pasted") : t("downloader.paste")}
          </button>
          <button type="submit" className="btn-gradient flex-1 !px-7 !py-3.5 text-sm sm:flex-none">
            {t("downloader.continue")}
          </button>
        </div>
      </div>
      {error && <p className="mt-2 px-2 text-sm text-red-400">{error}</p>}
      {!error && platform === "unknown" && value.trim() && (
        <p className="mt-2 px-2 text-sm text-slate-500">
          {t("downloader.unsupported")}
        </p>
      )}
    </form>
  );
}
