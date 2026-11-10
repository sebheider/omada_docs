import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ClipboardCheck, Download, FileDown, KeyRound, Moon, Plug, Save, Settings as SettingsIcon, Sun, Trash2, Upload, UserPlus, XCircle } from 'lucide-react';
import { del, downloadFile, get, patch, post, put, upload } from '../api/client';
import type { AuditEntry, ControllerSettings, Paged, Role, User } from '../api/types';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useToast } from '../context/ToastContext';
import { Badge, Card, ConfirmDialog, ErrorBox, Field, KeyValue, Modal, PageHeader, Pager, Spinner, Tabs } from '../components/ui';
import { fmtDate, fmtValue, humanize } from '../lib/format';

type Tab = 'general' | 'controller' | 'users' | 'backup' | 'audit';

const INTERVAL_LABELS: Record<string, string> = { manual: 'Manual only', '5m': 'Every 5 minutes', '15m': 'Every 15 minutes', '30m': 'Every 30 minutes', '1h': 'Every hour', '1d': 'Daily' };

/* ------------------------------------------------------------------ general */

function PasswordCard() {
  const { user } = useAuth();
  const toast = useToast();
  const [cur, setCur] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: () => post('auth/password', { current_password: cur, new_password: pw }),
    onSuccess: () => {
      toast.success('Password changed. Other sessions were signed out.');
      setCur('');
      setPw('');
      setPw2('');
    },
    onError: (e) => setErr(e instanceof Error ? e.message : String(e)),
  });
  if (user?.auth_source !== 'local') {
    return (
      <Card title="Password" icon={<KeyRound className="h-4 w-4 text-slate-500" />}>
        <p className="text-sm text-slate-500">Your account is authenticated by the reverse proxy and has no local password.</p>
      </Card>
    );
  }
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (pw.length < 10) return setErr('The new password must be at least 10 characters long.');
    if (pw !== pw2) return setErr('The passwords do not match.');
    m.mutate();
  };
  return (
    <Card title="Change password" icon={<KeyRound className="h-4 w-4 text-slate-500" />}>
      <form className="space-y-3" onSubmit={submit}>
        <Field label="Current password">
          <input className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required />
        </Field>
        <Field label="New password" hint="At least 10 characters">
          <input className="input" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} required />
        </Field>
        <Field label="Repeat new password">
          <input className="input" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} required />
        </Field>
        {err && <p className="text-sm text-red-600 dark:text-red-400">{err}</p>}
        <button className="btn-primary" disabled={m.isPending}>
          <Save className="h-4 w-4" /> Change password
        </button>
      </form>
    </Card>
  );
}

function GeneralTab() {
  const { theme, setTheme } = useTheme();
  const { state, user } = useAuth();
  const toast = useToast();
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="Appearance">
          <div className="flex gap-2">
            <button className={theme === 'light' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTheme('light')}>
              <Sun className="h-4 w-4" /> Light
            </button>
            <button className={theme === 'dark' ? 'btn-primary' : 'btn-secondary'} onClick={() => setTheme('dark')}>
              <Moon className="h-4 w-4" /> Dark
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-500">Stored in this browser.</p>
        </Card>
        <Card title="Documentation & data">
          <ul className="space-y-2 text-sm">
            <li>
              <Link to="/export" className="link inline-flex items-center gap-1.5">
                <FileDown className="h-4 w-4" /> Export documentation (PDF, Word, HTML, CSV)
              </Link>
            </li>
            <li>
              <Link to="/quality" className="link inline-flex items-center gap-1.5">
                <ClipboardCheck className="h-4 w-4" /> Data quality report
              </Link>
            </li>
            <li>
              <button
                className="link inline-flex items-center gap-1.5"
                onClick={() => downloadFile('dataset/export', undefined, 'omada-dataset.json').catch((e: unknown) => toast.error(e))}
              >
                <Download className="h-4 w-4" /> Download technical dataset (JSON)
              </button>
            </li>
          </ul>
        </Card>
        <Card title="About">
          <KeyValue
            items={[
              { label: 'Application', value: 'Omada Network Documentation' },
              { label: 'Version', value: state?.version },
              { label: 'Mode', value: state?.demo_mode ? <Badge tone="violet">Demo mode</Badge> : 'Production' },
              { label: 'Authentication', value: humanize(state?.auth_mode ?? '') },
              { label: 'Signed in as', value: user ? `${user.username} (${user.role})` : null },
              { label: 'Last login', value: user?.last_login ? fmtDate(user.last_login) : null },
            ]}
          />
          <p className="mt-3 text-xs text-slate-500">Data from the Omada controller is read-only. The application never changes the controller configuration.</p>
        </Card>
      </div>
      <PasswordCard />
    </div>
  );
}

