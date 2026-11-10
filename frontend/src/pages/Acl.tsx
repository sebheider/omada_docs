import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Background, Controls, MarkerType, MiniMap, Position, ReactFlow, type Edge, type Node } from '@xyflow/react';
import { AlertTriangle, Info, Shield, ShieldAlert } from 'lucide-react';
import { useAcl } from '../api/hooks';
import type { AclData, AclGraphEdge, AclRule, AclSide, IpGroup, MatrixCell, Segment } from '../api/types';
import { useTheme } from '../context/ThemeContext';
import { DataTable } from '../components/DataTable';
import { DetailShell, displayName, ObjectLink, RawPropertiesCard } from '../components/detail';
import { Badge, BoolBadge, Card, cx, EmptyState, ErrorBox, KeyValue, Mono, PageHeader, Spinner, StatusBadge, Tabs, type Tone } from '../components/ui';
import { ACL_TYPE_LABELS, describeSide } from '../lib/acl';
import { fmtValue, humanize } from '../lib/format';
import { layoutGraph, useFlowNodes } from '../lib/layout';
import { objectPath } from '../lib/routes';

type Tab = 'rules' | 'matrix' | 'graph' | 'groups';

export const STATUS_COLORS: Record<string, { bg: string; text: string; hex: string; label: string }> = {
  allowed: { bg: 'bg-emerald-500', text: 'text-white', hex: '#10b981', label: 'Allowed' },
  blocked: { bg: 'bg-red-500', text: 'text-white', hex: '#ef4444', label: 'Blocked' },
  restricted: { bg: 'bg-amber-400', text: 'text-amber-950', hex: '#f59e0b', label: 'Restricted (partially allowed)' },
  unknown: { bg: 'bg-slate-400', text: 'text-white', hex: '#94a3b8', label: 'Unknown' },
};

function actionTone(a: string | null | undefined): Tone {
  const s = (a ?? '').toLowerCase();
  if (['allow', 'permit', 'accept'].includes(s)) return 'green';
  if (['deny', 'drop', 'block', 'reject'].includes(s)) return 'red';
  return 'gray';
}

export function ActionBadge({ action }: { action: string | null | undefined }) {
  return <Badge tone={actionTone(action)}>{(action ?? 'unknown').toUpperCase()}</Badge>;
}

export function ConfidenceBadge({ confidence, reasons }: { confidence: string | null | undefined; reasons?: string[] }) {
  if (!confidence) return <Badge tone="gray">n/a</Badge>;
  const tone: Tone = confidence === 'high' ? 'green' : confidence === 'medium' ? 'amber' : 'red';
  return (
    <Badge tone={tone} title={reasons?.length ? reasons.join('\n') : 'No uncertainties detected'}>
      {humanize(confidence)}
      {reasons && reasons.length > 0 && <Info className="h-3 w-3" />}
    </Badge>
  );
}

function SideCell({ side }: { side: AclSide | null | undefined }) {
  return <span className={cx('text-sm', side?.negate && 'text-red-700 dark:text-red-300')}>{describeSide(side)}</span>;
}

