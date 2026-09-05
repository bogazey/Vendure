# Loady Design Asset Pack

This pack contains production-ready decorative assets matching the cinematic Loady reference.

## Folder map

- `brand/` — reserved for the official Brand Identity #2 logo assets.
- `backgrounds/hero-cinematic-wave.svg` — landing hero background, full-width.
- `backgrounds/section-wave-left.svg` / `section-wave-right.svg` — section transitions / pricing / CTA backgrounds.
- `textures/subtle-grid.svg` — very low-opacity page/grid overlay.
- `textures/noise-overlay.svg` — optional subtle texture overlay.
- `hero/media-tiles/` — floating hero media tiles. Hide/reduce on mobile.
- `icons/features/` — Save / Convert / Organize / Process icons.
- `icons/steps/` — Paste / Pick / Keep icons.
- `icons/social/` — footer social icon placeholders.
- `pricing/` — Pro card accent and Most Popular badge.

## Placement guide

### Landing hero
Use `hero-cinematic-wave.svg` as an absolutely positioned background layer behind the hero.
Add `subtle-grid.svg` above it at low opacity.
Place media tiles around the headline:
- `video-tile.svg`: top-left / right
- `audio-tile.svg`: lower-left
- `image-tile.svg`: right-mid
- `link-tile.svg`: optional far edge

Recommended CSS:
- hero background: `cover`, center, no-repeat
- floating tiles: absolute, 120–220px desktop; hidden below ~768px
- use mild transforms only; do not animate aggressively

### Feature cards
Use one icon per card:
Save → `icons/features/save.svg`
Convert → `icons/features/convert.svg`
Organize → `icons/features/organize.svg`
Process → `icons/features/process.svg`

### How it works
Paste → `icons/steps/paste.svg`
Pick → `icons/steps/pick.svg`
Keep → `icons/steps/keep.svg`

### Pricing
Apply `pricing/pro-glow.svg` behind/around the Pro card.
Use `pricing/most-popular-badge.svg` only if the plan is truly the recommended plan.

### Footer
Use the official Brand Identity #2 horizontal logo.
Use social icons only if those social links are actually active.

## Important
These SVGs are decorative assets and can be recolored only if you intentionally update the Loady token system.
Do not change the official logo geometry/colors once you add the actual brand assets.
