import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import { Cable, ClipboardCheck, Globe, HelpCircle, Laptop, Network, Router, Server, Waypoints, Wifi } from 'lucide-react';
import { useTopology } from '../api/hooks';
import type { TopoEdge, TopoNode } from '../api/types';
import { useTheme } from '../context/ThemeContext';
import { Badge, Card, cx, EmptyState, ErrorBox, PageHeader, Spinner } from '../components/ui';
import { layoutGraph, useFlowNodes } from '../lib/layout';
import { objectPath } from '../lib/routes';

type TopoData = { label: string; type: string; sub: string; status?: string; role?: string };

const TYPE_STYLE: Record<string, { icon: typeof Router; cls: string; label: string }> = {
  internet: { icon: Globe, cls: 'border-sky-400 bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-100', label: 'Internet / WAN' },
  gateway: { icon: Router, cls: 'border-violet-400 bg-violet-50 text-violet-900 dark:bg-violet-950 dark:text-violet-100', label: 'Gateway' },
  switch: { icon: Cable, cls: 'border-brand-500 bg-brand-50 text-brand-900 dark:bg-brand-950 dark:text-brand-100', label: 'Switch' },
  ap: { icon: Wifi, cls: 'border-amber-400 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-100', label: 'Access point' },
  client: { icon: Laptop, cls: 'border-slate-300 bg-white text-slate-800 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100', label: 'Client' },
};

function TopoNodeView({ data }: NodeProps<Node<TopoData>>) {
  const style = TYPE_STYLE[data.type] ?? { icon: HelpCircle, cls: 'border-slate-300 bg-slate-50 dark:bg-slate-800', label: data.type };
  const Icon = data.role === 'server' ? Server : style.icon;
  const offline = data.status && !['online', 'connected'].includes(data.status);
  return (
    <div className={cx('w-[190px] cursor-pointer rounded-lg border-2 px-2.5 py-1.5 shadow-sm', style.cls, offline && 'border-red-500 opacity-80')}>
      <Handle type="target" position={Position.Top} className="!h-1.5 !w-1.5 !border-0 !bg-slate-400" />
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold" title={data.label}>
            {data.label}
          </div>
          <div className="truncate text-[10px] opacity-75" title={data.sub}>
            {data.sub}
          </div>
        </div>
        {data.status && <span className={cx('h-2 w-2 shrink-0 rounded-full', offline ? 'bg-red-500' : 'bg-emerald-500')} title={data.status} />}
      </div>
      <Handle type="source" position={Position.Bottom} className="!h-1.5 !w-1.5 !border-0 !bg-slate-400" />
    </div>
  );
}

const nodeTypes = { topo: TopoNodeView };

const MINIMAP_COLORS: Record<string, string> = { internet: '#38bdf8', gateway: '#8b5cf6', switch: '#23766a', ap: '#f59e0b', client: '#94a3b8' };

const EVIDENCE: Record<string, { color: string; dash?: string; label: string; description: string }> = {
  api: { color: '#64748b', label: 'Controller (API)', description: 'Uplink reported by the controller' },
  lldp: { color: '#0284c7', label: 'LLDP', description: 'Neighbour discovered via LLDP' },
  manual: { color: '#23766a', dash: '6 4', label: 'Manual', description: 'Documented manually' },
  derived: { color: '#94a3b8', dash: '3 4', label: 'Derived', description: 'Inferred from other data' },
};

function nodeSub(n: TopoNode): string {
  const d = n.data ?? {};
  if (n.type === 'internet') {
    const wans = (d.wans as { name: string; status?: string }[] | undefined) ?? [];
    return wans.map((w) => `${w.name}${w.status ? ` (${w.status})` : ''}`).join(', ') || 'WAN';
  }
  if (n.type === 'client') return [d.ip, d.network].filter(Boolean).join(' · ');
  return [d.model, d.ip].filter(Boolean).join(' · ');
}

function buildFlow(nodes: TopoNode[], edges: TopoEdge[]): { nodes: Node<TopoData>[]; edges: Edge[] } {
  const rfNodes: Node<TopoData>[] = nodes.map((n) => ({
    id: n.id,
    type: 'topo',
    position: { x: 0, y: 0 },
    data: {
      label: n.label,
      type: n.type,
      sub: nodeSub(n),
      status: n.type === 'client' || n.type === 'internet' ? undefined : (n.data?.status as string | undefined),
      role: n.data?.role as string | undefined,
    },
  }));
  const rfEdges: Edge[] = edges.map((e) => {
    const ev = EVIDENCE[e.evidence] ?? EVIDENCE.derived;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label ?? undefined,
      labelStyle: { fontSize: 10 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 3,
      style: { stroke: ev.color, strokeWidth: e.evidence === 'lldp' ? 2.5 : 1.8, strokeDasharray: ev.dash },
      markerEnd: { type: MarkerType.ArrowClosed, color: ev.color, width: 14, height: 14 },
      type: 'smoothstep',
    };
  });
  return { nodes: layoutGraph(rfNodes, rfEdges, { nodeWidth: 190, nodeHeight: 50, ranksep: 70, nodesep: 24 }), edges: rfEdges };
}

