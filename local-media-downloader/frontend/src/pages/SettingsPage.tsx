import { useEffect, useState } from "react";
import ErrorBanner from "../components/ErrorBanner";
import { ApiError, api } from "../services/api";
import type { AppSettings, CookieSource, HealthResponse, Theme } from "../types/api";
import type { DownloadPreferencesOut } from "../types/commercial";
import { applyTheme } from "../utils/theme";

const COOKIE_SOURCES: { value: CookieSource; label: string }[] = [
  { value: "none", label: "No cookies" },
  { value: "chrome", label: "Chrome" },
  { value: "firefox", label: "Firefox" },
  { value: "edge", label: "Edge" },
  { value: "safari", label: "Safari" },
  { value: "file", label: "Cookie file" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-surface-border bg-surface-raised p-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">{title}</h2>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-slate-400">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "rounded-md border border-surface-border bg-surface px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none";

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [preferences, setPreferences] = useState<DownloadPreferencesOut | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [folderStatus, setFolderStatus] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((err) => setError(err instanceof ApiError ? err.message : "Could not load settings."));
    api
      .getDownloadPreferences()
      .then(setPreferences)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load download preferences."));
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  const persist = async (patch: Partial<AppSettings>) => {
    if (!settings) return;
    const next = { ...settings, ...patch };
    setSettings(next);
    try {
      const saved = await api.updateSettings(patch);
      setSettings(saved);
      applyTheme(saved.theme);
      setSaveMessage("Saved");
      setTimeout(() => setSaveMessage(null), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save settings.");
    }
  };

  // container_mode / cookie_source / cookie_file_path are per-account, not
  // part of the shared AppSettings row above - see types/commercial.ts and
  // COMMERCIAL_ARCHITECTURE.md for why. Persisted separately so one user's
  // choice here can never affect anyone else's downloads.
  const persistPreferences = async (patch: Partial<DownloadPreferencesOut>) => {
    if (!preferences) return;
    const next = { ...preferences, ...patch };
    setPreferences(next);
    try {
      const saved = await api.updateDownloadPreferences(patch);
      setPreferences(saved);
      setSaveMessage("Saved");
      setTimeout(() => setSaveMessage(null), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save download preferences.");
    }
  };

  const handleFolderChange = async (path: string) => {
    setSettings((prev) => (prev ? { ...prev, download_dir: path } : prev));
  };

  const handleFolderBlur = async (path: string) => {
    const result = await api.validateFolder(path).catch(() => null);
    if (result?.valid) {
      setFolderStatus(null);
      await persist({ download_dir: path });
    } else {
      setFolderStatus(result?.reason || "This folder could not be used.");
    }
  };

  if (!settings || !preferences) {
    return <div className="mx-auto max-w-3xl px-6 py-10 text-sm text-slate-500">Loading settings…</div>;
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-50">Settings</h1>
        {saveMessage && <span className="text-xs text-emerald-400">{saveMessage}</span>}
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <Section title="General">
        <Field label="Download folder">
          <div className="flex gap-2">
            <input
              type="text"
              value={settings.download_dir}
              onChange={(e) => handleFolderChange(e.target.value)}
              onBlur={(e) => handleFolderBlur(e.target.value)}
              className={`${inputClass} flex-1`}
            />
            <button
              type="button"
              onClick={() => api.openPath(settings.download_dir).catch(() => undefined)}
              className="rounded-md border border-surface-border px-3 py-2 text-sm text-slate-300 hover:border-slate-500"
            >
              Open Downloads Folder
            </button>
          </div>
          {folderStatus && <span className="text-xs text-red-400">{folderStatus}</span>}
        </Field>

        <Field label="Maximum simultaneous downloads">
          <input
            type="number"
            min={1}
            max={10}
            value={settings.max_concurrent_downloads}
            onChange={(e) => persist({ max_concurrent_downloads: Number(e.target.value) })}
            className={`${inputClass} w-24`}
          />
        </Field>

        <Field label="Theme">
          <select
            value={settings.theme}
            onChange={(e) => persist({ theme: e.target.value as Theme })}
            className={inputClass}
          >
            <option value="system">System</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </Field>
      </Section>

      <Section title="Video">
        <Field label="Default video quality">
          <select
            value={settings.default_video_quality}
            onChange={(e) => persist({ default_video_quality: e.target.value })}
            className={inputClass}
          >
            {["best", "2160", "1440", "1080", "720", "480", "360"].map((q) => (
              <option key={q} value={q}>
                {q === "best" ? "Best Available" : `${q}p`}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Video output">
          <select
            value={preferences.container_mode}
            onChange={(e) =>
              persistPreferences({ container_mode: e.target.value as DownloadPreferencesOut["container_mode"] })
            }
            className={inputClass}
          >
            <option value="compatibility">Compatibility MP4 (default)</option>
            <option value="original">Best Quality / Original Container</option>
          </select>
          <span className="text-xs text-slate-500">
            {preferences.container_mode === "compatibility"
              ? "Always downloads a genuine, broadly-playable MP4 (H.264/AAC), converting with FFmpeg when the source is WebM/VP9/AV1/Opus."
              : "Keeps the best source streams' native codec/container as-is (may be WebM or MKV) — never converts."}
          </span>
        </Field>

        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={settings.embed_metadata}
            onChange={(e) => persist({ embed_metadata: e.target.checked })}
            className="h-4 w-4 accent-indigo-500"
          />
          Embed metadata (title, uploader) into the file
        </label>

        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={settings.save_thumbnail}
            onChange={(e) => persist({ save_thumbnail: e.target.checked })}
            className="h-4 w-4 accent-indigo-500"
          />
          Save thumbnail alongside downloaded files
        </label>
      </Section>

      <Section title="Audio">
        <Field label="Preferred audio format">
          <select
            value={settings.preferred_audio_format}
            onChange={(e) => persist({ preferred_audio_format: e.target.value })}
            className={inputClass}
          >
            <option value="mp3">MP3</option>
            <option value="m4a">M4A</option>
            <option value="best">Best (original)</option>
          </select>
        </Field>

        <Field label="MP3 bitrate">
          <select
            value={settings.mp3_bitrate}
            onChange={(e) => persist({ mp3_bitrate: Number(e.target.value) })}
            className={inputClass}
          >
            {[128, 192, 256, 320].map((rate) => (
              <option key={rate} value={rate}>
                {rate} kbps
              </option>
            ))}
          </select>
        </Field>

        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={settings.embed_thumbnail_in_audio}
            onChange={(e) => persist({ embed_thumbnail_in_audio: e.target.checked })}
            className="h-4 w-4 accent-indigo-500"
          />
          Embed thumbnail into downloaded audio files
        </label>
      </Section>

      <Section title="Authentication">
        <p className="text-xs text-slate-500">
          Cookies remain on this computer and are only used locally by the downloader. They are never uploaded
          anywhere, and these choices are private to your account — no other user's downloads are affected by them.
        </p>
        <Field label="Cookie source">
          <select
            value={preferences.cookie_source}
            onChange={(e) => persistPreferences({ cookie_source: e.target.value as CookieSource })}
            className={inputClass}
          >
            {COOKIE_SOURCES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </Field>

        {preferences.cookie_source === "file" && (
          <Field label="Cookie file path (Netscape format)">
            <input
              type="text"
              value={preferences.cookie_file_path || ""}
              onChange={(e) => setPreferences({ ...preferences, cookie_file_path: e.target.value })}
              onBlur={(e) => persistPreferences({ cookie_file_path: e.target.value })}
              placeholder="/path/to/cookies.txt"
              className={inputClass}
            />
          </Field>
        )}
      </Section>

      <Section title="Advanced">
        <div className="grid grid-cols-2 gap-3 text-sm text-slate-400">
          <span>yt-dlp version</span>
          <span className="text-slate-300">{health?.ytdlp_version || "—"}</span>
          <span>FFmpeg path</span>
          <span className="truncate text-slate-300">{health?.ffmpeg_path || "Not found"}</span>
        </div>

        <Field label="Network timeout (seconds)">
          <input
            type="number"
            min={5}
            max={300}
            value={settings.network_timeout_seconds}
            onChange={(e) => persist({ network_timeout_seconds: Number(e.target.value) })}
            className={`${inputClass} w-24`}
          />
        </Field>

        <Field label="Retries">
          <input
            type="number"
            min={0}
            max={20}
            value={settings.retries}
            onChange={(e) => persist({ retries: Number(e.target.value) })}
            className={`${inputClass} w-24`}
          />
        </Field>
      </Section>
    </div>
  );
}
