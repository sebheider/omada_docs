import { useParams } from 'react-router-dom';
import { Building2, Server } from 'lucide-react';
import type { BaseEntity } from '../api/types';
import { DetailShell, RawPropertiesCard } from '../components/detail';
import { Card, KeyValue, Mono, StatusBadge } from '../components/ui';
import { fmtSeconds, fmtValue } from '../lib/format';

export function SiteDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<BaseEntity>
      kind="site"
      objectKey={key}
      crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Sites' }]}
      icon={<Building2 className="h-5 w-5 text-brand-600" />}
    >
      {(d) => (
        <>
          <Card title="Site">
            <KeyValue
              cols={3}
              items={[
                { label: 'Site ID', value: <Mono>{d.entity.key}</Mono> },
                { label: 'Region', value: d.entity.region as string },
                { label: 'Time zone', value: d.entity.timezone as string },
                { label: 'Scenario', value: d.entity.scenario as string },
                { label: 'Address', value: d.entity.address as string },
                { label: 'Type', value: d.entity.site_type as string },
                { label: 'Primary site', value: d.entity.primary === undefined ? null : d.entity.primary ? 'Yes' : 'No' },
              ]}
            />
          </Card>
          <RawPropertiesCard entity={d.entity} />
        </>
      )}
    </DetailShell>
  );
}

export function ControllerPage() {
  return (
    <DetailShell<BaseEntity>
      kind="controller"
      objectKey="controller"
      crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Controller' }]}
      icon={<Server className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => <StatusBadge status={d.entity.status as string} />}
    >
      {(d) => (
        <>
          <Card title="Omada controller">
            <KeyValue
              cols={3}
              items={[
                { label: 'Model / type', value: (d.entity.model as string) ?? (d.entity.controller_type as string) },
                { label: 'Version', value: d.entity.version as string },
                { label: 'Open API version', value: d.entity.api_version as string },
                { label: 'Controller ID', value: d.entity.controller_id ? <Mono>{d.entity.controller_id}</Mono> : null },
                { label: 'Host', value: d.entity.host as string },
                { label: 'MAC', value: d.entity.mac ? <Mono>{String(d.entity.mac)}</Mono> : null },
                { label: 'Serial', value: d.entity.serial as string },
                { label: 'Time zone', value: d.entity.timezone as string },
                { label: 'Uptime', value: d.entity.uptime_seconds ? fmtSeconds(Number(d.entity.uptime_seconds)) : null },
                { label: 'Capacity', value: d.entity.capacity ? fmtValue(d.entity.capacity) : null },
              ]}
            />
          </Card>
          <RawPropertiesCard entity={d.entity} />
        </>
      )}
    </DetailShell>
  );
}
