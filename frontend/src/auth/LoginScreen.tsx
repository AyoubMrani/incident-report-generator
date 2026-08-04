// The signed-out state.
//
// Deliberately plain: one action, and enough context that a user landing here
// after a session expiry understands why. The seed credentials are listed
// because this stack is local-only and a teammate running `docker compose up`
// otherwise has no way to know them — the realm export is the source of truth
// for that list.

import React from 'react';

interface Props {
  onLogin: () => void;
  error?: string | null;
}

export default function LoginScreen({ onLogin, error }: Props) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm p-8">
          <div className="flex flex-col items-center text-center">
            <div className="h-12 w-12 rounded-xl bg-slate-900 dark:bg-slate-100 flex items-center justify-center mb-4">
              <span className="text-lg font-semibold text-white dark:text-slate-900">N</span>
            </div>
            <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
              NTT Incident Platform
            </h1>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              Sign in to search incidents and generate reports.
            </p>
          </div>

          {error && (
            <div
              role="alert"
              className="mt-6 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300"
            >
              {error}
            </div>
          )}

          <button
            onClick={onLogin}
            className="mt-6 w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
          >
            Sign in with Keycloak
          </button>

          <details className="mt-6 text-xs text-slate-500 dark:text-slate-400">
            <summary className="cursor-pointer select-none hover:text-slate-700 dark:hover:text-slate-300">
              Local development accounts
            </summary>
            <ul className="mt-2 space-y-1 font-mono">
              <li>admin / admin — full access</li>
              <li>analyst / analyst — chat + write reports</li>
              <li>viewer / viewer — read only</li>
            </ul>
          </details>
        </div>
      </div>
    </div>
  );
}
