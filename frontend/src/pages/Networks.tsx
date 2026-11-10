import { useParams, useSearchParams } from 'react-router-dom';
import { Globe, Network as NetworkIcon, Route, ShieldCheck } from 'lucide-react';
import { useEntities } from '../api/hooks';
import type { BaseEntity, Network } from '../api/types';
import { DataTable } from '../components/DataTable';
import { DetailShell, displayName, RawPropertiesCard } from '../components/detail';
import { Badge, BoolBadge, Card, EmptyState, ErrorBox, KeyValue, Mono, PageHeader, Spinner, StatusBadge, Tabs } from '../components/ui';
import { fmtValue, humanize } from '../lib/format';
import { objectPath } from '../lib/routes';
import { NameCell } from './Devices';

type Tab = 'networks' | 'wan' | 'routes' | 'vpn';

function dhcpRange(n: Network): string {
  if (!n.dhcp) return '';
  if (n.dhcp.enabled === false) return 'disabled';
  return n.dhcp.range_start ? `${n.dhcp.range_start} – ${n.dhcp.range_end ?? '?'}` : '';
}

function dnsText(n: Network): string {
  if (!n.dhcp) return '';
  if (n.dhcp.dns_servers?.length) return n.dhcp.dns_servers.join(', ');
  return n.dhcp.dns_mode ? humanize(n.dhcp.dns_mode) : '';
}

export function NetworksPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab) || 'networks';
  const networks = useEntities<Network>('network');
  const wans = useEntities('wan');
  const routes = useEntities('route');
  const vpns = useEntities('vpn');
  const setTab = (t: Tab) => setParams(t === 'networks' ? {} : { tab: t }, { replace: true });
  const current = { networks, wan: wans, routes, vpn: vpns }[tab];

  return (
    <div>
      <PageHeader title="VLANs and Networks" crumbs={[{ label: 'VLANs and Networks' }]} subtitle="LAN networks, DHCP, WAN connections, static routes and VPNs" />
      <Tabs<Tab>
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'networks', label: 'Networks / VLANs', count: networks.data?.items.length },
          { id: 'wan', label: 'WAN', count: wans.data?.items.length },
          { id: 'routes', label: 'Static routes', count: routes.data?.items.length },
          { id: 'vpn', label: 'VPN', count: vpns.data?.items.length },
        ]}
      />
      {current.isLoading ? (
        <Spinner />
      ) : current.error ? (
        <ErrorBox error={current.error} />
      ) : tab === 'networks' ? (
        <DataTable<Network>
          rows={networks.data?.items ?? []}
          rowKey={(n) => n.key}
          rowHref={(n) => objectPath('network', n.key)}
          initialSort={{ id: 'vlan', dir: 'asc' }}
          searchPlaceholder="Filter by name, VLAN, subnet…"
          emptyText="No networks found."
          columns={[
            { id: 'vlan', header: 'VLAN', value: (n) => n.vlan_id, cell: (n) => (n.vlan_id !== null && n.vlan_id !== undefined ? <Badge tone="blue">{n.vlan_id}</Badge> : '—') },
            { id: 'name', header: 'Name', value: (n) => displayName(n), cell: (n) => <NameCell name={n.name} manualName={n.manual?.display_name} /> },
            { id: 'subnet', header: 'Subnet', value: (n) => n.subnet, cell: (n) => (n.subnet ? <Mono>{n.subnet}</Mono> : '—') },
            { id: 'gateway', header: 'Gateway', value: (n) => n.gateway, cell: (n) => (n.gateway ? <Mono>{n.gateway}</Mono> : '—') },
            { id: 'dhcp', header: 'DHCP range', value: dhcpRange, cell: (n) => <span className="whitespace-nowrap font-mono text-xs">{dhcpRange(n) || '—'}</span> },
            { id: 'dns', header: 'DNS', value: dnsText },
            { id: 'purpose', header: 'Purpose', value: (n) => (n.purpose ? humanize(n.purpose) : ''), filter: true },
            { id: 'desc', header: 'Description', value: (n) => n.manual?.description ?? '', className: 'max-w-[18rem] truncate' },
          ]}
        />
      ) : tab === 'wan' ? (
        <DataTable<BaseEntity>
          rows={wans.data?.items ?? []}
          rowKey={(n) => n.key}
          rowHref={(n) => objectPath('wan', n.key)}
          emptyText="No WAN information available."
          columns={[
            { id: 'name', header: 'Name', value: (n) => displayName(n) },
            { id: 'status', header: 'Status', value: (n) => n.status, cell: (n) => <StatusBadge status={n.status as string} /> },
            { id: 'type', header: 'Connection type', value: (n) => n.type },
            { id: 'isp', header: 'ISP', value: (n) => n.isp },
            { id: 'address', header: 'IP address', value: (n) => (n.ipv4 as { address?: string } | null)?.address },
            { id: 'vlan', header: 'VLAN', value: (n) => n.vlan_id },
            { id: 'speed', header: 'Speed', value: (n) => n.speed },
            { id: 'desc', header: 'Description', value: (n) => n.description },
          ]}
        />
      ) : tab === 'routes' ? (
        <DataTable<BaseEntity>
          rows={routes.data?.items ?? []}
          rowKey={(n) => n.key}
          rowHref={(n) => objectPath('route', n.key)}
          emptyText="No static routes configured."
          columns={[
            { id: 'name', header: 'Name', value: (n) => displayName(n) },
            { id: 'enabled', header: 'Enabled', value: (n) => n.enabled, cell: (n) => <BoolBadge value={n.enabled as boolean} /> },
            { id: 'dest', header: 'Destinations', value: (n) => (n.destinations as string[]) ?? [] },
            { id: 'type', header: 'Type', value: (n) => (n.route_type ? humanize(String(n.route_type)) : '') },
            { id: 'hop', header: 'Next hop / interface', value: (n) => n.next_hop ?? n.interface },
            { id: 'metric', header: 'Metric', value: (n) => n.metric },
          ]}
        />
      ) : (
        <DataTable<BaseEntity>
          rows={vpns.data?.items ?? []}
          rowKey={(n) => n.key}
          rowHref={(n) => objectPath('vpn', n.key)}
          emptyText="No VPN configuration available."
          columns={[
            { id: 'name', header: 'Name', value: (n) => displayName(n) },
            { id: 'type', header: 'Type', value: (n) => n.type },
            { id: 'enabled', header: 'Enabled', value: (n) => n.enabled, cell: (n) => <BoolBadge value={n.enabled as boolean} /> },
            { id: 'remote', header: 'Remote', value: (n) => n.remote_ip ?? n.remote_site },
            { id: 'local', header: 'Local networks', value: (n) => (n.local_networks as string[]) ?? [] },
            { id: 'rsub', header: 'Remote subnets', value: (n) => (n.remote_subnets as string[]) ?? [] },
          ]}
        />
      )}
    </div>
  );
}

