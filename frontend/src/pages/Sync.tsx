import { useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ArchiveRestore, RefreshCw, Upload } from 'lucide-react';
import { get, upload } from '../api/client';
import { useSyncStatus } from '../api/hooks';
import type { BackupImport, BackupObjectRef, Paged, SyncRun, SyncRunDetail } from '../api/types';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { DataTable } from '../components/DataTable';
import { Badge, Card, cx, EmptyState, ErrorBox, KeyValue, Mono, PageHeader, Pager, Spinner, StatusBadge, Tabs } from '../components/ui';
import { fmtDate, fmtDuration, fmtRelative, fmtValue, humanize, kindLabel } from '../lib/format';
import { objectPath } from '../lib/routes';
import { SyncNowButton } from './Dashboard';

type Tab = 'history' | 'backup';

function RunCounts({ r }: { r: SyncRun }) {
  return (
    <span className="flex flex-wrap gap-1 text-xs">
      <Badge tone="green">+{r.new_objects ?? 0}</Badge>
      <Badge tone="amber">~{r.changed_objects ?? 0}</Badge>
      <Badge tone="red">−{r.removed_objects ?? 0}</Badge>
    </span>
  );
}

function StatusCard() {
  const { data, isLoading, error } = useSyncStatus();
  if (isLoading) return <Spinner />;
  if (error || !data) return <ErrorBox error={error} />;
  const last = data.last;
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card title="Current status">
        <div className="flex items-center gap-3">
          <RefreshCw className={cx('h-8 w-8', data.running ? 'animate-spin text-brand-600' : 'text-slate-400')} />
          <div>
            <div className="text-lg font-semibold">{data.running ? 'Synchronisation running…' : 'Idle'}</div>
            <div className="text-sm text-slate-500">
              Interval: {humanize(data.interval)} · Next run: {data.next_run ? `${fmtDate(data.next_run)} (${fmtRelative(data.next_run)})` : 'not scheduled'}
            </div>
          </div>
        </div>
      </Card>
      <Card title="Last synchronisation">
        {last ? (
          <div className="space-y-1 text-sm">
            <div className="flex items-center gap-2">
              <StatusBadge status={last.status} />
              <Link className="link" to={`/sync/runs/${last.id}`}>
                Run #{last.id}
              </Link>
            </div>
            <div>
              {fmtDate(last.started_at)} · {fmtDuration(last.duration_ms)}
            </div>
            <RunCounts r={last} />
            {last.error && <div className="text-xs text-red-600 dark:text-red-400">{last.error}</div>}
          </div>
        ) : (
          <p className="text-sm text-slate-500">No synchronisation has been run yet.</p>
        )}
      </Card>
      <Card title="Statistics">
        <KeyValue
          items={[
            { label: 'Total runs', value: data.total_runs },
            { label: 'Last success', value: data.last_success ? fmtDate(data.last_success.started_at) : null },
            { label: 'Last failure', value: data.last_failure ? <Link className="link" to={`/sync/runs/${data.last_failure.id}`}>{fmtDate(data.last_failure.started_at)}</Link> : 'none' },
          ]}
        />
      </Card>
    </div>
  );
}

const LIMIT = 25;

