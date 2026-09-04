import type { ReactNode } from "react";

export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-6 py-14">
      <div>
        <h1 className="text-2xl font-bold text-slate-50">{title}</h1>
        <p className="mt-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          Draft placeholder text. This has not been reviewed by a lawyer and should not be treated as final legal
          copy - have it reviewed before this product accepts real customers.
        </p>
      </div>
      <div className="flex flex-col gap-4 text-sm leading-relaxed text-slate-300">{children}</div>
    </div>
  );
}

export function LegalSection({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-slate-100">{heading}</h2>
      <div className="text-sm text-slate-400">{children}</div>
    </section>
  );
}