export function NetworkDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<Network>
      kind="network"
      objectKey={key}
      crumbs={[{ label: 'VLANs and Networks', to: '/networks' }]}
      icon={<NetworkIcon className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => (
        <>
          {d.entity.vlan_id !== null && d.entity.vlan_id !== undefined && <Badge tone="blue">VLAN {d.entity.vlan_id}</Badge>}
          {d.entity.subnet && <Mono>{d.entity.subnet}</Mono>}
        </>
      )}
    >
      {(d) => {
        const n = d.entity;
        const dhcp = n.dhcp;
        const ipv6 = n.ipv6 as { enabled?: boolean; mode?: string } | null | undefined;
        return (
          <>
            <Card title="Network">
              <KeyValue
                cols={3}
                items={[
                  { label: 'VLAN ID', value: n.vlan_id },
                  { label: 'Purpose', value: n.purpose ? humanize(n.purpose) : null },
                  { label: 'Application', value: n.application ? humanize(n.application) : null },
                  { label: 'Subnet', value: n.subnet ? <Mono>{n.subnet}</Mono> : null },
                  { label: 'Gateway', value: n.gateway ? <Mono>{n.gateway}</Mono> : null },
                  { label: 'Netmask', value: n.netmask },
                  { label: 'Domain', value: n.domain },
                  { label: 'Primary network', value: n.primary === undefined || n.primary === null ? null : n.primary ? 'Yes' : 'No' },
                  { label: 'Guest network', value: n.guest === undefined || n.guest === null ? null : n.guest ? 'Yes' : 'No' },
                  { label: 'IGMP snooping', value: n.igmp_snooping === undefined || n.igmp_snooping === null ? null : n.igmp_snooping ? 'On' : 'Off' },
                  { label: 'DHCP guard', value: n.dhcp_guard === undefined || n.dhcp_guard === null ? null : n.dhcp_guard ? 'On' : 'Off' },
                  { label: 'IPv6', value: ipv6 ? (ipv6.enabled ? humanize(ipv6.mode ?? 'enabled') : 'Disabled') : null },
                ]}
              />
            </Card>
            <Card title="DHCP server">
              {!dhcp ? (
                <EmptyState>No DHCP information available.</EmptyState>
              ) : (
                <>
                  <KeyValue
                    cols={3}
                    items={[
                      { label: 'DHCP', value: <BoolBadge value={dhcp.enabled} yes="Enabled" no="Disabled" /> },
                      { label: 'Range start', value: dhcp.range_start ? <Mono>{dhcp.range_start}</Mono> : null },
                      { label: 'Range end', value: dhcp.range_end ? <Mono>{dhcp.range_end}</Mono> : null },
                      { label: 'Lease time', value: dhcp.lease_minutes ? `${dhcp.lease_minutes} min` : null },
                      { label: 'DNS mode', value: dhcp.dns_mode ? humanize(dhcp.dns_mode) : null },
                      { label: 'DNS servers', value: dhcp.dns_servers?.length ? dhcp.dns_servers.join(', ') : null },
                      { label: 'Default gateway (DHCP)', value: dhcp.gateway },
                    ]}
                  />
                  <h3 className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-slate-500">Reservations ({dhcp.reservations?.length ?? 0})</h3>
                  {dhcp.reservations?.length ? (
                    <div className="overflow-x-auto">
                      <table className="table-base">
                        <thead>
                          <tr>
                            <th>Name</th>
                            <th>MAC</th>
                            <th>IP</th>
                            <th>Description</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dhcp.reservations.map((r, i) => (
                            <tr key={i}>
                              <td>{r.name ?? '—'}</td>
                              <td><Mono>{r.mac}</Mono></td>
                              <td><Mono>{r.ip}</Mono></td>
                              <td>{r.description ?? '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">No DHCP reservations.</p>
                  )}
                </>
              )}
            </Card>
            <RawPropertiesCard entity={n} />
          </>
        );
      }}
    </DetailShell>
  );
}

export function WanDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<BaseEntity>
      kind="wan"
      objectKey={key}
      crumbs={[{ label: 'VLANs and Networks', to: '/networks' }, { label: 'WAN', to: '/networks?tab=wan' }]}
      icon={<Globe className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => <StatusBadge status={d.entity.status as string} />}
    >
      {(d) => {
        const w = d.entity;
        const v4 = (w.ipv4 ?? {}) as Record<string, unknown>;
        const v6 = (w.ipv6 ?? {}) as Record<string, unknown>;
        return (
          <>
            <Card title="WAN connection">
              <KeyValue
                cols={3}
                items={[
                  { label: 'Status', value: <StatusBadge status={w.status as string} /> },
                  { label: 'Connection type', value: w.type as string },
                  { label: 'ISP', value: w.isp as string },
                  { label: 'Speed', value: w.speed as string },
                  { label: 'VLAN', value: w.vlan_id as number },
                  { label: 'Description', value: w.description as string },
                ]}
              />
            </Card>
            <Card title="IPv4">
              <KeyValue
                cols={3}
                items={[
                  { label: 'Type', value: v4.type as string },
                  { label: 'Address', value: v4.address ? <Mono>{String(v4.address)}</Mono> : null },
                  { label: 'Netmask', value: v4.netmask as string },
                  { label: 'Gateway', value: v4.gateway as string },
                  { label: 'DNS', value: fmtValue(v4.dns) === '—' ? null : fmtValue(v4.dns) },
                  { label: 'Settings', value: fmtValue(v4.settings) === '—' ? null : fmtValue(v4.settings) },
                ]}
              />
            </Card>
            <Card title="IPv6">
              <KeyValue
                cols={3}
                items={[
                  { label: 'Enabled', value: v6.enabled === undefined ? null : v6.enabled ? 'Yes' : 'No' },
                  { label: 'Type', value: v6.type as string },
                  { label: 'Address', value: v6.address as string },
                  { label: 'Gateway', value: v6.gateway as string },
                ]}
              />
            </Card>
            <RawPropertiesCard entity={w} />
          </>
        );
      }}
    </DetailShell>
  );
}

