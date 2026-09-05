import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { HealthResponse } from "../types/api";
import { PLAN_LABELS } from "../types/commercial";
import LoadyLogo from "./LoadyLogo";

interface HeaderProps { health: HealthResponse | null; healthError: boolean; appShell?: boolean }

export default function Header({ appShell = false }: HeaderProps) {
  const { account, logout } = useAuth();
  const navigate = useNavigate();
  const [accountOpen, setAccountOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navClass = ({ isActive }: { isActive: boolean }) => `nav-pill ${isActive ? "nav-pill-active" : ""}`;
  const mobileClass = ({ isActive }: { isActive: boolean }) => `mobile-nav-link ${isActive ? "mobile-nav-link-active" : ""}`;
  const closeMobile = () => setMobileOpen(false);
  const handleSignOut = async () => { setAccountOpen(false); setMobileOpen(false); await logout(); navigate("/"); };

  return (
    <header className={`premium-header ${appShell ? "lg:flex lg:justify-end lg:pr-8" : ""}`}>
      <div
        className={`premium-nav ${
          appShell
            ? "lg:mx-0 lg:w-fit lg:min-w-0 lg:justify-end lg:rounded-2xl lg:border-white/[0.07] lg:bg-[#090d17]/80 lg:px-2"
            : ""
        }`}
      >
        <Link to="/" className={`shrink-0 ${appShell ? "lg:hidden" : ""}`} aria-label="Loady home">
          <LoadyLogo size={34} />
        </Link>

        {!appShell && (
          <nav className="hidden items-center gap-1 lg:flex" aria-label="Primary navigation">
            <Link to="/#features" className="nav-pill">Features</Link>
            <Link to="/#how-it-works" className="nav-pill">How it works</Link>
            <NavLink to="/pricing" className={navClass}>Pricing</NavLink>
          </nav>
        )}

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          {account ? (
            <div className="relative">
              <button type="button" onClick={() => setAccountOpen((v) => !v)} className="account-trigger" aria-expanded={accountOpen}>
                <span className="hidden max-w-[170px] truncate text-slate-400 sm:inline">{account.user.email}</span>
                <span className="sr-only">{PLAN_LABELS[account.subscription.plan]}</span>
                <span className="avatar-chip">{account.user.email.slice(0, 1).toUpperCase()}</span>
              </button>
              {accountOpen && (
                <div className="account-menu">
                  <p className="truncate border-b border-white/[0.08] px-3 py-2.5 text-xs text-slate-400">{account.user.email}</p>
                  <p className="px-3 py-2 text-xs text-slate-500">{account.usage.plan === "free" ? `${account.usage.daily_free_downloads_remaining ?? 0} download(s) remaining today` : `${account.usage.credits_remaining ?? 0} credit(s) remaining`}</p>
                  <Link to="/dashboard" onClick={() => setAccountOpen(false)}>Dashboard</Link>
                  <Link to="/account" onClick={() => setAccountOpen(false)}>Account</Link>
                  <button type="button" onClick={handleSignOut}>Sign out</button>
                </div>
              )}
            </div>
          ) : (
            <div className="hidden items-center gap-2 sm:flex">
              <Link to="/login" className="nav-pill">Sign in</Link>
              <Link to="/signup" className="btn-gradient !px-5 !py-2.5">Get started</Link>
            </div>
          )}
          <button type="button" className="menu-button lg:hidden" onClick={() => setMobileOpen((v) => !v)} aria-expanded={mobileOpen} aria-label={mobileOpen ? "Close navigation" : "Open navigation"}>
            {mobileOpen ? <span className="text-xl leading-none">×</span> : <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 7h16M4 12h16M4 17h16" /></svg>}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="mobile-menu lg:hidden">
          <nav className="flex flex-col gap-1" aria-label="Mobile navigation">
            {account ? <>
              <NavLink to="/dashboard" className={mobileClass} onClick={closeMobile}>Download</NavLink>
              <NavLink to="/history" className={mobileClass} onClick={closeMobile}>My downloads</NavLink>
              <NavLink to="/account" className={mobileClass} onClick={closeMobile}>Account</NavLink>
              <NavLink to="/settings" className={mobileClass} onClick={closeMobile}>Settings</NavLink>
              <NavLink to="/billing" className={mobileClass} onClick={closeMobile}>Billing</NavLink>
              <button type="button" onClick={handleSignOut} className="mobile-nav-link text-left text-red-300">Sign out</button>
            </> : <>
              <Link to="/#features" className="mobile-nav-link" onClick={closeMobile}>Features</Link>
              <Link to="/#how-it-works" className="mobile-nav-link" onClick={closeMobile}>How it works</Link>
              <NavLink to="/pricing" className={mobileClass} onClick={closeMobile}>Pricing</NavLink>
              <NavLink to="/login" className={mobileClass} onClick={closeMobile}>Sign in</NavLink>
              <Link to="/signup" className="btn-gradient mt-2 w-full" onClick={closeMobile}>Get started</Link>
            </>}
          </nav>
        </div>
      )}
    </header>
  );
}
