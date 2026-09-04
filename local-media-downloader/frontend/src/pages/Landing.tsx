import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const FEATURES: { title: string; body: string }[] = [
  {
    title: "Save",
    body: "Pull video and audio from YouTube, TikTok, Instagram, and Facebook straight to your computer.",
  },
  {
    title: "Convert",
    body: "Every video lands as a genuine, playable MP4 by default - or keep the original container if you'd rather.",
  },
  {
    title: "Organize",
    body: "A searchable history of everything you've downloaded, with quick access to the files on disk.",
  },
  {
    title: "Process",
    body: "Clip ranges, pick exact formats and bitrates, and batch through a whole playlist at once on paid plans.",
  },
];

const STEPS = [
  { step: "1", body: "Paste a link to content you're authorized to use." },
  { step: "2", body: "Pick a quality, format, or clip range." },
  { step: "3", body: "Download, converted and ready to use." },
];

export default function Landing() {
  const { account } = useAuth();

  return (
    <div className="flex flex-col">
      <section className="mx-auto flex max-w-3xl flex-col items-center gap-5 px-6 py-24 text-center">
        <h1 className="text-4xl font-bold tracking-tight text-slate-50 sm:text-5xl">Save. Convert. Create.</h1>
        <p className="max-w-xl text-base text-slate-400">
          Your personal media utility for downloading and processing content you're authorized to use.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link
            to={account ? "/dashboard" : "/signup"}
            className="rounded-md bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-400"
          >
            {account ? "Go to Dashboard" : "Get started free"}
          </Link>
          <Link
            to="/pricing"
            className="rounded-md border border-surface-border px-5 py-2.5 text-sm font-semibold text-slate-200 hover:border-slate-500"
          >
            See pricing
          </Link>
        </div>
      </section>

      <section className="mx-auto grid max-w-5xl gap-5 px-6 pb-20 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <div key={f.title} className="flex flex-col gap-2 rounded-xl border border-surface-border bg-surface-raised p-5">
            <h3 className="text-sm font-semibold text-slate-50">{f.title}</h3>
            <p className="text-sm text-slate-400">{f.body}</p>
          </div>
        ))}
      </section>

      <section className="border-y border-surface-border bg-surface-raised/40 px-6 py-16">
        <div className="mx-auto flex max-w-4xl flex-col gap-8">
          <h2 className="text-center text-xl font-semibold text-slate-50">How it works</h2>
          <div className="grid gap-6 sm:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.step} className="flex flex-col items-center gap-2 text-center">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500/20 text-sm font-semibold text-indigo-300">
                  {s.step}
                </span>
                <p className="text-sm text-slate-400">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto flex max-w-3xl flex-col items-center gap-4 px-6 py-20 text-center">
        <h2 className="text-xl font-semibold text-slate-50">Ready to try it?</h2>
        <p className="text-sm text-slate-400">Free forever for light use. Upgrade any time.</p>
        <Link
          to={account ? "/dashboard" : "/signup"}
          className="rounded-md bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-indigo-400"
        >
          {account ? "Go to Dashboard" : "Create your free account"}
        </Link>
        <p className="mt-2 max-w-md text-xs text-slate-600">
          For use with content you own or are otherwise authorized to download. See our{" "}
          <Link to="/terms" className="underline decoration-dotted underline-offset-2 hover:text-slate-400">
            Terms
          </Link>{" "}
          and{" "}
          <Link to="/copyright" className="underline decoration-dotted underline-offset-2 hover:text-slate-400">
            Copyright Policy
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
