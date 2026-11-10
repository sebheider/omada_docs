import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileText, GitBranch, History, Link2, Pencil, Plus, Trash2, UserRound } from 'lucide-react';
import { del, get, post, put } from '../api/client';
import { useEntities, useEntity, useManualMeta } from '../api/hooks';
import type { BaseEntity, Change, EntityDetail, ManualDescription, ManualDocument, Relationship, RelatedRef } from '../api/types';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { fmtDate, humanize, kindLabel } from '../lib/format';
import { objectPath } from '../lib/routes';
import { Markdown } from './Markdown';
import {
  Badge,
  Card,
  ConfirmDialog,
  type Crumb,
  EmptyState,
  ErrorBox,
  Field,
  MetaLine,
  Modal,
  PageHeader,
  SourceBadge,
  Spinner,
  StatusBadge,
} from './ui';

export function displayName(e: BaseEntity | null | undefined): string {
  if (!e) return '';
  return e.manual?.display_name || e.name || String(e.key);
}

export function ObjectLink({ type, id, children, deviceType }: { type: string; id: string | number; children: ReactNode; deviceType?: string | null }) {
  const to = objectPath(type, id, { deviceType });
  return to ? (
    <Link to={to} className="link">
      {children}
    </Link>
  ) : (
    <>{children}</>
  );
}

function invalidateObject(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ predicate: (q) => !['auth-state', 'sync-status', 'manual-meta', 'sites'].includes(String(q.queryKey[0])) });
}

/* ------------------------------------------------------------------ manual description */

