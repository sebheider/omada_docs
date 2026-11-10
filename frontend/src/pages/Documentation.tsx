import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Download, Eye, FileText, Paperclip, Pencil, Plus, Save, Trash2, Upload, X } from 'lucide-react';
import { apiUrl, del, downloadFile, get, post, put, upload } from '../api/client';
import { useManualMeta } from '../api/hooks';
import type { Attachment, ManualDescription, ManualDocument } from '../api/types';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { DataTable } from '../components/DataTable';
import { ObjectPicker, RelationshipsCard } from '../components/detail';
import { Markdown } from '../components/Markdown';
import { Badge, Card, ConfirmDialog, cx, EmptyState, ErrorBox, Field, PageHeader, Spinner, Tabs } from '../components/ui';
import { fmtBytes, fmtDate, humanize, kindLabel } from '../lib/format';
import { objectPath } from '../lib/routes';

type Tab = 'documents' | 'descriptions';

const PREVIEWABLE = /^(image\/(png|jpeg|gif|webp)|application\/pdf)$/;

export function categoryLabel(c: string): string {
  return humanize(c);
}

function DocumentsList() {
  const { isAdmin } = useAuth();
  const meta = useManualMeta();
  const [params, setParams] = useSearchParams();
  const category = params.get('category') ?? '';
  const q = params.get('q') ?? '';
  const [text, setText] = useState(q);
  const docs = useQuery({ queryKey: ['documents', category, q], queryFn: () => get<ManualDocument[]>('manual/documents', { category: category || null, q: q || null }) });
  const update = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            update('q', text.trim());
          }}
        >
          <input className="input w-64" placeholder="Search title, text, tags…" value={text} onChange={(e) => setText(e.target.value)} aria-label="Search documents" />
          <button className="btn-secondary">Search</button>
        </form>
        <select className="input w-56" value={category} onChange={(e) => update('category', e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {(meta.data?.document_categories ?? []).map((c) => (
            <option key={c} value={c}>
              {categoryLabel(c)}
            </option>
          ))}
        </select>
        {isAdmin && (
          <Link to="/documentation/new" className="btn-primary ml-auto">
            <Plus className="h-4 w-4" /> New document
          </Link>
        )}
      </div>
      {docs.isLoading ? (
        <Spinner />
      ) : docs.error || !docs.data ? (
        <ErrorBox error={docs.error} />
      ) : docs.data.length === 0 ? (
        <Card>
          <EmptyState icon={<BookOpen className="h-8 w-8" />}>{q || category ? 'No documents match the filter.' : 'No documents yet. Create the first one to document architecture, cabling, procedures or emergency plans.'}</EmptyState>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {docs.data.map((d) => (
            <Link key={d.id} to={`/documentation/${d.id}`} className="card block p-4 transition-colors hover:border-brand-400">
              <div className="flex items-start gap-2">
                <FileText className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />
                <div className="min-w-0">
                  <div className="truncate font-semibold text-slate-900 dark:text-white">{d.title}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <Badge tone="brand">{categoryLabel(d.category)}</Badge>
                    {d.tags.map((t) => (
                      <Badge key={t} tone="gray">
                        #{t}
                      </Badge>
                    ))}
                  </div>
                  <div className="mt-2 text-xs text-slate-500">
                    Updated {fmtDate(d.updated_at)} {d.updated_by && `by ${d.updated_by}`}
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function DescriptionsList() {
  const q = useQuery({ queryKey: ['descriptions'], queryFn: () => get<ManualDescription[]>('manual/descriptions') });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={q.error} />;
  return (
    <DataTable<ManualDescription>
      rows={q.data}
      rowKey={(d) => `${d.object_type}:${d.object_key}`}
      rowHref={(d) => objectPath(d.object_type, d.object_key)}
      initialSort={{ id: 'updated', dir: 'desc' }}
      emptyText="No object has a manual description yet. Open any object (device, network, port…) to document it."
      columns={[
        { id: 'type', header: 'Object type', value: (d) => kindLabel(d.object_type), filter: true },
        { id: 'name', header: 'Display name', value: (d) => d.display_name ?? d.object_key, cell: (d) => <span className="font-medium">{d.display_name ?? <span className="font-mono text-xs">{d.object_key}</span>}</span> },
        { id: 'desc', header: 'Description', value: (d) => d.description ?? '', className: 'max-w-md truncate' },
        { id: 'location', header: 'Location', value: (d) => d.location },
        { id: 'responsible', header: 'Responsible', value: (d) => d.responsible },
        { id: 'tags', header: 'Tags', value: (d) => d.tags, cell: (d) => <span className="flex flex-wrap gap-1">{d.tags.map((t) => <Badge key={t} tone="gray">#{t}</Badge>)}</span> },
        { id: 'updated', header: 'Updated', value: (d) => d.updated_at, cell: (d) => <span className="whitespace-nowrap">{fmtDate(d.updated_at)}</span> },
      ]}
    />
  );
}

export function DocumentationPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab) || 'documents';
  return (
    <div>
      <PageHeader title="Documentation" icon={<BookOpen className="h-5 w-5 text-brand-600" />} crumbs={[{ label: 'Documentation' }]} subtitle="Manual documentation: free documents with attachments, and descriptions of individual objects" />
      <Tabs<Tab>
        active={tab}
        onChange={(t) => setParams(t === 'documents' ? {} : { tab: t }, { replace: true })}
        tabs={[
          { id: 'documents', label: 'Documents' },
          { id: 'descriptions', label: 'Object descriptions' },
        ]}
      />
      {tab === 'documents' ? <DocumentsList /> : <DescriptionsList />}
    </div>
  );
}

function AttachmentsCard({ doc }: { doc: ManualDocument }) {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const meta = useManualMeta();
  const fileRef = useRef<HTMLInputElement>(null);
  const [deleting, setDeleting] = useState<Attachment | null>(null);
  const up = useMutation({
    mutationFn: (f: File) => upload<Attachment>(`manual/documents/${doc.id}/attachments`, f),
    onSuccess: () => {
      toast.success('Attachment uploaded.');
      if (fileRef.current) fileRef.current.value = '';
      void qc.invalidateQueries({ queryKey: ['document', String(doc.id)] });
    },
    onError: (e) => toast.error(e),
  });
  const rm = useMutation({
    mutationFn: (id: number) => del(`manual/attachments/${id}`),
    onSuccess: () => {
      toast.success('Attachment deleted.');
      setDeleting(null);
      void qc.invalidateQueries({ queryKey: ['document', String(doc.id)] });
    },
    onError: (e) => toast.error(e),
  });
  const atts = doc.attachments ?? [];
  return (
    <Card
      title="Attachments"
      icon={<Paperclip className="h-4 w-4 text-slate-500" />}
      actions={
        isAdmin && (
          <>
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              accept={(meta.data?.attachment_types ?? []).map((t) => `.${t}`).join(',') || undefined}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) up.mutate(f);
              }}
            />
            <button className="btn-secondary py-1" disabled={up.isPending} onClick={() => fileRef.current?.click()}>
              <Upload className="h-3.5 w-3.5" /> {up.isPending ? 'Uploading…' : 'Upload'}
            </button>
          </>
        )
      }
    >
      {atts.length === 0 ? (
        <EmptyState>No attachments.</EmptyState>
      ) : (
        <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {atts.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="truncate font-medium" title={a.filename}>
                  {a.filename}
                </div>
                <div className="text-xs text-slate-500">
                  {fmtBytes(a.size)} · {fmtDate(a.uploaded_at)}
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                {PREVIEWABLE.test(a.content_type) && (
                  <a className="btn-ghost p-1" href={apiUrl(`manual/attachments/${a.id}`, { inline: true })} target="_blank" rel="noopener noreferrer" title="Preview" aria-label={`Preview ${a.filename}`}>
                    <Eye className="h-4 w-4" />
                  </a>
                )}
                <button className="btn-ghost p-1" title="Download" aria-label={`Download ${a.filename}`} onClick={() => downloadFile(`manual/attachments/${a.id}`, undefined, a.filename).catch((e: unknown) => toast.error(e))}>
                  <Download className="h-4 w-4" />
                </button>
                {isAdmin && (
                  <button className="btn-ghost p-1 text-red-600" title="Delete" aria-label={`Delete ${a.filename}`} onClick={() => setDeleting(a)}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {meta.data && isAdmin && <p className="mt-2 text-xs text-slate-500">Allowed: {meta.data.attachment_types.join(', ')}</p>}
      <ConfirmDialog
        open={!!deleting}
        title="Delete attachment"
        message={`Delete “${deleting?.filename ?? ''}”?`}
        confirmLabel="Delete"
        danger
        busy={rm.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleting && rm.mutate(deleting.id)}
      />
    </Card>
  );
}

function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: ['document', id],
    queryFn: () => get<ManualDocument>(`manual/documents/${encodeURIComponent(id ?? '')}`),
    enabled: !!id && id !== 'new',
  });
}

export function DocumentViewPage() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const q = useDocument(id);
  const [confirm, setConfirm] = useState(false);
  const rm = useMutation({
    mutationFn: () => del(`manual/documents/${id}`),
    onSuccess: () => {
      toast.success('Document deleted.');
      void qc.invalidateQueries({ queryKey: ['documents'] });
      navigate('/documentation');
    },
    onError: (e) => toast.error(e),
  });
  const crumbs = [{ label: 'Documentation', to: '/documentation' }];
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <><PageHeader title="Document" crumbs={crumbs} /><ErrorBox error={q.error} /></>;
  const d = q.data;
  return (
    <div>
      <PageHeader
        title={d.title}
        icon={<FileText className="h-5 w-5 text-brand-600" />}
        crumbs={[...crumbs, { label: d.title }]}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone="brand">{categoryLabel(d.category)}</Badge>
            {d.tags.map((t) => (
              <Badge key={t} tone="gray">
                #{t}
              </Badge>
            ))}
            <span className="text-xs">
              Created {fmtDate(d.created_at)} by {d.created_by ?? '—'} · updated {fmtDate(d.updated_at)} by {d.updated_by ?? '—'}
            </span>
          </span>
        }
        actions={
          isAdmin && (
            <>
              <Link to={`/documentation/${d.id}/edit`} className="btn-secondary">
                <Pencil className="h-4 w-4" /> Edit
              </Link>
              <button className="btn-danger" onClick={() => setConfirm(true)}>
                <Trash2 className="h-4 w-4" /> Delete
              </button>
            </>
          )
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="border-l-4 border-l-brand-500">
            {d.body ? <Markdown text={d.body} /> : <EmptyState>This document has no content yet.</EmptyState>}
          </Card>
        </div>
        <div className="space-y-4">
          <AttachmentsCard doc={d} />
          <RelationshipsCard objectType="document" objectKey={String(d.id)} relationships={d.relationships ?? []} />
        </div>
      </div>
      <ConfirmDialog
        open={confirm}
        title="Delete document"
        message={`Delete “${d.title}” including all attachments and relationships?`}
        confirmLabel="Delete"
        danger
        busy={rm.isPending}
        onCancel={() => setConfirm(false)}
        onConfirm={() => rm.mutate()}
      />
    </div>
  );
}

interface PendingRel {
  target_type: string;
  target_key: string;
  relation: string;
}

export function DocumentEditPage() {
  const { id } = useParams();
  const isNew = !id;
  const { isAdmin } = useAuth();
  const meta = useManualMeta();
  const toast = useToast();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const q = useDocument(id);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('other');
  const [tags, setTags] = useState('');
  const [body, setBody] = useState('');
  const [mode, setMode] = useState<'split' | 'edit' | 'preview'>('split');
  const [err, setErr] = useState<string | null>(null);
  const [rels, setRels] = useState<PendingRel[]>([]);
  const [pick, setPick] = useState({ type: 'device', key: '', relation: 'related' });

  useEffect(() => {
    if (q.data) {
      setTitle(q.data.title);
      setCategory(q.data.category);
      setTags(q.data.tags.join(', '));
      setBody(q.data.body ?? '');
    }
  }, [q.data]);

  const tagList = useMemo(
    () =>
      tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    [tags],
  );

  const save = useMutation({
    mutationFn: () => {
      const payload = { title: title.trim(), body, category, tags: tagList };
      return isNew ? post<ManualDocument>('manual/documents', { ...payload, relationships: rels }) : put<ManualDocument>(`manual/documents/${id}`, payload);
    },
    onSuccess: (doc) => {
      toast.success(isNew ? 'Document created.' : 'Document saved.');
      void qc.invalidateQueries({ queryKey: ['documents'] });
      void qc.invalidateQueries({ queryKey: ['document'] });
      navigate(`/documentation/${doc.id ?? id}`);
    },
    onError: (e) => setErr(e instanceof Error ? e.message : String(e)),
  });

  if (!isAdmin) return <ErrorBox error="Only administrators can edit documentation." title="Read-only access" />;
  if (!isNew && q.isLoading) return <Spinner />;
  if (!isNew && (q.error || !q.data)) return <ErrorBox error={q.error} />;

  const crumbs = [{ label: 'Documentation', to: '/documentation' }, ...(isNew ? [] : [{ label: q.data?.title ?? '', to: `/documentation/${id}` }]), { label: isNew ? 'New document' : 'Edit' }];

  return (
    <div>
      <PageHeader
        title={isNew ? 'New document' : `Edit: ${q.data?.title ?? ''}`}
        crumbs={crumbs}
        actions={
          <>
            <Link to={isNew ? '/documentation' : `/documentation/${id}`} className="btn-secondary">
              Cancel
            </Link>
            <button
              className="btn-primary"
              disabled={save.isPending || !title.trim()}
              onClick={() => {
                setErr(null);
                save.mutate();
              }}
            >
              <Save className="h-4 w-4" /> {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </>
        }
      />
      {err && <div className="mb-4"><ErrorBox error={err} title="Could not save" /></div>}
      <div className="space-y-4">
        <Card>
          <div className="grid gap-3 md:grid-cols-[2fr_1fr_1fr]">
            <Field label="Title">
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} required autoFocus />
            </Field>
            <Field label="Category">
              <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                {(meta.data?.document_categories ?? ['other']).map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel(c)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tags" hint="Comma-separated">
              <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} />
            </Field>
          </div>
        </Card>
        <Card
          title="Content (Markdown)"
          actions={
            <div className="flex rounded-md border border-slate-200 p-0.5 text-xs dark:border-slate-700">
              {(['edit', 'split', 'preview'] as const).map((m) => (
                <button key={m} className={cx('rounded px-2 py-0.5', mode === m ? 'bg-brand-600 text-white' : 'text-slate-600 dark:text-slate-300')} onClick={() => setMode(m)}>
                  {humanize(m)}
                </button>
              ))}
            </div>
          }
        >
          <div className={cx('grid gap-4', mode === 'split' && 'lg:grid-cols-2')}>
            {mode !== 'preview' && (
              <textarea
                className="input min-h-[28rem] font-mono text-sm"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={'# Heading\n\nDescribe the network, procedures, contacts…\n\n- lists\n- **bold**, `code`\n\n| Table | Header |\n|---|---|'}
                aria-label="Document content"
              />
            )}
            {mode !== 'edit' && (
              <div className="min-h-[28rem] overflow-auto rounded-md border border-dashed border-slate-300 p-3 dark:border-slate-700">
                {body.trim() ? <Markdown text={body} /> : <p className="text-sm italic text-slate-400">Preview</p>}
              </div>
            )}
          </div>
          <p className="mt-2 text-xs text-slate-500">Do not store passwords or other secrets in the documentation – texts that look like credentials are rejected.</p>
        </Card>
        {isNew ? (
          <Card title="Related objects">
            {rels.length > 0 && (
              <ul className="mb-3 space-y-1 text-sm">
                {rels.map((r, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Badge tone="gray">{humanize(r.relation)}</Badge> {kindLabel(r.target_type)} <span className="font-mono text-xs">{r.target_key}</span>
                    <button className="btn-ghost p-0.5" onClick={() => setRels(rels.filter((_, j) => j !== i))} aria-label="Remove">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="grid items-end gap-3 md:grid-cols-[10rem_1fr_auto]">
              <Field label="Relation">
                <select className="input" value={pick.relation} onChange={(e) => setPick({ ...pick, relation: e.target.value })}>
                  {(meta.data?.relations ?? ['related']).map((r) => (
                    <option key={r} value={r}>
                      {humanize(r)}
                    </option>
                  ))}
                </select>
              </Field>
              <ObjectPicker type={pick.type} objectKey={pick.key} onChange={(type, key) => setPick({ ...pick, type, key })} />
              <button
                className="btn-secondary"
                disabled={!pick.key}
                onClick={() => {
                  setRels([...rels, { target_type: pick.type, target_key: pick.key, relation: pick.relation }]);
                  setPick({ ...pick, key: '' });
                }}
              >
                <Plus className="h-4 w-4" /> Add
              </button>
            </div>
            <p className="mt-2 text-xs text-slate-500">Attachments can be uploaded after the document has been created.</p>
          </Card>
        ) : (
          <p className="text-sm text-slate-500">Relationships and attachments are managed on the document page.</p>
        )}
      </div>
    </div>
  );
}
