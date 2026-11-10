import { QUALITY_LABELS } from './Quality';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowLeftRight,
  ClipboardCheck,
  Download,
  History,
  Network,
  RefreshCw,
  Router,
  Server,
  Settings,
  Shield,
  Users,
  Wifi,
} from 'lucide-react';
import { post } from '../api/client';
import { useDashboard, useSyncStatus } from '../api/hooks';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import { Badge, Card, cx, EmptyState, ErrorBox, KeyValue, PageHeader, Spinner, StatusBadge } from '../components/ui';
import { ObjectLink } from '../components/detail';
import { fmtDate, fmtDuration, fmtRelative, fmtSeconds, humanize, kindLabel } from '../lib/format';

function StatCard({
  icon,
  label,
  value,
  sub,
  to,
  tone = 'default',
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  to?: string;
  tone?: 'default' | 'warn' | 'bad' | 'good';
}) {
  const body = (
    <div className={cx('card flex h-full items-start gap-3 p-4 transition-shadow', to && 'hover:shadow-md')}>
      <div
        className={cx(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
          tone === 'bad'
            ? 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300'
            : tone === 'warn'
              ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300'
              : tone === 'good'
                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300'
                : 'bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300',
        )}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
        <div className="text-2xl font-semibold leading-tight text-slate-900 dark:text-white">{value}</div>
        {sub && <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{sub}</div>}
      </div>
    </div>
  );
  return to ? (
    <Link to={to} className="block">
      {body}
    </Link>
  ) : (
    body
  );
}

export function SyncNowButton({ className }: { className?: string }) {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const status = useSyncStatus();
  const m = useMutation({
    mutationFn: () => post<{ started: boolean }>('sync'),
    onSuccess: () => {
      toast.notify('Synchronization started');
      void qc.invalidateQueries({ queryKey: ['sync-status'] });
      void qc.invalidateQueries({ queryKey: ['sync-history'] });
    },
    onError: (e) => toast.error(e),
  });
  if (!isAdmin) return null;
  const running = status.data?.running || m.isPending;
  return (
    <button className={cx('btn-primary', className)} onClick={() => m.mutate()} disabled={running}>
      <RefreshCw className={cx('h-4 w-4', running && 'animate-spin')} />
      {running ? 'Synchronizing…' : 'Sync now'}
    </button>
  );
}

const TYPE_LABELS: Record<string, string> = { gateway: 'Gateways', switch: 'Switches', ap: 'Access points' };

