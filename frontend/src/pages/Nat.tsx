import { useParams } from 'react-router-dom';
import { ArrowRightLeft } from 'lucide-react';
import { useEntities } from '../api/hooks';
import type { NatRule } from '../api/types';
import { DataTable } from '../components/DataTable';
import { DetailShell, displayName, RawPropertiesCard } from '../components/detail';
import { Badge, BoolBadge, Card, ErrorBox, KeyValue, Mono, PageHeader, Spinner } from '../components/ui';
import { humanize } from '../lib/format';
import { objectPath } from '../lib/routes';
import { NameCell } from './Devices';

function sourceText(r: NatRule): string {
  if (r.source_addresses?.length) return r.source_addresses.join(', ');
  return r.source && r.source !== 'any' ? r.source : 'Any';
}

function protoText(r: NatRule): string {
  return (r.protocol ?? '').toUpperCase().replace('_', '/');
}

export function NatPage() {
  const q = useEntities<NatRule>('nat_rule');
  return (
    <div>
      <PageHeader title="NAT / Port Forwarding" crumbs={[{ label: 'NAT / Port Forwarding' }]} subtitle="Port forwarding, DMZ and other NAT rules on the gateway" />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : (
        <DataTable<NatRule>
          rows={q.data?.items ?? []}
          rowKey={(r) => r.key}
          rowHref={(r) => objectPath('nat_rule', r.key)}
          initialSort={{ id: 'name', dir: 'asc' }}
          emptyText="No NAT or port forwarding rules found."
          columns={[
            { id: 'name', header: 'Name', value: (r) => displayName(r), cell: (r) => <NameCell name={r.name} manualName={r.manual?.display_name} /> },
            { id: 'type', header: 'Type', value: (r) => humanize(r.nat_type ?? ''), filter: true, cell: (r) => (r.dmz ? <Badge tone="red">DMZ</Badge> : humanize(r.nat_type ?? '')) },
            { id: 'enabled', header: 'Enabled', value: (r) => r.enabled, cell: (r) => <BoolBadge value={r.enabled} />, filter: true },
            { id: 'proto', header: 'Protocol', value: protoText },
            { id: 'ext', header: 'External port', value: (r) => r.external_port, cell: (r) => (r.external_port ? <Mono>{r.external_port}</Mono> : '—') },
            {
              id: 'target',
              header: 'Internal target',
              value: (r) => `${r.internal_ip ?? ''}${r.internal_port ? `:${r.internal_port}` : ''}`,
              cell: (r) => (r.internal_ip ? <Mono>{`${r.internal_ip}${r.internal_port ? `:${r.internal_port}` : ''}`}</Mono> : '—'),
            },
            { id: 'source', header: 'Allowed source', value: sourceText },
            { id: 'wan', header: 'WAN', value: (r) => r.wan_port_ids ?? [] },
            { id: 'desc', header: 'Description', value: (r) => r.manual?.description ?? '', className: 'max-w-[16rem] truncate' },
          ]}
        />
      )}
    </div>
  );
}

export function NatDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<NatRule>
      kind="nat_rule"
      objectKey={key}
      crumbs={[{ label: 'NAT / Port Forwarding', to: '/nat' }]}
      icon={<ArrowRightLeft className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => (
        <>
          <BoolBadge value={d.entity.enabled} yes="Enabled" no="Disabled" />
          {d.entity.dmz && <Badge tone="red">DMZ</Badge>}
        </>
      )}
    >
      {(d) => {
        const r = d.entity;
        return (
          <>
            <Card title="Forwarding">
              <div className="mb-4 flex flex-wrap items-center gap-3 rounded-md bg-slate-50 p-3 text-sm dark:bg-slate-800/50">
                <span>
                  <span className="label mb-0">From</span> {sourceText(r)}
                </span>
                <span>→</span>
                <span>
                  <span className="label mb-0">WAN</span> {r.wan_port_ids?.join(', ') || 'any'} : <Mono>{r.external_port ?? '*'}</Mono> ({protoText(r) || 'any'})
                </span>
                <span>→</span>
                <span>
                  <span className="label mb-0">Internal</span> <Mono>{`${r.internal_ip ?? '?'}${r.internal_port ? `:${r.internal_port}` : ''}`}</Mono>
                </span>
              </div>
              <KeyValue
                cols={3}
                items={[
                  { label: 'NAT type', value: humanize(r.nat_type ?? '') },
                  { label: 'Enabled', value: <BoolBadge value={r.enabled} /> },
                  { label: 'DMZ', value: r.dmz ? 'Yes' : 'No' },
                  { label: 'Protocol', value: protoText(r) },
                  { label: 'External port', value: r.external_port },
                  { label: 'Internal IP', value: r.internal_ip },
                  { label: 'Internal port', value: r.internal_port },
                  { label: 'Allowed source', value: sourceText(r) },
                  { label: 'WAN ports', value: r.wan_port_ids?.join(', ') },
                ]}
              />
              {r.dmz && <p className="mt-3 text-sm text-red-600 dark:text-red-400">DMZ forwards all unsolicited incoming traffic to the internal host.</p>}
            </Card>
            <RawPropertiesCard entity={r} />
          </>
        );
      }}
    </DetailShell>
  );
}