function parseTags(s: string): string[] {
  return s
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

export function ManualCard({
  objectType,
  objectKey,
  siteId,
  manual,
  originalName,
}: {
  objectType: string;
  objectKey: string;
  siteId?: string | null;
  manual: ManualDescription | null;
  originalName?: string | null;
}) {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [form, setForm] = useState({ display_name: '', description: '', location: '', responsible: '', notes: '', tags: '' });
  const [preview, setPreview] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = () => {
    setForm({
      display_name: manual?.display_name ?? '',
      description: manual?.description ?? '',
      location: manual?.location ?? '',
      responsible: manual?.responsible ?? '',
      notes: manual?.notes ?? '',
      tags: (manual?.tags ?? []).join(', '),
    });
    setError(null);
    setPreview(false);
    setEditing(true);
  };

  const save = useMutation({
    mutationFn: () =>
      put<ManualDescription>(`manual/descriptions/${objectType}/${encodeURIComponent(objectKey)}`, {
        display_name: form.display_name || null,
        description: form.description || null,
        location: form.location || null,
        responsible: form.responsible || null,
        notes: form.notes || null,
        tags: parseTags(form.tags),
        site_id: siteId ?? null,
      }),
    onSuccess: () => {
      toast.success('Manual documentation saved');
      setEditing(false);
      invalidateObject(qc);
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });

  const remove = useMutation({
    mutationFn: () => del(`manual/descriptions/${objectType}/${encodeURIComponent(objectKey)}`),
    onSuccess: () => {
      toast.success('Manual documentation removed');
      setConfirm(false);
      invalidateObject(qc);
    },
    onError: (e) => {
      setConfirm(false);
      toast.error(e);
    },
  });

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => {
    const v = e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };

  return (
    <Card
      title="Manual documentation"
      icon={<UserRound className="h-4 w-4 text-brand-600 dark:text-brand-400" />}
      className="border-l-4 border-l-brand-500"
      actions={
        <>
          <SourceBadge source="manual" />
          {isAdmin && !editing && (
            <button className="btn-secondary py-1" onClick={start}>
              <Pencil className="h-3.5 w-3.5" /> {manual ? 'Edit' : 'Add'}
            </button>
          )}
          {isAdmin && !editing && manual && (
            <button className="btn-ghost py-1 text-red-600" onClick={() => setConfirm(true)} aria-label="Delete manual documentation">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </>
      }
    >
      {editing ? (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            setError(null);
            save.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Display name" hint={originalName ? `Controller name: ${originalName}` : undefined}>
              <input className="input" value={form.display_name} onChange={set('display_name')} maxLength={255} />
            </Field>
            <Field label="Tags" hint="Comma separated">
              <input className="input" value={form.tags} onChange={set('tags')} />
            </Field>
            <Field label="Location">
              <input className="input" value={form.location} onChange={set('location')} maxLength={255} />
            </Field>
            <Field label="Responsible">
              <input className="input" value={form.responsible} onChange={set('responsible')} maxLength={255} />
            </Field>
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="label mb-0">Description (Markdown)</span>
              <button type="button" className="text-xs link" onClick={() => setPreview((p) => !p)}>
                {preview ? 'Edit' : 'Preview'}
              </button>
            </div>
            {preview ? (
              <div className="min-h-[8rem] rounded-md border border-slate-200 p-3 dark:border-slate-700">
                <Markdown text={form.description} />
              </div>
            ) : (
              <textarea aria-label="Description (Markdown)" className="input min-h-[8rem] font-mono" value={form.description} onChange={set('description')} />
            )}
          </div>
          <Field label="Notes">
            <textarea className="input min-h-[4rem]" value={form.notes} onChange={set('notes')} />
          </Field>
          <p className="text-xs text-slate-500">Never store passwords, keys or other credentials here – the server rejects texts that look like secrets.</p>
          {error && <ErrorBox error={error} title="Could not save" />}
          <div className="flex gap-2">
            <button type="submit" className="btn-primary" disabled={save.isPending}>
              Save
            </button>
            <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : manual ? (
        <div className="space-y-3">
          {manual.display_name && (
            <div className="text-sm">
              <span className="label inline">Display name: </span>
              <span className="font-medium">{manual.display_name}</span>
            </div>
          )}
          {manual.description ? <Markdown text={manual.description} /> : <p className="text-sm italic text-slate-400">No description.</p>}
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            {manual.location && (
              <div>
                <dt className="label">Location</dt>
                <dd>{manual.location}</dd>
              </div>
            )}
            {manual.responsible && (
              <div>
                <dt className="label">Responsible</dt>
                <dd>{manual.responsible}</dd>
              </div>
            )}
          </dl>
          {manual.notes && (
            <div>
              <div className="label">Notes</div>
              <p className="whitespace-pre-wrap text-sm">{manual.notes}</p>
            </div>
          )}
          {manual.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {manual.tags.map((t) => (
                <Badge key={t} tone="brand">
                  #{t}
                </Badge>
              ))}
            </div>
          )}
          <p className="text-xs text-slate-500">
            Last edited {fmtDate(manual.updated_at)} {manual.updated_by && `by ${manual.updated_by}`}
          </p>
        </div>
      ) : (
        <EmptyState>
          No manual documentation yet.
          {isAdmin ? ' Use “Add” to describe purpose, location and responsibility.' : ''}
        </EmptyState>
      )}
      <ConfirmDialog
        open={confirm}
        title="Delete manual documentation"
        message="The manual description, location, responsible person, notes and tags of this object will be deleted."
        confirmLabel="Delete"
        danger
        busy={remove.isPending}
        onConfirm={() => remove.mutate()}
        onCancel={() => setConfirm(false)}
      />
    </Card>
  );
}

/* ------------------------------------------------------------------ object picker */

const PICKABLE = ['device', 'switch_port', 'network', 'wlan', 'client', 'acl_rule', 'nat_rule', 'wan', 'route', 'vpn', 'ip_group', 'port_profile', 'site', 'document'];

function EntityOptions({ kind, value, onChange }: { kind: string; value: string; onChange: (v: string) => void }) {
  const entities = useEntities(kind);
  if (entities.isLoading) return <select className="input" disabled><option>Loading…</option></select>;
  const items = [...(entities.data?.items ?? [])].sort((a, b) => displayName(a).localeCompare(displayName(b), undefined, { numeric: true }));
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} required>
      <option value="">Select…</option>
      {items.map((e) => (
        <option key={e.key} value={e.key}>
          {kind === 'switch_port' ? `${e.switch_name ?? ''} · ${displayName(e)}` : displayName(e)}
          {kind === 'network' && e.vlan_id ? ` (VLAN ${e.vlan_id})` : ''}
        </option>
      ))}
    </select>
  );
}

function DocumentOptions({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const docs = useQuery({ queryKey: ['documents', '', ''], queryFn: () => get<ManualDocument[]>('manual/documents') });
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} required>
      <option value="">Select…</option>
      {(docs.data ?? []).map((d) => (
        <option key={d.id} value={String(d.id)}>
          {d.title}
        </option>
      ))}
    </select>
  );
}

export function ObjectPicker({
  type,
  objectKey,
  onChange,
  types,
}: {
  type: string;
  objectKey: string;
  onChange: (type: string, key: string) => void;
  types?: string[];
}) {
  const meta = useManualMeta();
  const available = (types ?? PICKABLE).filter((t) => !meta.data || meta.data.object_types.includes(t));
  const extra = (meta.data?.object_types ?? []).filter((t) => !PICKABLE.includes(t) && !types);
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Object type">
        <select className="input" value={type} onChange={(e) => onChange(e.target.value, '')}>
          {[...available, ...extra].map((t) => (
            <option key={t} value={t}>
              {kindLabel(t)}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Object">
        {type === 'document' ? (
          <DocumentOptions value={objectKey} onChange={(k) => onChange(type, k)} />
        ) : PICKABLE.includes(type) ? (
          <EntityOptions kind={type} value={objectKey} onChange={(k) => onChange(type, k)} />
        ) : (
          <input className="input" value={objectKey} placeholder="Identifier / name" onChange={(e) => onChange(type, e.target.value)} required />
        )}
      </Field>
    </div>
  );
}

/* ------------------------------------------------------------------ relationships */

function RelationshipTarget({ r, selfType, selfKey }: { r: Relationship; selfType: string; selfKey: string }) {
  const outgoing = r.source_type === selfType && r.source_key === selfKey;
  const type = outgoing ? r.target_type : r.source_type;
  const key = outgoing ? r.target_key : r.source_key;
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <Badge tone="gray">{outgoing ? humanize(r.relation) : `${humanize(r.relation)} (incoming)`}</Badge>
      <span className="text-xs text-slate-500">{kindLabel(type)}</span>
      <ResolvedName type={type} id={key} />
    </span>
  );
}

function ResolvedName({ type, id }: { type: string; id: string }) {
  const known = PICKABLE.includes(type) && type !== 'document';
  const entity = useEntity(known ? type : '', known ? id : undefined);
  const doc = useQuery({
    queryKey: ['document', id],
    queryFn: () => get<ManualDocument>(`manual/documents/${id}`),
    enabled: type === 'document',
    retry: false,
  });
  const label = type === 'document' ? (doc.data?.title ?? `Document #${id}`) : entity.data ? displayName({ ...entity.data.entity, manual: entity.data.manual }) : id;
  return (
    <ObjectLink type={type} id={id} deviceType={entity.data?.entity.type as string | undefined}>
      {label}
    </ObjectLink>
  );
}

export function RelationshipsCard({ objectType, objectKey, relationships }: { objectType: string; objectKey: string; relationships: Relationship[] }) {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const meta = useManualMeta();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState({ type: 'device', key: '' });
  const [relation, setRelation] = useState('related');
  const [description, setDescription] = useState('');
  const [deleting, setDeleting] = useState<Relationship | null>(null);

  const add = useMutation({
    mutationFn: () =>
      post('manual/relationships', {
        source_type: objectType,
        source_key: objectKey,
        target_type: target.type,
        target_key: target.key,
        relation,
        description: description || null,
      }),
    onSuccess: () => {
      toast.success('Relationship added');
      setOpen(false);
      setTarget({ type: 'device', key: '' });
      setDescription('');
      invalidateObject(qc);
    },
    onError: (e) => toast.error(e),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`manual/relationships/${id}`),
    onSuccess: () => {
      toast.success('Relationship removed');
      setDeleting(null);
      invalidateObject(qc);
    },
    onError: (e) => toast.error(e),
  });

  return (
    <Card
      title="Manual relationships"
      icon={<Link2 className="h-4 w-4 text-brand-600 dark:text-brand-400" />}
      actions={
        isAdmin && (
          <button className="btn-secondary py-1" onClick={() => setOpen(true)}>
            <Plus className="h-3.5 w-3.5" /> Add
          </button>
        )
      }
    >
      {relationships.length === 0 ? (
        <EmptyState>No manual relationships.</EmptyState>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {relationships.map((r) => (
            <li key={r.id} className="flex items-start justify-between gap-2 py-2">
              <div className="min-w-0">
                <RelationshipTarget r={r} selfType={objectType} selfKey={objectKey} />
                {r.description && <p className="mt-0.5 text-xs text-slate-500">{r.description}</p>}
              </div>
              {isAdmin && (
                <button className="btn-ghost p-1 text-red-600" onClick={() => setDeleting(r)} aria-label="Remove relationship">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <Modal
        open={open}
        title="Add relationship"
        onClose={() => setOpen(false)}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button className="btn-primary" disabled={!target.key || add.isPending} onClick={() => add.mutate()}>
              Add relationship
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <Field label="Relation">
            <select className="input" value={relation} onChange={(e) => setRelation(e.target.value)}>
              {(meta.data?.relations ?? ['related']).map((r) => (
                <option key={r} value={r}>
                  {humanize(r)}
                </option>
              ))}
            </select>
          </Field>
          <ObjectPicker type={target.type} objectKey={target.key} onChange={(type, key) => setTarget({ type, key })} />
          <Field label="Description (optional)">
            <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
          </Field>
        </div>
      </Modal>
      <ConfirmDialog
        open={!!deleting}
        title="Remove relationship"
        message="The manual relationship will be removed."
        confirmLabel="Remove"
        danger
        busy={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onCancel={() => setDeleting(null)}
      />
    </Card>
  );
}

/* ------------------------------------------------------------------ related objects */

export function RelatedCard({ related }: { related: Record<string, RelatedRef[]> }) {
  const groups = Object.entries(related ?? {}).filter(([, v]) => v.length);
  return (
    <Card title="Related objects" icon={<GitBranch className="h-4 w-4 text-slate-500" />} subtitle="Derived automatically from the controller data">
      {groups.length === 0 ? (
        <EmptyState>No related objects found.</EmptyState>
      ) : (
        <div className="space-y-4">
          {groups.map(([label, items]) => (
            <div key={label}>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                {humanize(label)} <span className="font-normal">({items.length})</span>
              </h3>
              <ul className="space-y-1 text-sm">
                {items.slice(0, 50).map((i) => (
                  <li key={`${i.object_type}:${i.object_key}`} className="flex flex-wrap items-baseline gap-x-2">
                    <ObjectLink type={i.object_type} id={i.object_key}>
                      {i.name ?? i.object_key}
                    </ObjectLink>
                    {i.detail && <span className="text-xs text-slate-500">{i.detail}</span>}
                  </li>
                ))}
                {items.length > 50 && <li className="text-xs text-slate-500">… and {items.length - 50} more</li>}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ change history */

export function ChangeValue({ v }: { v: string | null }) {
  if (v === null || v === undefined || v === '') return <span className="text-slate-400">—</span>;
  return <span className="break-all font-mono text-xs">{v.length > 300 ? `${v.slice(0, 300)}…` : v}</span>;
}

export function ChangesCard({ changes }: { changes: Change[] }) {
  return (
    <Card title="Change history" icon={<History className="h-4 w-4 text-slate-500" />} bodyClassName="p-0">
      {changes.length === 0 ? (
        <EmptyState>No recorded changes for this object.</EmptyState>
      ) : (
        <div className="max-h-96 overflow-auto">
          <table className="table-base">
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Field</th>
                <th>Before</th>
                <th>After</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {changes.map((c, i) => (
                <tr key={c.id ?? i}>
                  <td className="whitespace-nowrap">{fmtDate(c.ts)}</td>
                  <td>
                    <span className="flex gap-1">
                      <StatusBadge status={c.change_type} />
                      <Badge tone={c.kind === 'manual' ? 'brand' : 'gray'}>{c.kind === 'manual' ? 'manual' : 'config'}</Badge>
                    </span>
                  </td>
                  <td>{c.field ?? '—'}</td>
                  <td>
                    <ChangeValue v={c.before} />
                  </td>
                  <td>
                    <ChangeValue v={c.after} />
                  </td>
                  <td>{c.username ?? (c.kind === 'config' ? 'sync' : '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ detail page shell */

export function DetailShell<T extends BaseEntity>({
  kind,
  objectKey,
  crumbs,
  icon,
  subtitle,
  actions,
  children,
  aside,
}: {
  kind: string;
  objectKey: string | undefined;
  crumbs: Crumb[] | ((d: EntityDetail<T>) => Crumb[]);
  icon?: ReactNode;
  subtitle?: (d: EntityDetail<T>) => ReactNode;
  actions?: (d: EntityDetail<T>) => ReactNode;
  children: (d: EntityDetail<T>) => ReactNode;
  aside?: (d: EntityDetail<T>) => ReactNode;
}) {
  const q = useEntity<T>(kind, objectKey);
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data)
    return (
      <>
        <PageHeader title={kindLabel(kind)} crumbs={typeof crumbs === 'function' ? [] : crumbs} />
        <ErrorBox error={q.error ?? 'Object not found'} title="Object could not be loaded" />
      </>
    );
  const d = q.data;
  const e = d.entity;
  const technical = e.name || String(e.key);
  const manualName = d.manual?.display_name;
  return (
    <div>
      <PageHeader
        crumbs={[...(typeof crumbs === 'function' ? crumbs(d) : crumbs), { label: manualName || technical }]}
        icon={icon}
        title={manualName || technical}
        subtitle={
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="gray">{kindLabel(kind)}</Badge>
              {manualName && manualName !== technical && (
                <span>
                  Controller name: <span className="font-medium text-slate-700 dark:text-slate-300">{technical}</span>
                </span>
              )}
              {subtitle?.(d)}
            </div>
            <MetaLine meta={e._meta} />
          </div>
        }
        actions={actions?.(d)}
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">{children(d)}</div>
        <div className="space-y-4">
          <ManualCard objectType={kind} objectKey={String(e.key)} siteId={e.site_id} manual={d.manual} originalName={technical} />
          {aside?.(d)}
          <RelatedCard related={d.related} />
          <RelationshipsCard objectType={kind} objectKey={String(e.key)} relationships={d.relationships} />
        </div>
      </div>
      <div className="mt-4">
        <ChangesCard changes={d.changes} />
      </div>
    </div>
  );
}

/** Generic property card: lists all remaining scalar/array fields of an entity. */
export function RawPropertiesCard({ entity, exclude = [] }: { entity: BaseEntity; exclude?: string[] }) {
  const skip = new Set(['kind', 'key', '_meta', 'manual', 'site_id', ...exclude]);
  const entries = Object.entries(entity).filter(([k]) => !skip.has(k));
  return (
    <Card title="All technical properties" icon={<FileText className="h-4 w-4 text-slate-500" />} subtitle="As collected from the controller" bodyClassName="p-0">
      <details>
        <summary className="cursor-pointer px-4 py-2 text-sm text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200">
          Show {entries.length} fields
        </summary>
        <table className="table-base">
          <tbody>
            {entries.map(([k, v]) => (
              <tr key={k}>
                <td className="w-1/3 font-medium text-slate-500">{humanize(k)}</td>
                <td>
                  {v === null || v === undefined || v === '' ? (
                    <span className="italic text-slate-400">not available</span>
                  ) : typeof v === 'object' ? (
                    <pre className="whitespace-pre-wrap break-all font-mono text-xs">{JSON.stringify(v, null, 1)}</pre>
                  ) : (
                    <span className="break-all">{String(v)}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </Card>
  );
}
