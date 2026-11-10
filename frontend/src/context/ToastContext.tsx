import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

type ToastKind = 'success' | 'error' | 'info';
interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastCtx {
  notify: (message: string, kind?: ToastKind) => void;
  error: (err: unknown) => void;
  success: (message: string) => void;
}

const Ctx = createContext<ToastCtx | null>(null);
let seq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const notify = useCallback(
    (message: string, kind: ToastKind = 'info') => {
      const id = ++seq;
      setToasts((t) => [...t.slice(-4), { id, kind, message }]);
      setTimeout(() => dismiss(id), kind === 'error' ? 8000 : 4000);
    },
    [dismiss],
  );
  const error = useCallback(
    (err: unknown) => notify(err instanceof Error ? err.message : String(err), 'error'),
    [notify],
  );
  const success = useCallback((m: string) => notify(m, 'success'), [notify]);

  return (
    <Ctx.Provider value={{ notify, error, success }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === 'error' ? 'alert' : 'status'}
            className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm shadow-lg ${
              t.kind === 'error'
                ? 'border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200'
                : t.kind === 'success'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200'
                  : 'border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100'
            }`}
          >
            {t.kind === 'error' ? (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            ) : t.kind === 'success' ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
            )}
            <span className="flex-1 break-words">{t.message}</span>
            <button className="opacity-60 hover:opacity-100" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('ToastProvider missing');
  return c;
}
