// The signed-out state.
//
// A split layout: brand and context on the left, the single action on the
// right. The left panel is what makes this read as a product rather than a
// login box — and it collapses on small screens, where a marketing panel above
// the form would just push the button below the fold.
//
// Only one control is offered. Keycloak owns credentials, so a username and
// password field here would be a lie about where the login happens.

import React from 'react';
import { AlertCircle, ArrowRight, Database, Lock, Search } from 'lucide-react';
import { NTT_BLUE, NttMark } from '../ui/Brand';

interface Props {
  onLogin: () => void;
  error?: string | null;
}

const CAPABILITIES = [
  {
    icon: <Search className="w-4 h-4" />,
    title: 'Search that understands intent',
    body: 'Keyword and semantic retrieval, fused — find the incident even when you remember it in different words.',
  },
  {
    icon: <Database className="w-4 h-4" />,
    title: 'Answers grounded in your reports',
    body: 'Every response cites the incident report it came from, so you can verify before you act.',
  },
  {
    icon: <Lock className="w-4 h-4" />,
    title: 'Runs entirely on your infrastructure',
    body: 'Self-hosted models and storage. No incident data leaves the estate.',
  },
];

export default function LoginScreen({ onLogin, error }: Props) {
  return (
    <div className="bg-app flex min-h-screen">
      {/* ── Brand panel ─────────────────────────────────────────────────── */}
      <div className="relative hidden w-[52%] shrink-0 overflow-hidden lg:flex lg:flex-col lg:justify-between bg-app-surface p-12">
        {/* Depth without an image asset. */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 h-[420px] w-[420px] rounded-full opacity-[0.10] blur-3xl dark:opacity-[0.16]"
          style={{ background: NTT_BLUE }}
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-32 -left-20 h-[380px] w-[380px] rounded-full opacity-[0.07] blur-3xl dark:opacity-[0.12]"
          style={{ background: NTT_BLUE }}
        />

        <div className="relative flex items-center gap-3">
          <NttMark size={34} />
          <span className="text-[15px] font-semibold tracking-tight text-app">
            <span style={{ color: NTT_BLUE }}>NTT</span> DATA
          </span>
        </div>

        <div className="relative max-w-md">
          <h1 className="text-[32px] font-semibold leading-[1.15] tracking-tight text-slate-900 dark:text-slate-50">
            Resolve incidents with
            <br />
            what your team already knows.
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed text-app-muted">
            A retrieval assistant over your incident reports — and the report
            generator that keeps them current.
          </p>

          <ul className="mt-10 space-y-5">
            {CAPABILITIES.map((c) => (
              <li key={c.title} className="flex gap-3.5">
                <span
                  className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                  style={{ background: `${NTT_BLUE}14`, color: NTT_BLUE }}
                >
                  {c.icon}
                </span>
                <span>
                  <span className="block text-sm font-medium text-slate-900 dark:text-slate-200">
                    {c.title}
                  </span>
                  <span className="mt-0.5 block text-[13px] leading-relaxed text-app-muted">
                    {c.body}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-slate-400 dark:text-slate-600">
          Internal platform · NTT DATA
        </p>
      </div>

      {/* ── Sign-in panel ───────────────────────────────────────────────── */}
      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-[360px]">
          {/* Brand repeats here only where the left panel is hidden. */}
          <div className="mb-10 flex items-center gap-2.5 lg:hidden">
            <NttMark size={30} />
            <span className="text-sm font-semibold tracking-tight text-app">
              <span style={{ color: NTT_BLUE }}>NTT</span> DATA
            </span>
          </div>

          <h2 className="text-[26px] font-semibold tracking-tight text-slate-900 dark:text-slate-50">
            Sign in
          </h2>
          <p className="mt-2 text-sm text-app-muted">
            Continue with your NTT DATA account.
          </p>

          {error && (
            <div
              role="alert"
              className="mt-6 flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-3 text-[13px] text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300"
            >
              <AlertCircle className="mt-0.5 w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            onClick={onLogin}
            className="group mt-7 flex w-full items-center justify-center gap-2 rounded-lg px-4 py-3 text-sm font-medium text-white shadow-sm transition hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 "
            style={{ background: NTT_BLUE }}
          >
            Continue with Keycloak
            <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
          </button>

          <div className="mt-8 flex items-center gap-3">
            <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
            <span className="text-[11px] uppercase tracking-wider text-slate-400">
              Local development
            </span>
            <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
          </div>

          {/* The realm export seeds these; a teammate running the stack has no
              other way to discover them. */}
          <div className="mt-4 overflow-hidden rounded-lg border border-app">
            {[
              ['admin', 'Full access'],
              ['analyst', 'Chat + write reports'],
              ['viewer', 'Read only'],
            ].map(([user, role], i) => (
              <div
                key={user}
                className={`flex items-center justify-between px-3.5 py-2 text-[12px] ${
                  i > 0 ? 'border-t border-app' : ''
                }`}
              >
                <code className="font-mono text-slate-700 dark:text-slate-300">
                  {user} / {user}
                </code>
                <span className="text-slate-400 dark:text-slate-500">{role}</span>
              </div>
            ))}
          </div>

          <p className="mt-6 text-center text-[11px] leading-relaxed text-slate-400 dark:text-slate-600">
            Protected by Keycloak. Your credentials are never seen by this
            application.
          </p>
        </div>
      </div>
    </div>
  );
}
