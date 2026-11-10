import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowUpCircle, Cable, Zap } from 'lucide-react';
import { useEntities } from '../api/hooks';
import type { BaseEntity, Device, SwitchPort } from '../api/types';
import { DataTable, type Column } from '../components/DataTable';
import { DetailShell, displayName, ObjectLink, RawPropertiesCard } from '../components/detail';
import { Badge, Card, cx, EmptyState, ErrorBox, KeyValue, Mono, PageHeader, Spinner, StatusBadge, Tabs } from '../components/ui';
import { fmtBytes, fmtValue, humanize } from '../lib/format';
import { objectPath } from '../lib/routes';
import { NameCell } from './Devices';

/* ------------------------------------------------------------------ port panel */

function portTone(p: SwitchPort): string {
  if (p.link_status === 'up') {
    if (p.link_role === 'uplink') return 'border-sky-500 bg-sky-500 text-white';
    return 'border-emerald-600 bg-emerald-500 text-white';
  }
  if (p.link_status === 'disabled') return 'border-slate-300 bg-slate-200 text-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500';
  if (p.link_status === 'down') return 'border-slate-400 bg-slate-100 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300';
  return 'border-dashed border-slate-400 bg-white text-slate-500 dark:bg-slate-900';
}

function portTitle(p: SwitchPort): string {
  const parts = [
    `Port ${p.port}${p.name && p.name !== `Port${p.port}` ? ` – ${p.name}` : ''}`,
    `Link: ${p.link_status ?? 'unknown'}${p.speed ? ` (${p.speed})` : ''}`,
    p.link_role ? `Role: ${p.link_role}` : '',
    p.native_network ? `Native: ${p.native_network}${p.native_vlan_id ? ` (VLAN ${p.native_vlan_id})` : ''}` : '',
    p.poe?.active ? `PoE: ${p.poe.power_w ?? '?'} W` : '',
    p.connected?.length ? `Connected: ${p.connected.map((c) => c.name ?? c.mac).join(', ')}` : '',
    p.manual?.description ? `Note: ${p.manual.description.slice(0, 80)}` : '',
  ];
  return parts.filter(Boolean).join('\n');
}

function PortSquare({ p }: { p: SwitchPort }) {
  const isFiber = (p.port_type ?? '').toLowerCase().includes('sfp') || (p.port_type ?? '').toLowerCase().includes('fib');
  const to = objectPath('switch_port', p.key) ?? '#';
  return (
    <Link
      to={to}
      title={portTitle(p)}
      className={cx(
        'relative flex h-11 w-11 flex-col items-center justify-center border-2 text-xs font-semibold shadow-sm transition-transform hover:scale-110 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500',
        isFiber ? 'rounded-sm' : 'rounded-md',
        portTone(p),
      )}
      aria-label={`Port ${p.port}, link ${p.link_status ?? 'unknown'}`}
    >
      <span>{p.port}</span>
      {isFiber && <span className="text-[8px] font-normal leading-none">SFP</span>}
      {p.poe?.active && <Zap className="absolute -right-1 -top-1 h-3.5 w-3.5 fill-yellow-300 text-yellow-600" />}
      {p.link_role === 'uplink' && <ArrowUpCircle className="absolute -left-1 -top-1 h-3.5 w-3.5 rounded-full bg-white text-sky-600" />}
      {p.manual && <span className="absolute -bottom-1 -right-1 h-2.5 w-2.5 rounded-full border border-white bg-brand-500" />}
    </Link>
  );
}