export function TopologyPage() {
  const [clients, setClients] = useState<'none' | 'important' | 'all'>('important');
  const { data, isLoading, error, isFetching } = useTopology(clients);
  const { theme } = useTheme();
  const navigate = useNavigate();
  const flow = useMemo(() => (data ? buildFlow(data.nodes, data.edges) : null), [data]);
  const byId = useMemo(() => new Map((data?.nodes ?? []).map((n) => [n.id, n])), [data]);
  const [nodes, onNodesChange] = useFlowNodes(flow?.nodes);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Network Overview"
        icon={<Waypoints className="h-5 w-5 text-brand-600" />}
        crumbs={[{ label: 'Network Overview' }]}
        subtitle="Logical topology: Internet → gateway → switches → access points → clients"
        actions={
          <>
            <div className="inline-flex overflow-hidden rounded-md border border-slate-300 dark:border-slate-700" role="group" aria-label="Clients shown">
              {(['none', 'important', 'all'] as const).map((c) => (
                <button
                  key={c}
                  className={cx(
                    'px-3 py-1.5 text-sm',
                    clients === c ? 'bg-brand-600 text-white' : 'bg-white hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700',
                  )}
                  onClick={() => setClients(c)}
                >
                  {c === 'none' ? 'No clients' : c === 'important' ? 'Important clients' : 'All clients'}
                </button>
              ))}
            </div>
            <Link to="/quality" className="btn-secondary">
              <ClipboardCheck className="h-4 w-4" /> Data quality
            </Link>
          </>
        }
      />
      {error ? (
        <ErrorBox error={error} />
      ) : isLoading || !flow ? (
        <Spinner />
      ) : (
        <>
          <div className="card relative h-[68vh] min-h-[420px] overflow-hidden">
            {isFetching && <div className="absolute right-3 top-3 z-10 text-xs text-slate-500">Updating…</div>}
            {flow.nodes.length === 0 ? (
              <EmptyState>No topology data available. Run a synchronization first.</EmptyState>
            ) : (
              <ReactFlow
                key={clients}
                nodes={nodes}
                onNodesChange={onNodesChange}
                edges={flow.edges}
                nodeTypes={nodeTypes}
                colorMode={theme}
                fitView
                fitViewOptions={{ padding: 0.12, minZoom: 0.6, maxZoom: 1.2 }}
                minZoom={0.1}
                maxZoom={2.5}
                nodesConnectable={false}
                proOptions={{ hideAttribution: true }}
                onNodeClick={(_, node) => {
                  const n = byId.get(node.id);
                  if (!n) return;
                  if (n.type === 'internet') return navigate('/networks?tab=wan');
                  const key = String(n.data?.key ?? n.id.split(':').slice(1).join(':'));
                  const path = n.type === 'client' ? objectPath('client', key) : objectPath('device', key, { deviceType: n.type });
                  if (path) navigate(path);
                }}
              >
                <Background gap={20} />
                <Controls showInteractive={false} />
                <MiniMap pannable zoomable nodeStrokeWidth={3} nodeColor={(n) => MINIMAP_COLORS[(n.data as TopoData).type] ?? '#94a3b8'} />
              </ReactFlow>
            )}
            <div className="absolute bottom-3 left-14 z-10 rounded-md border border-slate-200 bg-white/95 p-2 text-[11px] shadow-sm dark:border-slate-700 dark:bg-slate-900/95">
              <div className="mb-1 font-semibold uppercase tracking-wide text-slate-500">Connection source</div>
              {Object.entries(EVIDENCE).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2" title={v.description}>
                  <svg width="28" height="6" aria-hidden>
                    <line x1="0" y1="3" x2="28" y2="3" stroke={v.color} strokeWidth={k === 'lldp' ? 2.5 : 1.8} strokeDasharray={v.dash} />
                  </svg>
                  {v.label}
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Notes" className="lg:col-span-1">
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
                {data?.notes.map((n, i) => <li key={i}>{n}</li>)}
                {!data?.notes.length && <li>No notes.</li>}
              </ul>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {Object.entries(TYPE_STYLE).map(([k, v]) => (
                  <span key={k} className={cx('inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px]', v.cls)}>
                    <v.icon className="h-3 w-3" /> {v.label}
                  </span>
                ))}
              </div>
            </Card>
            <Card title={`Unresolved devices & connections (${data?.unresolved.length ?? 0})`} className="lg:col-span-2">
              {data?.unresolved.length ? (
                <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
                  {data.unresolved.map((u, i) => (
                    <li key={i} className="py-1.5">
                      <span className="font-medium">{String(u.name ?? u.key ?? u.mac ?? 'Unknown')}</span>
                      {u.reason && <span className="ml-2 text-slate-500">{String(u.reason)}</span>}
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState>All devices could be placed in the topology.</EmptyState>
              )}
            </Card>
          </div>

          <Card title="Network segmentation" icon={<Network className="h-4 w-4 text-slate-500" />}>
            {data?.segmentation.length ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {data.segmentation.map((s) => (
                  <Link
                    key={s.id}
                    to={objectPath('network', s.id) ?? '#'}
                    className={cx(
                      'block rounded-lg border p-3 transition-shadow hover:shadow-md',
                      s.guest ? 'border-amber-300 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/30' : 'border-slate-200 dark:border-slate-700',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold">{s.name}</span>
                      {s.vlan_id !== null && <Badge tone="blue">VLAN {s.vlan_id}</Badge>}
                    </div>
                    <div className="mt-1 font-mono text-xs text-slate-600 dark:text-slate-400">{s.subnet ?? 'no subnet'}</div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {s.guest && <Badge tone="amber">Guest</Badge>}
                      <Badge tone="gray">{s.client_count} clients</Badge>
                      {s.ssids.map((x) => (
                        <Badge key={x} tone="violet">
                          <Wifi className="h-3 w-3" /> {x}
                        </Badge>
                      ))}
                    </div>
                    {s.description && <p className="mt-2 line-clamp-2 text-xs text-slate-500">{s.description}</p>}
                  </Link>
                ))}
              </div>
            ) : (
              <EmptyState>No networks available.</EmptyState>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