export function RouteDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<BaseEntity>
      kind="route"
      objectKey={key}
      crumbs={[{ label: 'VLANs and Networks', to: '/networks' }, { label: 'Static routes', to: '/networks?tab=routes' }]}
      icon={<Route className="h-5 w-5 text-brand-600" />}
    >
      {(d) => (
        <>
          <Card title="Static route">
            <KeyValue
              cols={3}
              items={[
                { label: 'Enabled', value: <BoolBadge value={d.entity.enabled as boolean} /> },
                { label: 'Destinations', value: fmtValue(d.entity.destinations) },
                { label: 'Route type', value: d.entity.route_type ? humanize(String(d.entity.route_type)) : null },
                { label: 'Next hop', value: d.entity.next_hop as string },
                { label: 'Interface', value: (d.entity.interface as string) ?? null },
                { label: 'Metric', value: d.entity.metric as number },
              ]}
            />
          </Card>
          <RawPropertiesCard entity={d.entity} />
        </>
      )}
    </DetailShell>
  );
}

export function VpnDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<BaseEntity>
      kind="vpn"
      objectKey={key}
      crumbs={[{ label: 'VLANs and Networks', to: '/networks' }, { label: 'VPN', to: '/networks?tab=vpn' }]}
      icon={<ShieldCheck className="h-5 w-5 text-brand-600" />}
    >
      {(d) => (
        <>
          <Card title="VPN">
            <KeyValue
              cols={3}
              items={[
                { label: 'Type', value: d.entity.type as string },
                { label: 'Enabled', value: <BoolBadge value={d.entity.enabled as boolean} /> },
                { label: 'Remote gateway', value: d.entity.remote_ip as string },
                { label: 'Remote site', value: d.entity.remote_site as string },
                { label: 'Local networks', value: fmtValue(d.entity.local_networks) },
                { label: 'Remote subnets', value: fmtValue(d.entity.remote_subnets) },
                { label: 'Working mode', value: d.entity.working_mode as string },
              ]}
            />
            <p className="mt-3 text-xs text-slate-500">Pre-shared keys and certificates are never collected or displayed.</p>
          </Card>
          <RawPropertiesCard entity={d.entity} />
        </>
      )}
    </DetailShell>
  );
}
