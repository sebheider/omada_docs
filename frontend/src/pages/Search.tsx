import { useEffect, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search as SearchIcon } from 'lucide-react';
import { get } from '../api/client';
import type { SearchResult } from '../api/types';
import { useSite } from '../context/SiteContext';
import { Badge, Card, EmptyState, ErrorBox, PageHeader, Spinner } from '../components/ui';
import { humanize } from '../lib/format';
import { objectPath } from '../lib/routes';

const CATEGORY_LABELS: Record<string, string> = {
  devices: 'Devices',
  clients: 'Clients',
  networks: 'Networks / VLANs',
  wlans: 'WLANs',
  switch_ports: 'Switch ports',
  acl_rules: 'ACL rules',
  nat_rules: 'NAT rules',
  ip_groups: 'IP / port groups',
  documentation: 'Documentation',
};

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const [input, setInput] = useState(q);
  const { siteId } = useSite();
  useEffect(() => setInput(q), [q]);
  const res = useQuery({
    queryKey: ['search', q, siteId],
    queryFn: () => get<SearchResult>('search', { q, site_id: siteId }),
    enabled: q.trim().length > 0,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setParams(input.trim() ? { q: input.trim() } : {});
  };
  return (
    <div>
      <PageHeader title="Search" crumbs={[{ label: 'Search' }]} subtitle="Search devices, clients, networks, WLANs, ports, rules and documentation by name, IP, MAC, VLAN, description and more" />
      <form onSubmit={submit} className="mb-6 flex max-w-3xl gap-2">
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
          <input
            className="input py-2.5 pl-10 text-base"
            placeholder="e.g. 192.168.10.5, AA-BB-CC, VLAN 20, NAS, port 8…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            autoFocus
            aria-label="Search query"
          />
        </div>
        <button type="submit" className="btn-primary">
          Search
        </button>
      </form>
      {!q ? (
        <Card>
          <EmptyState icon={<SearchIcon className="h-8 w-8" />}>Enter a search term to find objects across the whole documentation.</EmptyState>
        </Card>
      ) : res.isLoading ? (
        <Spinner />
      ) : res.error ? (
        <ErrorBox error={res.error} />
      ) : !res.data?.total ? (
        <Card>
          <EmptyState>No results for “{q}”.</EmptyState>
        </Card>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            {res.data.total} result{res.data.total === 1 ? '' : 's'} for “{q}”
          </p>
          {res.data.groups.map((g) => (
            <Card key={g.category} title={<span className="flex items-center gap-2">{CATEGORY_LABELS[g.category] ?? humanize(g.category)} <Badge tone="gray">{g.items.length}</Badge></span>} bodyClassName="p-0">
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {g.items.map((it) => {
                  const to = objectPath(it.object_type, it.object_key);
                  const inner = (
                    <>
                      <div className="font-medium text-slate-900 dark:text-slate-100">{it.title}</div>
                      {it.subtitle && <div className="text-xs text-slate-500">{it.subtitle}</div>}
                      {it.reason && <div className="mt-0.5 text-xs text-brand-700 dark:text-brand-300">Match: {it.reason}</div>}
                    </>
                  );
                  return (
                    <li key={`${it.object_type}:${it.object_key}`}>
                      {to ? (
                        <Link to={to} className="block px-4 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/60">
                          {inner}
                        </Link>
                      ) : (
                        <div className="px-4 py-2.5">{inner}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
