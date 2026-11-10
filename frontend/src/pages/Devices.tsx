import { useParams } from 'react-router-dom';
import { Cable, Router, Wifi } from 'lucide-react';
import { useEntities } from '../api/hooks';
import type { Device } from '../api/types';
import { DataTable, type Column } from '../components/DataTable';
import { DetailShell, displayName, ObjectLink, RawPropertiesCard } from '../components/detail';
import { Badge, Card, ErrorBox, KeyValue, Mono, PageHeader, Spinner, StatusBadge } from '../components/ui';
import { fmtDate, fmtSeconds, humanize } from '../lib/format';
import { objectPath } from '../lib/routes';
import { SwitchPortsSection } from './Switches';

export const DEVICE_TYPE_LABELS: Record<string, string> = { gateway: 'Gateway', switch: 'Switch', ap: 'Access point' };

export function DeviceTypeBadge({ type }: { type: string | null | undefined }) {
  const Icon = type === 'switch' ? Cable : type === 'ap' ? Wifi : Router;
  return (
    <Badge tone={type === 'gateway' ? 'violet' : type === 'switch' ? 'brand' : type === 'ap' ? 'amber' : 'gray'}>
      <Icon className="h-3 w-3" />
      {DEVICE_TYPE_LABELS[type ?? ''] ?? humanize(type ?? 'unknown')}
    </Badge>
  );
}

export function NameCell({ name, manualName, sub }: { name: string | null | undefined; manualName?: string | null; sub?: string | null }) {
  return (
    <div className="min-w-0">
      <div className="font-medium text-slate-900 dark:text-slate-100">{manualName || name || '—'}</div>
      {manualName && manualName !== name && <div className="text-xs text-slate-500">{name}</div>}
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function deviceColumns(): Column<Device>[] {
  return [
    { id: 'name', header: 'Name', value: (d) => displayName(d), cell: (d) => <NameCell name={d.name} manualName={d.manual?.display_name} /> },
    { id: 'type', header: 'Type', value: (d) => DEVICE_TYPE_LABELS[d.type ?? ''] ?? d.type, cell: (d) => <DeviceTypeBadge type={d.type} />, filter: true },
    { id: 'model', header: 'Model', value: (d) => d.model },
    { id: 'ip', header: 'IP address', value: (d) => d.ip, cell: (d) => (d.ip ? <Mono>{d.ip}</Mono> : '—') },
    { id: 'mac', header: 'MAC', value: (d) => d.mac, cell: (d) => <Mono>{d.mac}</Mono> },
    { id: 'firmware', header: 'Firmware', value: (d) => d.firmware, className: 'max-w-[12rem] truncate' },
    { id: 'status', header: 'Status', value: (d) => d.status, cell: (d) => <StatusBadge status={d.status} />, filter: true },
    {
      id: 'uplink',
      header: 'Uplink',
      value: (d) => (d.uplink_device_name ? `${d.uplink_device_name}${d.uplink_port ? ` port ${d.uplink_port}` : ''}` : ''),
    },
    { id: 'location', header: 'Location', value: (d) => d.manual?.location ?? '' },
  ];
}

export function DevicesPage() {
  const q = useEntities<Device>('device');
  return (
    <div>
      <PageHeader title="Devices" crumbs={[{ label: 'Devices' }]} subtitle="Gateways, switches and access points managed by the controller" />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : (
        <DataTable
          rows={q.data?.items ?? []}
          columns={deviceColumns()}
          rowKey={(d) => d.key}
          rowHref={(d) => objectPath('device', d.key, { deviceType: d.type })}
          initialSort={{ id: 'type', dir: 'asc' }}
          searchPlaceholder="Filter by name, IP, MAC, model…"
          emptyText="No devices found. Run a synchronization first."
        />
      )}
    </div>
  );
}

export function DeviceDetailPage({ section }: { section?: 'switches' }) {
  const { key } = useParams();
  const crumbs = section === 'switches' ? [{ label: 'Switches and Ports', to: '/switches' }] : [{ label: 'Devices', to: '/devices' }];
  return (
    <DetailShell<Device>
      kind="device"
      objectKey={key}
      crumbs={crumbs}
      icon={<Router className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => (
        <>
          <DeviceTypeBadge type={d.entity.type} />
          <StatusBadge status={d.entity.status} />
        </>
      )}
    >
      {(d) => {
        const e = d.entity;
        return (
          <>
            <Card title="General">
              <KeyValue
                cols={3}
                items={[
                  { label: 'Model', value: e.model },
                  { label: 'Model name', value: e.model_name },
                  { label: 'Hardware version', value: e.hw_version as string },
                  { label: 'Serial number', value: e.serial },
                  { label: 'Firmware', value: e.firmware },
                  { label: 'Status', value: <StatusBadge status={e.status} /> },
                  { label: 'Adopted', value: e.adopted === undefined || e.adopted === null ? null : e.adopted ? 'Yes' : 'No' },
                  { label: 'Uptime', value: e.uptime ?? fmtSeconds(e.uptime_seconds) },
                  { label: 'Last seen', value: e.last_seen ? fmtDate(e.last_seen as string) : null },
                  { label: 'CPU', value: e.cpu_percent !== null && e.cpu_percent !== undefined ? `${e.cpu_percent} %` : null },
                  { label: 'Memory', value: e.memory_percent !== null && e.memory_percent !== undefined ? `${e.memory_percent} %` : null },
                  { label: 'Connected clients', value: e.client_count ?? null },
                ]}
              />
            </Card>
            <Card title="Addressing & uplink">
              <KeyValue
                cols={3}
                items={[
                  { label: 'IP address', value: e.ip ? <Mono>{e.ip}</Mono> : null },
                  { label: 'MAC address', value: <Mono>{e.mac}</Mono> },
                  { label: 'Public IP', value: e.public_ip as string },
                  { label: 'IPv6', value: Array.isArray(e.ipv6) && e.ipv6.length ? (e.ipv6 as string[]).join(', ') : null },
                  {
                    label: 'Uplink device',
                    value: e.uplink_device_mac ? (
                      <ObjectLink type="device" id={e.uplink_device_mac}>
                        {e.uplink_device_name ?? e.uplink_device_mac}
                      </ObjectLink>
                    ) : e.type === 'gateway' ? (
                      'Internet (WAN)'
                    ) : null,
                  },
                  { label: 'Uplink port', value: e.uplink_port },
                  { label: 'Uplink speed', value: e.uplink_speed },
                ]}
              />
            </Card>
            {e.type === 'switch' && <SwitchPortsSection switchMac={String(e.key)} />}
            <RawPropertiesCard entity={e} />
          </>
        );
      }}
    </DetailShell>
  );
}
