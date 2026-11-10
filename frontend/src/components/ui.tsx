import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ChevronRight, Home, Loader2, X } from 'lucide-react';
import { fmtDate, humanize } from '../lib/format';

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}

export function Card({
  title,
  actions,
  children,
  className,
  bodyClassName,
  icon,
  subtitle,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  icon?: ReactNode;
  subtitle?: ReactNode;
}) {
  return (
    <section className={cx('card', className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-2.5 dark:border-slate-800">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              {icon}
              {title}
            </h2>
            {subtitle && <p className="text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx('p-4', bodyClassName)}>{children}</div>
    </section>
  );
}

const TONES = {
  green: 'bg-emerald-100 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-400/30',
  red: 'bg-red-100 text-red-800 ring-red-600/20 dark:bg-red-500/15 dark:text-red-300 dark:ring-red-400/30',
  amber: 'bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-400/30',
  blue: 'bg-sky-100 text-sky-800 ring-sky-600/20 dark:bg-sky-500/15 dark:text-sky-300 dark:ring-sky-400/30',
  violet: 'bg-violet-100 text-violet-800 ring-violet-600/20 dark:bg-violet-500/15 dark:text-violet-300 dark:ring-violet-400/30',
  gray: 'bg-slate-100 text-slate-700 ring-slate-500/20 dark:bg-slate-700/40 dark:text-slate-300 dark:ring-slate-500/30',
  brand: 'bg-brand-100 text-brand-800 ring-brand-600/20 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-400/30',
} as const;
export type Tone = keyof typeof TONES;

export function Badge({ tone = 'gray', children, title, className }: { tone?: Tone; children: ReactNode; title?: string; className?: string }) {
  return (
    <span
      title={title}
      className={cx('inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset', TONES[tone], className)}
    >
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, Tone> = {
  online: 'green',
  connected: 'green',
  up: 'green',
  ok: 'green',
  success: 'green',
  imported: 'green',
  allowed: 'green',
  allow: 'green',
  permit: 'green',
  high: 'green',
  valid: 'green',
  active: 'green',
  enabled: 'green',
  offline: 'red',
  disconnected: 'red',
  down: 'red',
  error: 'red',
  failed: 'red',
  rejected: 'red',
  blocked: 'red',
  deny: 'red',
  drop: 'red',
  low: 'red',
  removed: 'red',
  restricted: 'amber',
  partial: 'amber',
  medium: 'amber',
  warning: 'amber',
  pending: 'amber',
  isolated: 'amber',
  modified: 'amber',
  unsupported: 'gray',
  unknown: 'gray',
  disabled: 'gray',
  running: 'blue',
  added: 'blue',
  heartbeat_missed: 'amber',
};

export function StatusBadge({ status, label, title }: { status: string | null | undefined; label?: string; title?: string }) {
  if (status === null || status === undefined || status === '') return <Badge tone="gray">unknown</Badge>;
  const s = String(status).toLowerCase();
  return (
    <Badge tone={STATUS_TONES[s] ?? 'gray'} title={title}>
      {s === 'running' && <Loader2 className="h-3 w-3 animate-spin" />}
      {label ?? humanize(String(status))}
    </Badge>
  );
}

export function BoolBadge({ value, yes = 'Yes', no = 'No' }: { value: boolean | null | undefined; yes?: string; no?: string }) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>;
  return <Badge tone={value ? 'green' : 'gray'}>{value ? yes : no}</Badge>;
}

const SOURCE_LABELS: Record<string, { label: string; tone: Tone; title: string }> = {
  api: { label: 'Controller', tone: 'blue', title: 'Retrieved directly from the Omada controller' },
  demo: { label: 'Demo data', tone: 'violet', title: 'Generated example data (demo mode)' },
  backup: { label: 'Backup', tone: 'amber', title: 'Imported from a controller backup' },
  manual: { label: 'Manual', tone: 'brand', title: 'Added manually' },
  derived: { label: 'Derived', tone: 'gray', title: 'Automatically derived from other data' },
  lldp: { label: 'LLDP', tone: 'blue', title: 'Discovered via LLDP' },
  carried_forward: { label: 'Previous sync', tone: 'amber', title: 'Not available in the last sync – value carried forward' },
  unknown: { label: 'Unknown', tone: 'gray', title: 'Source unknown' },
};

export function SourceBadge({ source }: { source: string | null | undefined }) {
  const s = SOURCE_LABELS[source ?? 'unknown'] ?? { label: humanize(source ?? 'unknown'), tone: 'gray' as Tone, title: '' };
  return (
    <Badge tone={s.tone} title={s.title}>
      {s.label}
    </Badge>
  );
}

export function Spinner({ label = 'Loading…', className }: { label?: string; className?: string }) {
  return (
    <div className={cx('flex items-center justify-center gap-2 p-8 text-sm text-slate-500', className)}>
      <Loader2 className="h-5 w-5 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorBox({ error, title = 'Could not load data' }: { error: unknown; title?: string }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <div className="font-medium">{title}</div>
        <div>{msg}</div>
      </div>
    </div>
  );
}

export function EmptyState({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
      {icon}
      {children}
    </div>
  );
}

export function NotAvailable({ text = 'Not available' }: { text?: string }) {
  return <span className="italic text-slate-400 dark:text-slate-500">{text}</span>;
}

export interface Crumb {
  label: ReactNode;
  to?: string;
}

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-1 flex flex-wrap items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
      <Link to="/" className="hover:text-slate-800 dark:hover:text-slate-200" aria-label="Dashboard">
        <Home className="h-3.5 w-3.5" />
      </Link>
      {items.map((c, i) => (
        <span key={i} className="flex items-center gap-1">
          <ChevronRight className="h-3 w-3" />
          {c.to ? (
            <Link to={c.to} className="hover:text-slate-800 hover:underline dark:hover:text-slate-200">
              {c.label}
            </Link>
          ) : (
            <span className="text-slate-700 dark:text-slate-300">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}

export function PageHeader({
  title,
  subtitle,
  crumbs,
  actions,
  icon,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  crumbs?: Crumb[];
  actions?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="mb-4">
      {crumbs && <Breadcrumbs items={crumbs} />}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900 dark:text-white">
            {icon}
            <span className="truncate">{title}</span>
          </h1>
          {subtitle && <div className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{subtitle}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: T; label: ReactNode; count?: number }[];
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={t.id === active}
          onClick={() => onChange(t.id)}
          className={cx(
            '-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium',
            t.id === active
              ? 'border-brand-600 text-brand-700 dark:border-brand-400 dark:text-brand-300'
              : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200',
          )}
        >
          {t.label}
          {t.count !== undefined && (
            <span className="rounded-full bg-slate-100 px-1.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeRef.current();
    window.addEventListener('keydown', onKey);
    ref.current?.focus();
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 pt-[8vh]" onMouseDown={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        className={cx('card w-full outline-none', wide ? 'max-w-4xl' : 'max-w-lg')}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <h2 className="text-base font-semibold">{title}</h2>
          <button className="btn-ghost p-1" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto p-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3 dark:border-slate-800">{footer}</footer>}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  danger,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button className="btn-secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className={danger ? 'btn-danger' : 'btn-primary'} onClick={onConfirm} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {confirmLabel}
          </button>
        </>
      }
    >
      <div className="text-sm text-slate-700 dark:text-slate-300">{message}</div>
    </Modal>
  );
}

/** Definition list of label/value pairs. */
export function KeyValue({ items, cols = 2 }: { items: { label: string; value: ReactNode; hidden?: boolean }[]; cols?: 1 | 2 | 3 }) {
  return (
    <dl className={cx('grid gap-x-6 gap-y-3', cols === 1 ? 'grid-cols-1' : cols === 2 ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3')}>
      {items
        .filter((i) => !i.hidden)
        .map((i) => (
          <div key={i.label} className="min-w-0">
            <dt className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{i.label}</dt>
            <dd className="mt-0.5 break-words text-sm text-slate-800 dark:text-slate-200">
              {i.value === null || i.value === undefined || i.value === '' ? <NotAvailable /> : i.value}
            </dd>
          </div>
        ))}
    </dl>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{hint}</span>}
    </label>
  );
}

export function MetaLine({ meta }: { meta?: { source?: string; collected_at?: string | null; updated_at?: string | null; validation_status?: string | null } }) {
  if (!meta) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
      <SourceBadge source={meta.source} />
      <span>Collected {fmtDate(meta.collected_at)}</span>
      {meta.updated_at && meta.updated_at !== meta.collected_at && <span>· last change {fmtDate(meta.updated_at)}</span>}
      {meta.validation_status && meta.validation_status !== 'valid' && <StatusBadge status={meta.validation_status} />}
    </div>
  );
}

export function Mono({ children, wrap }: { children: ReactNode; wrap?: boolean }) {
  return <span className={cx('font-mono text-[0.8rem]', wrap ? 'break-all' : 'whitespace-nowrap')}>{children}</span>;
}

/** Simple server-side pager (offset/limit). */
export function Pager({ total, offset, limit, onChange }: { total: number; offset: number; limit: number; onChange: (offset: number) => void }) {
  if (total <= limit) return <div className="px-3 py-2 text-xs text-slate-500">{total} {total === 1 ? 'entry' : 'entries'}</div>;
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2 text-xs text-slate-500">
      <span>
        {offset + 1}–{Math.min(total, offset + limit)} of {total}
      </span>
      <span className="flex items-center gap-1">
        <button className="btn-secondary px-2 py-1 text-xs" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </button>
        <span className="px-1">
          Page {page} / {pages}
        </span>
        <button className="btn-secondary px-2 py-1 text-xs" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Next
        </button>
      </span>
    </div>
  );
}