export function PortPanel({ ports }: { ports: SwitchPort[] }) {
  const sorted = [...ports].sort((a, b) => (a.port ?? 0) - (b.port ?? 0));
  const copper = sorted.filter((p) => !/sfp|fib/i.test(p.port_type ?? ''));
  const fiber = sorted.filter((p) => /sfp|fib/i.test(p.port_type ?? ''));
  const top = copper.filter((_, i) => i % 2 === 0);
  const bottom = copper.filter((_, i) => i % 2 === 1);
  const totalPoe = ports.reduce((s, p) => s + (p.poe?.power_w ?? 0), 0);
  return (
    <div>
      <div className="overflow-x-auto">
        <div className="inline-flex gap-4 rounded-lg border border-slate-300 bg-gradient-to-b from-slate-100 to-slate-200 p-3 dark:border-slate-700 dark:from-slate-800 dark:to-slate-900">
          <div className="flex flex-col gap-2">
            <div className="flex gap-1.5">{top.map((p) => <PortSquare key={p.key} p={p} />)}</div>
            {bottom.length > 0 && <div className="flex gap-1.5">{bottom.map((p) => <PortSquare key={p.key} p={p} />)}</div>}
          </div>
          {fiber.length > 0 && (
            <div className="flex flex-col flex-wrap gap-2 border-l border-slate-300 pl-4 dark:border-slate-600">
              <div className="flex gap-1.5">{fiber.map((p) => <PortSquare key={p.key} p={p} />)}</div>
            </div>
          )}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-emerald-500" /> Link up</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-sky-500" /> Uplink</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm border border-slate-400 bg-slate-100 dark:bg-slate-800" /> Link down</span>
        <span className="flex items-center gap-1"><span className="h-3 w-3 rounded-sm border border-dashed border-slate-400" /> Unknown</span>
        <span className="flex items-center gap-1"><Zap className="h-3 w-3 fill-yellow-300 text-yellow-600" /> PoE active</span>
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-brand-500" /> Manually documented</span>
        <span className="ml-auto">
          {ports.filter((p) => p.link_status === 'up').length}/{ports.length} ports up · PoE {totalPoe.toFixed(1)} W
        </span>
      </div>
    </div>
  );
}

export function connectedText(p: SwitchPort): string {
  return (p.connected ?? []).map((c) => c.name ?? c.mac ?? '').filter(Boolean).join(', ');
}

export function portColumns(withSwitch = false): Column<SwitchPort>[] {
  const cols: Column<SwitchPort>[] = [
    { id: 'port', header: 'Port', value: (p) => p.port, cell: (p) => <span className="font-semibold">{p.port}</span> },
    ...(withSwitch ? [{ id: 'switch', header: 'Switch', value: (p: SwitchPort) => p.switch_name, filter: true } as Column<SwitchPort>] : []),
    { id: 'name', header: 'Name', value: (p) => displayName(p), cell: (p) => <NameCell name={p.name} manualName={p.manual?.display_name} /> },
    {
      id: 'link',
      header: 'Link',
      value: (p) => p.link_status,
      cell: (p) => (
        <span className="flex flex-wrap items-center gap-1">
          <StatusBadge status={p.link_status} />
          {p.speed && <span className="text-xs text-slate-500">{p.speed}</span>}
          {p.link_role === 'uplink' && <Badge tone="blue">uplink</Badge>}
        </span>
      ),
      filter: true,
    },
    { id: 'poe', header: 'PoE W', value: (p) => (p.poe?.active ? (p.poe.power_w ?? 0) : null), cell: (p) => (p.poe?.active ? `${p.poe.power_w ?? '?'} W` : p.poe?.supported ? <span className="text-slate-400">off</span> : '—') },
    { id: 'profile', header: 'Profile', value: (p) => p.profile_name, filter: true },
    { id: 'native', header: 'Native VLAN', value: (p) => (p.native_network ? `${p.native_network}${p.native_vlan_id ? ` (${p.native_vlan_id})` : ''}` : '') },
    {
      id: 'tagged',
      header: 'Tagged VLANs',
      value: (p) => p.tagged_networks ?? [],
      cell: (p) => (p.tagged_networks?.length ? <span className="text-xs">{p.tagged_networks.join(', ')}</span> : '—'),
    },
    {
      id: 'connected',
      header: 'Connected device',
      value: connectedText,
      cell: (p) =>
        p.connected?.length ? (
          <span className="flex flex-col">
            {p.connected.map((c, i) => (
              <span key={i}>
                {c.mac ? (
                  <ObjectLink type={c.type === 'client' || !c.type ? 'client' : 'device'} id={c.mac} deviceType={c.type}>
                    {c.name ?? c.mac}
                  </ObjectLink>
                ) : (
                  c.name
                )}
                {c.source && c.source !== 'api' && <span className="ml-1 text-[10px] text-slate-500">({c.source})</span>}
              </span>
            ))}
          </span>
        ) : (
          '—'
        ),
    },
    { id: 'desc', header: 'Description', value: (p) => p.manual?.description ?? '', className: 'max-w-[16rem] truncate' },
  ];
  return cols;
}

