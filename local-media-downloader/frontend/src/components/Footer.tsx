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
    <footer className="border-t border-white/[0.06] px-6 py-12">
      <div className="mx-auto grid max-w-6xl gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div className="flex flex-col gap-2">
          <LoadyLogo size={24} />
          <p className="max-w-xs text-sm text-slate-500">Media Without Limits</p>
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

      <p className="mx-auto mt-8 max-w-2xl text-center text-xs text-slate-500">
        Loady is a personal media utility for content you own or are otherwise authorized to access and download. It
        is not intended to bypass copy protection, DRM, or paywalls. &copy; {new Date().getFullYear()} Loady.
      </p>
    </footer>
  );
}
