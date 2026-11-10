import { useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { cx } from './ui';

export interface Column<T> {
  id: string;
  header: ReactNode;
  /** Value used for sorting, filtering and as the default cell content. */
  value: (row: T) => unknown;
  cell?: (row: T) => ReactNode;
  sortable?: boolean;
  /** Show a select filter with the distinct values of this column. */
  filter?: boolean;
  className?: string;
  headerClassName?: string;
}

function toText(v: unknown): string {
  if (v === null || v === undefined) return '';
  if (Array.isArray(v)) return v.map(toText).join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

function compare(a: unknown, b: unknown): number {
  const ea = a === null || a === undefined || a === '';
  const eb = b === null || b === undefined || b === '';
  if (ea && eb) return 0;
  if (ea) return 1;
  if (eb) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(b) - Number(a);
  return collator.compare(toText(a), toText(b));
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  rowHref,
  initialSort,
  searchPlaceholder = 'Filter…',
  toolbar,
  emptyText = 'No entries.',
  pageSizes = [25, 50, 100],
  defaultPageSize = 25,
  hideSearch,
  rowClassName,
  compact,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T, index: number) => string;
  rowHref?: (row: T) => string | null | undefined;
  initialSort?: { id: string; dir: 'asc' | 'desc' };
  searchPlaceholder?: string;
  toolbar?: ReactNode;
  emptyText?: ReactNode;
  pageSizes?: number[];
  defaultPageSize?: number;
  hideSearch?: boolean;
  rowClassName?: (row: T) => string | undefined;
  compact?: boolean;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<{ id: string; dir: 'asc' | 'desc' } | null>(initialSort ?? null);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(defaultPageSize);

  const filterOptions = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const c of columns) {
      if (!c.filter) continue;
      const set = new Set<string>();
      for (const r of rows) {
        const v = c.value(r);
        if (Array.isArray(v)) v.forEach((x) => set.add(toText(x)));
        else set.add(toText(v));
      }
      out[c.id] = [...set].sort((a, b) => collator.compare(a, b));
    }
    return out;
  }, [rows, columns]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const active = Object.entries(filters).filter(([, v]) => v !== '');
    let out = rows.filter((r) => {
      for (const [id, val] of active) {
        const col = columns.find((c) => c.id === id);
        if (!col) continue;
        const v = col.value(r);
        const ok = Array.isArray(v) ? v.map(toText).includes(val) : toText(v) === val;
        if (!ok) return false;
      }
      if (!q) return true;
      return columns.some((c) => toText(c.value(r)).toLowerCase().includes(q));
    });
    if (sort) {
      const col = columns.find((c) => c.id === sort.id);
      if (col) {
        out = [...out].sort((a, b) => {
          const res = compare(col.value(a), col.value(b));
          return sort.dir === 'asc' ? res : -res;
        });
      }
    }
    return out;
  }, [rows, columns, query, filters, sort]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pages - 1);
  const visible = filtered.slice(current * pageSize, current * pageSize + pageSize);

  const toggleSort = (id: string) => {
    setSort((s) => (s?.id !== id ? { id, dir: 'asc' } : s.dir === 'asc' ? { id, dir: 'desc' } : null));
  };

  const hasFilters = columns.some((c) => c.filter);

  return (
    <div className="card overflow-hidden">
      {(!hideSearch || hasFilters || toolbar) && (
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 p-2.5 dark:border-slate-800">
          {!hideSearch && (
            <div className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                className="input pl-8"
                value={query}
                placeholder={searchPlaceholder}
                aria-label="Filter table"
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
              />
            </div>
          )}
          {columns
            .filter((c) => c.filter)
            .map((c) => (
              <select
                key={c.id}
                className="input w-auto"
                aria-label={`Filter by ${typeof c.header === 'string' ? c.header : c.id}`}
                value={filters[c.id] ?? ''}
                onChange={(e) => {
                  const v = e.target.value;
                  setFilters((f) => ({ ...f, [c.id]: v }));
                  setPage(0);
                }}
              >
                <option value="">{typeof c.header === 'string' ? `All ${c.header.toLowerCase()}` : 'All'}</option>
                {filterOptions[c.id]?.map((o) => (
                  <option key={o} value={o}>
                    {o === '' ? '(empty)' : o}
                  </option>
                ))}
              </select>
            ))}
          <div className="ml-auto flex items-center gap-2">{toolbar}</div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="table-base">
          <thead>
            <tr>
              {columns.map((c) => {
                const sortable = c.sortable !== false;
                const active = sort?.id === c.id;
                return (
                  <th key={c.id} className={c.headerClassName} aria-sort={active ? (sort?.dir === 'asc' ? 'ascending' : 'descending') : undefined}>
                    {sortable ? (
                      <button className="inline-flex items-center gap-1 uppercase hover:text-slate-800 dark:hover:text-slate-200" onClick={() => toggleSort(c.id)}>
                        {c.header}
                        {active ? (
                          sort?.dir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                        ) : (
                          <ArrowUpDown className="h-3 w-3 opacity-30" />
                        )}
                      </button>
                    ) : (
                      c.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="py-8 text-center text-slate-500">
                  {rows.length === 0 ? emptyText : 'No entries match the filter.'}
                </td>
              </tr>
            )}
            {visible.map((r, i) => {
              const href = rowHref?.(r);
              return (
                <tr
                  key={rowKey(r, i)}
                  className={cx(
                    href && 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50',
                    compact && '[&>td]:py-1.5',
                    rowClassName?.(r),
                  )}
                  onClick={(e) => {
                    if (!href) return;
                    const target = e.target as HTMLElement;
                    if (target.closest('a,button,input,select,textarea')) return;
                    if (e.metaKey || e.ctrlKey) {
                      window.open(new URL(href.replace(/^\//, ''), document.baseURI).toString(), '_blank');
                    } else navigate(href);
                  }}
                >
                  {columns.map((c) => (
                    <td key={c.id} className={c.className}>
                      {c.cell ? c.cell(r) : toText(c.value(r)) || <span className="text-slate-400">—</span>}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 px-3 py-2 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <span>
          {filtered.length === rows.length ? `${rows.length} ${rows.length === 1 ? 'entry' : 'entries'}` : `${filtered.length} of ${rows.length} entries`}
        </span>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1">
            Rows
            <select
              className="input w-auto py-0.5 text-xs"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(0);
              }}
            >
              {pageSizes.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <span>
            Page {current + 1} / {pages}
          </span>
          <button className="btn-ghost p-1" disabled={current === 0} onClick={() => setPage(current - 1)} aria-label="Previous page">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button className="btn-ghost p-1" disabled={current >= pages - 1} onClick={() => setPage(current + 1)} aria-label="Next page">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
