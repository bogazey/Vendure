import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  const { i18n } = useTranslation();
  return (
    <div className="relative z-10 mx-auto flex max-w-2xl flex-col gap-5 px-6 py-14">
      <div>
        <h1 className="font-display text-2xl font-bold text-slate-50">{title}</h1>
        <p className="mt-2 text-xs text-slate-400">
          {i18n.resolvedLanguage === "ar" ? "سارية من سبتمبر 2026" : "Effective September 2026"}
        </p>
      </div>
      <div className="glass-panel flex flex-col gap-4 p-6 text-sm leading-relaxed text-slate-300">{children}</div>
    </div>
  );
}

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-display text-sm font-semibold text-slate-100">{heading}</h2>
      <div className="text-sm text-slate-400">{children}</div>
    </section>
  );
}
