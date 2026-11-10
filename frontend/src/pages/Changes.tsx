import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { GitCompare, History } from 'lucide-react';
import { get } from '../api/client';
import type { Change, Paged, Snapshot, SnapshotCompare } from '../api/types';
import { useSite } from '../context/SiteContext';
import { ChangeValue } from '../components/detail';
import { Badge, Card, EmptyState, ErrorBox, Field, PageHeader, Pager, Spinner, StatusBadge, Tabs } from '../components/ui';
import { fmtDate, kindLabel, KIND_LABELS } from '../lib/format';
import { objectPath } from '../lib/routes';

type Tab = 'changes' | 'snapshots';

export function ChangeTable({ changes, showUser = true }: { changes: Change[]; showUser?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="table-base">
        <thead>
          <tr>
            {changes.some((c) => c.ts) && <th>Time</th>}
            <th>Object</th>
            <th>Change</th>
            <th>Field</th>
            <th>Before</th>
            <th>After</th>
            {showUser && <th>By</th>}
          </tr>
        </thead>
        <tbody>
          {changes.map((c, i) => {
            const to = c.change_type !== 'removed' ? objectPath(c.object_type, c.object_key) : null;
            return (
              <tr key={c.id ?? i}>
                {changes.some((x) => x.ts) && <td className="whitespace-nowrap">{fmtDate(c.ts)}</td>}
                <td>
                  <div className="font-medium">{to ? <Link className="link" to={to}>{c.object_name ?? c.object_key}</Link> : (c.object_name ?? c.object_key)}</div>
                  <div className="text-xs text-slate-500">{kindLabel(c.object_type)}</div>
                </td>
                <td>
                  <span className="flex flex-wrap gap-1">
                    <StatusBadge status={c.change_type} />
                    {c.kind && <Badge tone={c.kind === 'manual' ? 'brand' : 'gray'}>{c.kind}</Badge>}
                  </span>
                </td>
                <td className="whitespace-nowrap">{c.field ?? '—'}</td>
                <td className="max-w-xs">
                  <ChangeValue v={c.before} />
                </td>
                <td className="max-w-xs">
                  <ChangeValue v={c.after} />
                </td>
                {showUser && <td>{c.username ?? (c.kind === 'config' ? (c.sync_id ? <Link className="link" to={`/sync/runs/${c.sync_id}`}>sync #{c.sync_id}</Link> : 'sync') : '—')}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const LIMIT = 50;

function ChangesTab() {
  const [params, setParams] = useSearchParams();
  const { siteId } = useSite();
  const filters = {
    kind: params.get('kind') ?? '',
    object_type: params.get('object_type') ?? '',
    change_type: params.get('change_type') ?? '',
    days: params.get('days') ?? '',
    q: params.get('q') ?? '',
    sync_id: params.get('sync_id') ?? '',
  };
  const offset = Number(params.get('offset') ?? 0);
  const [text, setText] = useState(filters.q);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete('offset');
    setParams(next, { replace: true });
  };
  const q = useQuery({
    queryKey: ['changes', filters, offset, siteId],
    queryFn: () => get<Paged<Change>>('changes', { ...filters, site_id: siteId, limit: LIMIT, offset }),
    placeholderData: keepPreviousData,
  });
  return (
    <Card bodyClassName="p-0">
      <div className="grid gap-3 border-b border-slate-200 p-3 sm:grid-cols-3 lg:grid-cols-6 dark:border-slate-800">
        <Field label="Kind">
          <select className="input" value={filters.kind} onChange={(e) => set('kind', e.target.value)}>
            <option value="">All</option>
            <option value="config">Configuration (sync)</option>
            <option value="manual">Manual documentation</option>
          </select>
        </Field>
        <Field label="Object type">
          <select className="input" value={filters.object_type} onChange={(e) => set('object_type', e.target.value)}>
            <option value="">All</option>
            {[...Object.keys(KIND_LABELS), 'document', 'relationship']
              .filter((v, i, a) => a.indexOf(v) === i)
              .map((k) => (
                <option key={k} value={k}>
                  {kindLabel(k)}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Change type">
          <select className="input" value={filters.change_type} onChange={(e) => set('change_type', e.target.value)}>
            <option value="">All</option>
            <option value="added">Added</option>
            <option value="modified">Modified</option>
            <option value="removed">Removed</option>
          </select>
        </Field>
        <Field label="Period">
          <select className="input" value={filters.days} onChange={(e) => set('days', e.target.value)}>
            <option value="">All time</option>
            <option value="1">Last 24 hours</option>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="365">Last year</option>
          </select>
        </Field>
        <form
          className="sm:col-span-2"
          onSubmit={(e) => {
            e.preventDefault();
            set('q', text.trim());
          }}
        >
          <Field label="Text">
            <div className="flex gap-2">
              <input className="input" placeholder="Name, field, value…" value={text} onChange={(e) => setText(e.target.value)} />
              <button className="btn-secondary" type="submit">
                Apply
              </button>
            </div>
          </Field>
        </form>
      </div>
      {filters.sync_id && (
        <div className="flex items-center gap-2 border-b border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
          Showing changes of sync run #{filters.sync_id}
          <button className="btn-ghost py-0.5 text-xs" onClick={() => set('sync_id', '')}>
            Clear
          </button>
        </div>
      )}
      {q.isLoading ? (
        <Spinner />
      ) : q.error || !q.data ? (
        <ErrorBox error={q.error} />
      ) : q.data.items.length === 0 ? (
        <EmptyState icon={<History className="h-8 w-8" />}>No changes match the filters.</EmptyState>
      ) : (
        <>
          <ChangeTable changes={q.data.items} />
          <Pager
            total={q.data.total}
            offset={offset}
            limit={LIMIT}
            onChange={(o) => {
              const next = new URLSearchParams(params);
              next.set('offset', String(o));
              setParams(next, { replace: true });
            }}
          />
        </>
      )}
    </Card>
  );
}

function SnapshotsTab() {
  const snaps = useQuery({ queryKey: ['snapshots'], queryFn: () => get<Snapshot[]>('snapshots') });
  const [a, setA] = useState<number | ''>('');
  const [b, setB] = useState<number | ''>('');
  const [clients, setClients] = useState(false);
  const [cmp, setCmp] = useState<{ a: number; b: number; clients: boolean } | null>(null);
  const diff = useQuery({
    queryKey: ['snapshot-compare', cmp],
    queryFn: () => get<SnapshotCompare>('snapshots/compare', { a: cmp!.a, b: cmp!.b, include_clients: cmp!.clients }),
    enabled: !!cmp,
  });
  if (snaps.isLoading) return <Spinner />;
  if (snaps.error || !snaps.data) return <ErrorBox error={snaps.error} />;
  const list = snaps.data;
  const label = (s: Snapshot) => `#${s.id} · ${fmtDate(s.created_at)} · ${s.source}${s.label ? ` · ${s.label}` : ''}`;
  const pick = (s: Snapshot) => {
    if (a === '' || b !== '') {
      setA(s.id);
      setB('');
    } else if (s.id < a) {
      setB(a);
      setA(s.id);
    } else setB(s.id);
  };
  return (
    <div className="space-y-4">
      <Card title="Compare snapshots" icon={<GitCompare className="h-4 w-4 text-slate-500" />}>
        <div className="grid items-end gap-3 md:grid-cols-[1fr_1fr_auto_auto]">
          <Field label="Older snapshot (A)">
            <select className="input" value={a} onChange={(e) => setA(e.target.value ? Number(e.target.value) : '')}>
              <option value="">Select…</option>
              {list.map((s) => (
                <option key={s.id} value={s.id}>
                  {label(s)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Newer snapshot (B)">
            <select className="input" value={b} onChange={(e) => setB(e.target.value ? Number(e.target.value) : '')}>
              <option value="">Select…</option>
              {list.map((s) => (
                <option key={s.id} value={s.id}>
                  {label(s)}
                </option>
              ))}
            </select>
          </Field>
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input type="checkbox" checked={clients} onChange={(e) => setClients(e.target.checked)} /> Include clients
          </label>
          <button className="btn-primary" disabled={a === '' || b === '' || a === b} onClick={() => a !== '' && b !== '' && setCmp({ a, b, clients })}>
            Compare
          </button>
        </div>
        {list.length < 2 && <p className="mt-2 text-sm text-slate-500">At least two snapshots are required for a comparison.</p>}
      </Card>
      {cmp &&
        (diff.isLoading ? (
          <Spinner />
        ) : diff.error || !diff.data ? (
          <ErrorBox error={diff.error} />
        ) : (
          <Card
            title={`Differences #${diff.data.a.id} → #${diff.data.b.id}`}
            actions={
              <span className="flex gap-1">
                <Badge tone="green">{diff.data.summary.added} added</Badge>
                <Badge tone="amber">{diff.data.summary.modified} modified</Badge>
                <Badge tone="red">{diff.data.summary.removed} removed</Badge>
              </span>
            }
            bodyClassName="p-0"
          >
            {diff.data.changes.length ? <ChangeTable changes={diff.data.changes} showUser={false} /> : <EmptyState>The two snapshots are identical.</EmptyState>}
          </Card>
        ))}
      <Card title="Snapshots" subtitle="A configuration snapshot is stored after each synchronisation and backup import. Click rows to select A and B." bodyClassName="p-0">
        {list.length === 0 ? (
          <EmptyState>No snapshots yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Created</th>
                  <th>Source</th>
                  <th>Label</th>
                  <th>Controller version</th>
                  <th>Objects</th>
                  <th>Checksum</th>
                </tr>
              </thead>
              <tbody>
                {list.map((s) => (
                  <tr key={s.id} className={s.id === a || s.id === b ? 'bg-brand-50 dark:bg-brand-900/20' : 'cursor-pointer'} onClick={() => pick(s)}>
                    <td className="font-semibold">
                      #{s.id} {s.id === a && <Badge tone="brand">A</Badge>} {s.id === b && <Badge tone="brand">B</Badge>}
                    </td>
                    <td className="whitespace-nowrap">{fmtDate(s.created_at)}</td>
                    <td>
                      <Badge tone="gray">{s.source}</Badge>
                    </td>
                    <td>{s.label ?? '—'}</td>
                    <td>{s.controller_version ?? '—'}</td>
                    <td>{s.object_count}</td>
                    <td className="font-mono text-xs text-slate-500" title={s.checksum}>
                      {s.checksum.slice(0, 12)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

export function ChangesPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab) || 'changes';
  return (
    <div>
      <PageHeader title="Change History" icon={<History className="h-5 w-5 text-brand-600" />} crumbs={[{ label: 'Change History' }]} subtitle="Configuration changes detected during synchronisation and edits of the manual documentation" />
      <Tabs<Tab>
        active={tab}
        onChange={(t) => setParams(t === 'changes' ? {} : { tab: t }, { replace: true })}
        tabs={[
          { id: 'changes', label: 'Changes' },
          { id: 'snapshots', label: 'Snapshots & comparison' },
        ]}
      />
      {tab === 'changes' ? <ChangesTab /> : <SnapshotsTab />}
    </div>
  );
}