function HistoryTab() {
  const [offset, setOffset] = useState(0);
  const status = useSyncStatus();
  const q = useQuery({
    queryKey: ['sync-history', offset, status.data?.running],
    queryFn: () => get<Paged<SyncRun>>('sync/history', { limit: LIMIT, offset }),
    placeholderData: keepPreviousData,
    refetchInterval: status.data?.running ? 2000 : false,
  });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={q.error} />;
  return (
    <Card title="Synchronisation history" bodyClassName="p-0">
      {q.data.items.length === 0 ? (
        <EmptyState>No synchronisation runs yet.</EmptyState>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Started</th>
                  <th>Duration</th>
                  <th>Status</th>
                  <th>Trigger</th>
                  <th>Changes (new/changed/removed)</th>
                  <th>Objects</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link className="link font-semibold" to={`/sync/runs/${r.id}`}>
                        #{r.id}
                      </Link>
                    </td>
                    <td className="whitespace-nowrap">{fmtDate(r.started_at)}</td>
                    <td>{fmtDuration(r.duration_ms)}</td>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                    <td>{humanize(r.trigger)}</td>
                    <td>
                      <RunCounts r={r} />
                    </td>
                    <td>{r.total_objects ?? '—'}</td>
                    <td className="max-w-xs truncate text-xs text-red-600 dark:text-red-400" title={r.error ?? undefined}>
                      {r.error ?? ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={q.data.total} offset={offset} limit={LIMIT} onChange={setOffset} />
        </>
      )}
    </Card>
  );
}

function ImportCounts({ imp }: { imp: BackupImport }) {
  const c = imp.comparison_counts;
  if (!c) return <span className="text-slate-400">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      <Badge tone={c.conflicts ? 'red' : 'green'}>{c.conflicts} conflicts</Badge>
      <Badge tone="blue">{c.only_in_backup} only in backup</Badge>
      <Badge tone="gray">{c.only_in_api} only in API</Badge>
    </span>
  );
}

function BackupTab() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const imports = useQuery({ queryKey: ['backup-imports'], queryFn: () => get<BackupImport[]>('backup/imports') });
  const m = useMutation({
    mutationFn: (f: File) => upload<BackupImport>('backup/import', f),
    onSuccess: (rec) => {
      if (rec.status === 'imported') toast.success(`Backup “${rec.filename}” imported.`);
      else toast.notify(`Backup “${rec.filename}” was rejected – see details.`, 'error');
      setFile(null);
      if (fileRef.current) fileRef.current.value = '';
      void qc.invalidateQueries({ predicate: (q) => !['auth-state', 'sync-status', 'manual-meta', 'sites'].includes(String(q.queryKey[0])) });
    },
    onError: (e) => toast.error(e),
  });
  return (
    <div className="space-y-4">
      {isAdmin && (
        <Card title="Import Omada controller backup" icon={<ArchiveRestore className="h-4 w-4 text-slate-500" />}>
          <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
            Upload an Omada controller backup / exported configuration (or a dataset JSON exported by this application). Supported data is imported as a separate source and
            compared with the data from the Open API. API data always takes precedence; conflicts are listed for review. Secrets contained in the backup are discarded.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <input ref={fileRef} type="file" className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm dark:file:bg-slate-800 dark:file:text-slate-200" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button className="btn-primary" disabled={!file || m.isPending} onClick={() => file && m.mutate(file)}>
              <Upload className="h-4 w-4" /> {m.isPending ? 'Importing…' : 'Import'}
            </button>
          </div>
          {m.data && (
            <div className="mt-3 text-sm">
              Result: <StatusBadge status={m.data.status} />{' '}
              <Link className="link" to={`/sync/imports/${m.data.id}`}>
                View details
              </Link>
            </div>
          )}
        </Card>
      )}
      <Card title="Import history" bodyClassName="p-0">
        {imports.isLoading ? (
          <Spinner />
        ) : imports.error || !imports.data ? (
          <ErrorBox error={imports.error} />
        ) : imports.data.length === 0 ? (
          <EmptyState>No backups have been imported yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Import</th>
                  <th>Date</th>
                  <th>File</th>
                  <th>Format</th>
                  <th>Controller version</th>
                  <th>Status</th>
                  <th>Comparison</th>
                  <th>By</th>
                </tr>
              </thead>
              <tbody>
                {imports.data.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <Link className="link font-semibold" to={`/sync/imports/${i.id}`}>
                        #{i.id}
                      </Link>
                    </td>
                    <td className="whitespace-nowrap">{fmtDate(i.imported_at)}</td>
                    <td className="max-w-[14rem] truncate" title={i.filename}>
                      {i.filename}
                    </td>
                    <td>{i.detected_format ?? '—'}</td>
                    <td>{i.controller_version ?? '—'}</td>
                    <td>
                      <StatusBadge status={i.status} />
                    </td>
                    <td>
                      <ImportCounts imp={i} />
                    </td>
                    <td>{i.imported_by ?? '—'}</td>
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

export function SyncPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get('tab') === 'backup' ? 'backup' : 'history';
  const setTab = (t: Tab) => setParams(t === 'history' ? {} : { tab: t }, { replace: true });
  return (
    <div>
      <PageHeader
        title="Synchronization"
        icon={<RefreshCw className="h-5 w-5 text-brand-600" />}
        crumbs={[{ label: 'Synchronization' }]}
        subtitle="Read-only data collection from the Omada controller via the Open API, and backup imports"
        actions={<SyncNowButton />}
      />
      <div className="mb-4">
        <StatusCard />
      </div>
      <Tabs<Tab>
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'history', label: 'Sync history' },
          { id: 'backup', label: 'Backup import' },
        ]}
      />
      {tab === 'history' ? <HistoryTab /> : <BackupTab />}
    </div>
  );
}

