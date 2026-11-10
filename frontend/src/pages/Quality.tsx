import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, ClipboardCheck } from 'lucide-react';
import { get } from '../api/client';
import type { QualityReport } from '../api/types';
import { useSite } from '../context/SiteContext';
import { Badge, Card, cx, ErrorBox, PageHeader, Spinner } from '../components/ui';
import { humanize, kindLabel } from '../lib/format';
import { objectPath } from '../lib/routes';

export const QUALITY_LABELS: Record<string, { title: string; hint: string }> = {
  unassigned_devices: { title: 'Unassigned / pending devices', hint: 'Devices that are not adopted or not assigned to a site.' },
  unknown_port_connections: { title: 'Unknown port connections', hint: 'Switch ports with link but no identified neighbour.' },
  vlans_without_description: { title: 'VLANs without description', hint: 'Networks that have no manual description yet.' },
  unreliable_acl_rules: { title: 'Unreliable ACL interpretation', hint: 'ACL rules whose meaning could not be determined with high confidence.' },
  devices_without_location: { title: 'Devices without location', hint: 'Network devices without a documented physical location.' },
  unresolved_connections: { title: 'Unresolved topology connections', hint: 'Devices whose uplink could not be determined.' },
  source_conflicts: { title: 'Conflicts between data sources', hint: 'Differences between the controller API and an imported backup.' },
  stale_data: { title: 'Stale data', hint: 'Objects that were carried forward from an earlier sync because the endpoint failed.' },
  unsupported_endpoints: { title: 'Unsupported / failed endpoints', hint: 'API endpoints that were not available on this controller.' },
};

export function QualityPage() {
  const { siteId } = useSite();
  const q = useQuery({ queryKey: ['quality', siteId], queryFn: () => get<QualityReport>('quality', { site_id: siteId }) });
  const sections = q.data ? Object.keys(q.data.sections) : [];
  const total = q.data ? Object.values(q.data.summary).reduce((a, b) => a + b, 0) : 0;
  const { hash } = useLocation();
  useEffect(() => {
    if (q.data && hash) document.getElementById(`q-${decodeURIComponent(hash.slice(1))}`)?.scrollIntoView({ behavior: 'smooth' });
  }, [q.data, hash]);
  return (
    <div>
      <PageHeader
        title="Data quality"
        icon={<ClipboardCheck className="h-5 w-5 text-brand-600" />}
        crumbs={[{ label: 'Network Overview', to: '/topology' }, { label: 'Data quality' }]}
        subtitle="Gaps and uncertainties in the documentation that should be reviewed"
        actions={q.data && <Badge tone={total ? 'amber' : 'green'}>{total} open findings</Badge>}
      />
      {q.isLoading ? (
        <Spinner />
      ) : q.error || !q.data ? (
        <ErrorBox error={q.error} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <nav className="card h-max p-2 lg:sticky lg:top-20" aria-label="Sections">
            {sections.map((s) => {
              const n = q.data.summary[s] ?? q.data.sections[s].length;
              return (
                <a key={s} href={`#q-${s}`} onClick={(e) => { e.preventDefault(); document.getElementById(`q-${s}`)?.scrollIntoView({ behavior: 'smooth' }); }} className="flex items-center justify-between gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                  <span className="truncate">{QUALITY_LABELS[s]?.title ?? humanize(s)}</span>
                  <Badge tone={n ? 'amber' : 'green'}>{n}</Badge>
                </a>
              );
            })}
          </nav>
          <div className="space-y-4">
            {sections.map((s) => {
              const items = q.data.sections[s];
              return (
                <div id={`q-${s}`} key={s} className="scroll-mt-20">
                  <Card
                    title={<span className="flex items-center gap-2">{QUALITY_LABELS[s]?.title ?? humanize(s)} <Badge tone={items.length ? 'amber' : 'green'}>{items.length}</Badge></span>}
                    subtitle={QUALITY_LABELS[s]?.hint}
                    bodyClassName={cx(items.length > 0 && 'p-0')}
                  >
                    {items.length === 0 ? (
                      <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
                        <CheckCircle2 className="h-4 w-4" /> No findings.
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="table-base">
                          <thead>
                            <tr>
                              <th>Object</th>
                              <th>Type</th>
                              <th>Detail</th>
                            </tr>
                          </thead>
                          <tbody>
                            {items.map((it, i) => {
                              const to = it.object_key ? objectPath(it.object_type, it.object_key) : null;
                              return (
                                <tr key={`${it.object_type}:${it.object_key}:${i}`}>
                                  <td className="font-medium">{to ? <Link className="link" to={to}>{it.name ?? it.object_key}</Link> : (it.name ?? it.object_key ?? '—')}</td>
                                  <td className="whitespace-nowrap">{kindLabel(it.object_type)}</td>
                                  <td className="text-slate-600 dark:text-slate-300">{it.detail ?? '—'}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </Card>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
