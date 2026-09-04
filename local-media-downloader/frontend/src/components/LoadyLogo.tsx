/**
 * Loady's mark: a rounded gradient badge (blue -> purple -> aqua) with an
 * abstract "keep what you flow through" glyph - a downward arrow
 * resolving into a solid bar, standing in for save/keep.
 *
 * No existing "Brand Identity #2" asset file was found anywhere in this
 * repository - this is an original mark built to the confirmed palette
 * and tone (see COMMERCIAL_ARCHITECTURE.md / PR notes). Swap the <svg>
 * markup below for the real asset the moment one is available; nothing
 * else needs to change since every caller just renders <LoadyLogo />.
 */
interface LoadyLogoProps {
  size?: number;
  withWordmark?: boolean;
  className?: string;
}

export default function LoadyLogo({ size = 32, withWordmark = true, className = "" }: LoadyLogoProps) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="loady-mark-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#4F7CFF" />
            <stop offset="55%" stopColor="#9D5CFF" />
            <stop offset="100%" stopColor="#2DD9E8" />
          </linearGradient>
        </defs>
        <rect width="64" height="64" rx="18" fill="url(#loady-mark-gradient)" />
        <path
          d="M32 15v22m0 0-9-9m9 9 9-9"
          stroke="white"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <rect x="19" y="44" width="26" height="5" rx="2.5" fill="white" />
      </svg>
      {withWordmark && (
        <span className="font-display text-lg font-semibold tracking-tight text-slate-50">Loady</span>
      )}
    </span>
  );
}
