import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, ExternalLink, FileDown } from 'lucide-react';
import { apiUrl, downloadFile, get } from '../api/client';
import type { ExportOptions } from '../api/types';
import { useSite } from '../context/SiteContext';
import { useToast } from '../context/ToastContext';
import { Card, cx, ErrorBox, Field, PageHeader, Spinner } from '../components/ui';
import { humanize } from '../lib/format';

const FORMAT_INFO: Record<string, { label: string; hint: string }> = {
  pdf: { label: 'PDF', hint: 'Printable document with table of contents' },
  docx: { label: 'Word (DOCX)', hint: 'Editable Microsoft Word document' },
  html: { label: 'HTML', hint: 'Single self-contained web page' },
  csv: { label: 'CSV', hint: 'One table for spreadsheets' },
};

export function ExportPage() {
  const opts = useQuery({ queryKey: ['export-options'], queryFn: () => get<ExportOptions>('export/options') });
  const { siteId, sites } = useSite();
  const toast = useToast();
  const [format, setFormat] = useState('pdf');
  const [site, setSite] = useState(siteId ?? '');
  const [chapters, setChapters] = useState<string[]>([]);
  const [anonymize, setAnonymize] = useState(true);
  const [days, setDays] = useState(90);
  const [table, setTable] = useState('devices');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (opts.data) setChapters(opts.data.default_chapters);
  }, [opts.data]);
  useEffect(() => setSite(siteId ?? ''), [siteId]);

  const query = () => ({
    format,
    site_id: site || null,
    chapters: format === 'csv' ? null : chapters.join(','),
    anonymize,
    change_days: days,
    table: format === 'csv' ? table : null,
  });

  const run = async () => {
    if (format !== 'csv' && !chapters.length) {
      toast.error('Select at least one chapter.');
      return;
    }
    setBusy(true);
    try {
      await downloadFile('export', query(), `network-documentation.${format}`);
      toast.success('Export created.');
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id: string) => setChapters((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  return (
    <div>
      <PageHeader title="Export documentation" icon={<FileDown className="h-5 w-5 text-brand-600" />} crumbs={[{ label: 'Settings', to: '/settings' }, { label: 'Export' }]} subtitle="Create a complete network documentation as PDF, Word, HTML or CSV" />
      {opts.isLoading ? (
        <Spinner />
      ) : opts.error || !opts.data ? (
        <ErrorBox error={opts.error} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Card title="Format">
              <div className="grid gap-2 sm:grid-cols-2">
                {opts.data.formats.map((f) => (
                  <label
                    key={f}
                    className={cx(
                      'flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm',
                      format === f ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20' : 'border-slate-200 hover:border-slate-300 dark:border-slate-700',
                    )}
                  >
                    <input type="radio" name="format" className="mt-0.5" checked={format === f} onChange={() => setFormat(f)} />
                    <span>
                      <span className="block font-medium">{FORMAT_INFO[f]?.label ?? f.toUpperCase()}</span>
                      <span className="text-xs text-slate-500">{FORMAT_INFO[f]?.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </Card>
            {format === 'csv' ? (
              <Card title="CSV table">
                <Field label="Table">
                  <select className="input max-w-xs" value={table} onChange={(e) => setTable(e.target.value)}>
                    {opts.data.csv_tables.map((t) => (
                      <option key={t} value={t}>
                        {humanize(t)}
                      </option>
                    ))}
                  </select>
                </Field>
              </Card>
            ) : (
              <Card
                title="Chapters"
                actions={
                  <div className="flex gap-1">
                    <button className="btn-ghost py-0.5 text-xs" onClick={() => setChapters(Object.keys(opts.data.chapters))}>
                      All
                    </button>
                    <button className="btn-ghost py-0.5 text-xs" onClick={() => setChapters(opts.data.default_chapters)}>
                      Default
                    </button>
                    <button className="btn-ghost py-0.5 text-xs" onClick={() => setChapters([])}>
                      None
                    </button>
                  </div>
                }
              >
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {Object.entries(opts.data.chapters).map(([id, title]) => (
                    <label key={id} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={chapters.includes(id)} onChange={() => toggle(id)} />
                      {title}
                    </label>
                  ))}
                </div>
              </Card>
            )}
          </div>
          <div className="space-y-4">
            <Card title="Options">
              <div className="space-y-3">
                {sites.length > 1 && (
                  <Field label="Site">
                    <select className="input" value={site} onChange={(e) => setSite(e.target.value)}>
                      {sites.map((s) => (
                        <option key={s.key} value={s.key}>
                          {s.manual?.display_name || s.name || s.key}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" className="mt-0.5" checked={anonymize} onChange={(e) => setAnonymize(e.target.checked)} />
                  <span>
                    Anonymise client data
                    <span className="block text-xs text-slate-500">Masks client names, MAC and IP addresses (recommended when sharing).</span>
                  </span>
                </label>
                <Field label="Change history (days)">
                  <input className="input" type="number" min={1} max={3650} value={days} onChange={(e) => setDays(Math.max(1, Math.min(3650, Number(e.target.value) || 90)))} />
                </Field>
              </div>
            </Card>
            <button className="btn-primary w-full justify-center" disabled={busy} onClick={run}>
              <Download className="h-4 w-4" /> {busy ? 'Generating…' : `Download ${FORMAT_INFO[format]?.label ?? format}`}
            </button>
            {format === 'html' && (
              <a className="btn-secondary w-full justify-center" href={apiUrl('export', { ...query(), download: false })} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-4 w-4" /> Open HTML in new tab
              </a>
            )}
            <p className="text-xs text-slate-500">Passwords, keys and other secrets are never included in exports. PDF generation may take a few seconds.</p>
          </div>
        </div>
      )}
    </div>
  );
}
