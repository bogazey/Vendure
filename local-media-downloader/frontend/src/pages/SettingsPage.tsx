import { useEffect, useState } from "react";
import ErrorBanner from "../components/ErrorBanner";
import { useTranslation } from "react-i18next";
import { ApiError, api } from "../services/api";
import { appPageShell } from "../styles/ui";
import type { AppSettings, CookieSource, HealthResponse, Theme } from "../types/api";
import type { DownloadPreferencesOut } from "../types/commercial";
import { applyTheme } from "../utils/theme";

const COOKIE_SOURCES: CookieSource[] = ["none", "chrome", "firefox", "edge", "safari", "file"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="glass-panel flex flex-col gap-3 p-5">
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

const inputClass = "input-glass py-2";

export default function SettingsPage() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [preferences, setPreferences] = useState<DownloadPreferencesOut | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch((err) => setError(err instanceof ApiError ? err.message : t("settingsPage.loadError")));
    api
      .getDownloadPreferences()
      .then(setPreferences)
      .catch((err) => setError(err instanceof ApiError ? err.message : t("settingsPage.preferencesError")));
    api.health().then(setHealth).catch(() => undefined);
  }, [t]);

  const persist = async (patch: Partial<AppSettings>) => {
    if (!settings) return;
    const next = { ...settings, ...patch };
    setSettings(next);
    try {
      const saved = await api.updateSettings(patch);
      setSettings(saved);
      applyTheme(saved.theme);
      setSaveMessage(t("app.saved"));
      setTimeout(() => setSaveMessage(null), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settingsPage.saveError"));
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
      setSaveMessage(t("app.saved"));
      setTimeout(() => setSaveMessage(null), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("settingsPage.savePreferencesError"));
    }
  };

  if (!settings || !preferences) {
    return <div className="relative z-10 mx-auto max-w-3xl px-6 py-10 text-sm text-slate-500">{t("settingsPage.loading")}</div>;
  }

  return (
    <div className={appPageShell}>
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-slate-50">{t("app.settingsTitle")}</h1>
        {saveMessage && <span className="text-xs text-emerald-400">{saveMessage}</span>}
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <div className="flex flex-col gap-6 lg:grid lg:grid-cols-2 lg:items-start lg:gap-6">
      <Section title={t("app.general")}>
        <Field label={t("settingsPage.downloadFolder")}>
          <div className="flex gap-2">
            <span
              className={`${inputClass} flex-1 truncate text-slate-400`}
              title={settings.download_dir}
            >
              {settings.download_dir}
            </span>
            <button type="button" onClick={() => api.openPath(settings.download_dir).catch(() => undefined)} className="btn-glass px-3 py-2">
              {t("settingsPage.openFolder")}
            </button>
          </div>
          <span className="text-xs text-slate-500">
            {t("settingsPage.folderHelp")}
          </span>
        </Field>

        <Field label={t("settingsPage.maximum")}>
          <input
            type="number"
            min={1}
            max={10}
            value={settings.max_concurrent_downloads}
            onChange={(e) => persist({ max_concurrent_downloads: Number(e.target.value) })}
            className={`${inputClass} w-24`}
          />
        </Field>

        <Field label={t("settingsPage.theme")}>
          <select
            value={settings.theme}
            onChange={(e) => persist({ theme: e.target.value as Theme })}
            className={inputClass}
          >
            {/* "system" no longer tracks the OS - Loady's dark identity is
                fixed, so it's relabeled here to say what it actually does.
                The stored value stays "system" for API/backend compatibility. */}
            <option value="system">{t("settingsPage.darkDefault")}</option>
            <option value="light">{t("settingsPage.light")}</option>
            <option value="dark">{t("settingsPage.dark")}</option>
          </select>
        </Field>
      </Section>

      <Section title={t("app.video")}>
        <Field label={t("settingsPage.defaultQuality")}>
          <select
            value={settings.default_video_quality}
            onChange={(e) => persist({ default_video_quality: e.target.value })}
            className={inputClass}
          >
            {["best", "2160", "1440", "1080", "720", "480", "360"].map((q) => (
              <option key={q} value={q}>
                {q === "best" ? t("settingsPage.bestAvailable") : `${q}p`}
              </option>
            ))}
          </select>
        </Field>

        <Field label={t("settingsPage.videoOutput")}>
          <select
            value={preferences.container_mode}
            onChange={(e) =>
              persistPreferences({ container_mode: e.target.value as DownloadPreferencesOut["container_mode"] })
            }
            className={inputClass}
          >
            <option value="compatibility">{t("settingsPage.compatibility")}</option>
            <option value="original">{t("settingsPage.original")}</option>
          </select>
          <span className="text-xs text-slate-500">
            {preferences.container_mode === "compatibility"
              ? t("settingsPage.compatibilityHelp")
              : t("settingsPage.originalHelp")}
          </span>
        </Field>

        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={settings.embed_metadata}
            onChange={(e) => persist({ embed_metadata: e.target.checked })}
            className="h-4 w-4 rounded border-white/20 bg-transparent accent-brand-aqua"
          />
          {t("settingsPage.embedMetadata")}
        </label>

        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={settings.save_thumbnail}
            onChange={(e) => persist({ save_thumbnail: e.target.checked })}
            className="h-4 w-4 rounded border-white/20 bg-transparent accent-brand-aqua"
          />
          {t("settingsPage.saveThumbnail")}
        </label>
      </Section>

      <Section title={t("app.audio")}>
        <Field label={t("settingsPage.audioFormat")}>
          <select
            value={settings.preferred_audio_format}
            onChange={(e) => persist({ preferred_audio_format: e.target.value })}
            className={inputClass}
          >
            <option value="mp3">MP3</option>
            <option value="m4a">M4A</option>
            <option value="best">{t("settingsPage.bestOriginal")}</option>
          </select>
        </Field>

        <Field label={t("settingsPage.bitrate")}>
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
            className="h-4 w-4 rounded border-white/20 bg-transparent accent-brand-aqua"
          />
          {t("settingsPage.embedAudioThumbnail")}
        </label>
      </Section>

      <Section title={t("app.authentication")}>
        <p className="text-xs text-slate-500">
          {t("settingsPage.cookiesHelp")}
        </p>
        <Field label={t("settingsPage.cookieSource")}>
          <select
            value={preferences.cookie_source}
            onChange={(e) => persistPreferences({ cookie_source: e.target.value as CookieSource })}
            className={inputClass}
          >
            {COOKIE_SOURCES.map((source) => (
              <option key={source} value={source}>
                {source === "none" ? t("settingsPage.noCookies") : source === "file" ? t("settingsPage.cookieFile") : source[0].toUpperCase() + source.slice(1)}
              </option>
            ))}
          </select>
        </Field>

        {preferences.cookie_source === "file" && (
          <Field label={t("settingsPage.cookiePath")}>
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

      <Section title={t("app.advanced")}>
        <div className="grid grid-cols-2 gap-3 text-sm text-slate-400">
          <span>{t("settingsPage.ytdlp")}</span>
          <span className="text-slate-300">{health?.ytdlp_version || "—"}</span>
          <span>{t("settingsPage.ffmpeg")}</span>
          <span className="truncate text-slate-300">{health?.ffmpeg_path || t("settingsPage.notFound")}</span>
        </div>

        <Field label={t("settingsPage.timeout")}>
          <input
            type="number"
            min={5}
            max={300}
            value={settings.network_timeout_seconds}
            onChange={(e) => persist({ network_timeout_seconds: Number(e.target.value) })}
            className={`${inputClass} w-24`}
          />
        </Field>

        <Field label={t("settingsPage.retries")}>
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
    </div>
  );
}
