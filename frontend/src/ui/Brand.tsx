// NTT DATA brand marks, as inline SVG.
//
// Inline rather than an <img> to a remote file for three reasons: the app is
// served from one origin with no external requests, the mark has to recolour
// with the theme (a raster or fixed-fill file cannot), and an offline/air-gapped
// deployment must not show a broken image where the brand should be.
//
// The wordmark uses `currentColor`, so it inherits whatever text colour the
// surrounding element sets — one component, correct in both themes.

import React from 'react';

// NTT DATA blue. Fixed, because a brand colour that shifts with the theme is
// no longer a brand colour.
export const NTT_BLUE = '#0072C6';

/**
 * The NTT DATA mark: an open ring with a teardrop nested inside it.
 *
 * Traced from the official asset (`ntt_data.png` at the repo root) rather than
 * embedding that PNG: the mark appears at 24-96px across the app and at 16px in
 * the favicon, where a raster asset softens badly, and vector lets the colour
 * follow the theme.
 *
 * The ring is a stroked circle with a gap at the top, and the teardrop sits in
 * that gap — a rounded triangle with a hole, drawn as a single path with
 * `fillRule="evenodd"` so the counter punches through cleanly at any size.
 */
export function NttMark({
  size = 32,
  className = '',
  color = NTT_BLUE,
}: {
  size?: number;
  className?: string;
  color?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      className={className}
      role="img"
      aria-label="NTT DATA"
    >
      {/* Outer ring, opened at the top where the teardrop breaks through. */}
      <path
        d="M69.5 15.6a41 41 0 1 1-39 0"
        stroke={color}
        strokeWidth="13"
        strokeLinecap="round"
        fill="none"
      />
      {/* Teardrop: apex at the top, bowl at the bottom, with a counter. */}
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M50 12c7.6 9.4 15.5 18.4 15.5 28.2C65.5 50.4 58.6 58 50 58s-15.5-7.6-15.5-17.8C34.5 30.4 42.4 21.4 50 12Zm0 17.6c-3.4 4.4-6.6 8.5-6.6 12.6a6.6 6.6 0 0 0 13.2 0c0-4.1-3.2-8.2-6.6-12.6Z"
        fill={color}
      />
    </svg>
  );
}

/**
 * Full horizontal lockup: mark + "NTT DATA" wordmark, both in brand blue.
 *
 * The official logo is monochrome blue — the wordmark is not a contrasting
 * colour — so this keeps both parts on `NTT_BLUE`, which also reads correctly
 * on light and dark surfaces without a second asset.
 */
export function NttLogo({
  height = 24,
  className = '',
  color = NTT_BLUE,
}: {
  height?: number;
  className?: string;
  color?: string;
}) {
  return (
    <span
      className={`inline-flex items-center ${className}`}
      style={{ gap: height * 0.3 }}
      aria-label="NTT DATA"
    >
      <NttMark size={height} color={color} />
      <span
        className="font-bold leading-none"
        style={{
          fontSize: height * 0.66,
          color,
          // The real wordmark is wide and tightly set; a touch of tracking
          // gets closer to it than the default.
          letterSpacing: '0.01em',
        }}
      >
        NTT DATA
      </span>
    </span>
  );
}

/**
 * Product lockup: brand above, product name below. Used where the app needs to
 * name itself as well as the brand.
 */
export function ProductLockup({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <NttMark size={28} />
      <div className="min-w-0 leading-tight">
        <div
          className="text-[13px] font-bold tracking-tight"
          style={{ color: NTT_BLUE }}
        >
          NTT DATA
        </div>
        <div className="truncate text-[11px] text-slate-500 dark:text-slate-400">
          Incident Platform
        </div>
      </div>
    </div>
  );
}
