import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import HeroUrlInput from "../components/HeroUrlInput";
import { useAuth } from "../context/AuthContext";
import { gradientText, secondaryButton } from "../styles/ui";

/**
 * Decorative floating tiles gesturing at "multi-platform support" around
 * the hero, per the master reference's composition. Deliberately abstract
 * (a generic play/note/aperture/chat glyph in each platform's brand-ish
 * color) rather than the real YouTube/TikTok/Instagram/Facebook marks -
 * tasteful and secondary, never implying affiliation with those platforms.
 */
function PlatformTile({ className, children }: { className: string; children: ReactNode }) {
  return (
    <div
      aria-hidden="true"
      className={`absolute hidden h-14 w-14 rotate-6 items-center justify-center rounded-2xl shadow-lg lg:flex ${className}`}
      style={{ boxShadow: "0 12px 30px -8px rgba(0,0,0,0.6)" }}
    >
      <svg viewBox="0 0 24 24" width={22} height={22} fill="white" stroke="none">
        {children}
      </svg>
    </div>
  );
}

const ICON_TINTS = {
  blue: "border-brand-blue/25 bg-brand-blue/10 text-brand-blue",
  purple: "border-brand-purple/25 bg-brand-purple/10 text-brand-purple",
  aqua: "border-brand-aqua/25 bg-brand-aqua/10 text-brand-aqua",
} as const;

function FeatureIcon({ tint, children }: { tint: keyof typeof ICON_TINTS; children: ReactNode }) {
  return (
    <span className={`flex h-10 w-10 items-center justify-center rounded-xl border ${ICON_TINTS[tint]}`}>
      <svg viewBox="0 0 24 24" width={18} height={18} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round">
        {children}
      </svg>
    </span>
  );
}

