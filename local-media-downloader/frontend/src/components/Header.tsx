import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { HealthResponse } from "../types/api";
import { PLAN_LABELS } from "../types/commercial";
import LoadyLogo from "./LoadyLogo";

interface HeaderProps {
  health: HealthResponse | null;
  healthError: boolean;
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" : "bg-amber-400"}`}
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
    `rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
      isActive ? "bg-white/10 text-slate-50" : "text-slate-400 hover:text-slate-100"
    }`;

  const handleSignOut = async () => {
    setMenuOpen(false);
    await logout();
    navigate("/");
  };

  return (
    <header className="glass-nav sticky top-0 z-20">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
        <Link to="/" className="shrink-0">
          <LoadyLogo size={30} />
        </Link>

        <div className="hidden items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1 backdrop-blur-xl sm:flex">
          {account ? (
            <>
              <NavLink to="/dashboard" className={navClass}>
                Downloader
              </NavLink>
              <NavLink to="/history" className={navClass}>
                My Downloads
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
            className="hidden items-center gap-3 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-400 backdrop-blur-xl lg:flex"
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
                className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] py-1.5 pl-1.5 pr-3 text-sm text-slate-200 backdrop-blur-xl transition-colors hover:border-white/20 hover:bg-white/[0.07]"
              >
                <span className="rounded-full bg-brand-gradient px-2.5 py-1 text-xs font-semibold text-white shadow-glow">
                  {PLAN_LABELS[account.subscription.plan]}
                </span>
                <span className="hidden max-w-[10rem] truncate sm:inline">{account.user.email}</span>
                <span className="text-slate-500">▾</span>
              </button>
              {menuOpen && (
                <>
                  <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                  <div className="glass-panel-raised absolute right-0 z-20 mt-2 w-56 overflow-hidden p-1.5">
                    <div className="border-b border-white/10 px-3 py-2.5 text-xs text-slate-400">
                      {account.usage.plan === "free"
                        ? `${account.usage.daily_free_downloads_remaining ?? 0} free download(s) left today`
                        : `${account.usage.credits_remaining ?? 0} credit(s) remaining`}
                    </div>
                    <Link
                      to="/account"
                      onClick={() => setMenuOpen(false)}
                      className="block rounded-xl px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/[0.06]"
                    >
                      Account
                    </Link>
                    <Link
                      to="/billing"
                      onClick={() => setMenuOpen(false)}
                      className="block rounded-xl px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/[0.06]"
                    >
                      Billing
                    </Link>
                    <Link
                      to="/usage"
                      onClick={() => setMenuOpen(false)}
                      className="block rounded-xl px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/[0.06]"
                    >
                      Usage
                    </Link>
                    <Link
                      to="/settings"
                      onClick={() => setMenuOpen(false)}
                      className="block rounded-xl px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/[0.06]"
                    >
                      Settings
                    </Link>
                    {account.user.role === "admin" && (
                      <Link
                        to="/admin"
                        onClick={() => setMenuOpen(false)}
                        className="block rounded-xl px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/[0.06]"
                      >
                        Admin
                      </Link>
                    )}
                    <button
                      type="button"
                      onClick={handleSignOut}
                      className="mt-0.5 block w-full rounded-xl px-3 py-2 text-left text-sm text-red-400 transition-colors hover:bg-red-500/10"
                    >
                      Sign out
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/login" className="rounded-full px-3.5 py-2 text-sm font-medium text-slate-300 transition-colors hover:text-slate-100">
                Sign in
              </Link>
              <Link to="/signup" className="btn-gradient !px-4 !py-2 text-sm">
                Get started
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
