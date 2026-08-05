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
// The arcs draw themselves with stroke-dashoffset, which the compositor
// animates without layout work — smooth even while the main thread is busy
// parsing the bundle.

import React, { useEffect, useState } from 'react';
import { NTT_BLUE } from './Brand';

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

      {/* Same geometry as NttMark, animated. Each ring counter-rotates while
          its dash pattern draws in, so the mark assembles rather than merely
          appearing. */}
      <svg width="96" height="96" viewBox="0 0 48 48" fill="none" className="relative">
        <circle
          cx="24" cy="24" r="20"
          stroke={NTT_BLUE} strokeWidth="3.5" strokeLinecap="round"
          pathLength="100" strokeDasharray="78 22"
          className="ntt-arc-outer"
        />
        <circle
          cx="24" cy="24" r="11.5"
          stroke={NTT_BLUE} strokeWidth="3.5" strokeLinecap="round"
          pathLength="100" strokeDasharray="62 38" opacity="0.7"
          className="ntt-arc-inner"
        />
        <circle cx="24" cy="24" r="3.4" fill={NTT_BLUE} className="ntt-core" />
      </svg>

      <div className="relative mt-7 text-center">
        <div className="text-[15px] font-semibold tracking-[0.2em] text-slate-800 dark:text-slate-100">
          <span style={{ color: NTT_BLUE }}>NTT</span> DATA
        </div>
        <div className="mt-1.5 text-xs tracking-wide text-slate-400 dark:text-slate-500">
          Incident Platform
        </div>
      </div>

      {/* Indeterminate bar: honest about not knowing how long this takes. */}
      <div className="relative mt-8 h-[3px] w-40 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div className="ntt-progress h-full w-1/3 rounded-full" style={{ background: NTT_BLUE }} />
      </div>
    </div>
  );
}
