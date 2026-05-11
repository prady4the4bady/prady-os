import React, { useCallback, useEffect, useRef, useState } from 'react';

interface GraphNode {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled';
  depth: number;
  index_in_row: number;
  agent_id?: string;
  result?: string;
}

interface GraphEdge {
  from: string;
  to: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface PopoverState {
  node: GraphNode;
  x: number;
  y: number;
}

const STATUS_COLOR: Record<string, string> = {
  pending: '#8E8E93',
  running: '#007AFF',
  done: '#34C759',
  failed: '#FF3B30',
  cancelled: '#FF9500',
};

const NODE_W = 160;
const NODE_H = 40;
const ROW_GAP = 120;
const SVG_PADDING = 40;

function layoutNodes(nodes: GraphNode[]): Map<string, { cx: number; cy: number }> {
  const rowMap = new Map<number, GraphNode[]>();
  for (const n of nodes) {
    const row = rowMap.get(n.depth) ?? [];
    row.push(n);
    rowMap.set(n.depth, row);
  }

  const maxRowSize = Math.max(...Array.from(rowMap.values()).map(r => r.length), 1);
  const svgWidth = Math.max(600, (maxRowSize + 1) * (NODE_W + 40));

  const positions = new Map<string, { cx: number; cy: number }>();
  for (const [depth, rowNodes] of rowMap.entries()) {
    const count = rowNodes.length;
    rowNodes.forEach((n, i) => {
      const cx = ((i + 1) * svgWidth) / (count + 1);
      const cy = SVG_PADDING + depth * ROW_GAP + NODE_H / 2;
      positions.set(n.id, { cx, cy });
    });
  }
  return positions;
}

function calcSvgDims(nodes: GraphNode[]): { width: number; height: number } {
  const rowMap = new Map<number, number>();
  for (const n of nodes) rowMap.set(n.depth, (rowMap.get(n.depth) ?? 0) + 1);
  const maxRowSize = Math.max(...Array.from(rowMap.values()), 1);
  const maxDepth = Math.max(...nodes.map(n => n.depth), 0);
  return {
    width: Math.max(600, (maxRowSize + 1) * (NODE_W + 40)),
    height: SVG_PADDING * 2 + (maxDepth + 1) * ROW_GAP,
  };
}

interface TaskGraphProps {
  taskId: string;
}

export const TaskGraph: React.FC<TaskGraphProps> = ({ taskId }) => {
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [popover, setPopover] = useState<PopoverState | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const fetchGraph = useCallback(async () => {
    try {
      const resp = await fetch(`http://localhost:8104/swarm/graph/${taskId}`);
      if (!resp.ok) {
        setError(`HTTP ${resp.status}`);
        return;
      }
      const data: GraphData = await resp.json();
      setGraph(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, [taskId]);

  useEffect(() => {
    fetchGraph();
    intervalRef.current = setInterval(fetchGraph, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchGraph]);

  const handleNodeClick = (node: GraphNode, e: React.MouseEvent<SVGGElement>) => {
    const rect = containerRef.current?.getBoundingClientRect();
    const x = e.clientX - (rect?.left ?? 0);
    const y = e.clientY - (rect?.top ?? 0);
    setPopover(prev => (prev?.node.id === node.id ? null : { node, x, y }));
  };

  if (error) {
    return (
      <div style={{ color: '#FF3B30', fontSize: 13, padding: '8px 0' }}>
        Graph load error: {error}
      </div>
    );
  }
  if (!graph) {
    return <div style={{ color: '#8E8E93', fontSize: 13, padding: '8px 0' }}>Loading graph…</div>;
  }
  if (graph.nodes.length === 0) {
    return <div style={{ color: '#8E8E93', fontSize: 13 }}>No nodes yet.</div>;
  }

  const positions = layoutNodes(graph.nodes);
  const { width, height } = calcSvgDims(graph.nodes);

  return (
    <div ref={containerRef} style={{ position: 'relative', overflowX: 'auto' }}>
      <svg
        width={width}
        height={height}
        style={{ display: 'block', background: 'transparent' }}
        onClick={() => setPopover(null)}
      >
        {/* Edges */}
        {graph.edges.map(edge => {
          const from = positions.get(edge.from);
          const to = positions.get(edge.to);
          if (!from || !to) return null;
          return (
            <line
              key={`${edge.from}->${edge.to}`}
              x1={from.cx}
              y1={from.cy + NODE_H / 2}
              x2={to.cx}
              y2={to.cy - NODE_H / 2}
              stroke="#3A3A3C"
              strokeWidth={1.5}
            />
          );
        })}

        {/* Nodes */}
        {graph.nodes.map(node => {
          const pos = positions.get(node.id);
          if (!pos) return null;
          const color = STATUS_COLOR[node.status] ?? STATUS_COLOR.pending;
          return (
            <g
              key={node.id}
              transform={`translate(${pos.cx - NODE_W / 2}, ${pos.cy - NODE_H / 2})`}
              style={{ cursor: 'pointer' }}
              onClick={e => { e.stopPropagation(); handleNodeClick(node, e); }}
            >
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={8}
                fill={color + '22'}
                stroke={color}
                strokeWidth={1.5}
              />
              {/* Status dot */}
              <circle cx={12} cy={NODE_H / 2} r={5} fill={color} />
              <text
                x={22}
                y={NODE_H / 2 + 1}
                dominantBaseline="middle"
                fontSize={11}
                fill="#F2F2F7"
                fontFamily="-apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif"
              >
                {node.label.length > 18 ? node.label.slice(0, 18) + '…' : node.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Popover */}
      {popover && (
        <div
          style={{
            position: 'absolute',
            top: popover.y + 8,
            left: Math.min(popover.x + 8, width - 220),
            background: '#1C1C1E',
            border: '1px solid #3A3A3C',
            borderRadius: 10,
            padding: '10px 14px',
            width: 210,
            zIndex: 10,
            boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: '#F2F2F7', marginBottom: 4 }}>
            {popover.node.label}
          </div>
          <div style={{ fontSize: 11, color: STATUS_COLOR[popover.node.status] ?? '#8E8E93', marginBottom: 4 }}>
            {popover.node.status}
          </div>
          {popover.node.agent_id && (
            <div style={{ fontSize: 11, color: '#8E8E93' }}>Agent: {popover.node.agent_id}</div>
          )}
          {popover.node.result && (
            <div
              style={{
                fontSize: 11,
                color: '#8E8E93',
                marginTop: 4,
                maxHeight: 60,
                overflowY: 'auto',
                wordBreak: 'break-all',
              }}
            >
              {popover.node.result.slice(0, 120)}
              {popover.node.result.length > 120 ? '…' : ''}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TaskGraph;
