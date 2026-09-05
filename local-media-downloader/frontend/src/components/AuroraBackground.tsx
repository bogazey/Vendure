/**
 * Fixed, full-viewport cinematic background: a few large blurred gradient
 * blobs with a slow CSS-only drift, plus a faint grid for depth. Rendered
 * once at the App shell level, behind everything (z-0) - every page's own
 * content sits in a `relative z-10` wrapper so it's never occluded.
 *
 * Deliberately cheap: no JS animation loop, no canvas, three divs animated
 * purely via CSS transforms (GPU-composited), disabled outright under
 * prefers-reduced-motion (see index.css).
 */
export default function AuroraBackground() {
  return (
    <div className="aurora-layer" aria-hidden="true">
      <div
        className="aurora-blob animate-aurora-drift-1 bg-brand-radial-1"
        style={{ top: "-10%", left: "-10%", width: "55vw", height: "55vw" }}
      />
      <div
        className="aurora-blob animate-aurora-drift-2 bg-brand-radial-2"
        style={{ top: "10%", right: "-15%", width: "50vw", height: "50vw" }}
      />
      <div
        className="aurora-blob animate-aurora-drift-3 bg-brand-radial-3"
        style={{ bottom: "-20%", left: "20%", width: "60vw", height: "60vw" }}
      />
      <div className="aurora-grid" />
    </div>
  );
}
