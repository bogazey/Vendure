import { Link } from "react-router-dom";
import HeroUrlInput from "../components/HeroUrlInput";
import { useAuth } from "../context/AuthContext";

const A = "/assets/design";
const FEATURES = [
  { title: "Save", body: "Keep the media that matters, ready whenever you are.", icon: `${A}/icons/features/save.svg`, tone: "blue" },
  { title: "Convert", body: "Choose clean, compatible video and audio formats.", icon: `${A}/icons/features/convert.svg`, tone: "purple" },
  { title: "Organize", body: "Find every saved file in one calm, searchable library.", icon: `${A}/icons/features/organize.svg`, tone: "aqua" },
  { title: "Process", body: "Clip ranges, tune quality, and handle playlists with precision.", icon: `${A}/icons/features/process.svg`, tone: "violet" },
];
const STEPS = [
  { n: "01", title: "Paste your link", body: "Drop in a link from a supported platform.", icon: `${A}/icons/steps/paste.svg` },
  { n: "02", title: "Pick your format", body: "Choose the quality and output you want.", icon: `${A}/icons/steps/pick.svg` },
  { n: "03", title: "Keep it close", body: "Download it for personal offline access.", icon: `${A}/icons/steps/keep.svg` },
];

export default function Landing() {
  const { account } = useAuth();
  return (
    <main className="landing-page">
      <section className="hero-section">
        <img src={`${A}/backgrounds/hero-cinematic-wave.svg`} alt="" aria-hidden="true" className="hero-wave" />
        <div className="hero-vignette" aria-hidden="true" />
        <div className="hero-stage">
          <img src={`${A}/hero/media-tiles/video-tile.svg`} alt="" className="media-tile tile-video" aria-hidden="true" />
          <img src={`${A}/hero/media-tiles/audio-tile.svg`} alt="" className="media-tile tile-audio" aria-hidden="true" />
          <img src={`${A}/hero/media-tiles/image-tile.svg`} alt="" className="media-tile tile-image" aria-hidden="true" />
          <img src={`${A}/hero/media-tiles/link-tile.svg`} alt="" className="media-tile tile-link" aria-hidden="true" />
          <div className="hero-copy">
            <span className="hero-eyebrow"><span /> Your media, on your terms</span>
            <h1>Freedom to keep<br /><span className="gradient-text">what you love.</span></h1>
            <p>Save the videos, sounds, and moments that matter—for personal offline access, in the format you choose.</p>
          </div>
          <div className="hero-console"><HeroUrlInput /></div>
          <p className="hero-microcopy">Fast. Simple. Yours.</p>
        </div>
      </section>

      <section id="features" className="section-shell scroll-mt-24">
        <div className="section-intro">
          <span className="section-kicker">Built around your library</span>
          <h2>Everything you need. Nothing you don’t.</h2>
          <p>Powerful media tools, shaped into a focused and beautifully simple workflow.</p>
        </div>
        <div className="feature-grid">
          {FEATURES.map((f, i) => <article key={f.title} className={`feature-card feature-${f.tone}`}>
            <span className="feature-index">0{i + 1}</span>
            <div className="feature-icon"><img src={f.icon} alt="" aria-hidden="true" /></div>
            <h3>{f.title}</h3><p>{f.body}</p>
          </article>)}
        </div>
      </section>

      <section id="how-it-works" className="section-shell how-section scroll-mt-24">
        <div className="section-intro"><span className="section-kicker">From link to library</span><h2>Three steps. That’s it.</h2></div>
        <div className="step-path">
          {STEPS.map((s) => <article key={s.n} className="step-card">
            <div className="step-top"><span className="step-number">{s.n}</span><img src={s.icon} alt="" aria-hidden="true" /></div>
            <h3>{s.title}</h3><p>{s.body}</p>
          </article>)}
        </div>
      </section>

      <section className="final-cta">
        <div className="cta-glow" aria-hidden="true" />
        <span className="section-kicker">Your library is waiting</span>
        <h2>Ready to try it?</h2>
        <p>Start free. Keep the moments you care about.</p>
        <Link to={account ? "/dashboard" : "/signup"} className="btn-gradient !px-7 !py-3.5">
          {account ? "Go to downloader" : "Create your free account"}
        </Link>
      </section>
    </main>
  );
}
