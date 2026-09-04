import { Link } from "react-router-dom";
import LoadyLogo from "./LoadyLogo";

/**
 * Understated, global footer - branding, legal links, and a short use
 * notice. Mounted once in App.tsx so every page gets it without repeating
 * markup, and kept minimal since it's not the focal point of any page.
 */
export default function Footer() {
  return (
    <footer className="border-t border-white/[0.06] px-6 py-8">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 text-center sm:flex-row sm:items-center sm:justify-between sm:text-left">
        <LoadyLogo size={22} />

        <nav className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-slate-400">
          <Link to="/terms" className="transition-colors hover:text-slate-200">
            Terms
          </Link>
          <Link to="/privacy" className="transition-colors hover:text-slate-200">
            Privacy
          </Link>
          <Link to="/copyright" className="transition-colors hover:text-slate-200">
            Copyright
          </Link>
        </nav>
      </div>
      <p className="mx-auto mt-5 max-w-2xl text-center text-xs text-slate-500">
        Loady is a personal media utility for content you own or are otherwise authorized to access and download. It
        is not intended to bypass copy protection, DRM, or paywalls. &copy; {new Date().getFullYear()} Loady.
      </p>
    </footer>
  );
}
