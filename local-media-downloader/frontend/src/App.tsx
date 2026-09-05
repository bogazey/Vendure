import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import AuroraBackground from "./components/AuroraBackground";
import FirstRunSetup from "./components/FirstRunSetup";
import Footer from "./components/Footer";
import Header from "./components/Header";
import ProtectedRoute, { AdminRoute } from "./components/ProtectedRoute";
import Sidebar from "./components/Sidebar";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Account from "./pages/Account";
import Admin from "./pages/Admin";
import ForgotPassword from "./pages/auth/ForgotPassword";
import Login from "./pages/auth/Login";
import ResetPassword from "./pages/auth/ResetPassword";
import Signup from "./pages/auth/Signup";
import VerifyEmail from "./pages/auth/VerifyEmail";
import Billing from "./pages/Billing";
import Dashboard from "./pages/Dashboard";
import HistoryPage from "./pages/HistoryPage";
import Landing from "./pages/Landing";
import Copyright from "./pages/legal/Copyright";
import Privacy from "./pages/legal/Privacy";
import Terms from "./pages/legal/Terms";
import Pricing from "./pages/Pricing";
import SettingsPage from "./pages/SettingsPage";
import Usage from "./pages/Usage";
import { api } from "./services/api";
import type { HealthResponse } from "./types/api";
import { applyTheme } from "./utils/theme";

const HEALTH_POLL_MS = 15000;

// Routes that belong to the authenticated product shell - these get the
// left Sidebar (desktop) instead of the marketing top nav, and no footer,
// per the master website reference. Mobile is unaffected: it keeps the
// existing Header hamburger drawer everywhere, sidebar or not.
const APP_ROUTE_PREFIXES = ["/dashboard", "/history", "/settings", "/account", "/billing", "/usage"];

function AppShell() {
  const { account } = useAuth();
  const location = useLocation();
  const isAppRoute = APP_ROUTE_PREFIXES.some((p) => location.pathname.startsWith(p));
  const showSidebar = isAppRoute && !!account;

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
  }, []);

  // FFmpeg is a local-machine prerequisite for actually running downloads,
  // so it only gates the downloader itself (Dashboard/History/Settings) -
  // marketing, auth, legal, and account/billing pages work regardless.
  const showFfmpegGate = health !== null && !health.ffmpeg_available;
  const gated = (element: ReactElement) =>
    showFfmpegGate ? <FirstRunSetup onRecheck={checkHealth} checking={checking} /> : element;

  return (
    <div className="relative min-h-screen bg-surface">
      <AuroraBackground />
      <div className="relative z-10 flex min-h-screen">
        {showSidebar && <Sidebar />}
        <div className="flex min-h-screen flex-1 flex-col">
          <Header health={health} healthError={healthError} appShell={showSidebar} />
          <div className="flex flex-1 flex-col">
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/verify-email" element={<VerifyEmail />} />
              <Route path="/terms" element={<Terms />} />
              <Route path="/privacy" element={<Privacy />} />
              <Route path="/copyright" element={<Copyright />} />

              <Route path="/dashboard" element={<ProtectedRoute>{gated(<Dashboard />)}</ProtectedRoute>} />
              <Route path="/history" element={<ProtectedRoute>{gated(<HistoryPage />)}</ProtectedRoute>} />
              <Route path="/settings" element={<ProtectedRoute>{gated(<SettingsPage />)}</ProtectedRoute>} />
              <Route path="/account" element={<ProtectedRoute><Account /></ProtectedRoute>} />
              <Route path="/billing" element={<ProtectedRoute><Billing /></ProtectedRoute>} />
              <Route path="/usage" element={<ProtectedRoute><Usage /></ProtectedRoute>} />
              <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
            </Routes>
          </div>
          {!showSidebar && <Footer />}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
