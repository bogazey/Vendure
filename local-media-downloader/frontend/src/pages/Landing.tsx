import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import HeroUrlInput from "../components/HeroUrlInput";
import { useAuth } from "../context/AuthContext";

const A = "/assets/design";
const FEATURES = [
  { key: "save", icon: `${A}/icons/features/save.svg`, tone: "blue" },
  { key: "convert", icon: `${A}/icons/features/convert.svg`, tone: "purple" },
  { key: "organize", icon: `${A}/icons/features/organize.svg`, tone: "aqua" },
  { key: "process", icon: `${A}/icons/features/process.svg`, tone: "violet" },
];
const STEPS = [
  { n: "01", key: "paste", icon: `${A}/icons/steps/paste.svg` },
  { n: "02", key: "format", icon: `${A}/icons/steps/pick.svg` },
  { n: "03", key: "keep", icon: `${A}/icons/steps/keep.svg` },
];

export default function Landing() {
  const { t } = useTranslation();
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
            <span className="hero-eyebrow"><span /> {t("hero.eyebrow")}</span>
            <h1>{t("hero.line1")}<br /><span className="gradient-text">{t("hero.line2")}</span></h1>
            <p>{t("hero.body")}</p>
          </div>
          <div className="hero-console"><HeroUrlInput /></div>
          <p className="hero-microcopy">{t("hero.micro")}</p>
        </div>
      </section>

      <section id="features" className="section-shell scroll-mt-24">
        <div className="section-intro">
          <span className="section-kicker">{t("landing.featuresKicker")}</span>
          <h2>{t("landing.featuresTitle")}</h2>
          <p>{t("landing.featuresBody")}</p>
        </div>
        <div className="feature-grid">
          {FEATURES.map((f, i) => <article key={f.key} className={`feature-card feature-${f.tone}`}>
            <span className="feature-index">0{i + 1}</span>
            <div className="feature-icon"><img src={f.icon} alt="" aria-hidden="true" /></div>
            <h3>{t(`landing.features.${f.key}.0`)}</h3><p>{t(`landing.features.${f.key}.1`)}</p>
          </article>)}
        </div>
      </section>

      <section id="how-it-works" className="section-shell how-section scroll-mt-24">
        <div className="section-intro"><span className="section-kicker">{t("landing.stepsKicker")}</span><h2>{t("landing.stepsTitle")}</h2></div>
        <div className="step-path">
          {STEPS.map((s) => <article key={s.n} className="step-card">
            <div className="step-top"><span className="step-number">{s.n}</span><img src={s.icon} alt="" aria-hidden="true" /></div>
            <h3>{t(`landing.steps.${s.key}.0`)}</h3><p>{t(`landing.steps.${s.key}.1`)}</p>
          </article>)}
        </div>
      </section>

      <section className="final-cta">
        <div className="cta-glow" aria-hidden="true" />
        <span className="section-kicker">{t("landing.ctaKicker")}</span>
        <h2>{t("landing.ctaTitle")}</h2>
        <p>{t("landing.ctaBody")}</p>
        <Link to={account ? "/dashboard" : "/signup"} className="btn-gradient !px-7 !py-3.5">
          {account ? t("landing.ctaAccount") : t("landing.ctaGuest")}
        </Link>
      </section>
    </main>
  );
}
