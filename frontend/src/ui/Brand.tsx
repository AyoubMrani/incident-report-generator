// NTT DATA brand marks.
//
// These are the official assets (`logo.png`, `icon.png` and their dark-mode
// variants), imported so Vite fingerprints and inlines/serves them — not
// fetched from nttdata-solutions.com, which sits behind Cloudflare and refuses
// anything that is not a browser.
//
// Light and dark are *different files* rather than one file recoloured with
// CSS: the dark variant is white where the light one is blue, and a filter
// that produced that would also wash out the blue mark inside it. Both are
// rendered and the inactive one hidden, so the swap is instant on theme change
// with no flash of the wrong asset while a new image decodes.

import React from 'react';
import iconLight from '../assets/icon-light.png';
import iconDark from '../assets/icon-dark.png';
import logoLight from '../assets/logo-light.png';
import logoDark from '../assets/logo-dark.png';

// NTT DATA blue, for UI accents that are not the logo itself.
export const NTT_BLUE = '#0072C6';

/**
 * The circular mark alone — favicon-adjacent uses, collapsed sidebar, avatars.
 *
 * The asset is 1549x1467 (not square), so it is constrained by height and
 * given `w-auto`; forcing a square box would squash it.
 */
export function NttMark({
  size = 32,
  className = '',
}: {
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center ${className}`}
      style={{ height: size }}
      aria-label="NTT DATA"
      role="img"
    >
      <img
        src={iconLight}
        alt=""
        className="block h-full w-auto dark:hidden"
        draggable={false}
      />
      <img
        src={iconDark}
        alt=""
        className="hidden h-full w-auto dark:block"
        draggable={false}
      />
    </span>
  );
}

/**
 * Full horizontal lockup: mark + "NTT DATA" wordmark, as one official asset.
 */
export function NttLogo({
  height = 22,
  className = '',
}: {
  height?: number;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center ${className}`}
      style={{ height }}
      aria-label="NTT DATA"
      role="img"
    >
      <img
        src={logoLight}
        alt=""
        className="block h-full w-auto dark:hidden"
        draggable={false}
      />
      <img
        src={logoDark}
        alt=""
        className="hidden h-full w-auto dark:block"
        draggable={false}
      />
    </span>
  );
}

/**
 * Product lockup: brand above, product name below.
 */
export function ProductLockup({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <NttMark size={26} />
      <div className="min-w-0 leading-tight">
        <div className="text-[13px] font-bold tracking-tight text-app">
          NTT DATA
        </div>
        <div className="truncate text-[11px] text-app-muted">
          Incident Platform
        </div>
      </div>
    </div>
  );
}
