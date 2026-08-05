// Toasts.
//
// Added because several actions previously succeeded or failed silently —
// generating a report, saving a correction, rating an answer. A user who gets
// no acknowledgement assumes the click did not register and does it again.
//
// Deliberately tiny (no library): a context, a reducer-free array, and a timer.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { AlertTriangle, Check, Info, X } from 'lucide-react';

type ToastKind = 'success' | 'error' | 'info';

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

// Errors stay longer: they usually carry something the user has to read and
// act on, while a success is just an acknowledgement.
const DURATION: Record<ToastKind, number> = {
  success: 3200,
  info: 3800,
  error: 6000,
};

const STYLES: Record<ToastKind, { cls: string; icon: React.ReactNode }> = {
  success: {
    cls: 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/60 dark:text-emerald-200',
    icon: <Check className="w-4 h-4 shrink-0" />,
  },
  error: {
    cls: 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/50 dark:bg-red-950/60 dark:text-red-200',
    icon: <AlertTriangle className="w-4 h-4 shrink-0" />,
  },
  info: {
    cls: 'border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200',
    icon: <Info className="w-4 h-4 shrink-0" />,
  },
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((kind: ToastKind, message: string) => {
    // Date.now() alone collides when two toasts fire in the same millisecond,
    // which React then renders with duplicate keys.
    const id = Date.now() + Math.random();
    setToasts((list) => [...list.slice(-3), { id, kind, message }]);
    setTimeout(() => setToasts((l) => l.filter((t) => t.id !== id)), DURATION[kind]);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => push('success', m),
      error: (m) => push('error', m),
      info: (m) => push('info', m),
    }),
    [push],
  );

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed bottom-5 right-5 z-[90] flex w-full max-w-sm flex-col gap-2"
        role="region"
        aria-label="Notifications"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`ntt-rise pointer-events-auto flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-[13px] shadow-lg ${STYLES[t.kind].cls}`}
          >
            {STYLES[t.kind].icon}
            <span className="flex-1 leading-snug">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="shrink-0 opacity-50 transition hover:opacity-100"
              aria-label="Dismiss"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/**
 * Toast API. Returns no-ops outside a provider rather than throwing, so a
 * component used in isolation (or a test) does not crash on a cosmetic call.
 */
export function useToast(): ToastApi {
  const ctx = useContext(ToastCtx);
  return (
    ctx ?? {
      success: () => {},
      error: () => {},
      info: () => {},
    }
  );
}

/** Copy text to the clipboard and toast the result. */
export function useCopy() {
  const toast = useToast();
  return useCallback(
    async (text: string, label = 'Copied to clipboard') => {
      try {
        await navigator.clipboard.writeText(text);
        toast.success(label);
      } catch {
        toast.error('Could not copy — your browser blocked clipboard access.');
      }
    },
    [toast],
  );
}
