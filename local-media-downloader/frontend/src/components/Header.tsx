import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { HealthResponse } from "../types/api";
import { PLAN_LABELS } from "../types/commercial";

interface HeaderProps {
  health: HealthResponse | null;
  healthError: boolean;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${ok ? "bg-emerald-400" : "bg-amber-400"}`}
      aria-hidden
    />
  );
}

export default function Header({ health, healthError }: HeaderProps) {
  const { account, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const backendOk = !!health && health.status === "ok";
  const ffmpegOk = !!health?.ffmpeg_available;

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
      isActive ? "bg-surface-raised text-slate-50" : "text-slate-400 hover:text-slate-200"
    }`;

  const handleSignOut = async () => {
    setMenuOpen(false);
    await logout();
    navigate("/");
  };

  return (
    <header className="sticky top-0 z-10 border-b border-surface-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
        <Link to="/" className="flex items-center gap-3">
          <span className="text-xl">⬇️</span>
          <span className="text-base font-semibold tracking-tight">Local Media Downloader</span>
        </Link>

        <div className="flex items-center gap-1 rounded-lg border border-surface-border bg-surface-raised/50 p-1">
          {account ? (
            <>
              <NavLink to="/dashboard" className={navClass}>
                Dashboard
              </NavLink>
              <NavLink to="/history" className={navClass}>
                Downloads
              </NavLink>
              <NavLink to="/pricing" className={navClass}>
                Pricing
              </NavLink>
            </>
          ) : (
            <>
              <NavLink to="/" end className={navClass}>
                Home
              </NavLink>
              <NavLink to="/pricing" className={navClass}>
                Pricing
              </NavLink>
            </>
          )}
        </div>

        <div className="flex items-center gap-3">
          <div
            className="hidden items-center gap-3 rounded-md border border-surface-border px-3 py-1.5 text-xs text-slate-400 sm:flex"
            title={
              healthError
                ? "Backend unreachable"
                : `Backend: ${backendOk ? "ready" : "degraded"} · FFmpeg: ${ffmpegOk ? "found" : "missing"}`
            }
          >
            <span className="flex items-center gap-1.5">
              <StatusDot ok={!healthError && backendOk} />
              Backend
            </span>
            <span className="flex items-center gap-1.5">
              <StatusDot ok={!healthError && ffmpegOk} />
              FFmpeg
            </span>
          </div>

          {account ? (
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-2 rounded-md border border-surface-border px-3 py-1.5 text-sm text-slate-200 hover:border-slate-500"
              >
                <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-xs font-semibold text-indigo-300">
                  {PLAN_LABELS[account.subscription.plan]}
                </span>
                <span className="hidden max-w-[10rem] truncate sm:inline">{account.user.email}</span>
                <span className="text-slate-500">▾</span>
              </button>
              {menuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                  <div className="absolute right-0 z-20 mt-2 w-52 rounded-lg border border-surface-border bg-surface-raised p-1 shadow-lg">
                    <div className="border-b border-surface-border px-3 py-2 text-xs text-slate-500">
                      {account.usage.plan === "free"
                        ? `${account.usage.daily_free_downloads_remaining ?? 0} free download(s) left today`
                        : `${account.usage.credits_remaining ?? 0} credit(s) remaining`}
                    </div>
                    <Link to="/account" onClick={() => setMenuOpen(false)} className="block rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-surface">
                      Account
                    </Link>
                    <Link to="/billing" onClick={() => setMenuOpen(false)} className="block rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-surface">
                      Billing
                    </Link>
                    <Link to="/usage" onClick={() => setMenuOpen(false)} className="block rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-surface">
                      Usage
                    </Link>
                    <Link to="/settings" onClick={() => setMenuOpen(false)} className="block rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-surface">
                      Settings
                    </Link>
                    {account.user.role === "admin" && (
                      <Link to="/admin" onClick={() => setMenuOpen(false)} className="block rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-surface">
                        Admin
                      </Link>
                    )}
                    <button
                      type="button"
                      onClick={handleSignOut}
                      className="block w-full rounded-md px-3 py-2 text-left text-sm text-red-400 hover:bg-surface"
                    >
                      Sign out
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/login" className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-300 hover:text-slate-100">
                Sign in
              </Link>
              <Link
                to="/signup"
                className="rounded-md bg-indigo-500 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-400"
              >
                Get started
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
