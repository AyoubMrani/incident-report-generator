// Live health indicator for the sidebar.
//
// The backend degrades in pieces rather than all at once — the chatbot can be
// down while reports still work, or Postgres can drop while the process stays
// up. /api/health already reports each part separately; without surfacing it,
// a user meets that state as an unexplained error mid-task instead.

import React, { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';

interface Health {
  status: string;
  chatbot_ready: boolean;
  chatbot_error: string | null;
  chat_backend: string;
  storage_backend: string;
  database_ready: boolean | null;
  auth_enabled: boolean;
}

const POLL_MS = 30_000;

export default function SystemStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [reachable, setReachable] = useState(true);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        // Health is public, so this needs no token and keeps working on the
        // login screen — where "is the backend even up?" matters most.
        const res = await fetch('/api/health');
        if (cancelled) return;
        if (!res.ok) throw new Error(String(res.status));
        setHealth(await res.json());
        setReachable(true);
      } catch {
        if (!cancelled) setReachable(false);
      }
    };

    check();
    const timer = setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const degraded =
    !reachable ||
    !health ||
    health.database_ready === false ||
    !health.chatbot_ready;

  const tone = !reachable
    ? { dot: 'bg-red-500', label: 'Offline' }
    : degraded
      ? { dot: 'bg-amber-500', label: 'Degraded' }
      : { dot: 'bg-emerald-500', label: 'All systems normal' };

  const rows: [string, boolean | null, string][] = health
    ? [
        ['Chatbot', health.chatbot_ready, health.chatbot_error ?? ''],
        ['Database', health.database_ready, health.chat_backend],
        ['Storage', true, health.storage_backend],
        ['Auth', health.auth_enabled, health.auth_enabled ? 'Keycloak' : 'disabled'],
      ]
    : [];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition hover:bg-slate-100 dark:hover:bg-slate-800"
        aria-expanded={open}
        title="System status"
      >
        <span className="relative flex h-2 w-2 shrink-0">
          {!degraded && (
            <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${tone.dot} opacity-60`} />
          )}
          <span className={`relative inline-flex h-2 w-2 rounded-full ${tone.dot}`} />
        </span>
        <span className="flex-1 truncate text-[11px] text-slate-500 dark:text-slate-400">
          {tone.label}
        </span>
        <Activity className="w-3 h-3 shrink-0 text-slate-400" />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-20 mb-2 w-56 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          {!reachable ? (
            <p className="px-3 py-2.5 text-[12px] text-red-600 dark:text-red-400">
              Cannot reach the API. Is the backend running?
            </p>
          ) : (
            rows.map(([label, ok, detail]) => (
              <div
                key={label}
                className="flex items-center gap-2 border-b border-slate-100 px-3 py-2 text-[12px] last:border-0 dark:border-slate-800"
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    ok === false ? 'bg-red-500' : ok === null ? 'bg-slate-300' : 'bg-emerald-500'
                  }`}
                />
                <span className="text-slate-600 dark:text-slate-300">{label}</span>
                <span className="ml-auto max-w-[7rem] truncate text-slate-400" title={detail}>
                  {detail || (ok ? 'ready' : 'unavailable')}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
