import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import LoadyLogo from "./LoadyLogo";

function FooterColumn({ heading, children }: { heading: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2.5">
      <h3 className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">{heading}</h3>
      <nav className="flex flex-col gap-2 text-sm text-slate-400">{children}</nav>
    </div>
  );
}

const footerLinkClass = "transition-colors hover:text-slate-200";

/**
 * Global footer - mounted once in App.tsx so every route gets it. Column
 * layout (Product / Account / Legal) follows the master website reference's
 * footer panel; the brand phrase "Media Without Limits" is from the Brand
 * Identity #2 kit's README/guidelines, used here verbatim.
 */
export default function Footer() {
  const { account } = useAuth();

  return (
    <footer className="relative border-t border-white/[0.06] bg-[#05070d]/80 px-6 py-14">
      <div className="mx-auto grid max-w-6xl gap-10 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1fr]">
        <div className="flex flex-col gap-2">
          <LoadyLogo size={27} />
          <p className="mt-2 max-w-xs text-sm leading-6 text-slate-400">Freedom to keep what you love.</p>
        </div>

        <FooterColumn heading="Product">
          <Link to="/" className={footerLinkClass}>
            Home
          </Link>
          <Link to="/pricing" className={footerLinkClass}>
            Pricing
          </Link>
        </FooterColumn>

        <FooterColumn heading="Account">
          {account ? (
            <>
              <Link to="/account" className={footerLinkClass}>
                Account
              </Link>
              <Link to="/settings" className={footerLinkClass}>
                Settings
              </Link>
              <Link to="/billing" className={footerLinkClass}>
                Billing
              </Link>
            </>
          ) : (
            <>
              <Link to="/login" className={footerLinkClass}>
                Sign in
              </Link>
              <Link to="/signup" className={footerLinkClass}>
                Create account
              </Link>
            </>
          )}
        </FooterColumn>

        <FooterColumn heading="Legal">
          <Link to="/terms" className={footerLinkClass}>
            Terms
          </Link>
          <Link to="/privacy" className={footerLinkClass}>
            Privacy
          </Link>
          <Link to="/copyright" className={footerLinkClass}>
            Copyright
          </Link>
        </FooterColumn>
      </div>

      <div className="mx-auto mt-12 flex max-w-6xl flex-col gap-2 border-t border-white/[0.06] pt-7 text-xs leading-5 text-slate-500 sm:flex-row sm:items-end sm:justify-between">
        <p className="max-w-2xl">
          Loady is a personal media utility for content you own or are otherwise authorized to access and download.
          It is not intended to bypass copy protection, DRM, or paywalls.
        </p>
        <p>&copy; {new Date().getFullYear()} Loady. Not affiliated with YouTube, TikTok, Instagram, or Facebook.</p>
      </div>
    </footer>
  );
}
