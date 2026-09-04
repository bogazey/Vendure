import { NavLink } from "react-router-dom";
import type { HealthResponse } from "../types/api";

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
  const backendOk = !!health && health.status === "ok";
  const ffmpegOk = !!health?.ffmpeg_available;

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
      isActive ? "bg-surface-raised text-slate-50" : "text-slate-400 hover:text-slate-200"
    }`;

  return (
    <header className="sticky top-0 z-10 border-b border-surface-border bg-surface/95 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="text-xl">⬇️</span>
          <span className="text-base font-semibold tracking-tight">Local Media Downloader</span>
        </div>

        <div className="flex items-center gap-1 rounded-lg border border-surface-border bg-surface-raised/50 p-1">
          <NavLink to="/" end className={navClass}>
            Dashboard
          </NavLink>
          <NavLink to="/history" className={navClass}>
            Downloads
          </NavLink>
          <NavLink to="/settings" className={navClass}>
            Settings
          </NavLink>
        </div>

        <div
          className="flex items-center gap-3 rounded-md border border-surface-border px-3 py-1.5 text-xs text-slate-400"
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
      </div>
    </header>
  );
}