function RuleTable({ rules, ruleNames }: { rules: AclRule[]; ruleNames: Map<string, string> }) {
  return (
    <DataTable<AclRule>
      rows={rules}
      rowKey={(r) => r.key}
      rowHref={(r) => objectPath('acl_rule', r.key)}
      initialSort={{ id: 'index', dir: 'asc' }}
      hideSearch
      defaultPageSize={50}
      rowClassName={(r) => (r.enabled === false ? 'opacity-60' : undefined)}
      columns={[
        { id: 'index', header: '#', value: (r) => r.index ?? null, className: 'w-10 font-semibold' },
        {
          id: 'name',
          header: 'Name',
          value: (r) => displayName(r),
          cell: (r) => (
            <div>
              <div className="font-medium text-slate-900 dark:text-slate-100">{displayName(r)}</div>
              {r.manual?.display_name && <div className="text-xs text-slate-500">{r.name}</div>}
            </div>
          ),
        },
        { id: 'enabled', header: 'Enabled', value: (r) => r.enabled, cell: (r) => <BoolBadge value={r.enabled} /> },
        { id: 'source', header: 'Source', value: (r) => describeSide(r.source), cell: (r) => <SideCell side={r.source} /> },
        { id: 'destination', header: 'Destination', value: (r) => describeSide(r.destination), cell: (r) => <SideCell side={r.destination} /> },
        { id: 'protocols', header: 'Protocols', value: (r) => (r.protocols ?? []).map((p) => p.toUpperCase()).join(', ') },
        { id: 'action', header: 'Action', value: (r) => r.action, cell: (r) => <ActionBadge action={r.action} /> },
        {
          id: 'direction',
          header: 'Direction',
          value: (r) => (r.directions?.length ? r.directions.map(humanize).join(', ') : r.direction && r.direction !== 'unknown' ? humanize(r.direction) : ''),
        },
        {
          id: 'explanation',
          header: 'Explanation',
          value: (r) => r.analysis?.explanation ?? '',
          cell: (r) => (
            <div className="min-w-[16rem] max-w-md text-xs leading-relaxed">
              {r.analysis?.explanation ?? <span className="italic text-slate-400">No interpretation available</span>}
              {r.analysis?.shadowed_by && (
                <div className="mt-1 flex items-start gap-1 text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                  <span>
                    Shadowed by{' '}
                    {[r.analysis.shadowed_by].flat().map((k, i) => (
                      <span key={k}>
                        {i > 0 && ', '}
                        <ObjectLink type="acl_rule" id={k}>
                          {ruleNames.get(k) ?? k}
                        </ObjectLink>
                      </span>
                    ))}
                  </span>
                </div>
              )}
            </div>
          ),
        },
        {
          id: 'confidence',
          header: 'Confidence',
          value: (r) => r.analysis?.confidence,
          cell: (r) => <ConfidenceBadge confidence={r.analysis?.confidence} reasons={r.analysis?.confidence_reasons} />,
        },
      ]}
    />
  );
}

function RulesTab({ data }: { data: AclData }) {
  const [query, setQuery] = useState('');
  const ruleNames = useMemo(() => new Map(data.rules.map((r) => [r.key, displayName(r)])), [data.rules]);
  const q = query.trim().toLowerCase();
  const filtered = q
    ? data.rules.filter((r) =>
        [displayName(r), r.name, describeSide(r.source), describeSide(r.destination), r.action, r.analysis?.explanation, (r.protocols ?? []).join(' ')]
          .join(' ')
          .toLowerCase()
          .includes(q),
      )
    : data.rules;
  const types = ['gateway', 'switch', 'eap', ...new Set(data.rules.map((r) => r.acl_type ?? 'other'))].filter((t, i, a) => a.indexOf(t) === i);
  if (!data.rules.length) return <Card><EmptyState>No ACL rules found.</EmptyState></Card>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input className="input max-w-sm" placeholder="Filter rules…" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Filter rules" />
        <span className="text-xs text-slate-500">Rules are evaluated top-down per ACL type; the first matching rule wins.</span>
      </div>
      {types.map((t) => {
        const rules = filtered.filter((r) => (r.acl_type ?? 'other') === t);
        if (!rules.length) return null;
        return (
          <section key={t}>
            <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
              <Shield className="h-4 w-4" /> {ACL_TYPE_LABELS[t] ?? humanize(t)} <Badge tone="gray">{rules.length}</Badge>
            </h2>
            <RuleTable rules={rules} ruleNames={ruleNames} />
          </section>
        );
      })}
    </div>
  );
}

function segLabel(s: Segment): string {
  return s.vlan_id !== null && s.vlan_id !== undefined ? `${s.name} (${s.vlan_id})` : s.name;
}

