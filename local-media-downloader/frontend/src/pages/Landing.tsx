import { Link } from "react-router-dom";
import HeroUrlInput from "../components/HeroUrlInput";
import { useAuth } from "../context/AuthContext";
import { gradientText, secondaryButton } from "../styles/ui";

const ASSETS = "/assets/design";

/**
 * Floating hero media tiles from the supplied Loady design asset pack
 * (design-reference/loady-website-assets), positioned per its
 * docs/ASSET_PLACEMENT.md guide: video top-left/right, audio lower-left,
 * image right-mid. Decorative glass tiles, not real photos or platform
 * logos - hidden below lg per the pack's own guidance.
 */
function MediaTile({ src, className, rotate }: { src: string; className: string; rotate: number }) {
  return (
    <img
      src={src}
      alt=""
      aria-hidden="true"
      className={`pointer-events-none absolute hidden h-32 w-32 lg:block xl:h-40 xl:w-40 ${className}`}
      style={{ transform: `rotate(${rotate}deg)` }}
    />
  );
}

const FEATURES: { title: string; body: string; icon: string }[] = [
  {
    title: "Save",
    body: "Pull video and audio from YouTube, TikTok, Instagram, and Facebook straight to your device.",
    icon: `${ASSETS}/icons/features/save.svg`,
  },
  {
    title: "Convert",
    body: "Every video lands as a genuine, playable MP4 by default - or keep the original container if you'd rather.",
    icon: `${ASSETS}/icons/features/convert.svg`,
  },
  {
    title: "Organize",
    body: "A searchable library of everything you've saved, with quick access to every file.",
    icon: `${ASSETS}/icons/features/organize.svg`,
  },
  {
    title: "Process",
    body: "Clip ranges, pick exact formats and bitrates, and batch through a whole playlist at once on paid plans.",
    icon: `${ASSETS}/icons/features/process.svg`,
  },
];

const STEPS = [
  { step: "1", title: "Paste", icon: `${ASSETS}/icons/steps/paste.svg`, body: "Add a link from YouTube, TikTok, Instagram or Facebook." },
  { step: "2", title: "Pick", icon: `${ASSETS}/icons/steps/pick.svg`, body: "Choose your format, quality, and options." },
  { step: "3", title: "Keep", icon: `${ASSETS}/icons/steps/keep.svg`, body: "Download and enjoy it offline, anytime." },
];

const SUPPORTED_PLATFORMS = [
  { name: "YouTube", icon: `${ASSETS}/icons/social/youtube.svg` },
  { name: "TikTok", icon: `${ASSETS}/icons/social/tiktok.svg` },
  { name: "Instagram", icon: `${ASSETS}/icons/social/instagram.svg` },
  { name: "Facebook", icon: `${ASSETS}/icons/social/facebook.svg` },
];

export default function Landing() {
  const { account } = useAuth();

  return (
    <div className="relative z-10 flex flex-col">
      <section className="relative overflow-hidden">
        {/* Hero background from the supplied Loady design asset pack
            (design-reference/loady-website-assets), full-bleed behind the
            whole hero, placed per its own docs/ASSET_PLACEMENT.md rather
            than approximated with CSS gradients - the asset already
            contains the radial glows and wave-line strokes the previous
            hand-rolled divs were chasing. */}
        <img
          src={`${ASSETS}/backgrounds/hero-cinematic-wave.svg`}
          alt=""
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -z-20 h-full w-full object-cover"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -z-10 opacity-40"
          style={{ backgroundImage: `url(${ASSETS}/textures/subtle-grid.svg)`, backgroundRepeat: "repeat" }}
        />

        {/* Media tiles anchor to this wider (max-w-6xl) box rather than the
            narrower text column below, so they sit clear in the margins
            beside the headline instead of overlapping it - the tiles are
            absolutely positioned so this wrapper takes its height from the
            text column it contains. */}
        <div className="relative mx-auto max-w-6xl px-6">
          <MediaTile src={`${ASSETS}/hero/media-tiles/video-tile.svg`} className="left-0 top-6" rotate={-6} />
          <MediaTile src={`${ASSETS}/hero/media-tiles/video-tile.svg`} className="right-0 top-0" rotate={6} />
          <MediaTile src={`${ASSETS}/hero/media-tiles/audio-tile.svg`} className="left-6 bottom-16" rotate={5} />
          <MediaTile src={`${ASSETS}/hero/media-tiles/image-tile.svg`} className="right-6 bottom-6" rotate={-5} />

        <div className="relative mx-auto flex max-w-3xl flex-col items-center gap-6 pb-14 pt-20 text-center sm:pt-28">
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

          <div className="flex items-center gap-3">
            <ul className="flex items-center -space-x-1.5" aria-label="Supported platforms">
              {SUPPORTED_PLATFORMS.map((p) => (
                <li key={p.name} className="rounded-full ring-2 ring-surface">
                  <img src={p.icon} alt="" aria-hidden="true" className="h-7 w-7" />
                  <span className="sr-only">{p.name}</span>
                </li>
              ))}
            </ul>
            <p className="text-sm font-medium text-slate-400">Fast. Simple. Yours.</p>
          </div>

          {!account && (
            <Link to="/pricing" className={`${secondaryButton} mt-2`}>
              See pricing
            </Link>
          )}
        </div>
        </div>
      </section>

      <section id="features" className="mx-auto grid w-full max-w-5xl scroll-mt-24 gap-5 px-6 pb-14 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="flex flex-col gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.015] p-5 transition-all duration-200 hover:-translate-y-1 hover:border-white/20 hover:bg-white/[0.03] hover:shadow-glow-lg"
          >
            <img src={f.icon} alt="" aria-hidden="true" className="h-10 w-10" />
            <h3 className="font-display text-base font-semibold tracking-tight text-slate-50">{f.title}</h3>
            <p className="text-sm text-slate-300">{f.body}</p>
          </div>
        ))}
      </section>

      <section id="how-it-works" className="scroll-mt-24 px-6 py-14">
        <div className="mx-auto flex max-w-4xl flex-col gap-10">
          <h2 className="text-center font-display text-3xl font-bold text-slate-50 sm:text-4xl">How it works</h2>
          <p className="-mt-6 text-center text-sm text-slate-400">Three simple steps. From link to your library.</p>

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
                <img src={s.icon} alt="" aria-hidden="true" className="h-16 w-16 rounded-full bg-surface" />
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-[11px] font-semibold text-slate-300">
                    {s.step}
                  </span>
                  <h3 className="font-display text-base font-semibold text-slate-50">{s.title}</h3>
                </div>
                <p className="max-w-[15rem] text-sm text-slate-300">{s.body}</p>
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
