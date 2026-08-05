// Boot screen shown while the app resolves its session.
//
// It fills real waiting time — checking auth config, consuming an OIDC
// redirect, fetching /api/me — rather than being decorative. Two rules keep it
// from becoming an annoyance:
//
//   * a minimum visible time, so a fast resolve does not produce a jarring
//     one-frame flash of the splash;
//   * a fade-out rather than an unmount, so the app appears to arrive rather
//     than replace it.
//
// The mark is the real icon asset (see Brand.tsx) inside an animated ring —
// a pulse and a spinning arc around it — rather than being redrawn as SVG
// paths. An earlier version hand-traced the mark and got the shape wrong
// (concentric rings instead of the circle-and-teardrop); using the actual
// asset here removes that failure mode entirely.

import React, { useEffect, useState } from 'react';
import { NTT_BLUE, NttLogo, NttMark } from './Brand';

const MIN_VISIBLE_MS = 900;

export default function BootScreen({ done }: { done: boolean }) {
  const [hidden, setHidden] = useState(false);
  const [canHide, setCanHide] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setCanHide(true), MIN_VISIBLE_MS);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!done || !canHide) return;
    // Match the CSS transition below, then stop rendering entirely so the
    // overlay cannot swallow clicks once it is invisible.
    const t = setTimeout(() => setHidden(true), 420);
    return () => clearTimeout(t);
  }, [done, canHide]);

  if (hidden) return null;
  const leaving = done && canHide;

  return (
    <div
      className={`fixed inset-0 z-[100] flex flex-col items-center justify-center bg-app transition-opacity duration-[400ms] ${
        leaving ? 'pointer-events-none opacity-0' : 'opacity-100'
      }`}
      role="status"
      aria-live="polite"
      aria-label="Loading NTT DATA Incident Platform"
    >
      {/* Depth without an image: a soft brand-blue wash behind the mark. */}
      <div
        aria-hidden
        className="pointer-events-none absolute h-[420px] w-[420px] rounded-full opacity-[0.07] blur-3xl"
        style={{ background: NTT_BLUE }}
      />

      {/* The real icon, pulsing, with a spinning arc orbiting it — motion
          supplied by the container since the asset itself is a static PNG. */}
      <div className="relative flex h-24 w-24 items-center justify-center">
        <svg
          viewBox="0 0 48 48"
          fill="none"
          className="ntt-arc-outer absolute inset-0 h-full w-full"
        >
          <circle
            cx="24" cy="24" r="21"
            stroke={NTT_BLUE} strokeWidth="2" strokeLinecap="round"
            pathLength="100" strokeDasharray="30 70" opacity="0.55"
          />
        </svg>
        <div className="ntt-core">
          <NttMark size={56} />
        </div>
      </div>

      <div className="relative mt-7 text-center">
        <NttLogo height={18} />
        <div className="mt-2 text-xs tracking-wide text-app-muted">
          Incident Platform
        </div>
      </div>

      {/* Indeterminate bar: honest about not knowing how long this takes. */}
      <div className="bg-app-hover relative mt-8 h-[3px] w-40 overflow-hidden rounded-full">
        <div className="ntt-progress h-full w-1/3 rounded-full" style={{ background: NTT_BLUE }} />
      </div>
    </div>
  );
}
