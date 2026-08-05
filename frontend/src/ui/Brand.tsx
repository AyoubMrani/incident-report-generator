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
 * The circular mark — for favicons, avatars, the collapsed sidebar.
 *
 * Concentric rings with a gap, echoing NTT DATA's circular device. Each ring is
 * a full circle drawn with a dash pattern rather than a half-arc path: an arc
 * with a round cap reads as a stray "C" at small sizes, which is what the first
 * attempt produced. `pathLength="100"` normalises the dash maths so the gap is
 * a readable percentage rather than a radius-dependent magic number.
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
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      role="img"
      aria-label="NTT DATA"
    >
      {/* Outer ring: a near-complete circle, opened at the top right. */}
      <circle
        cx="24" cy="24" r="20"
        stroke={color} strokeWidth="3.5" strokeLinecap="round"
        pathLength="100" strokeDasharray="78 22" strokeDashoffset="14"
      />
      {/* Inner ring, opened on the opposite side for rotational balance. */}
      <circle
        cx="24" cy="24" r="11.5"
        stroke={color} strokeWidth="3.5" strokeLinecap="round"
        pathLength="100" strokeDasharray="62 38" strokeDashoffset="64"
        opacity="0.7"
      />
      <circle cx="24" cy="24" r="3.4" fill={color} />
    </svg>
  );
}

/**
 * Full lockup: mark + "NTT DATA" wordmark.
 *
 * The wordmark is `currentColor` so it reads correctly on light and dark
 * surfaces without a second asset.
 */
export function NttLogo({
  height = 28,
  className = '',
  markColor = NTT_BLUE,
}: {
  height?: number;
  className?: string;
  markColor?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <NttMark size={height} color={markColor} />
      <span
        className="font-semibold tracking-tight leading-none"
        style={{ fontSize: height * 0.62 }}
      >
        <span style={{ color: markColor }}>NTT</span>
        <span className="ml-1 text-current">DATA</span>
      </span>
    </span>
  );
}

/**
 * Product lockup used in the sidebar: brand above, product name below.
 */
export function ProductLockup({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <NttMark size={30} />
      <div className="min-w-0 leading-tight">
        <div className="text-[13px] font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          <span style={{ color: NTT_BLUE }}>NTT</span> DATA
        </div>
        <div className="truncate text-[11px] text-slate-500 dark:text-slate-400">
          Incident Platform
        </div>
      </div>
    </div>
  );
}