export function DashboardPage() {
  const { data, isLoading, error } = useDashboard();
  const { isAdmin } = useAuth();
  if (isLoading) return <Spinner />;
  if (error || !data) return <ErrorBox error={error} />;

  const devTotal = Object.values(data.devices_by_type).reduce((a, b) => a + b.total, 0);
  const devOnline = Object.values(data.devices_by_type).reduce((a, b) => a + b.online, 0);
  const last = data.sync.last;
  const controller = data.controller;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Dashboard"
        subtitle={controller ? `${controller.name ?? 'Omada Controller'} · ${String(controller.version ?? '')}` : 'Network documentation overview'}
        actions={
          <>
            <SyncNowButton />
            <Link to="/export" className="btn-secondary">
              <Download className="h-4 w-4" /> Export
            </Link>
          </>
        }
      />

      {!data.configured && !data.demo_mode && (
        <div className="card flex flex-wrap items-center gap-4 border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
          <AlertTriangle className="h-8 w-8 text-amber-600" />
          <div className="flex-1">
            <div className="font-semibold">The Omada controller connection is not configured yet</div>
            <div className="text-sm text-slate-600 dark:text-slate-300">
              Enter the controller address and the Open API client credentials to start collecting the network documentation.
            </div>
          </div>
          {isAdmin ? (
            <Link to="/settings" className="btn-primary">
              <Settings className="h-4 w-4" /> Configure controller
            </Link>
          ) : (
            <span className="text-sm">Please ask an administrator to configure the controller.</span>
          )}
        </div>
      )}
      {data.configured && data.syncs_total === 0 && (
        <div className="card p-4 text-sm">No synchronization has been run yet. {isAdmin && 'Use “Sync now” to collect the controller data.'}</div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={<Router className="h-5 w-5" />}
          label="Devices online"
          value={`${devOnline} / ${devTotal}`}
          tone={devOnline < devTotal ? 'warn' : devTotal ? 'good' : 'default'}
          to="/devices"
          sub={
            <span className="flex flex-wrap gap-x-3">
              {Object.entries(data.devices_by_type).map(([t, v]) => (
                <span key={t}>
                  {TYPE_LABELS[t] ?? humanize(t)}: {v.online}/{v.total}
                </span>
              ))}
            </span>
          }
        />
        <StatCard
          icon={<Network className="h-5 w-5" />}
          label="Networks / VLANs"
          value={data.counts.network ?? 0}
          to="/networks"
          sub={`${data.counts.wan ?? 0} WAN · ${data.counts.route ?? 0} routes · ${data.counts.vpn ?? 0} VPN`}
        />
        <StatCard icon={<Wifi className="h-5 w-5" />} label="WLANs" value={data.counts.wlan ?? 0} to="/wlans" sub={`${data.counts.switch_port ?? 0} switch ports documented`} />
        <StatCard
          icon={<Users className="h-5 w-5" />}
          label="Clients"
          value={data.clients.total}
          to="/clients"
          sub={`${data.clients.wireless} wireless · ${data.clients.wired} wired`}
        />
        <StatCard
          icon={<Shield className="h-5 w-5" />}
          label="ACL rules"
          value={data.acl.total}
          to="/acl"
          tone={data.acl.low_confidence || data.acl.shadowed ? 'warn' : 'default'}
          sub={`${data.acl.low_confidence} uncertain · ${data.acl.shadowed} shadowed`}
        />
        <StatCard icon={<ArrowLeftRight className="h-5 w-5" />} label="NAT rules" value={data.counts.nat_rule ?? 0} to="/nat" />
        <StatCard
          icon={<History className="h-5 w-5" />}
          label="Changes (7 days)"
          value={data.changes_7d.config + data.changes_7d.manual}
          to="/changes"
          sub={`${data.changes_7d.config} configuration · ${data.changes_7d.manual} manual`}
        />
        <StatCard
          icon={<ClipboardCheck className="h-5 w-5" />}
          label="Data quality issues"
          value={data.quality.total}
          to="/quality"
          tone={data.quality.total ? 'warn' : 'good'}
          sub="Missing descriptions, conflicts, unresolved links"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Synchronization"
          icon={<RefreshCw className="h-4 w-4 text-slate-500" />}
          actions={
            <Link to="/sync" className="text-xs link">
              Details
            </Link>
          }
        >
          {last ? (
            <KeyValue
              items={[
                { label: 'Last run', value: <span className="flex items-center gap-2"><StatusBadge status={data.sync.running ? 'running' : last.status} /> {fmtRelative(last.started_at)}</span> },
                { label: 'Duration', value: fmtDuration(last.duration_ms) },
                { label: 'Last success', value: data.sync.last_success ? fmtDate(data.sync.last_success.finished_at) : null },
                { label: 'Next run', value: data.sync.next_run ? fmtDate(data.sync.next_run) : data.sync.interval === 'manual' ? 'Manual only' : null },
                { label: 'Objects', value: last.total_objects },
                { label: 'Changes', value: `+${last.new_objects ?? 0} / ~${last.changed_objects ?? 0} / −${last.removed_objects ?? 0}` },
                { label: 'Error', value: last.error, hidden: !last.error },
              ]}
            />
          ) : (
            <EmptyState>No synchronization yet.</EmptyState>
          )}
        </Card>

        <Card
          title="Controller"
          icon={<Server className="h-4 w-4 text-slate-500" />}
          actions={
            controller && (
              <Link to="/controller" className="text-xs link">
                Details
              </Link>
            )
          }
        >
          {controller ? (
            <KeyValue
              items={[
                { label: 'Name', value: controller.name },
                { label: 'Model', value: String(controller.model ?? controller.controller_type ?? '') },
                { label: 'Version', value: String(controller.version ?? '') },
                { label: 'Status', value: <StatusBadge status={String(controller.status ?? 'unknown')} /> },
                { label: 'Uptime', value: fmtSeconds(controller.uptime_seconds as number | null) },
                { label: 'Application', value: `v${data.version}` },
              ]}
            />
          ) : (
            <EmptyState>No controller information available.</EmptyState>
          )}
        </Card>

        <Card
          title="Attention"
          icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
          actions={
            <Link to="/quality" className="text-xs link">
              Data quality
            </Link>
          }
        >
          <ul className="space-y-1.5 text-sm">
            {data.devices_offline.map((d) => (
              <li key={d.key} className="flex items-center justify-between gap-2">
                <ObjectLink type="device" id={d.key} deviceType={d.type}>
                  {d.name ?? d.key}
                </ObjectLink>
                <StatusBadge status="offline" />
              </li>
            ))}
            {Object.entries(data.quality.sections)
              .filter(([, n]) => n > 0)
              .map(([s, n]) => (
                <li key={s} className="flex items-center justify-between gap-2">
                  <Link to={`/quality#${s}`} className="link">
                    {QUALITY_LABELS[s]?.title ?? humanize(s)}
                  </Link>
                  <Badge tone="amber">{n}</Badge>
                </li>
              ))}
            {data.devices_offline.length === 0 && data.quality.total === 0 && <li className="text-slate-500">Everything looks fine.</li>}
          </ul>
        </Card>
      </div>

      <Card
        title="Recent changes"
        icon={<History className="h-4 w-4 text-slate-500" />}
        bodyClassName="p-0"
        actions={
          <Link to="/changes" className="text-xs link">
            All changes
          </Link>
        }
      >
        {data.recent_changes.length === 0 ? (
          <EmptyState>No changes recorded yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Object</th>
                  <th>Change</th>
                  <th>Field</th>
                  <th>By</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_changes.map((c) => (
                  <tr key={c.id}>
                    <td className="whitespace-nowrap">{fmtRelative(c.ts)}</td>
                    <td>
                      <span className="mr-1 text-xs text-slate-500">{kindLabel(c.object_type)}</span>
                      <ObjectLink type={c.object_type} id={c.object_key}>
                        {c.object_name ?? c.object_key}
                      </ObjectLink>
                    </td>
                    <td>
                      <StatusBadge status={c.change_type} />
                    </td>
                    <td>{c.field ?? '—'}</td>
                    <td>{c.username ?? (c.kind === 'config' ? 'sync' : '—')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
