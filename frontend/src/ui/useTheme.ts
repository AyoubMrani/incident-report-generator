// Light/dark theme with an explicit user override.
//
// Three states rather than two: "system" follows the OS and keeps following it
// when the OS changes, which a plain boolean cannot express — once a user has
// toggled, a boolean can no longer tell "chose light" from "OS happens to be
// light right now".
//
// The class is applied to <html> to match the `@custom-variant dark` rule in
// index.css. An inline script in index.html applies it before first paint;
// doing it only here would flash the light theme on every load.

import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'ntt.theme';

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
}

function applyTheme(theme: Theme): void {
  const dark = theme === 'dark' || (theme === 'system' && systemPrefersDark());
  document.documentElement.classList.toggle('dark', dark);
}

function storedTheme(): Theme {
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'system';
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(storedTheme);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  // Track OS changes only while following the system, so a user who picked a
  // theme is not overridden when their machine switches at sunset.
  useEffect(() => {
    if (theme !== 'system') return;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => applyTheme('system');
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => setThemeState(next), []);

  const toggle = useCallback(() => {
    // Toggling resolves "system" to the opposite of what is currently shown,
    // which is what a user pressing a sun/moon button expects.
    setThemeState((current) => {
      const isDark =
        current === 'dark' || (current === 'system' && systemPrefersDark());
      return isDark ? 'light' : 'dark';
    });
  }, []);

  const isDark =
    theme === 'dark' || (theme === 'system' && systemPrefersDark());

  return { theme, setTheme, toggle, isDark };
}
