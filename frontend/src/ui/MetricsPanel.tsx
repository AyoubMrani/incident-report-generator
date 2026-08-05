// Admin-only quality metrics.
//
// /api/feedback/summary has existed since the feedback loop was built and has
// never had a UI — the thumbs data was write-only. For an ops tool, "which
// answers land and which don't" is the number that tells you whether the
// retrieval is actually working, so it is worth surfacing.
//
// Admin-only because it aggregates across every user's conversations.

import React, { useEffect, useState } from 'react';
import { BarChart3, Loader2, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { NTT_BLUE } from './Brand';
import { authFetch } from '../auth/oidc';

interface Summary {
  up: number;
  down: number;
  total_rated: number;
  corrections: number;
}

export default function MetricsPanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setData(null);
    setError(null);
    authFetch('/api/feedback/summary')
      .then(async (r) => {
        if (r.status === 403) throw new Error('Admin access required.');
        if (!r.ok) throw new Error('Could not load metrics.');
        setData(await r.json());
      })
      .catch((e) => setError(e.message));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [open, onClose]);

  if (!open) return null;

  const rated = data?.total_rated ?? 0;
  // Undefined rather than 0 when nothing is rated: a "0% positive" badge on an
  // empty sample reads as a failing system rather than an absent measurement.
  const positive = rated > 0 ? Math.round(((data?.up ?? 0) / rated) * 100) : undefined;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Answer quality"
    >
      <div
        className="bg-app-elevated border-app w-full max-w-md rounded-xl border shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-app flex items-center justify-between border-b px-5 py-3.5">
          <h2 className="text-app flex items-center gap-2 text-[15px] font-semibold">
            <BarChart3 className="w-4 h-4" style={{ color: NTT_BLUE }} />
            Answer quality
          </h2>
          <button
            onClick={onClose}
            className="hover:bg-app-hover text-app-muted rounded-lg p-1 transition"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-5">
          {error ? (
            <p className="py-6 text-center text-[13px] text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : !data ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
            </div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                <Stat label="Rated" value={rated} />
                <Stat
                  label="Helpful"
                  value={data.up}
                  icon={<ThumbsUp className="w-3 h-3" />}
                  tone="text-emerald-600 dark:text-emerald-400"
                />
                <Stat
                  label="Not helpful"
                  value={data.down}
                  icon={<ThumbsDown className="w-3 h-3" />}
                  tone="text-red-600 dark:text-red-400"
                />
              </div>

              {positive !== undefined && (
                <div className="mt-5">
                  <div className="text-app-muted mb-1.5 flex justify-between text-[11px]">
                    <span>Positive rate</span>
                    <span className="text-app font-medium">{positive}%</span>
                  </div>
                  <div className="bg-app-hover h-2 overflow-hidden rounded-full">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${positive}%`, background: NTT_BLUE }}
                    />
                  </div>
                </div>
              )}

              <div className="border-app mt-5 border-t pt-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-app-muted text-[12px]">
                    Corrections submitted
                  </span>
                  <span className="text-app text-[15px] font-semibold">
                    {data.corrections}
                  </span>
                </div>
                <p className="text-app-muted mt-1.5 text-[11px] leading-relaxed">
                  Corrections are fed back into future answers for similar
                  questions — they are retrieval hints, not model training.
                </p>
              </div>

              {rated === 0 && (
                <p className="text-app-muted mt-4 text-center text-[12px]">
                  No answers rated yet. Use 👍 / 👎 on an answer to start
                  collecting this.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  icon,
  tone = 'text-app',
}: {
  label: string;
  value: number;
  icon?: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className="border-app rounded-lg border px-3 py-2.5">
      <div className={`flex items-center gap-1 text-[11px] ${tone}`}>
        {icon}
        {label}
      </div>
      <div className="text-app mt-0.5 text-[20px] font-semibold leading-none">
        {value}
      </div>
    </div>
  );
}