const FEATURES: { title: string; body: string; icon: ReactNode }[] = [
  {
    title: "Save",
    body: "Pull video and audio from YouTube, TikTok, Instagram, and Facebook straight to your device.",
    icon: (
      <FeatureIcon tint="blue">
        <path d="M12 4v11" />
        <path d="m7 11 5 5 5-5" />
        <path d="M5 19h14" />
      </FeatureIcon>
    ),
  },
  {
    title: "Convert",
    body: "Every video lands as a genuine, playable MP4 by default - or keep the original container if you'd rather.",
    icon: (
      <FeatureIcon tint="purple">
        <path d="M4 7h13l-3-3" />
        <path d="M20 17H7l3 3" />
      </FeatureIcon>
    ),
  },
  {
    title: "Organize",
    body: "A searchable library of everything you've saved, with quick access to every file.",
    icon: (
      <FeatureIcon tint="aqua">
        <rect x="4" y="5" width="16" height="14" rx="2" />
        <path d="M4 10h16" />
      </FeatureIcon>
    ),
  },
  {
    title: "Process",
    body: "Clip ranges, pick exact formats and bitrates, and batch through a whole playlist at once on paid plans.",
    icon: (
      <FeatureIcon tint="purple">
        <path d="M5 6h14" />
        <path d="M5 12h9" />
        <path d="M5 18h14" />
        <circle cx="16" cy="6" r="1.5" fill="currentColor" stroke="none" />
        <circle cx="10" cy="18" r="1.5" fill="currentColor" stroke="none" />
      </FeatureIcon>
    ),
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
      <section className="relative mx-auto flex max-w-3xl flex-col items-center gap-6 px-6 pb-14 pt-20 text-center sm:pt-28">
        {/* Layered atmospheric light sources rather than one flat gradient -
            a centered glow behind the headline/downloader plus two smaller,
            asymmetric sweeps (blue upper-left, aqua lower-right) for a bit
            of movement. All restrained: low opacity, heavily blurred,
            z-indexed behind content, never affecting text contrast. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[32rem] w-[52rem] -translate-x-1/2 rounded-full bg-brand-gradient-soft opacity-70 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 top-10 -z-10 h-72 w-72 rounded-full bg-brand-radial-1 opacity-60 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 bottom-0 -z-10 h-80 w-80 rounded-full bg-brand-radial-3 opacity-50 blur-3xl"
        />
        {/* A sharper diagonal beam, layered over the soft blurred glows above
            for a bit of the reference's "light cutting through darkness"
            quality rather than only diffuse blobs. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-10 top-0 -z-10 h-[36rem] w-40 origin-top-right rotate-[24deg] bg-gradient-to-b from-brand-aqua/25 via-brand-blue/10 to-transparent blur-2xl"
        />

        <PlatformTile className="-left-8 top-16 bg-red-500/90">
          <path d="M8 6.5v11l9-5.5-9-5.5Z" />
        </PlatformTile>
        <PlatformTile className="-right-6 top-24 bg-gradient-to-br from-amber-400 via-pink-500 to-purple-600">
          <circle cx="12" cy="12" r="5.5" />
        </PlatformTile>
        <PlatformTile className="-left-4 bottom-24 bg-neutral-900 ring-1 ring-white/20">
          <path d="M14 6c0 2.2 1.8 4 4 4v3a7 7 0 0 1-4-1.3V16a5 5 0 1 1-5-5c.3 0 .7 0 1 .1v3a2 2 0 1 0 1 1.8V4h3Z" />
        </PlatformTile>
        <PlatformTile className="-right-10 bottom-8 bg-blue-600">
          <path d="M12 5a7 7 0 0 0-1 13.9V15h-2v-3h2v-1.5c0-2 1.2-3.1 3-3.1.9 0 1.7.1 2 .1v2.3h-1.3c-1 0-1.2.5-1.2 1.1V12h2.4l-.3 3H14.5v3.9A7 7 0 0 0 12 5Z" />
        </PlatformTile>

        <span className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-1.5 text-xs font-medium uppercase tracking-[0.14em] text-slate-400 backdrop-blur-xl">
          Personal media, kept simple
        </span>

        <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight text-slate-50 sm:text-6xl lg:text-7xl">
          Freedom to keep <span className={gradientText}>what you love.</span>
        </h1>

        <p className="max-w-xl text-base text-slate-300 sm:text-lg">
          Loady lets you save the media you care about - straight from YouTube, TikTok, Instagram, and Facebook -
          for personal offline access, in the format you want.
        </p>

        <div className="w-full pt-2">
          <HeroUrlInput />
        </div>

        <p className="text-sm font-medium text-slate-400">Fast. Simple. Yours.</p>

        {!account && (
          <Link to="/pricing" className={`${secondaryButton} mt-2`}>
            See pricing
          </Link>
        )}
      </section>

      <section className="mx-auto grid w-full max-w-5xl gap-5 px-6 pb-14 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="flex flex-col gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.015] p-5 transition-all duration-200 hover:-translate-y-1 hover:border-white/20 hover:bg-white/[0.03] hover:shadow-glow-lg"
          >
            {f.icon}
            <h3 className="font-display text-base font-semibold tracking-tight text-slate-50">{f.title}</h3>
            <p className="text-sm text-slate-300">{f.body}</p>
          </div>
        ))}
      </section>

      <section className="px-6 py-14">
        <div className="mx-auto flex max-w-4xl flex-col gap-10">
          <h2 className="text-center font-display text-3xl font-bold text-slate-50 sm:text-4xl">How it works</h2>

          <div className="relative grid gap-10 sm:grid-cols-3 sm:gap-6">
            {/* Connecting path: a horizontal gradient line through the three
                badges on desktop, a vertical one on mobile - just enough to
                read as one progression rather than three isolated steps. */}
            <div
              aria-hidden="true"
              className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-gradient-to-b from-brand-blue/40 via-brand-purple/40 to-brand-aqua/40 sm:left-0 sm:top-5 sm:h-px sm:w-full sm:translate-x-0 sm:bg-gradient-to-r"
            />
            {STEPS.map((s) => (
              <div key={s.step} className="relative flex flex-col items-center gap-3 text-center">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-gradient text-sm font-semibold text-white shadow-glow ring-4 ring-surface">
                  {s.step}
                </span>
                <p className="text-sm text-slate-300">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto flex max-w-3xl flex-col items-center gap-4 px-6 pb-20 pt-6 text-center">
        <h2 className="font-display text-3xl font-bold text-slate-50 sm:text-4xl">Ready to try it?</h2>
        <p className="text-sm text-slate-300">Free forever for light use. Upgrade any time.</p>
        <Link to={account ? "/dashboard" : "/signup"} className="btn-gradient">
          {account ? "Go to Downloader" : "Create your free account"}
        </Link>
        <p className="mt-2 max-w-md text-xs text-slate-500">
          For use with content you own or are otherwise authorized to download. See our{" "}
          <Link to="/terms" className="underline decoration-dotted underline-offset-2 hover:text-slate-300">
            Terms
          </Link>{" "}
          and{" "}
          <Link to="/copyright" className="underline decoration-dotted underline-offset-2 hover:text-slate-300">
            Copyright Policy
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
