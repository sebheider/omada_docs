import dagre from '@dagrejs/dagre';
import { useCallback, useEffect, useState } from 'react';
import { applyNodeChanges, type Edge, type Node, type NodeChange } from '@xyflow/react';

/** Compute node positions with dagre (top-down by default). */
export function layoutGraph<N extends Node, E extends Edge>(
  nodes: N[],
  edges: E[],
  opts: { direction?: 'TB' | 'LR'; nodeWidth?: number; nodeHeight?: number; ranksep?: number; nodesep?: number } = {},
): N[] {
  const { direction = 'TB', nodeWidth = 190, nodeHeight = 64, ranksep = 80, nodesep = 30 } = opts;
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: direction, ranksep, nodesep, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) g.setNode(n.id, { width: nodeWidth, height: nodeHeight });
  for (const e of edges) if (g.hasNode(e.source) && g.hasNode(e.target)) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: (p?.x ?? 0) - nodeWidth / 2, y: (p?.y ?? 0) - nodeHeight / 2 } };
  });
}

const NO_NODES: never[] = [];

/** Keep laid-out nodes in local state so React Flow can measure and drag them. */
export function useFlowNodes<N extends Node>(nodes: N[] | undefined) {
  const source = nodes ?? (NO_NODES as N[]);
  const [state, setState] = useState<N[]>(source);
  useEffect(() => setState(source), [source]);
  const onNodesChange = useCallback((changes: NodeChange<N>[]) => setState((s) => applyNodeChanges(changes, s)), []);
  return [state, onNodesChange] as const;
}
