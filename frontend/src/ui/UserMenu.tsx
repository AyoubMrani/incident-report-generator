// Signed-in user, their role, and sign-out.
//
// The role badge is shown rather than hidden because this app has a genuinely
// read-only role: a viewer who cannot see why the "New report" button is
// missing will report it as a bug.

import React, { useEffect, useRef, useState } from 'react';
import { LogOut, Moon, Sun, ShieldCheck, Eye, PenLine, UserCog, Settings, BarChart3 } from 'lucide-react';
import type { UserInfo } from '../auth/oidc';
import { NTT_BLUE } from './Brand';

interface Props {
  user: UserInfo;
  onLogout: () => void;
  isDark: boolean;
  onToggleTheme: () => void;
  authEnabled: boolean;
  /** Sidebar is collapsed — show the avatar only. */
  collapsed?: boolean;
  onOpenProfile?: () => void;
  onOpenSettings?: () => void;
  /** Admin-only: answer quality metrics. Undefined hides the entry. */
  onOpenMetrics?: () => void;
}

function primaryRole(user: UserInfo): { label: string; icon: React.ReactNode } {
  if (user.is_admin) return { label: 'Admin', icon: <ShieldCheck className="w-3 h-3" /> };
  if (user.can_write) return { label: 'Analyst', icon: <PenLine className="w-3 h-3" /> };
  return { label: 'Viewer', icon: <Eye className="w-3 h-3" /> };
}

function initials(user: UserInfo): string {
  const source = user.display_name || user.username || '?';
  return source
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}

export default function UserMenu({
  user,
  onLogout,
  isDark,
  onToggleTheme,
  authEnabled,
  collapsed = false,
  onOpenProfile,
  onOpenSettings,
  onOpenMetrics,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  const role = primaryRole(user);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? `${user.display_name || user.username} — ${role.label}` : undefined}
        className={`flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition hover:bg-slate-100 dark:hover:bg-slate-800 ${
          collapsed ? 'justify-center px-0' : ''
        }`}
      >
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt=""
            className="h-8 w-8 shrink-0 rounded-full object-cover"
          />
        ) : (
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
            style={{ background: NTT_BLUE }}
          >
            {initials(user)}
          </span>
        )}
        {!collapsed && (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium text-app">
              {user.display_name || user.username}
            </span>
            <span className="flex items-center gap-1 text-[11px] text-app-muted">
              {role.icon}
              {role.label}
            </span>
          </span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 z-20 mb-2 w-full min-w-[13rem] overflow-hidden rounded-lg border-app bg-app-elevated border shadow-lg"
        >
          {user.email && (
            <div className="border-b border-slate-100 px-3 py-2 dark:border-slate-800">
              <p className="truncate text-xs text-app-muted">
                {user.email}
              </p>
            </div>
          )}

          {onOpenProfile && (
            <button
              role="menuitem"
              onClick={() => { onOpenProfile(); setOpen(false); }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <UserCog className="w-4 h-4" />
              Profile
            </button>
          )}

          {onOpenSettings && (
            <button
              role="menuitem"
              onClick={() => { onOpenSettings(); setOpen(false); }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <Settings className="w-4 h-4" />
              Settings
              <kbd className="ml-auto text-[10px] text-slate-400">⌘,</kbd>
            </button>
          )}

          {onOpenMetrics && (
            <button
              role="menuitem"
              onClick={() => { onOpenMetrics(); setOpen(false); }}
              className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-app transition hover:bg-app-hover"
            >
              <BarChart3 className="w-4 h-4" />
              Answer quality
            </button>
          )}

          <button
            role="menuitem"
            onClick={() => {
              onToggleTheme();
              setOpen(false);
            }}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            {isDark ? 'Light theme' : 'Dark theme'}
          </button>

          {authEnabled && (
            <button
              role="menuitem"
              onClick={onLogout}
              className="flex w-full items-center gap-2.5 border-t border-slate-100 px-3 py-2 text-left text-sm text-red-600 transition hover:bg-red-50 dark:border-slate-800 dark:text-red-400 dark:hover:bg-red-950/30"
            >
              <LogOut className="w-4 h-4" />
              Sign out
            </button>
          )}
        </div>
      )}
    </div>
  );
}
