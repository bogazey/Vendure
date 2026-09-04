import { useCallback, useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import FirstRunSetup from "./components/FirstRunSetup";
import Header from "./components/Header";
import Dashboard from "./pages/Dashboard";
import HistoryPage from "./pages/HistoryPage";
import SettingsPage from "./pages/SettingsPage";
import { api } from "./services/api";
import type { HealthResponse } from "./types/api";
import { applyTheme, getCachedThemePreference, watchSystemTheme } from "./utils/theme";

const HEALTH_POLL_MS = 15000;

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [checking, setChecking] = useState(false);

  const checkHealth = useCallback(async () => {
    setChecking(true);
    try {
      const result = await api.health();
      setHealth(result);
      setHealthError(false);
    } catch {
      setHealthError(true);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, HEALTH_POLL_MS);
    return () => clearInterval(interval);
  }, [checkHealth]);

  useEffect(() => {
    api
      .getSettings()
      .then((settings) => applyTheme(settings.theme))
      .catch(() => {
        // Keep whatever theme was applied from the local cache in main.tsx.
      });
    // Reads the freshly-persisted preference on every OS theme change, so it
    // stays correct even after SettingsPage applies a change of its own.
    watchSystemTheme(getCachedThemePreference);
  }, []);

  const showFfmpegGate = health !== null && !health.ffmpeg_available;

  return (
    <div className="min-h-screen bg-surface">
      <Header health={health} healthError={healthError} />
      {showFfmpegGate ? (
        <FirstRunSetup onRecheck={checkHealth} checking={checking} />
      ) : (
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      )}
    </div>
  );
}