export function SyncDetailPage() {
  const { id } = useParams();
  const status = useSyncStatus();
  const q = useQuery({
    queryKey: ['sync-run', id],
    queryFn: () => get<SyncRunDetail>(`sync/history/${encodeURIComponent(id ?? '')}`),
    refetchInterval: (query) => (query.state.data?.status === 'running' || status.data?.running ? 2000 : false),
  });
  const crumbs = [{ label: 'Synchronization', to: '/sync' }, { label: `Run #${id}` }];
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <><PageHeader title={`Sync run #${id}`} crumbs={crumbs} /><ErrorBox error={q.error} /></>;
  const r = q.data;
  const d = r.details ?? {};
  const eps = d.endpoints ?? [];
  const known = new Set(['endpoints', 'request_count', 'carried_forward', 'unsupported', 'controller_version', 'first_sync']);
  const extra = Object.entries(d).filter(([k, v]) => !known.has(k) && v !== null && v !== undefined);
  const counts = { ok: eps.filter((e) => e.status === 'ok').length, error: eps.filter((e) => e.status === 'error').length, unsupported: eps.filter((e) => e.status === 'unsupported').length };
  return (
    <div className="space-y-4">
      <PageHeader title={`Sync run #${r.id}`} crumbs={crumbs} subtitle={<span className="flex items-center gap-2"><StatusBadge status={r.status} /> {fmtDate(r.started_at)}</span>} />
      <Card title="Summary">
        <KeyValue
          cols={3}
          items={[
            { label: 'Status', value: <StatusBadge status={r.status} /> },
            { label: 'Trigger', value: humanize(r.trigger) },
            { label: 'Started', value: fmtDate(r.started_at, true) },
            { label: 'Finished', value: r.finished_at ? fmtDate(r.finished_at, true) : null },
            { label: 'Duration', value: fmtDuration(r.duration_ms) },
            { label: 'API requests', value: d.request_count },
            { label: 'Objects total', value: r.total_objects },
            {
              label: 'Changes',
              value: (
                <span className="flex items-center gap-2">
                  <RunCounts r={r} />
                  <Link className="link text-xs" to={`/changes?sync_id=${r.id}`}>
                    view changes
                  </Link>
                </span>
              ),
            },
            { label: 'Controller version', value: d.controller_version },
            { label: 'Carried forward objects', value: d.carried_forward },
            { label: 'First sync', value: d.first_sync === undefined ? null : d.first_sync ? 'Yes' : 'No' },
            { label: 'Snapshot', value: r.snapshot_id ? <Link className="link" to="/changes?tab=snapshots">#{r.snapshot_id}</Link> : null },
          ]}
        />
        {r.error && (
          <div className="mt-3 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {r.error}
          </div>
        )}
        {(d.carried_forward ?? 0) > 0 && (
          <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">Some endpoints failed; data from the previous successful synchronisation was kept and marked as stale.</p>
        )}
        {extra.length > 0 && (
          <div className="mt-4">
            <KeyValue items={extra.map(([k, v]) => ({ label: humanize(k), value: fmtValue(v) }))} />
          </div>
        )}
      </Card>
      {d.unsupported && d.unsupported.length > 0 && (
        <Card title="Unsupported endpoints">
          <p className="mb-2 text-sm text-slate-500">These API functions are not available on this controller version and were skipped.</p>
          <div className="flex flex-wrap gap-1">
            {d.unsupported.map((u, i) => (
              <Badge key={i} tone="gray">
                {fmtValue(u)}
              </Badge>
            ))}
          </div>
        </Card>
      )}
      <Card
        title="Endpoints"
        actions={
          <span className="flex gap-1">
            <Badge tone="green">{counts.ok} ok</Badge>
            <Badge tone="red">{counts.error} errors</Badge>
            <Badge tone="gray">{counts.unsupported} unsupported</Badge>
          </span>
        }
        bodyClassName="p-0"
      >
        <DataTable
          rows={eps}
          rowKey={(e, i) => `${e.endpoint}:${e.site_id ?? ''}:${i}`}
          initialSort={{ id: 'status', dir: 'asc' }}
          compact
          emptyText="No endpoint details recorded."
          rowClassName={(e) => (e.status === 'error' ? 'bg-red-50/60 dark:bg-red-950/20' : undefined)}
          columns={[
            { id: 'endpoint', header: 'Endpoint', value: (e) => e.endpoint, cell: (e) => <span className="font-medium">{e.endpoint}</span> },
            { id: 'path', header: 'Path', value: (e) => e.path, cell: (e) => <Mono wrap>{e.path}</Mono> },
            { id: 'site', header: 'Site', value: (e) => e.site_id ?? '—', filter: true },
            { id: 'status', header: 'Status', value: (e) => e.status, cell: (e) => <StatusBadge status={e.status} />, filter: true },
            { id: 'count', header: 'Objects', value: (e) => e.count },
            { id: 'error', header: 'Error', value: (e) => e.error ?? '', cell: (e) => <span className="text-xs text-red-600 dark:text-red-400">{e.error ?? ''}</span> },
          ]}
        />
      </Card>
    </div>
  );
}

function RefTable({ rows }: { rows: BackupObjectRef[] }) {
  return (
    <DataTable<BackupObjectRef>
      rows={rows}
      rowKey={(r, i) => `${r.object_type}:${r.object_key}:${i}`}
      rowHref={(r) => objectPath(r.object_type, r.object_key)}
      compact
      emptyText="None."
      columns={[
        { id: 'type', header: 'Type', value: (r) => kindLabel(r.object_type), filter: true },
        { id: 'name', header: 'Name', value: (r) => r.object_name ?? r.object_key },
        { id: 'key', header: 'Key', value: (r) => r.object_key, cell: (r) => <Mono wrap>{r.object_key}</Mono> },
        { id: 'site', header: 'Site', value: (r) => r.site_id },
      ]}
    />
  );
}

export function BackupImportDetailPage() {
  const { id } = useParams();
  const [tab, setTab] = useState<'conflicts' | 'backup' | 'api'>('conflicts');
  const q = useQuery({ queryKey: ['backup-import', id], queryFn: () => get<BackupImport>(`backup/imports/${encodeURIComponent(id ?? '')}`) });
  const crumbs = [{ label: 'Synchronization', to: '/sync' }, { label: `Backup import #${id}` }];
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <><PageHeader title={`Backup import #${id}`} crumbs={crumbs} /><ErrorBox error={q.error} /></>;
  const imp = q.data;
  const cmp = imp.comparison;
  return (
    <div className="space-y-4">
      <PageHeader title={imp.filename} crumbs={crumbs} subtitle={<span className="flex items-center gap-2"><StatusBadge status={imp.status} /> imported {fmtDate(imp.imported_at)} by {imp.imported_by ?? 'unknown'}</span>} />
      <Card title="Import">
        <KeyValue
          cols={3}
          items={[
            { label: 'Status', value: <StatusBadge status={imp.status} /> },
            { label: 'Detected format', value: imp.detected_format },
            { label: 'Controller version', value: imp.controller_version },
            { label: 'Backup version', value: imp.backup_version },
            { label: 'SHA-256', value: <span className="break-all font-mono text-xs">{imp.sha256}</span> },
            { label: 'Snapshot', value: imp.snapshot_id ? `#${imp.snapshot_id}` : null },
          ]}
        />
        {imp.errors.length > 0 && (
          <ul className="mt-3 space-y-1 text-sm">
            {imp.errors.map((e, i) => {
              const s = fmtValue(e);
              const warn = s.startsWith('Warning:');
              return (
                <li key={i} className={cx('flex items-start gap-1.5', warn ? 'text-amber-700 dark:text-amber-400' : 'text-red-700 dark:text-red-400')}>
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {s}
                </li>
              );
            })}
          </ul>
        )}
        {imp.unsupported.length > 0 && (
          <div className="mt-3">
            <div className="label">Unsupported content (ignored)</div>
            <div className="flex flex-wrap gap-1">
              {imp.unsupported.map((u, i) => (
                <Badge key={i} tone="gray">
                  {fmtValue(u)}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Card>
      {imp.counts && (
        <Card title="Imported objects">
          <div className="flex flex-wrap gap-2">
            {Object.entries(imp.counts).map(([k, v]) => (
              <Badge key={k} tone={v ? 'brand' : 'gray'}>
                {kindLabel(k)}: {v}
              </Badge>
            ))}
          </div>
        </Card>
      )}
      {cmp ? (
        <Card title="Comparison with controller API data" bodyClassName="pt-1">
          {cmp.api_has_data === false && <p className="mb-2 text-sm text-slate-500">No API data was available at import time; nothing could be compared.</p>}
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { id: 'conflicts', label: 'Conflicts', count: cmp.counts?.conflicts ?? cmp.conflicts.length },
              { id: 'backup', label: 'Only in backup', count: cmp.counts?.only_in_backup ?? cmp.only_in_backup.length },
              { id: 'api', label: 'Only in API', count: cmp.counts?.only_in_api ?? cmp.only_in_api.length },
            ]}
          />
          {tab === 'conflicts' ? (
            <DataTable
              rows={cmp.conflicts}
              rowKey={(c, i) => `${c.object_type}:${c.object_key}:${c.field}:${i}`}
              rowHref={(c) => objectPath(c.object_type, c.object_key)}
              compact
              emptyText="No conflicts – backup and API data agree."
              columns={[
                { id: 'type', header: 'Type', value: (c) => kindLabel(c.object_type), filter: true },
                { id: 'name', header: 'Object', value: (c) => c.object_name ?? c.object_key },
                { id: 'field', header: 'Field', value: (c) => c.field },
                { id: 'api', header: 'API value (used)', value: (c) => fmtValue(c.api_value), cell: (c) => <span className="font-mono text-xs text-emerald-700 dark:text-emerald-400">{fmtValue(c.api_value)}</span> },
                { id: 'backup', header: 'Backup value', value: (c) => fmtValue(c.backup_value), cell: (c) => <span className="font-mono text-xs text-amber-700 dark:text-amber-400">{fmtValue(c.backup_value)}</span> },
                { id: 'collected', header: 'API collected', value: (c) => c.api_collected_at, cell: (c) => fmtDate(c.api_collected_at) },
              ]}
            />
          ) : tab === 'backup' ? (
            <RefTable rows={cmp.only_in_backup} />
          ) : (
            <RefTable rows={cmp.only_in_api} />
          )}
        </Card>
      ) : (
        imp.status === 'imported' && <Card><EmptyState>No comparison data available.</EmptyState></Card>
      )}
    </div>
  );
}
