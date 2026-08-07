"use client";

import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

/**
 * Status → colour map for the node badges.
 */
const STATUS_COLORS = {
  fresh: "#22c55e",       // green
  stale: "#eab308",       // yellow
  regenerating: "#3b82f6", // blue
  drifted: "#ef4444",     // red
  pending: "#94a3b8",     // grey
};

/**
 * Custom node styling for artifact nodes in the dependency graph.
 */
function getNodeStyle(status) {
  const borderColor = STATUS_COLORS[status] || STATUS_COLORS.pending;
  return {
    background: "#1e1e2e",
    color: "#e2e8f0",
    border: `2px solid ${borderColor}`,
    borderRadius: "12px",
    padding: "16px 20px",
    fontSize: "13px",
    fontFamily: "'Inter', sans-serif",
    minWidth: "160px",
    textAlign: "center",
    boxShadow: `0 0 12px ${borderColor}33`,
  };
}

/**
 * The fixed artifact dependency layout.
 *
 * Layout:
 *   PRD (top)
 *     ↓
 *   SDD
 *    ↓  ↘
 *  DB    USER_STORIES
 *    ↓      ↓
 *  API    TASKS
 */
const LAYOUT_POSITIONS = {
  PRD:          { x: 300, y: 0 },
  SDD:          { x: 300, y: 120 },
  DB_SCHEMA:    { x: 150, y: 240 },
  API_SPEC:     { x: 150, y: 360 },
  USER_STORIES: { x: 450, y: 240 },
  TASKS:        { x: 450, y: 360 },
};

const EDGES_DEFINITION = [
  { id: "e-prd-sdd", source: "PRD", target: "SDD" },
  { id: "e-sdd-db",  source: "SDD", target: "DB_SCHEMA" },
  { id: "e-sdd-us",  source: "SDD", target: "USER_STORIES" },
  { id: "e-db-api",  source: "DB_SCHEMA", target: "API_SPEC" },
  { id: "e-us-tasks", source: "USER_STORIES", target: "TASKS" },
];

/**
 * Build React Flow nodes from artifact data.
 * @param {Array} artifacts - Array of artifact objects from the API.
 */
export function buildNodes(artifacts = []) {
  const artifactMap = {};
  artifacts.forEach((a) => {
    artifactMap[a.artifact_type] = a;
  });

  return Object.entries(LAYOUT_POSITIONS).map(([type, pos]) => {
    const artifact = artifactMap[type];
    const status = artifact?.status || "pending";
    const version = artifact?.version || 0;
    const quality = artifact?.quality_signal_score;

    return {
      id: type,
      position: pos,
      data: {
        label: (
          <div>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>{type.replace("_", " ")}</div>
            <div style={{
              display: "inline-block",
              padding: "2px 8px",
              borderRadius: "9999px",
              fontSize: "11px",
              fontWeight: 600,
              background: STATUS_COLORS[status] || STATUS_COLORS.pending,
              color: "#fff",
            }}>
              {status.toUpperCase()}
            </div>
            <div style={{ marginTop: 6, fontSize: "11px", opacity: 0.7 }}>
              v{version}
              {quality != null && ` • Q: ${(quality * 100).toFixed(0)}%`}
            </div>
          </div>
        ),
      },
      style: getNodeStyle(status),
    };
  });
}

/**
 * Build React Flow edges with styling.
 */
export function buildEdges() {
  return EDGES_DEFINITION.map((e) => ({
    ...e,
    type: "smoothstep",
    animated: true,
    style: { stroke: "#64748b", strokeWidth: 2 },
  }));
}

/**
 * DependencyGraph — renders the 6-node artifact DAG.
 *
 * @param {Object} props
 * @param {Array}  props.artifacts - Artifact data from the API.
 * @param {Function} props.onNodeClick - Callback when a node is clicked.
 */
export default function DependencyGraph({ artifacts = [], onNodeClick }) {
  const initialNodes = useMemo(() => buildNodes(artifacts), [artifacts]);
  const initialEdges = useMemo(() => buildEdges(), []);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const handleNodeClick = useCallback(
    (event, node) => {
      if (onNodeClick) onNodeClick(node.id);
    },
    [onNodeClick]
  );

  return (
    <div style={{ width: "100%", height: "600px", borderRadius: "12px", overflow: "hidden", background: "#0f0f1a" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        attributionPosition="bottom-left"
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e293b" gap={20} />
        <Controls
          style={{ background: "#1e1e2e", borderColor: "#334155", color: "#e2e8f0" }}
        />
        <MiniMap
          nodeColor={(node) => {
            const status = node.style?.borderColor || STATUS_COLORS.pending;
            return status;
          }}
          style={{ background: "#0f0f1a", borderColor: "#334155" }}
        />
      </ReactFlow>
    </div>
  );
}