/* ------------------------------------------------------------------ controller */

type CtrlForm = Omit<ControllerSettings, 'client_secret_set' | 'configured' | 'sync_intervals' | 'demo_mode' | 'next_run'> & { client_secret: string; site_ids_text: string };

function ControllerTab() {
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['controller-settings'], queryFn: () => get<ControllerSettings>('settings/controller') });
  const [form, setForm] = useState<CtrlForm | null>(null);
  const [test, setTest] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    if (q.data) {
      const { client_secret_set: _a, configured: _b, sync_intervals: _c, demo_mode: _d, next_run: _e, ...rest } = q.data;
      setForm({ ...rest, client_secret: '', site_ids_text: (q.data.site_ids ?? []).join(', ') });
    }
  }, [q.data]);
  const save = useMutation({
    mutationFn: (f: CtrlForm) => {
      const { site_ids_text, ...body } = f;
      return put<ControllerSettings>('settings/controller', {
        ...body,
        client_secret: f.client_secret || null,
        site_ids: site_ids_text
          .split(/[\s,]+/)
          .map((s) => s.trim())
          .filter(Boolean),
      });
    },
    onSuccess: () => {
      toast.success('Controller settings saved.');
      void qc.invalidateQueries({ queryKey: ['controller-settings'] });
      void qc.invalidateQueries({ queryKey: ['sync-status'] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (e) => toast.error(e),
  });
  const testM = useMutation({
    mutationFn: () => post<Record<string, unknown>>('settings/controller/test'),
    onSuccess: (r) => setTest(r),
    onError: (e) => setTest({ ok: false, error: e instanceof Error ? e.message : String(e) }),
  });
  if (q.isLoading || (!form && !q.error)) return <Spinner />;
  if (q.error || !q.data || !form) return <ErrorBox error={q.error} />;
  const set = <K extends keyof CtrlForm>(k: K, v: CtrlForm[K]) => setForm({ ...form, [k]: v });
  const intervals = q.data.sync_intervals ?? Object.keys(INTERVAL_LABELS);
  const sites = Array.isArray(test?.sites) ? (test.sites as { id?: string; name?: string }[]) : [];
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card title="Omada controller connection (Open API)" className="lg:col-span-2" icon={<Plug className="h-4 w-4 text-slate-500" />}>
        {q.data.demo_mode && (
          <p className="mb-3 rounded-md bg-violet-50 p-2 text-sm text-violet-800 dark:bg-violet-950/40 dark:text-violet-200">
            Demo mode is active – synchronisation uses built-in sample data instead of a real controller.
          </p>
        )}
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(form);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-[7rem_1fr_7rem]">
            <Field label="Scheme">
              <select className="input" value={form.scheme} onChange={(e) => set('scheme', e.target.value as 'https' | 'http')}>
                <option value="https">https</option>
                <option value="http">http</option>
              </select>
            </Field>
            <Field label="Host / IP" hint="A full URL can be pasted as well">
              <input className="input" value={form.host} onChange={(e) => set('host', e.target.value)} placeholder="omada.example.lan" />
            </Field>
            <Field label="Port">
              <input className="input" type="number" min={1} max={65535} value={form.port} onChange={(e) => set('port', Number(e.target.value))} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Omada ID (omadacId)">
              <input className="input font-mono" value={form.omadac_id} onChange={(e) => set('omadac_id', e.target.value)} />
            </Field>
            <Field label="API version">
              <select className="input" value={form.api_version} onChange={() => set('api_version', 'v1')}>
                <option value="v1">v1 (Open API)</option>
              </select>
            </Field>
            <Field label="Client ID">
              <input className="input font-mono" value={form.client_id} onChange={(e) => set('client_id', e.target.value)} autoComplete="off" />
            </Field>
            <Field label="Client secret" hint={q.data.client_secret_set ? 'A secret is stored. Leave empty to keep it.' : 'Stored encrypted, never displayed again.'}>
              <input
                className="input font-mono"
                type="password"
                autoComplete="new-password"
                value={form.client_secret}
                placeholder={q.data.client_secret_set ? '••• stored' : ''}
                onChange={(e) => set('client_secret', e.target.value)}
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.verify_ssl} onChange={(e) => set('verify_ssl', e.target.checked)} /> Verify TLS certificate
          </label>
          {!form.verify_ssl && <p className="text-xs text-amber-700 dark:text-amber-400">Certificate verification is disabled – only use this for self-signed certificates in trusted networks.</p>}
          <Field label="Sites to synchronise" hint="Comma-separated site IDs. Leave empty to synchronise all sites.">
            <input className="input font-mono" value={form.site_ids_text} onChange={(e) => set('site_ids_text', e.target.value)} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Sync interval">
              <select className="input" value={form.sync_interval} onChange={(e) => set('sync_interval', e.target.value)}>
                {intervals.map((i) => (
                  <option key={i} value={i}>
                    {INTERVAL_LABELS[i] ?? i}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Request timeout (s)">
              <input className="input" type="number" min={2} max={300} step="any" value={form.request_timeout} onChange={(e) => set('request_timeout', Number(e.target.value))} />
            </Field>
            <Field label="Max requests / s">
              <input className="input" type="number" min={0.2} max={50} step="any" value={form.max_requests_per_second} onChange={(e) => set('max_requests_per_second', Number(e.target.value))} />
            </Field>
            <Field label="Snapshots to keep">
              <input className="input" type="number" min={5} max={5000} value={form.snapshot_retention} onChange={(e) => set('snapshot_retention', Number(e.target.value))} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" disabled={save.isPending}>
              <Save className="h-4 w-4" /> {save.isPending ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="btn-secondary" disabled={testM.isPending} onClick={() => testM.mutate()}>
              <Plug className="h-4 w-4" /> {testM.isPending ? 'Testing…' : 'Test connection'}
            </button>
          </div>
          <p className="text-xs text-slate-500">Save before testing – the test uses the stored settings. Next scheduled run: {q.data.next_run ? fmtDate(q.data.next_run) : 'none'}.</p>
        </form>
      </Card>
      <div className="space-y-4">
        <Card title="Connection test">
          {!test ? (
            <p className="text-sm text-slate-500">Run a test to verify address, credentials and permissions.</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-2 font-semibold">
                {test.ok ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <XCircle className="h-5 w-5 text-red-600" />}
                {test.ok ? 'Connection successful' : 'Connection failed'}
              </div>
              <KeyValue
                cols={1}
                items={Object.entries(test)
                  .filter(([k]) => k !== 'ok' && k !== 'sites')
                  .map(([k, v]) => ({ label: humanize(k), value: k === 'duration_ms' ? `${String(v)} ms` : fmtValue(v) }))}
              />
              {sites.length > 0 && (
                <div>
                  <div className="label">Sites ({sites.length})</div>
                  <ul className="space-y-0.5">
                    {sites.map((s, i) => (
                      <li key={s.id ?? i}>
                        {s.name} <span className="font-mono text-xs text-slate-500">{s.id}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </Card>
        <Card title="Required permissions">
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Create an Open API application in the Omada controller (Settings → Platform Integration) in <em>client credentials</em> mode with a <strong>read-only</strong>{' '}
            (viewer) role for the sites to document.
          </p>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ users */

function UsersTab() {
  const { user: me } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['users'], queryFn: () => get<User[]>('users') });
  const [creating, setCreating] = useState(false);
  const [pwFor, setPwFor] = useState<User | null>(null);
  const [delUser, setDelUser] = useState<User | null>(null);
  const [nu, setNu] = useState({ username: '', password: '', role: 'viewer' as Role });
  const [newPw, setNewPw] = useState('');
  const refresh = () => void qc.invalidateQueries({ queryKey: ['users'] });
  const create = useMutation({
    mutationFn: () => post<User>('users', nu),
    onSuccess: () => {
      toast.success('User created.');
      setCreating(false);
      setNu({ username: '', password: '', role: 'viewer' });
      refresh();
    },
    onError: (e) => toast.error(e),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) => patch<User>(`users/${id}`, body),
    onSuccess: () => {
      toast.success('User updated.');
      setPwFor(null);
      setNewPw('');
      refresh();
    },
    onError: (e) => toast.error(e),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`users/${id}`),
    onSuccess: () => {
      toast.success('User deleted.');
      setDelUser(null);
      refresh();
    },
    onError: (e) => toast.error(e),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={q.error} />;
  return (
    <>
      <Card
        title="Users"
        actions={
          <button className="btn-primary" onClick={() => setCreating(true)}>
            <UserPlus className="h-4 w-4" /> Add user
          </button>
        }
        bodyClassName="p-0"
      >
        <div className="overflow-x-auto">
          <table className="table-base">
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Source</th>
                <th>Status</th>
                <th>Created</th>
                <th>Last login</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((u) => (
                <tr key={u.id}>
                  <td className="font-medium">
                    {u.username} {u.id === me?.id && <Badge tone="brand">you</Badge>}
                  </td>
                  <td>
                    <select
                      className="input w-28 py-1"
                      value={u.role}
                      disabled={u.id === me?.id}
                      onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value } })}
                      aria-label={`Role of ${u.username}`}
                    >
                      <option value="admin">Admin</option>
                      <option value="viewer">Viewer</option>
                    </select>
                  </td>
                  <td>{u.auth_source}</td>
                  <td>
                    <Badge tone={u.is_active ? 'green' : 'gray'}>{u.is_active ? 'Active' : 'Disabled'}</Badge>
                  </td>
                  <td className="whitespace-nowrap">{fmtDate(u.created_at)}</td>
                  <td className="whitespace-nowrap">{u.last_login ? fmtDate(u.last_login) : '—'}</td>
                  <td>
                    <div className="flex justify-end gap-1">
                      {u.auth_source === 'local' && (
                        <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setPwFor(u)}>
                          Set password
                        </button>
                      )}
                      {u.id !== me?.id && (
                        <>
                          <button className="btn-ghost px-2 py-1 text-xs" onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                            {u.is_active ? 'Disable' : 'Enable'}
                          </button>
                          <button className="btn-ghost px-2 py-1 text-xs text-red-600" onClick={() => setDelUser(u)} aria-label={`Delete ${u.username}`}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="px-4 py-2 text-xs text-slate-500">Admins can edit documentation, settings, run synchronisations and manage users. Viewers have read-only access.</p>
      </Card>
      <Modal
        open={creating}
        title="Add user"
        onClose={() => setCreating(false)}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setCreating(false)}>
              Cancel
            </button>
            <button className="btn-primary" disabled={create.isPending || !nu.username || nu.password.length < 10} onClick={() => create.mutate()}>
              Create
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Username" hint="Letters, digits and . _ @ -">
            <input className="input" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} autoComplete="off" />
          </Field>
          <Field label="Password" hint="At least 10 characters">
            <input className="input" type="password" autoComplete="new-password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} />
          </Field>
          <Field label="Role">
            <select className="input" value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value as Role })}>
              <option value="viewer">Viewer (read-only)</option>
              <option value="admin">Admin</option>
            </select>
          </Field>
        </div>
      </Modal>
      <Modal
        open={!!pwFor}
        title={`Set password for ${pwFor?.username ?? ''}`}
        onClose={() => setPwFor(null)}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setPwFor(null)}>
              Cancel
            </button>
            <button className="btn-primary" disabled={newPw.length < 10 || update.isPending} onClick={() => pwFor && update.mutate({ id: pwFor.id, body: { password: newPw } })}>
              Save
            </button>
          </>
        }
      >
        <Field label="New password" hint="At least 10 characters">
          <input className="input" type="password" autoComplete="new-password" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
        </Field>
      </Modal>
      <ConfirmDialog
        open={!!delUser}
        title="Delete user"
        message={`Delete the user “${delUser?.username ?? ''}”? This cannot be undone.`}
        confirmLabel="Delete"
        danger
        onCancel={() => setDelUser(null)}
        onConfirm={() => delUser && remove.mutate(delUser.id)}
      />
    </>
  );
}

/* ------------------------------------------------------------------ backup */

function BackupTab() {
  const toast = useToast();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const restore = useMutation({
    mutationFn: (f: File) => upload<Record<string, unknown>>('backup/restore', f),
    onSuccess: () => {
      toast.success('Application backup restored. Reloading…');
      setConfirm(false);
      void qc.invalidateQueries();
      window.setTimeout(() => window.location.reload(), 1200);
    },
    onError: (e) => {
      setConfirm(false);
      toast.error(e);
    },
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Download application backup" icon={<Download className="h-4 w-4 text-slate-500" />}>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          A ZIP archive with the database (manual documentation, history, snapshots, settings, users) and all attachments. Store it securely – it contains the encrypted controller
          credentials.
        </p>
        <button
          className="btn-primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await downloadFile('backup/app', undefined, 'omada-docs-backup.zip');
            } catch (e) {
              toast.error(e);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Download className="h-4 w-4" /> {busy ? 'Creating…' : 'Download backup'}
        </button>
      </Card>
      <Card title="Restore application backup" icon={<Upload className="h-4 w-4 text-slate-500" />}>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          Replaces <strong>all</strong> current data of this application with the content of the backup archive. Controller configuration is not affected.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input ref={fileRef} type="file" accept=".zip,application/zip" className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm dark:file:bg-slate-800 dark:file:text-slate-200" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button className="btn-danger" disabled={!file || restore.isPending} onClick={() => setConfirm(true)}>
            <Upload className="h-4 w-4" /> {restore.isPending ? 'Restoring…' : 'Restore'}
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          To import an Omada <em>controller</em> backup instead, use{' '}
          <Link className="link" to="/sync?tab=backup">
            Synchronization → Backup import
          </Link>
          .
        </p>
      </Card>
      <ConfirmDialog
        open={confirm}
        title="Restore application backup?"
        message={`All current data will be replaced by the backup “${file?.name ?? ''}”. This cannot be undone. Continue?`}
        confirmLabel="Restore"
        danger
        onCancel={() => setConfirm(false)}
        onConfirm={() => file && restore.mutate(file)}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ audit */

const AUDIT_LIMIT = 50;

function AuditTab() {
  const [offset, setOffset] = useState(0);
  const [action, setAction] = useState('');
  const q = useQuery({
    queryKey: ['audit', offset, action],
    queryFn: () => get<Paged<AuditEntry>>('audit', { limit: AUDIT_LIMIT, offset, action: action || null }),
    placeholderData: keepPreviousData,
  });
  return (
    <Card
      title="Audit log"
      actions={
        <select
          className="input w-48 py-1"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setOffset(0);
          }}
          aria-label="Filter by action"
        >
          <option value="">All actions</option>
          <option value="auth">Authentication</option>
          <option value="user">User management</option>
          <option value="settings">Settings</option>
          <option value="sync">Synchronisation</option>
          <option value="manual">Manual documentation</option>
          <option value="backup">Backups</option>
          <option value="export">Exports</option>
        </select>
      }
      bodyClassName="p-0"
    >
      {q.isLoading ? (
        <Spinner />
      ) : q.error || !q.data ? (
        <ErrorBox error={q.error} />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Action</th>
                  <th>Object</th>
                  <th>Details</th>
                  <th>IP</th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((a) => (
                  <tr key={a.id}>
                    <td className="whitespace-nowrap">{fmtDate(a.ts, true)}</td>
                    <td>{a.username ?? '—'}</td>
                    <td>
                      <Badge tone={a.action.includes('fail') ? 'red' : 'gray'}>{a.action}</Badge>
                    </td>
                    <td>{a.object_type ? `${a.object_type}${a.object_key ? `: ${a.object_key}` : ''}` : '—'}</td>
                    <td className="max-w-md truncate font-mono text-xs" title={a.details ? JSON.stringify(a.details) : undefined}>
                      {a.details ? JSON.stringify(a.details) : ''}
                    </td>
                    <td className="font-mono text-xs">{a.ip ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={q.data.total} offset={offset} limit={AUDIT_LIMIT} onChange={setOffset} />
        </>
      )}
    </Card>
  );
}

export function SettingsPage() {
  const { isAdmin } = useAuth();
  const [params, setParams] = useSearchParams();
  const requested = (params.get('tab') as Tab) || 'general';
  const tab: Tab = !isAdmin ? 'general' : requested;
  const tabs: { id: Tab; label: string }[] = [{ id: 'general', label: 'General' }];
  if (isAdmin)
    tabs.push({ id: 'controller', label: 'Controller' }, { id: 'users', label: 'Users' }, { id: 'backup', label: 'Application backup' }, { id: 'audit', label: 'Audit log' });
  return (
    <div>
      <PageHeader title="Settings" icon={<SettingsIcon className="h-5 w-5 text-brand-600" />} crumbs={[{ label: 'Settings' }]} />
      <Tabs<Tab> active={tab} onChange={(t) => setParams(t === 'general' ? {} : { tab: t }, { replace: true })} tabs={tabs} />
      {tab === 'general' ? <GeneralTab /> : tab === 'controller' ? <ControllerTab /> : tab === 'users' ? <UsersTab /> : tab === 'backup' ? <BackupTab /> : <AuditTab />}
    </div>
  );
}