export function SwitchPortsSection({ switchMac }: { switchMac: string }) {
  const q = useEntities<SwitchPort>('switch_port');
  const ports = useMemo(() => (q.data?.items ?? []).filter((p) => p.switch_mac === switchMac), [q.data, switchMac]);
  if (q.isLoading) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <>
      <Card title="Port panel" icon={<Cable className="h-4 w-4 text-slate-500" />} subtitle="Click a port to open its details">
        {ports.length ? <PortPanel ports={ports} /> : <EmptyState>No port information available for this switch.</EmptyState>}
      </Card>
      <DataTable
        rows={ports}
        columns={portColumns()}
        rowKey={(p) => p.key}
        rowHref={(p) => objectPath('switch_port', p.key)}
        initialSort={{ id: 'port', dir: 'asc' }}
        defaultPageSize={50}
        compact
      />
    </>
  );
}

/* ------------------------------------------------------------------ pages */

type SwitchesTab = 'switches' | 'ports' | 'profiles';

export function SwitchesPage() {
  const [tab, setTab] = useState<SwitchesTab>('switches');
  const devices = useEntities<Device>('device');
  const ports = useEntities<SwitchPort>('switch_port');
  const profiles = useEntities('port_profile');
  const switches = (devices.data?.items ?? []).filter((d) => d.type === 'switch');
  const allPorts = ports.data?.items ?? [];

  return (
    <div>
      <PageHeader title="Switches and Ports" crumbs={[{ label: 'Switches and Ports' }]} subtitle="Switch port documentation: link state, PoE, VLAN assignment and connected devices" />
      <Tabs<SwitchesTab>
        active={tab}
        onChange={setTab}
        tabs={[
          { id: 'switches', label: 'Switches', count: switches.length },
          { id: 'ports', label: 'All ports', count: allPorts.length },
          { id: 'profiles', label: 'Port profiles', count: profiles.data?.items.length },
        ]}
      />
      {devices.isLoading || ports.isLoading ? (
        <Spinner />
      ) : devices.error || ports.error ? (
        <ErrorBox error={devices.error ?? ports.error} />
      ) : tab === 'switches' ? (
        switches.length === 0 ? (
          <Card><EmptyState>No switches found.</EmptyState></Card>
        ) : (
          <div className="space-y-4">
            {switches.map((s) => {
              const sp = allPorts.filter((p) => p.switch_mac === s.key);
              return (
                <Card
                  key={s.key}
                  title={
                    <Link to={objectPath('device', s.key, { deviceType: 'switch' }) ?? '#'} className="link">
                      {displayName(s)}
                    </Link>
                  }
                  subtitle={[s.model, s.ip, s.manual?.location].filter(Boolean).join(' · ')}
                  actions={<StatusBadge status={s.status} />}
                >
                  {sp.length ? <PortPanel ports={sp} /> : <EmptyState>No port information available.</EmptyState>}
                </Card>
              );
            })}
          </div>
        )
      ) : tab === 'ports' ? (
        <DataTable
          rows={allPorts}
          columns={portColumns(true)}
          rowKey={(p) => p.key}
          rowHref={(p) => objectPath('switch_port', p.key)}
          initialSort={{ id: 'switch', dir: 'asc' }}
          defaultPageSize={50}
          compact
        />
      ) : (
        <DataTable
          rows={profiles.data?.items ?? []}
          columns={[
            { id: 'name', header: 'Name', value: (p) => displayName(p) },
            { id: 'native', header: 'Native network', value: (p) => p.native_network as string },
            { id: 'tagged', header: 'Tagged networks', value: (p) => (p.tagged_networks as string[]) ?? [] },
            { id: 'untagged', header: 'Untagged networks', value: (p) => (p.untagged_networks as string[]) ?? [] },
            { id: 'poe', header: 'PoE', value: (p) => p.poe as string },
            { id: 'type', header: 'Type', value: (p) => p.profile_type as string, filter: true },
          ]}
          rowKey={(p) => p.key}
          rowHref={(p) => objectPath('port_profile', p.key)}
        />
      )}
    </div>
  );
}

