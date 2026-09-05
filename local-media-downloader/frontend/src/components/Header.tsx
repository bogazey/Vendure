import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import type { HealthResponse } from "../types/api";
import LoadyLogo from "./LoadyLogo";
import LanguageSwitcher from "./LanguageSwitcher";

interface HeaderProps { health: HealthResponse | null; healthError: boolean; appShell?: boolean }

export default function Header({ appShell = false }: HeaderProps) {
  const { t } = useTranslation();
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
        <Link to="/" className={`shrink-0 ${appShell ? "lg:hidden" : ""}`} aria-label={t("nav.home")}>
          <LoadyLogo size={34} />
        </Link>

        {!appShell && (
          <nav className="hidden items-center gap-1 lg:flex" aria-label={t("nav.primary")}>
            <Link to="/#features" className="nav-pill">{t("nav.features")}</Link>
            <Link to="/#how-it-works" className="nav-pill">{t("nav.how")}</Link>
            <NavLink to="/pricing" className={navClass}>{t("nav.pricing")}</NavLink>
          </nav>
        )}

        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <div className="hidden lg:block"><LanguageSwitcher /></div>
          {account ? (
            <div className="relative">
              <button type="button" onClick={() => setAccountOpen((v) => !v)} className="account-trigger" aria-expanded={accountOpen}>
                <span className="hidden max-w-[170px] truncate text-slate-400 sm:inline">{account.user.email}</span>
                <span className="sr-only">{t(`pricing.plans.${account.subscription.plan}.name`)}</span>
                <span className="avatar-chip">{account.user.email.slice(0, 1).toUpperCase()}</span>
              </button>
              {accountOpen && (
                <div className="account-menu">
                  <p className="truncate border-b border-white/[0.08] px-3 py-2.5 text-xs text-slate-400">{account.user.email}</p>
                  <p className="px-3 py-2 text-xs text-slate-500">{account.usage.plan === "free" ? t("accountMenu.downloadsRemaining", { count: account.usage.daily_free_downloads_remaining ?? 0 }) : t("accountMenu.creditsRemaining", { count: account.usage.credits_remaining ?? 0 })}</p>
                  <Link to="/dashboard" onClick={() => setAccountOpen(false)}>{t("accountMenu.dashboard")}</Link>
                  <Link to="/account" onClick={() => setAccountOpen(false)}>{t("nav.account")}</Link>
                  <button type="button" onClick={handleSignOut}>{t("nav.signout")}</button>
                </div>
              )}
            </div>
          ) : (
            <div className="hidden items-center gap-2 sm:flex">
              <Link to="/login" className="nav-pill">{t("nav.login")}</Link>
              <Link to="/signup" className="btn-gradient !px-5 !py-2.5">{t("nav.signup")}</Link>
            </div>
          )}
          <button type="button" className="menu-button lg:hidden" onClick={() => setMobileOpen((v) => !v)} aria-expanded={mobileOpen} aria-label={mobileOpen ? t("nav.close") : t("nav.open")}>
            {mobileOpen ? <span className="text-xl leading-none">×</span> : <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 7h16M4 12h16M4 17h16" /></svg>}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <div className="mobile-menu lg:hidden">
          <nav className="flex flex-col gap-1" aria-label={t("nav.mobile")}>
            {account ? <>
              <NavLink to="/dashboard" className={mobileClass} onClick={closeMobile}>{t("nav.dashboard")}</NavLink>
              <NavLink to="/history" className={mobileClass} onClick={closeMobile}>{t("nav.downloads")}</NavLink>
              <NavLink to="/account" className={mobileClass} onClick={closeMobile}>{t("nav.account")}</NavLink>
              <NavLink to="/settings" className={mobileClass} onClick={closeMobile}>{t("nav.settings")}</NavLink>
              <NavLink to="/billing" className={mobileClass} onClick={closeMobile}>{t("nav.billing")}</NavLink>
              {account.user.role === "admin" && (
                <NavLink to="/admin" className={mobileClass} onClick={closeMobile}>{t("nav.admin")}</NavLink>
              )}
              <button type="button" onClick={handleSignOut} className="mobile-nav-link text-start text-red-300">{t("nav.signout")}</button>
            </> : <>
              <Link to="/#features" className="mobile-nav-link" onClick={closeMobile}>{t("nav.features")}</Link>
              <Link to="/#how-it-works" className="mobile-nav-link" onClick={closeMobile}>{t("nav.how")}</Link>
              <NavLink to="/pricing" className={mobileClass} onClick={closeMobile}>{t("nav.pricing")}</NavLink>
              <NavLink to="/login" className={mobileClass} onClick={closeMobile}>{t("nav.login")}</NavLink>
              <Link to="/signup" className="btn-gradient mt-2 w-full" onClick={closeMobile}>{t("nav.signup")}</Link>
            </>}
            <LanguageSwitcher mobile />
          </nav>
        </div>
      )}
    </header>
  );
}
