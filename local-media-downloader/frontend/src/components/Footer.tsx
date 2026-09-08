import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const { account } = useAuth();

  return (
    <footer className="relative border-t border-white/[0.06] bg-[#05070d]/80 px-6 py-14">
      <div className="mx-auto grid max-w-6xl gap-10 sm:grid-cols-2 lg:grid-cols-[1.6fr_1fr_1fr_1fr]">
        <div className="flex flex-col gap-2">
          <LoadyLogo size={27} />
          <p className="mt-2 max-w-xs text-sm leading-6 text-slate-400">{t("footer.tagline")}</p>
        </div>

        <FooterColumn heading={t("footer.product")}>
          <Link to="/" className={footerLinkClass}>
            {t("nav.home")}
          </Link>
          <Link to="/pricing" className={footerLinkClass}>
            {t("nav.pricing")}
          </Link>
        </FooterColumn>

        <FooterColumn heading={t("footer.account")}>
          {account ? (
            <>
              <Link to="/account" className={footerLinkClass}>
                {t("nav.account")}
              </Link>
              <Link to="/settings" className={footerLinkClass}>
                {t("nav.settings")}
              </Link>
              <Link to="/billing" className={footerLinkClass}>
                {t("nav.billing")}
              </Link>
            </>
          ) : (
            <>
              <Link to="/login" className={footerLinkClass}>
                {t("nav.login")}
              </Link>
              <Link to="/signup" className={footerLinkClass}>
                {t("footer.createAccount")}
              </Link>
            </>
          )}
        </FooterColumn>

        <FooterColumn heading={t("footer.legal")}>
          <Link to="/terms" className={footerLinkClass}>
            {t("footer.terms")}
          </Link>
          <Link to="/privacy" className={footerLinkClass}>
            {t("footer.privacy")}
          </Link>
          <Link to="/copyright" className={footerLinkClass}>
            {t("footer.copyright")}
          </Link>
          <Link to="/acceptable-use" className={footerLinkClass}>
            {t("footer.acceptableUse")}
          </Link>
          <Link to="/refund-policy" className={footerLinkClass}>
            {t("footer.refunds")}
          </Link>
        </FooterColumn>
      </div>

      <div className="mx-auto mt-12 flex max-w-6xl flex-col gap-2 border-t border-white/[0.06] pt-7 text-xs leading-5 text-slate-500 sm:flex-row sm:items-end sm:justify-between">
        <p className="max-w-2xl">
          {t("footer.notice")}
        </p>
        <p>{t("footer.copyrightLine", { year: new Date().getFullYear() })}</p>
      </div>
    </footer>
  );
}
