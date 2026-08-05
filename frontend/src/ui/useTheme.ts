// Theme: light, dim, black, or follow the system.
//
// Two dark variants, because they solve different problems:
//   dim    — a soft neutral charcoal. Easier on the eyes for long sessions
//            than pure black, which makes white text bloom against it.
//   black  — true #000. Saves power on OLED and is what people mean when
//            they ask for "actual dark mode".
//
// Both apply the `dark` class (so every existing `dark:` utility keeps
// working) and additionally set `data-theme`, which the stylesheet uses to
// override the surface variables. That layering is deliberate: adding a third
// palette must not mean auditing several hundred `dark:` utilities.
//
// "system" stays a distinct state rather than resolving to a boolean, so a
// user who has not chosen keeps following the OS when it changes at sunset,
// while a user who has chosen is never overridden.

import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dim' | 'black' | 'system';

export const THEMES: { id: Theme; label: string; hint: string }[] = [
  { id: 'light', label: 'Light', hint: 'Bright surfaces' },
  { id: 'dim', label: 'Dim', hint: 'Soft dark, easier for long sessions' },
  { id: 'black', label: 'Black', hint: 'True black — best on OLED' },
  { id: 'system', label: 'System', hint: 'Follow your OS setting' },
];

const STORAGE_KEY = 'ntt.theme';
// The system's dark preference resolves to this variant. `dim` rather than
// `black`, because true black is a deliberate choice (OLED, or preference)
// rather than what "the OS is in dark mode" implies.
const SYSTEM_DARK = 'dim' as const;

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

export type ResolvedTheme = 'light' | 'dim' | 'black';

/** The concrete palette a stored choice resolves to right now. */
export function resolveTheme(theme: Theme): ResolvedTheme {
  if (theme !== 'system') return theme;
  return systemPrefersDark() ? SYSTEM_DARK : 'light';
}

function applyTheme(theme: Theme): void {
  const resolved = resolveTheme(theme);
  const root = document.documentElement;
  root.classList.toggle('dark', resolved !== 'light');
  root.dataset.theme = resolved;
}

function storedTheme(): Theme {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw === 'light' || raw === 'dim' || raw === 'black' || raw === 'system'
    ? raw
    : 'system';
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(storedTheme);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  // Track OS changes only while following the system, so a user who picked a
  // theme is not overridden when their machine switches.
  useEffect(() => {
    if (theme !== 'system') return;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => applyTheme('system');
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);

  /** Quick flip between light and the last dark variant, for the menu toggle. */
  const toggle = useCallback(() => {
    setThemeState((current) => (resolveTheme(current) === 'light' ? SYSTEM_DARK : 'light'));
  }, []);

  const resolved = resolveTheme(theme);
  return { theme, resolved, setTheme, toggle, isDark: resolved !== 'light' };
}
