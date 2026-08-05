// Settings: appearance, behaviour, and a shortcut reference.
//
// The theme picker shows a real swatch of each palette rather than a label,
// because "Dim" and "Black" mean nothing until you see them side by side.
//
// Preferences are localStorage-only. They change how this browser behaves, not
// what the server stores, so a round trip would add latency and a failure mode
// for no benefit.

import React from 'react';
import { Check, Keyboard, Monitor, Send, Sparkles, X } from 'lucide-react';
import { THEMES, type Theme } from './useTheme';
import { NTT_BLUE } from './Brand';

export interface Preferences {
  /** Enter sends (true) or inserts a newline with ⌘/Ctrl+Enter to send (false). */
  enterToSend: boolean;
  /** Show the streaming tokens as they arrive. */
  showStreaming: boolean;
}

export const PREFS_KEY = 'ntt.prefs';

export const DEFAULT_PREFS: Preferences = {
  enterToSend: true,
  showStreaming: true,
};

export function loadPrefs(): Preferences {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(prefs: Preferences): void {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

// Swatches mirror the palettes in index.css.
const SWATCH: Record<string, { bg: string; surface: string; text: string; border: string }> = {
  light: { bg: '#ffffff', surface: '#f8fafc', text: '#0f172a', border: '#e2e8f0' },
  dim: { bg: '#16181c', surface: '#22262c', text: '#e8eaed', border: '#2c3138' },
  black: { bg: '#000000', surface: '#141414', text: '#f2f2f2', border: '#232323' },
  system: { bg: 'linear-gradient(135deg,#ffffff 50%,#16181c 50%)', surface: '#8891a0', text: '#8891a0', border: '#cbd5e1' },
};

const SHORTCUTS: [string, string][] = [
  ['⌘K', 'Search conversations'],
  ['⌘\\', 'Collapse or expand the sidebar'],
  ['⌘,', 'Open settings'],
  ['Enter', 'Send message'],
  ['Shift+Enter', 'New line'],
  ['Esc', 'Close dialogs'],
];

interface Props {
  open: boolean;
  onClose: () => void;
  theme: Theme;
  onSelectTheme: (theme: Theme) => void;
  prefs: Preferences;
  onChangePrefs: (prefs: Preferences) => void;
}

export default function SettingsDialog({
  open,
  onClose,
  theme,
  onSelectTheme,
  prefs,
  onChangePrefs,
}: Props) {
  React.useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [open, onClose]);

  if (!open) return null;

  const update = (patch: Partial<Preferences>) => {
    const next = { ...prefs, ...patch };
    savePrefs(next);
    onChangePrefs(next);
  };

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
    >
      <div
        className="bg-app-elevated border-app max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl border shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-app text-app sticky top-0 flex items-center justify-between border-b bg-inherit px-5 py-3.5">
          <h2 className="text-[15px] font-semibold">Settings</h2>
          <button
            onClick={onClose}
            className="hover:bg-app-hover text-app-muted rounded-lg p-1 transition"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-5">
          <SectionTitle icon={<Monitor className="w-3.5 h-3.5" />}>Appearance</SectionTitle>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {THEMES.map((t) => {
              const active = theme === t.id;
              const sw = SWATCH[t.id];
              return (
                <button
                  key={t.id}
                  onClick={() => onSelectTheme(t.id)}
                  title={t.hint}
                  className="group relative rounded-lg border p-1.5 text-left transition"
                  style={{
                    borderColor: active ? NTT_BLUE : 'var(--app-border)',
                    boxShadow: active ? `0 0 0 1px ${NTT_BLUE}` : undefined,
                  }}
                >
                  {/* Miniature of the app, so the choice is visible not verbal. */}
                  <span
                    className="block h-12 w-full overflow-hidden rounded"
                    style={{ background: sw.bg, border: `1px solid ${sw.border}` }}
                  >
                    <span className="flex h-full">
                      <span className="h-full w-1/3" style={{ background: sw.surface }} />
                      <span className="flex flex-1 flex-col justify-center gap-1 px-1.5">
                        <span className="block h-1 w-full rounded-full" style={{ background: sw.text, opacity: 0.75 }} />
                        <span className="block h-1 w-2/3 rounded-full" style={{ background: sw.text, opacity: 0.4 }} />
                      </span>
                    </span>
                  </span>
                  <span className="text-app mt-1.5 flex items-center gap-1 px-0.5 text-[12px] font-medium">
                    {t.label}
                    {active && <Check className="w-3 h-3" style={{ color: NTT_BLUE }} />}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-app-muted mt-2 text-[11px]">
            {THEMES.find((t) => t.id === theme)?.hint}
          </p>

          <SectionTitle icon={<Send className="w-3.5 h-3.5" />} className="mt-7">
            Composing
          </SectionTitle>
          <div className="mt-2 space-y-1">
            <Toggle
              label="Press Enter to send"
              hint={prefs.enterToSend ? 'Shift+Enter inserts a new line' : '⌘/Ctrl+Enter sends instead'}
              checked={prefs.enterToSend}
              onChange={(v) => update({ enterToSend: v })}
            />
            <Toggle
              label="Stream answers as they generate"
              hint="Off shows the finished answer only"
              checked={prefs.showStreaming}
              onChange={(v) => update({ showStreaming: v })}
            />
          </div>

          <SectionTitle icon={<Keyboard className="w-3.5 h-3.5" />} className="mt-7">
            Keyboard shortcuts
          </SectionTitle>
          <div className="border-app mt-2 overflow-hidden rounded-lg border">
            {SHORTCUTS.map(([keys, what], i) => (
              <div
                key={keys}
                className={`flex items-center justify-between px-3 py-1.5 text-[12px] ${
                  i > 0 ? 'border-app border-t' : ''
                }`}
              >
                <span className="text-app-muted">{what}</span>
                <kbd className="border-app text-app rounded border px-1.5 py-0.5 font-sans text-[11px]">
                  {keys}
                </kbd>
              </div>
            ))}
          </div>

          <p className="text-app-muted mt-6 flex items-start gap-1.5 text-[11px] leading-relaxed">
            <Sparkles className="mt-0.5 w-3 h-3 shrink-0" />
            Preferences are stored in this browser. Your profile, conversations
            and reports live on the server.
          </p>
        </div>
      </div>
    </div>
  );
}

function SectionTitle({
  icon,
  children,
  className = '',
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <h3
      className={`text-app-muted flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider ${className}`}
    >
      {icon}
      {children}
    </h3>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!checked)}
      role="switch"
      aria-checked={checked}
      className="hover:bg-app-hover flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition"
    >
      <span className="min-w-0 flex-1">
        <span className="text-app block text-[13px]">{label}</span>
        {hint && <span className="text-app-muted block text-[11px]">{hint}</span>}
      </span>
      <span
        className="relative h-5 w-9 shrink-0 rounded-full transition"
        style={{ background: checked ? NTT_BLUE : 'var(--app-border-strong)' }}
      >
        <span
          className="absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all"
          style={{ left: checked ? '1.125rem' : '0.125rem' }}
        />
      </span>
    </button>
  );
}
