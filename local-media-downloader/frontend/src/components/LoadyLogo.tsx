/**
 * The real Brand Identity #2 Loady logo - the official SVG masters from
 * design-reference/brand-kit/logos/, served as static files from
 * frontend/public/assets/brand/ and rendered via <img>, never redrawn or
 * reconstructed in CSS. Per the kit's logo rules: don't stretch, rotate,
 * recolor, or alter the gradient/geometry/proportions.
 *
 * Two horizontal lockup variants ship in the kit, one per background
 * ("dark" has near-white wordmark text for our dark UI, "light" has
 * near-black text for the Settings-selectable light theme) - both are
 * rendered and toggled with Tailwind's `dark:` variant, which already
 * tracks the same `.dark`/`.light` class on <html> that src/utils/theme.ts
 * applies everywhere else in the app.
 */
interface LoadyLogoProps {
  /** Height in px. For the icon-only mark this is also the width (it's square). */
  size?: number;
  withWordmark?: boolean;
  className?: string;
}

export default function LoadyLogo({ size = 32, withWordmark = true, className = "" }: LoadyLogoProps) {
  if (!withWordmark) {
    return (
      <img
        src="/assets/brand/loady-mark.svg"
        alt="Loady"
        width={size}
        height={size}
        className={className}
      />
    );
  }

  return (
    <span className={`inline-flex items-center ${className}`}>
      <img
        src="/assets/brand/loady-horizontal-dark.svg"
        alt="Loady"
        style={{ height: size, width: "auto" }}
        className="hidden dark:block"
      />
      <img
        src="/assets/brand/loady-horizontal-light.svg"
        alt="Loady"
        style={{ height: size, width: "auto" }}
        className="block dark:hidden"
      />
    </span>
  );
}