function CellDetail({ cell, segs, ruleNames, onClose }: { cell: MatrixCell; segs: Map<string, Segment>; ruleNames: Map<string, string>; onClose: () => void }) {
  const st = STATUS_COLORS[cell.status] ?? STATUS_COLORS.unknown;
  return (
    <Card
      title={
        <span>
          {segs.get(cell.source)?.name ?? cell.source} → {segs.get(cell.destination)?.name ?? cell.destination}
        </span>
      }
      actions={
        <button className="btn-ghost py-0.5 text-xs" onClick={onClose}>
          Close
        </button>
      }
    >
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cx('rounded px-2 py-0.5 text-xs font-semibold', st.bg, st.text)}>{st.label}</span>
          <ConfidenceBadge confidence={cell.confidence} />
          <Badge tone="gray">
            {cell.basis === 'rule' ? 'Based on ACL rules' : cell.basis === 'default' ? 'Default behaviour (no rule)' : 'Derived'}
          </Badge>
          {cell.computed_status && cell.computed_status !== cell.status && <span className="text-xs text-slate-500">computed: {cell.computed_status}</span>}
        </div>
        {cell.rules.length > 0 && (
          <div>
            <div className="label">Matching rules</div>
            <ul className="list-disc space-y-0.5 pl-5">
              {cell.rules.map((k) => (
                <li key={k}>
                  <ObjectLink type="acl_rule" id={k}>
                    {ruleNames.get(k) ?? k}
                  </ObjectLink>
                </li>
              ))}
            </ul>
          </div>
        )}
        {cell.notes.length > 0 && (
          <ul className="space-y-1 text-slate-600 dark:text-slate-300">
            {cell.notes.map((n, i) => (
              <li key={i} className="flex gap-1.5">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" /> {n}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

export function MatrixLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
      {Object.entries(STATUS_COLORS).map(([k, v]) => (
        <span key={k} className="flex items-center gap-1.5">
          <span className={cx('h-3 w-3 rounded-sm', v.bg)} /> {v.label}
        </span>
      ))}
      <span className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-emerald-500 opacity-40" /> Faded = default behaviour, no explicit rule
      </span>
    </div>
  );
}

function MatrixTab({ data }: { data: AclData }) {
  const [selected, setSelected] = useState<MatrixCell | null>(null);
  const segs = data.matrix.segments;
  const segMap = useMemo(() => new Map(segs.map((s) => [s.id, s])), [segs]);
  const cells = useMemo(() => new Map(data.matrix.cells.map((c) => [`${c.source}|${c.destination}`, c])), [data.matrix.cells]);
  const ruleNames = useMemo(() => new Map(data.rules.map((r) => [r.key, displayName(r)])), [data.rules]);
  if (!segs.length) return <Card><EmptyState>No network segments available for the communication matrix.</EmptyState></Card>;
  return (
    <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <Card title="Communication matrix" subtitle="Rows: source · Columns: destination. Click a cell for the rules and notes behind it." bodyClassName="p-3">
        <div className="mb-3">
          <MatrixLegend />
        </div>
        <div className="overflow-auto">
          <table className="border-separate border-spacing-1 text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-white p-1 text-left text-[10px] uppercase text-slate-500 dark:bg-slate-900">From ↓ / To →</th>
                {segs.map((s) => (
                  <th key={s.id} className="h-28 w-10 p-0 align-bottom font-medium">
                    <div className="mx-auto w-5 whitespace-nowrap [writing-mode:vertical-rl] rotate-180 text-left text-slate-700 dark:text-slate-300" title={s.cidrs.join(', ')}>
                      {segLabel(s)}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {segs.map((src) => (
                <tr key={src.id}>
                  <th className="sticky left-0 z-10 whitespace-nowrap bg-white pr-2 text-left font-medium text-slate-700 dark:bg-slate-900 dark:text-slate-300" title={src.cidrs.join(', ')}>
                    {segLabel(src)}
                    {src.guest && <Badge tone="amber" className="ml-1">guest</Badge>}
                  </th>
                  {segs.map((dst) => {
                    if (src.id === dst.id)
                      return (
                        <td key={dst.id} className="h-9 w-10 rounded bg-slate-100 text-center text-slate-400 dark:bg-slate-800">
                          —
                        </td>
                      );
                    const c = cells.get(`${src.id}|${dst.id}`);
                    const st = STATUS_COLORS[c?.status ?? 'unknown'] ?? STATUS_COLORS.unknown;
                    const isSel = selected && selected.source === src.id && selected.destination === dst.id;
                    return (
                      <td key={dst.id} className="h-9 w-10 p-0">
                        <button
                          className={cx(
                            'flex h-9 w-10 items-center justify-center rounded text-[10px] font-bold transition-transform hover:scale-110',
                            st.bg,
                            st.text,
                            c?.basis === 'default' && 'opacity-40',
                            c?.basis === 'derived' && 'opacity-70',
                            isSel && 'ring-2 ring-slate-900 ring-offset-1 dark:ring-white',
                          )}
                          title={`${src.name} → ${dst.name}: ${st.label}${c?.rules.length ? ` (${c.rules.length} rule${c.rules.length > 1 ? 's' : ''})` : ''}${c?.notes.length ? `\n${c.notes.join('\n')}` : ''}`}
                          onClick={() => c && setSelected(c)}
                          aria-label={`${src.name} to ${dst.name}: ${st.label}`}
                        >
                          {c?.rules.length ? c.rules.length : ''}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">Numbers show how many ACL rules determine the result of a cell.</p>
      </Card>
      {selected ? (
        <div className="xl:sticky xl:top-20">
          <CellDetail cell={selected} segs={segMap} ruleNames={ruleNames} onClose={() => setSelected(null)} />
        </div>
      ) : (
        <div className="hidden rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700 xl:block">
          Select a cell to see the rules and notes behind it.
        </div>
      )}
    </div>
  );
}

const SEG_NODE_STYLE: Record<string, { bg: string; border: string }> = {
  network: { bg: '#ecfdf5', border: '#2f9383' },
  group: { bg: '#eff6ff', border: '#3b82f6' },
  internet: { bg: '#f0f9ff', border: '#0284c7' },
};

function GraphTab({ data }: { data: AclData }) {
  const { theme } = useTheme();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<AclGraphEdge | null>(null);
  const ruleNames = useMemo(() => new Map(data.rules.map((r) => [r.key, displayName(r)])), [data.rules]);
  const segMap = useMemo(() => new Map(data.graph.nodes.map((s) => [s.id, s])), [data.graph.nodes]);
  const layoutNodes = useMemo(() => {
    const dark = theme === 'dark';
    const nodes: Node[] = data.graph.nodes.map((n) => {
      const st = SEG_NODE_STYLE[n.type] ?? SEG_NODE_STYLE.network;
      return {
        id: n.id,
        position: { x: 0, y: 0 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: { label: `${n.name}${n.vlan_id !== null && n.vlan_id !== undefined ? ` · VLAN ${n.vlan_id}` : ''}${n.type === 'group' ? ' (group)' : ''}` },
        style: {
          background: dark ? '#0f172a' : st.bg,
          border: `2px ${n.type === 'group' ? 'dashed' : 'solid'} ${st.border}`,
          color: dark ? '#e2e8f0' : '#0f172a',
          borderRadius: 8,
          fontSize: 12,
          fontWeight: 600,
          width: 170,
          opacity: n.has_rules === false ? 0.6 : 1,
        },
      };
    });
    const layoutEdges = data.graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target }));
    return layoutGraph(nodes, layoutEdges, { direction: 'LR', nodeWidth: 170, nodeHeight: 40, ranksep: 120, nodesep: 24 });
  }, [data.graph, theme]);
  const [nodes, onNodesChange] = useFlowNodes(layoutNodes);
  const edges = useMemo(() => {
    return data.graph.edges.map((e): Edge => {
      const c = STATUS_COLORS[e.status]?.hex ?? '#94a3b8';
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: 'default',
        animated: false,
        label: `${e.rules.length} rule${e.rules.length === 1 ? '' : 's'}`,
        labelStyle: { fontSize: 10 },
        style: { stroke: c, strokeWidth: selected?.id === e.id ? 4 : 2.2, strokeDasharray: e.dashed ? '6 4' : undefined },
        markerEnd: { type: MarkerType.ArrowClosed, color: c },
      };
    });
  }, [data.graph.edges, selected]);

  if (!data.graph.nodes.length) return <Card><EmptyState>No ACL graph data available.</EmptyState></Card>;
  return (
    <div className="grid gap-4 xl:grid-cols-4">
      <div className="card relative h-[65vh] min-h-[420px] overflow-hidden xl:col-span-3">
        <ReactFlow
          nodes={nodes}
          onNodesChange={onNodesChange}
          edges={edges}
          colorMode={theme}
          fitView
          fitViewOptions={{ padding: 0.08, minZoom: 0.6, maxZoom: 1.2 }}
          minZoom={0.1}
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
          onEdgeClick={(_, edge) => setSelected(data.graph.edges.find((e) => e.id === edge.id) ?? null)}
          onNodeClick={(_, node) => {
            const s = segMap.get(node.id);
            if (!s?.ref_id) return;
            const p = s.type === 'network' ? objectPath('network', s.ref_id) : s.type === 'group' ? objectPath('ip_group', s.ref_id) : null;
            if (p) navigate(p);
          }}
        >
          <Background gap={20} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor={(n) => SEG_NODE_STYLE[segMap.get(n.id)?.type ?? 'network']?.border ?? '#94a3b8'} />
        </ReactFlow>
      </div>
      <div className="space-y-4">
        <Card title="Legend">
          <div className="space-y-1.5 text-xs">
            {Object.entries(STATUS_COLORS).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <svg width="30" height="6" aria-hidden>
                  <line x1="0" y1="3" x2="30" y2="3" stroke={v.hex} strokeWidth="2.5" />
                </svg>
                {v.label}
              </div>
            ))}
            <div className="flex items-center gap-2">
              <svg width="30" height="6" aria-hidden>
                <line x1="0" y1="3" x2="30" y2="3" stroke="#94a3b8" strokeWidth="2.5" strokeDasharray="6 4" />
              </svg>
              Disabled rules / uncertain
            </div>
            <p className="pt-1 text-slate-500">Only explicit ACL rules are drawn. Click an edge to see its rules, click a node to open the network or group.</p>
          </div>
        </Card>
        {selected ? (
          <Card
            title={`${segMap.get(selected.source)?.name ?? selected.source} → ${segMap.get(selected.target)?.name ?? selected.target}`}
            actions={<button className="btn-ghost py-0.5 text-xs" onClick={() => setSelected(null)}>Close</button>}
          >
            <div className="space-y-2 text-sm">
              <div className="flex gap-2">
                <StatusBadge status={selected.status} />
                <ConfidenceBadge confidence={selected.confidence} />
              </div>
              <ul className="list-disc pl-5">
                {selected.rules.map((k) => (
                  <li key={k}>
                    <ObjectLink type="acl_rule" id={k}>
                      {ruleNames.get(k) ?? k}
                    </ObjectLink>
                  </li>
                ))}
                {selected.disabled_rules.map((k) => (
                  <li key={k} className="text-slate-500">
                    <ObjectLink type="acl_rule" id={k}>
                      {ruleNames.get(k) ?? k}
                    </ObjectLink>{' '}
                    (disabled)
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        ) : (
          <Card title="Selection">
            <p className="text-sm text-slate-500">Select an edge to see the rules behind it.</p>
          </Card>
        )}
      </div>
    </div>
  );
}

function groupEntries(g: IpGroup): string {
  const parts: string[] = [];
  if (g.entries?.length) parts.push(g.entries.map((e) => e.ip).filter(Boolean).join(', '));
  if (g.ports?.length) parts.push(`ports ${g.ports.join(', ')}`);
  if (g.macs?.length) parts.push(`${g.macs.length} MACs`);
  if (g.domains?.length) parts.push(fmtValue(g.domains));
  if (g.countries?.length) parts.push(fmtValue(g.countries));
  return parts.join(' · ');
}

function GroupsTab({ data }: { data: AclData }) {
  return (
    <DataTable<IpGroup>
      rows={data.ip_groups}
      rowKey={(g) => g.key}
      rowHref={(g) => objectPath('ip_group', g.key)}
      initialSort={{ id: 'name', dir: 'asc' }}
      emptyText="No IP or port groups defined."
      columns={[
        { id: 'name', header: 'Name', value: (g) => displayName(g) },
        { id: 'type', header: 'Type', value: (g) => humanize(g.type ?? ''), filter: true },
        { id: 'entries', header: 'Entries', value: groupEntries, cell: (g) => <span className="font-mono text-xs">{groupEntries(g) || '—'}</span> },
        { id: 'builtin', header: 'Built-in', value: (g) => g.built_in, cell: (g) => <BoolBadge value={g.built_in} /> },
        { id: 'desc', header: 'Description', value: (g) => g.manual?.description ?? g.description ?? '' },
      ]}
    />
  );
}

export function AclPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get('tab') as Tab) || 'rules';
  const { data, isLoading, error } = useAcl();
  const lowConf = data?.rules.filter((r) => r.analysis && r.analysis.confidence !== 'high').length ?? 0;
  const shadowed = data?.rules.filter((r) => r.analysis?.shadowed_by).length ?? 0;
  return (
    <div>
      <PageHeader
        title="ACL / Firewall"
        icon={<Shield className="h-5 w-5 text-brand-600" />}
        crumbs={[{ label: 'ACL / Firewall' }]}
        subtitle="Access control rules with plain-language explanations and a communication matrix between network segments"
        actions={
          data && (
            <>
              {lowConf > 0 && <Badge tone="amber">{lowConf} uncertain</Badge>}
              {shadowed > 0 && (
                <Badge tone="red">
                  <ShieldAlert className="h-3 w-3" /> {shadowed} shadowed
                </Badge>
              )}
            </>
          )
        }
      />
      <Tabs<Tab>
        active={tab}
        onChange={(t) => setParams(t === 'rules' ? {} : { tab: t }, { replace: true })}
        tabs={[
          { id: 'rules', label: 'Rules', count: data?.rules.length },
          { id: 'matrix', label: 'Communication matrix' },
          { id: 'graph', label: 'Graph' },
          { id: 'groups', label: 'IP / port groups', count: data?.ip_groups.length },
        ]}
      />
      {isLoading ? (
        <Spinner />
      ) : error || !data ? (
        <ErrorBox error={error} />
      ) : tab === 'rules' ? (
        <RulesTab data={data} />
      ) : tab === 'matrix' ? (
        <MatrixTab data={data} />
      ) : tab === 'graph' ? (
        <GraphTab data={data} />
      ) : (
        <GroupsTab data={data} />
      )}
    </div>
  );
}

function refType(sideType: string | null | undefined): string | null {
  if (!sideType) return null;
  if (sideType === 'network') return 'network';
  if (sideType.includes('group')) return 'ip_group';
  return null;
}

function SideDetail({ title, side }: { title: string; side: AclSide | null | undefined }) {
  const t = refType(side?.type);
  return (
    <div>
      <div className="label">{title}</div>
      {!side ? (
        <span className="italic text-slate-400">not available</span>
      ) : (
        <div className="space-y-1 text-sm">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone="gray">{humanize(side.type ?? 'unknown')}</Badge>
            {side.negate && <Badge tone="red">NOT (negated)</Badge>}
          </div>
          {side.refs?.length ? (
            <ul className="space-y-0.5">
              {side.refs.map((r, i) => (
                <li key={i} className="flex items-center gap-1.5">
                  {t && r.id ? (
                    <ObjectLink type={t} id={r.id}>
                      {r.name ?? r.id}
                    </ObjectLink>
                  ) : (
                    <span>{r.name ?? r.id}</span>
                  )}
                  {r.resolved === false && <Badge tone="amber">unresolved reference</Badge>}
                </li>
              ))}
            </ul>
          ) : (
            <div>{side.type === 'any' ? 'Any' : '—'}</div>
          )}
          {side.ports?.length ? <div>Ports: {side.ports.join(', ')}</div> : null}
        </div>
      )}
    </div>
  );
}

export function AclRuleDetailPage() {
  const { key } = useParams();
  const acl = useAcl();
  const ruleNames = useMemo(() => new Map((acl.data?.rules ?? []).map((r) => [r.key, displayName(r)])), [acl.data]);
  return (
    <DetailShell<AclRule>
      kind="acl_rule"
      objectKey={key}
      crumbs={[{ label: 'ACL / Firewall', to: '/acl' }]}
      icon={<Shield className="h-5 w-5 text-brand-600" />}
      subtitle={(d) => (
        <>
          <Badge tone="gray">{ACL_TYPE_LABELS[d.entity.acl_type ?? ''] ?? d.entity.acl_type}</Badge>
          <ActionBadge action={d.entity.action} />
          <BoolBadge value={d.entity.enabled} yes="Enabled" no="Disabled" />
        </>
      )}
    >
      {(d) => {
        const r = d.entity;
        const a = d.analysis;
        return (
          <>
            <Card title="Explanation" className="border-l-4 border-l-sky-500">
              {a ? (
                <div className="space-y-3">
                  <p className="text-sm leading-relaxed">{a.explanation}</p>
                  <div className="rounded-md bg-slate-100 p-2 font-mono text-xs dark:bg-slate-800">{a.technical}</div>
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span className="label mb-0">Confidence</span>
                    <ConfidenceBadge confidence={a.confidence} />
                    <span className="text-xs text-slate-500">Source: {a.data_source}</span>
                  </div>
                  {a.confidence_reasons.length > 0 && (
                    <ul className="list-disc space-y-0.5 pl-5 text-sm text-slate-600 dark:text-slate-300">
                      {a.confidence_reasons.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  )}
                  {a.shadowed_by && (
                    <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>
                        This rule is shadowed by{' '}
                        {[a.shadowed_by].flat().map((k, i) => (
                          <span key={k}>
                            {i > 0 && ', '}
                            <ObjectLink type="acl_rule" id={k}>
                              {ruleNames.get(k) ?? k}
                            </ObjectLink>
                          </span>
                        ))}{' '}
                        – an earlier rule already matches all of its traffic, so it is likely never applied.
                      </span>
                    </div>
                  )}
                  {a.related_rules.length > 0 && (
                    <div>
                      <div className="label">Related (overlapping) rules</div>
                      <ul className="list-disc pl-5 text-sm">
                        {a.related_rules.map((k) => (
                          <li key={k}>
                            <ObjectLink type="acl_rule" id={k}>
                              {ruleNames.get(k) ?? k}
                            </ObjectLink>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <EmptyState>No interpretation available for this rule.</EmptyState>
              )}
            </Card>
            <Card title="Rule definition">
              <div className="grid gap-4 sm:grid-cols-2">
                <SideDetail title="Source" side={r.source} />
                <SideDetail title="Destination" side={r.destination} />
              </div>
              <div className="mt-4">
                <KeyValue
                  cols={3}
                  items={[
                    { label: 'ACL type', value: ACL_TYPE_LABELS[r.acl_type ?? ''] ?? r.acl_type },
                    { label: 'Order (index)', value: r.index },
                    { label: 'Action', value: <ActionBadge action={r.action} /> },
                    { label: 'Protocols', value: (r.protocols ?? []).map((p) => p.toUpperCase()).join(', ') },
                    { label: 'Direction', value: r.directions?.length ? r.directions.map(humanize).join(', ') : r.direction ? humanize(r.direction) : null },
                    { label: 'State mode', value: r.state_mode ? humanize(String(r.state_mode)) : null },
                    { label: 'Time range', value: r.time_range_id ? <Mono>{String(r.time_range_id)}</Mono> : 'Always' },
                    { label: 'Binding', value: r.binding ? fmtValue(r.binding) : null },
                    { label: 'Controller description', value: r.description },
                  ]}
                />
              </div>
            </Card>
            <RawPropertiesCard entity={r} />
          </>
        );
      }}
    </DetailShell>
  );
}

export function IpGroupDetailPage() {
  const { key } = useParams();
  return (
    <DetailShell<IpGroup>
      kind="ip_group"
      objectKey={key}
      crumbs={[{ label: 'ACL / Firewall', to: '/acl' }, { label: 'IP / port groups', to: '/acl?tab=groups' }]}
      icon={<Shield className="h-5 w-5 text-brand-600" />}
    >
      {(d) => {
        const g = d.entity;
        return (
          <>
            <Card title="Group">
              <KeyValue
                items={[
                  { label: 'Type', value: humanize(g.type ?? '') },
                  { label: 'Built-in', value: g.built_in === undefined || g.built_in === null ? null : g.built_in ? 'Yes' : 'No' },
                  { label: 'Ports', value: g.ports?.length ? g.ports.join(', ') : null },
                  { label: 'Description', value: g.description },
                ]}
              />
              {g.entries?.length ? (
                <table className="table-base mt-4">
                  <thead>
                    <tr>
                      <th>Address / network</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.entries.map((e, i) => (
                      <tr key={i}>
                        <td>
                          <Mono>{e.ip}</Mono>
                        </td>
                        <td>{e.description ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
              {[g.macs, g.domains, g.countries].some((x) => x?.length) && (
                <div className="mt-4">
                  <KeyValue
                    items={[
                      { label: 'MAC addresses', value: g.macs?.length ? fmtValue(g.macs) : null },
                      { label: 'Domains', value: g.domains?.length ? fmtValue(g.domains) : null },
                      { label: 'Countries', value: g.countries?.length ? fmtValue(g.countries) : null },
                    ]}
                  />
                </div>
              )}
            </Card>
            <p className="text-xs text-slate-500">
              <Link to="/acl?tab=groups" className="link">
                All groups
              </Link>
            </p>
            <RawPropertiesCard entity={g} />
          </>
        );
      }}
    </DetailShell>
  );
}
