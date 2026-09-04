import { Link } from "react-router-dom";
import HeroUrlInput from "../components/HeroUrlInput";
import { useAuth } from "../context/AuthContext";
import { gradientText, secondaryButton } from "../styles/ui";

const FEATURES: { title: string; body: string }[] = [
  {
    title: "Save",
    body: "Pull video and audio from YouTube, TikTok, Instagram, and Facebook straight to your device.",
  },
  {
    title: "Convert",
    body: "Every video lands as a genuine, playable MP4 by default - or keep the original container if you'd rather.",
  },
  {
    title: "Organize",
    body: "A searchable library of everything you've saved, with quick access to every file.",
  },
  {
    title: "Process",
    body: "Clip ranges, pick exact formats and bitrates, and batch through a whole playlist at once on paid plans.",
  },
];

const STEPS = [
  { step: "1", body: "Paste a link to content you're authorized to use." },
  { step: "2", body: "Pick a quality, format, or clip range." },
  { step: "3", body: "Keep it - converted and ready, yours to access offline." },
];

export default function Landing() {
  const { account } = useAuth();

  return (
    <div className="relative z-10 flex flex-col">
      <section className="mx-auto flex max-w-3xl flex-col items-center gap-6 px-6 pb-16 pt-20 text-center sm:pt-28">
        <span className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-1.5 text-xs font-medium uppercase tracking-[0.14em] text-slate-400 backdrop-blur-xl">
          Personal media, kept simple
        </span>

        <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight text-slate-50 sm:text-6xl">
          Freedom to keep <span className={gradientText}>what you love.</span>
        </h1>

        <p className="max-w-xl text-base text-slate-400 sm:text-lg">
          Loady lets you save the media you care about - straight from YouTube, TikTok, Instagram, and Facebook -
          for personal offline access, in the format you want.
        </p>

        <div className="w-full pt-2">
          <HeroUrlInput />
        </div>

        <p className="text-sm font-medium text-slate-500">Fast. Simple. Yours.</p>

        {!account && (
          <Link to="/pricing" className={`${secondaryButton} mt-2`}>
            See pricing
          </Link>
        )}
      </section>

      <section className="mx-auto grid w-full max-w-5xl gap-5 px-6 pb-20 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <div key={f.title} className="glass-panel-raised flex flex-col gap-2 p-5 transition-transform duration-200 hover:-translate-y-0.5">
            <h3 className="font-display text-sm font-semibold text-slate-50">{f.title}</h3>
            <p className="text-sm text-slate-400">{f.body}</p>
          </div>
        ))}
      </section>

      <section className="border-y border-white/10 bg-white/[0.02] px-6 py-16 backdrop-blur-sm">
        <div className="mx-auto flex max-w-4xl flex-col gap-8">
          <h2 className="text-center font-display text-xl font-semibold text-slate-50">How it works</h2>
          <div className="grid gap-6 sm:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.step} className="flex flex-col items-center gap-3 text-center">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-gradient text-sm font-semibold text-white shadow-glow">
                  {s.step}
                </span>
                <p className="text-sm text-slate-400">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto flex max-w-3xl flex-col items-center gap-4 px-6 py-20 text-center">
        <h2 className="font-display text-2xl font-semibold text-slate-50">Ready to try it?</h2>
        <p className="text-sm text-slate-400">Free forever for light use. Upgrade any time.</p>
        <Link to={account ? "/dashboard" : "/signup"} className="btn-gradient">
          {account ? "Go to Downloader" : "Create your free account"}
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
