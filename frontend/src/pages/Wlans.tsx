import { useParams } from 'react-router-dom';
import { Wifi } from 'lucide-react';
import { useEntities } from '../api/hooks';
import type { Wlan } from '../api/types';
import { DataTable } from '../components/DataTable';
import { DetailShell, displayName, ObjectLink, RawPropertiesCard } from '../components/detail';
import { Badge, BoolBadge, Card, ErrorBox, KeyValue, PageHeader, Spinner } from '../components/ui';
import { fmtValue, humanize } from '../lib/format';
import { objectPath } from '../lib/routes';
import { NameCell } from './Devices';

function vlanText(w: Wlan): string {
  if (w.network_name) return `${w.network_name}${w.vlan_id ? ` (VLAN ${w.vlan_id})` : ''}`;
  if (w.vlan_enabled && w.vlan_id) return `VLAN ${w.vlan_id}`;
  return w.vlan_enabled === false ? 'Default (untagged)' : '';
}

function apText(w: Wlan): string {
  if (!w.ap_assignment) return '';
  if (w.ap_assignment === 'all') return 'All access points';
  return `${humanize(w.ap_assignment)}${w.ap_group_ids?.length ? ` (${w.ap_group_ids.length} groups)` : ''}`;
}

export function WlansPage() {
  const q = useEntities<Wlan>('wlan');
  return (
    <div>
      <PageHeader title="WLAN" crumbs={[{ label: 'WLAN' }]} subtitle="Wireless networks (SSIDs). Passwords and keys are never collected or shown." />
      {q.isLoading ? (
        <Spinner />
      ) : q.error ? (
        <ErrorBox error={q.error} />
      ) : (
        <DataTable<Wlan>
          rows={q.data?.items ?? []}
          rowKey={(w) => w.key}
          rowHref={(w) => objectPath('wlan', w.key)}
          initialSort={{ id: 'ssid', dir: 'asc' }}
          emptyText="No WLANs found."
          columns={[
            { id: 'ssid', header: 'SSID', value: (w) => w.ssid ?? displayName(w), cell: (w) => <NameCell name={w.ssid ?? w.name} manualName={w.manual?.display_name} sub={w.wlan_group ? `Group: ${w.wlan_group}` : null} /> },
            { id: 'enabled', header: 'Enabled', value: (w) => w.enabled, cell: (w) => <BoolBadge value={w.enabled} />, filter: true },
            { id: 'bands', header: 'Bands', value: (w) => w.bands ?? [], cell: (w) => <span className="flex flex-wrap gap-1">{(w.bands ?? []).map((b) => <Badge key={b} tone="gray">{b}</Badge>)}</span> },
            { id: 'security', header: 'Security', value: (w) => w.security, cell: (w) => <span>{w.security ?? '—'}{w.security_version && <span className="block text-xs text-slate-500">{w.security_version}</span>}</span>, filter: true },
            {
              id: 'vlan',
              header: 'VLAN / network',
              value: vlanText,
              cell: (w) => (w.network_id ? <ObjectLink type="network" id={w.network_id}>{vlanText(w)}</ObjectLink> : vlanText(w) || '—'),
            },
            { id: 'guest', header: 'Guest', value: (w) => w.guest, cell: (w) => (w.guest ? <Badge tone="amber">Guest</Badge> : <span className="text-slate-400">No</span>) },
            { id: 'ap', header: 'AP assignment', value: apText },
            { id: 'clients', header: 'Clients', value: (w) => w.client_count ?? null },
          ]}
        />
      )}
    </div>
  );
}

export function WlanDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<Wlan>
      kind="wlan"
      objectKey={key}
      crumbs={[{ label: 'WLAN', to: '/wlans' }]}
      icon={<Wifi className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => (
        <>
          <BoolBadge value={d.entity.enabled} yes="Enabled" no="Disabled" />
          {d.entity.guest && <Badge tone="amber">Guest</Badge>}
        </>
      )}
    >
      {(d) => {
        const w = d.entity;
        const schedule = w.schedule as { enabled?: boolean; action?: string | null } | null | undefined;
        return (
          <>
            <Card title="Wireless settings">
              <KeyValue
                cols={3}
                items={[
                  { label: 'SSID', value: w.ssid },
                  { label: 'WLAN group', value: w.wlan_group },
                  { label: 'Broadcast SSID', value: w.broadcast === undefined || w.broadcast === null ? null : w.broadcast ? 'Yes' : 'Hidden' },
                  { label: 'Bands', value: w.bands?.join(', ') },
                  { label: 'Security', value: w.security },
                  { label: 'Security version', value: w.security_version },
                  { label: 'Encryption', value: w.encryption as string },
                  { label: 'PMF', value: w.pmf as string },
                  { label: 'Fast roaming (802.11r)', value: w.fast_roaming_11r === undefined || w.fast_roaming_11r === null ? null : w.fast_roaming_11r ? 'On' : 'Off' },
                  { label: 'MLO', value: w.mlo === null || w.mlo === undefined ? null : fmtValue(w.mlo) },
                  { label: 'MAC filter', value: w.mac_filter === null || w.mac_filter === undefined ? null : fmtValue(w.mac_filter) },
                  { label: 'Schedule', value: schedule ? (schedule.enabled ? `Active (${schedule.action ?? 'scheduled'})` : 'None') : null },
                ]}
              />
              <p className="mt-3 text-xs text-slate-500">The WLAN password / pre-shared key is intentionally never collected or displayed.</p>
            </Card>
            <Card title="Network & assignment">
              <KeyValue
                cols={3}
                items={[
                  { label: 'VLAN enabled', value: w.vlan_enabled === undefined || w.vlan_enabled === null ? null : w.vlan_enabled ? 'Yes' : 'No' },
                  { label: 'VLAN ID', value: w.vlan_id },
                  {
                    label: 'Network',
                    value: w.network_id ? (
                      <ObjectLink type="network" id={w.network_id}>
                        {w.network_name ?? w.network_id}
                      </ObjectLink>
                    ) : null,
                  },
                  { label: 'Network source', value: w.network_source ? humanize(String(w.network_source)) : null },
                  { label: 'Guest network', value: w.guest === undefined || w.guest === null ? null : w.guest ? 'Yes' : 'No' },
                  { label: 'AP assignment', value: apText(w) || null },
                  { label: 'Connected clients', value: w.client_count ?? null },
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