export function PortDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<SwitchPort>
      kind="switch_port"
      objectKey={key}
      crumbs={(d) => [
        { label: 'Switches and Ports', to: '/switches' },
        ...(d.entity.switch_mac ? [{ label: d.entity.switch_name ?? d.entity.switch_mac, to: objectPath('device', d.entity.switch_mac, { deviceType: 'switch' }) ?? undefined }] : []),
      ]}
      icon={<Cable className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => (
        <>
          {d.entity.switch_mac && (
            <span>
              on{' '}
              <ObjectLink type="device" id={d.entity.switch_mac} deviceType="switch">
                {d.entity.switch_name ?? d.entity.switch_mac}
              </ObjectLink>
            </span>
          )}
          <StatusBadge status={d.entity.link_status} />
        </>
      )}
    >
      {(d) => {
        const p = d.entity;
        return (
          <>
            <Card title="Port state">
              <KeyValue
                cols={3}
                items={[
                  { label: 'Port number', value: p.port },
                  { label: 'Port type', value: p.port_type },
                  { label: 'Link status', value: <StatusBadge status={p.link_status} /> },
                  { label: 'Speed', value: p.speed },
                  { label: 'Duplex', value: p.duplex },
                  { label: 'Configured speed', value: p.configured_speed as string },
                  { label: 'Link role', value: p.link_role },
                  { label: 'LAG', value: p.lag === null || p.lag === undefined ? null : p.lag ? 'Yes' : 'No' },
                  { label: 'Port isolation', value: fmtValue(p.port_isolation) === '—' ? null : fmtValue(p.port_isolation) },
                  { label: 'Received', value: typeof p.rx_bytes === 'number' ? fmtBytes(p.rx_bytes) : null },
                  { label: 'Transmitted', value: typeof p.tx_bytes === 'number' ? fmtBytes(p.tx_bytes) : null },
                  { label: 'Warning', value: p.warning, hidden: !p.warning },
                ]}
              />
            </Card>
            <Card title="VLAN configuration">
              <KeyValue
                items={[
                  {
                    label: 'Profile',
                    value: p.profile_id ? (
                      <ObjectLink type="port_profile" id={p.profile_id}>
                        {p.profile_name ?? p.profile_id}
                      </ObjectLink>
                    ) : (
                      p.profile_name
                    ),
                  },
                  { label: 'Profile override', value: fmtValue(p.profile_override) === '—' ? null : fmtValue(p.profile_override) },
                  { label: 'Mode', value: p.network_mode ? humanize(p.network_mode) : null },
                  {
                    label: 'Native (untagged) network',
                    value: p.native_network_id ? (
                      <ObjectLink type="network" id={p.native_network_id}>
                        {p.native_network ?? p.native_network_id}
                        {p.native_vlan_id ? ` (VLAN ${p.native_vlan_id})` : ''}
                      </ObjectLink>
                    ) : (
                      p.native_network
                    ),
                  },
                  { label: 'Tagged networks', value: p.tagged_networks?.length ? p.tagged_networks.join(', ') : null },
                  { label: 'Additional untagged', value: p.untagged_networks?.length ? p.untagged_networks.join(', ') : null },
                ]}
              />
            </Card>
            <Card title="Power over Ethernet">
              {p.poe?.supported === false ? (
                <p className="text-sm text-slate-500">This port does not support PoE.</p>
              ) : (
                <KeyValue
                  cols={3}
                  items={[
                    { label: 'Supported', value: p.poe?.supported === undefined || p.poe?.supported === null ? null : p.poe.supported ? 'Yes' : 'No' },
                    { label: 'Enabled', value: p.poe?.enabled === undefined || p.poe?.enabled === null ? null : p.poe.enabled ? 'Yes' : 'No' },
                    { label: 'Delivering power', value: p.poe?.active === undefined || p.poe?.active === null ? null : p.poe.active ? 'Yes' : 'No' },
                    { label: 'Power', value: p.poe?.power_w !== null && p.poe?.power_w !== undefined ? `${p.poe.power_w} W` : null },
                    { label: 'PD class', value: p.poe?.pd_class },
                  ]}
                />
              )}
            </Card>
            <Card title="Connected devices">
              {p.connected?.length ? (
                <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
                  {p.connected.map((c, i) => (
                    <li key={i} className="flex flex-wrap items-center gap-2 py-1.5">
                      {c.mac ? (
                        <ObjectLink type={c.type === 'client' || !c.type ? 'client' : 'device'} id={c.mac} deviceType={c.type}>
                          {c.name ?? c.mac}
                        </ObjectLink>
                      ) : (
                        <span>{c.name ?? 'Unknown'}</span>
                      )}
                      {c.type && <Badge tone="gray">{humanize(c.type)}</Badge>}
                      {c.relation && <span className="text-xs text-slate-500">{humanize(c.relation)}</span>}
                      {c.mac && <Mono>{c.mac}</Mono>}
                      {c.source && <Badge tone={c.source === 'manual' ? 'brand' : c.source === 'lldp' ? 'blue' : 'gray'}>{c.source}</Badge>}
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState>No connected device known for this port.</EmptyState>
              )}
              {p.lldp !== null && p.lldp !== undefined && (
                <div className="mt-3">
                  <div className="label">LLDP neighbour</div>
                  <pre className="whitespace-pre-wrap font-mono text-xs">{JSON.stringify(p.lldp, null, 1)}</pre>
                </div>
              )}
            </Card>
            <RawPropertiesCard entity={p} />
          </>
        );
      }}
    </DetailShell>
  );
}

export function PortProfileDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<BaseEntity>
      kind="port_profile"
      objectKey={key}
      crumbs={[{ label: 'Switches and Ports', to: '/switches' }, { label: 'Port profiles' }]}
      icon={<Cable className="h-5 w-5 text-brand-600" />}
    >
      {(d) => {
        const p = d.entity;
        return (
          <>
            <Card title="Profile settings">
              <KeyValue
                items={[
                  {
                    label: 'Native network',
                    value: p.native_network_id ? (
                      <ObjectLink type="network" id={String(p.native_network_id)}>
                        {String(p.native_network ?? p.native_network_id)}
                      </ObjectLink>
                    ) : null,
                  },
                  { label: 'Tagged networks', value: fmtValue(p.tagged_networks) },
                  { label: 'Untagged networks', value: fmtValue(p.untagged_networks) },
                  { label: 'Voice network', value: p.voice_network_id ? String(p.voice_network_id) : null },
                  { label: 'PoE', value: p.poe ? String(p.poe) : null },
                  { label: 'Profile type', value: p.profile_type ? String(p.profile_type) : null },
                  { label: '802.1X', value: fmtValue(p.dot1x) === '—' ? null : fmtValue(p.dot1x) },
                  { label: 'Spanning tree', value: fmtValue(p.spanning_tree) === '—' ? null : fmtValue(p.spanning_tree) },
                  { label: 'Port isolation', value: fmtValue(p.port_isolation) === '—' ? null : fmtValue(p.port_isolation) },
                  { label: 'Loopback detection', value: fmtValue(p.loopback_detect) === '—' ? null : fmtValue(p.loopback_detect) },
                ]}
              />
            </Card>
            <RawPropertiesCard entity={p} />
          </>
        );
      }}
    </DetailShell>
  );
}
