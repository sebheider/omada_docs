import { useParams } from 'react-router-dom';
import { Laptop, Smartphone } from 'lucide-react';
import { useEntities } from '../api/hooks';
import type { Client } from '../api/types';
import { DataTable } from '../components/DataTable';
import { DetailShell, displayName, ObjectLink, RawPropertiesCard } from '../components/detail';
import { Badge, Card, ErrorBox, KeyValue, Mono, PageHeader, Spinner, StatusBadge } from '../components/ui';
import { fmtDate, fmtSeconds, humanize } from '../lib/format';
import { objectPath } from '../lib/routes';
import { NameCell } from './Devices';

function networkText(c: Client): string {
  return c.network_name ?? (c.vlan_id ? `VLAN ${c.vlan_id}` : c.network_id ?? '');
}

function attachText(c: Client): string {
  if (c.wireless) return [c.ssid, c.connected_device_name].filter(Boolean).join(' via ');
  return [c.connected_device_name, c.port ? `port ${c.port}` : null].filter(Boolean).join(' · ');
}

function ConnectedTo({ c }: { c: Client }) {
  if (!c.connected_device_mac && !c.ssid) return <span className="text-slate-400">—</span>;
  return (
    <span className="text-sm">
      {c.wireless && c.ssid && <span className="font-medium">{c.ssid}</span>}
      {c.wireless && c.ssid && c.connected_device_mac && <span className="text-slate-500"> via </span>}
      {c.connected_device_mac && (
        <ObjectLink type="device" id={c.connected_device_mac} deviceType={c.connected_device_type ?? undefined}>
          {c.connected_device_name ?? c.connected_device_mac}
        </ObjectLink>
      )}
      {!c.wireless && c.port && c.connected_device_mac && (
        <>
          {' · '}
          <ObjectLink type="switch_port" id={`${c.connected_device_mac}:${c.port}`}>
            port {c.port}
          </ObjectLink>
        </>
      )}
    </span>
  );
}

export function ClientsPage() {
  const q = useEntities<Client>('client');
  return (
    <div>
      <PageHeader title="Clients" crumbs={[{ label: 'Clients' }]} subtitle="Devices connected to the network, as reported by the controller at the last synchronisation" />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : (
        <DataTable<Client>
          rows={q.data?.items ?? []}
          rowKey={(c) => c.key}
          rowHref={(c) => objectPath('client', c.key)}
          initialSort={{ id: 'name', dir: 'asc' }}
          searchPlaceholder="Search name, IP, MAC, vendor, SSID…"
          emptyText="No clients found."
          columns={[
            { id: 'name', header: 'Name', value: (c) => displayName(c), cell: (c) => <NameCell name={c.name ?? c.hostname} manualName={c.manual?.display_name} sub={c.hostname && c.hostname !== c.name ? c.hostname : null} /> },
            { id: 'ip', header: 'IP', value: (c) => c.ip, cell: (c) => (c.ip ? <Mono>{c.ip}</Mono> : '—') },
            { id: 'mac', header: 'MAC', value: (c) => c.mac, cell: (c) => <Mono>{c.mac}</Mono> },
            { id: 'network', header: 'Network', value: networkText, filter: true },
            {
              id: 'conn',
              header: 'Connection',
              value: (c) => (c.wireless ? 'Wireless' : 'Wired'),
              cell: (c) => (
                <span className="flex items-center gap-1.5">
                  {c.wireless ? <Smartphone className="h-3.5 w-3.5 text-sky-500" /> : <Laptop className="h-3.5 w-3.5 text-slate-500" />}
                  {c.wireless ? 'Wireless' : 'Wired'}
                  {c.guest && <Badge tone="amber">guest</Badge>}
                </span>
              ),
              filter: true,
            },
            { id: 'attached', header: 'Connected to', value: attachText, cell: (c) => <ConnectedTo c={c} /> },
            { id: 'vendor', header: 'Vendor', value: (c) => c.vendor, filter: true },
            { id: 'status', header: 'Status', value: (c) => (c.active === false ? 'offline' : 'online'), cell: (c) => <StatusBadge status={c.active === false ? 'offline' : 'online'} />, filter: true },
          ]}
        />
      )}
    </div>
  );
}

export function ClientDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<Client>
      kind="client"
      objectKey={key}
      crumbs={[{ label: 'Clients', to: '/clients' }]}
      icon={<Laptop className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => (
        <>
          <StatusBadge status={d.entity.active === false ? 'offline' : 'online'} />
          <Badge tone={d.entity.wireless ? 'blue' : 'gray'}>{d.entity.wireless ? 'Wireless' : 'Wired'}</Badge>
          {d.entity.guest && <Badge tone="amber">Guest</Badge>}
        </>
      )}
    >
      {(d) => {
        const c = d.entity;
        const ipv6 = Array.isArray(c.ipv6) ? (c.ipv6 as string[]) : [];
        return (
          <>
            <Card title="Identification">
              <KeyValue
                cols={3}
                items={[
                  { label: 'MAC address', value: c.mac ? <Mono>{c.mac}</Mono> : null },
                  { label: 'IP address', value: c.ip ? <Mono>{c.ip}</Mono> : null },
                  { label: 'IPv6', value: ipv6.length ? ipv6.join(', ') : null },
                  { label: 'Hostname', value: c.hostname },
                  { label: 'Vendor', value: c.vendor },
                  { label: 'Device type', value: c.device_type ? humanize(String(c.device_type)) : null },
                  { label: 'Category', value: c.device_category ? humanize(String(c.device_category)) : null },
                  { label: 'Operating system', value: c.os as string },
                  { label: 'Model', value: c.model as string },
                  { label: 'Fixed IP (reservation)', value: c.fixed_ip ? String(c.fixed_ip) : null },
                ]}
              />
            </Card>
            <Card title="Connection">
              <KeyValue
                cols={3}
                items={[
                  { label: 'Connection type', value: c.connection_type ? humanize(c.connection_type) : c.wireless ? 'Wireless' : 'Wired' },
                  { label: 'Network', value: c.network_id ? <ObjectLink type="network" id={c.network_id}>{networkText(c)}</ObjectLink> : networkText(c) || null },
                  { label: 'VLAN', value: c.vlan_id },
                  { label: 'Connected to', value: <ConnectedTo c={c} /> },
                  { label: 'SSID', value: c.ssid },
                  { label: 'Radio', value: c.radio },
                  { label: 'Signal', value: c.signal_percent !== null && c.signal_percent !== undefined ? `${c.signal_percent} %${c.rssi ? ` (${String(c.rssi)} dBm)` : ''}` : null },
                  { label: 'Uptime', value: c.uptime_seconds ? fmtSeconds(Number(c.uptime_seconds)) : null },
                  { label: 'Last seen', value: c.last_seen ? fmtDate(c.last_seen) : null },
                ]}
              />
            </Card>
            <RawPropertiesCard entity={c} />
          </>
        );
      }}
    </DetailShell>
  );
}
