"use client";

import { useState, useCallback, useMemo, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
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
 * Status → class name for pipeline status badges.
 */
const STATUS_BADGE_CLASSES = {
  fresh: "pipeline-badge fresh",
  stale: "pipeline-badge stale",
  regenerating: "pipeline-badge regenerating",
  drifted: "pipeline-badge drifted",
  pending: "pipeline-badge pending",
};

const NODE_ICONS = {
  PRD: "📋",
  SDD: "📐",
  DB_SCHEMA: "🗄️",
  API_SPEC: "⚡",
  USER_STORIES: "👥",
  TASKS: "🔨",
  CODE_GENERATION: "🚀",
};

/**
 * Semantic Edge Type Color Palette
 * Matches Table 4.1 in system specification.
 */
export const EDGE_TYPE_COLORS = {
  DERIVES: "#38bdf8",     // Sky blue: direct architectural derivation
  DEPENDS_ON: "#c084fc",  // Light purple: schema/contract dependency
  REFERENCES: "#fbbf24",  // Amber: traceability reference
  IMPLEMENTS: "#34d399",  // Emerald: concrete code implementation
};

/**
 * Custom node styling for artifact nodes in the dependency graph.
 */
function getNodeStyle(status, isSelected = false) {
  const borderColor = STATUS_COLORS[status] || STATUS_COLORS.pending;
  return {
    background: isSelected ? "rgba(30, 41, 59, 0.95)" : "#131322",
    color: "#e2e8f0",
    border: `2px solid ${borderColor}`,
    borderRadius: "12px",
    padding: "16px 20px",
    fontSize: "13px",
    fontFamily: "'Inter', sans-serif",
    minWidth: "170px",
    textAlign: "center",
    boxShadow: isSelected
      ? `0 0 24px ${borderColor}99, 0 8px 32px rgba(0,0,0,0.8)`
      : `0 0 14px ${borderColor}33, 0 4px 16px rgba(0,0,0,0.5)`,
    cursor: "pointer",
    transition: "all 0.2s ease",
  };
}

/**
 * Symmetrical 5-Level Topological Layout for the 11-Edge DAG (Table 4.1).
 *
 *               PRD (Level 0, Center)
 *                     ↙             ↘
 *       SDD (Level 1, Left)     USER_STORIES (Level 1, Right)
 *         ↓            ↘               ↓
 *  DB_SCHEMA (L2) ➔  API_SPEC (L2)     ↓
 *         ↓            ↙       ↘       ↓
 *         ↓      TASKS (Level 3, Right)
 *         ↓            ↓       ↙
 *       CODE_GENERATION (Level 4, Center)
 */
export const LAYOUT_POSITIONS = {
  PRD:             { x: 360, y: 0 },
  SDD:             { x: 140, y: 150 },
  DB_SCHEMA:       { x: 140, y: 310 },
  API_SPEC:        { x: 360, y: 310 },
  USER_STORIES:    { x: 600, y: 170 },
  TASKS:           { x: 600, y: 390 },
  CODE_GENERATION: { x: 360, y: 550 },
};

/**
 * Canonical 11-Edge Type-Level Dependency Graph Specification
 * Derived strictly from Table 4.1 and backend graph_engine.py.
 */
export const TYPE_LEVEL_EDGES = [
  // 1. PRD → SDD (DERIVES)
  {
    id: "e-prd-sdd",
    source: "PRD",
    target: "SDD",
    edgeType: "DERIVES",
    info: "Requirement identifiers, constraints, actors, quality attributes",
  },
  // 2. SDD → DB Schema (DERIVES)
  {
    id: "e-sdd-db",
    source: "SDD",
    target: "DB_SCHEMA",
    edgeType: "DERIVES",
    info: "Entities, relationships, data-ownership boundaries",
  },
  // 3. SDD → API Spec (DERIVES)
  {
    id: "e-sdd-api",
    source: "SDD",
    target: "API_SPEC",
    edgeType: "DERIVES",
    info: "Components, service boundaries, authentication model",
  },
  // 4. DB Schema → API Spec (DEPENDS_ON)
  {
    id: "e-db-api",
    source: "DB_SCHEMA",
    target: "API_SPEC",
    edgeType: "DEPENDS_ON",
    info: "Resource fields, types, keys used in request/response bodies",
  },
  // 5. PRD → User Stories (REFERENCES)
  {
    id: "e-prd-us",
    source: "PRD",
    target: "USER_STORIES",
    edgeType: "REFERENCES",
    info: "Requirement IDs that each story satisfies",
  },
  // 6. API Spec → User Stories (REFERENCES)
  {
    id: "e-api-us",
    source: "API_SPEC",
    target: "USER_STORIES",
    edgeType: "REFERENCES",
    info: "Endpoints that realise each story",
  },
  // 7. User Stories → Tasks (DERIVES)
  {
    id: "e-us-tasks",
    source: "USER_STORIES",
    target: "TASKS",
    edgeType: "DERIVES",
    info: "Acceptance criteria turned into work items",
  },
  // 8. API Spec → Tasks (DEPENDS_ON)
  {
    id: "e-api-tasks",
    source: "API_SPEC",
    target: "TASKS",
    edgeType: "DEPENDS_ON",
    info: "Endpoints to be implemented and tested",
  },
  // 9. DB Schema → Code Generation (IMPLEMENTS)
  {
    id: "e-db-code",
    source: "DB_SCHEMA",
    target: "CODE_GENERATION",
    edgeType: "IMPLEMENTS",
    info: "Models and migrations",
  },
  // 10. API Spec → Code Generation (IMPLEMENTS)
  {
    id: "e-api-code",
    source: "API_SPEC",
    target: "CODE_GENERATION",
    edgeType: "IMPLEMENTS",
    info: "Routers and request/response models",
  },
  // 11. Tasks → Code Generation (REFERENCES)
  {
    id: "e-tasks-code",
    source: "TASKS",
    target: "CODE_GENERATION",
    edgeType: "REFERENCES",
    info: "Module layout and test stubs",
  },
];

/**
 * Build React Flow nodes from artifact data.
 * @param {Array} artifacts - Array of artifact objects from the API.
 * @param {string|null} selectedArtifactId - Optional selected node ID.
 */
export function buildNodes(artifacts = [], selectedArtifactId = null) {
  const artifactMap = {};
  artifacts.forEach((a) => {
    artifactMap[a.artifact_type] = a;
  });

  return Object.entries(LAYOUT_POSITIONS).map(([type, pos]) => {
    const artifact = artifactMap[type];
    const status = artifact?.status || "pending";
    const version = artifact?.version || 0;
    const quality = artifact?.quality_signal_score;
    const qualityPct = quality != null ? (quality <= 1.0 ? Math.round(quality * 100) : Math.round(quality)) : null;
    const icon = NODE_ICONS[type] || "📄";
    const isSelected = selectedArtifactId === type;

    return {
      id: type,
      position: pos,
      data: {
        label: (
          <div>
            <div style={{ fontWeight: 700, marginBottom: 6, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
              <span>{icon}</span>
              <span>{type.replace("_", " ")}</span>
            </div>
            <div style={{
              display: "inline-block",
              padding: "2px 8px",
              borderRadius: "9999px",
              fontSize: "11px",
              fontWeight: 600,
              background: STATUS_COLORS[status] || STATUS_COLORS.pending,
              color: "#fff",
              boxShadow: `0 0 8px ${(STATUS_COLORS[status] || STATUS_COLORS.pending)}66`,
            }}>
              {status.toUpperCase()}
            </div>
            <div style={{ marginTop: 6, fontSize: "11px", opacity: 0.75 }}>
              v{version}
              {qualityPct != null && ` • Q: ${qualityPct}%`}
            </div>
          </div>
        ),
      },
      style: getNodeStyle(status, isSelected),
    };
  });
}

/**
 * Build React Flow edges with strict Table 4.1 type labels, arrowheads, and colors.
 */
export function buildEdges(selectedEdgeId = null) {
  return TYPE_LEVEL_EDGES.map((e) => {
    const color = EDGE_TYPE_COLORS[e.edgeType] || "#64748b";
    const isSelected = selectedEdgeId === e.id;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      animated: true,
      label: e.edgeType,
      labelStyle: {
        fill: color,
        fontWeight: 700,
        fontSize: 9,
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        letterSpacing: "0.5px",
      },
      labelBgStyle: {
        fill: "#0b0f19",
        fillOpacity: 0.95,
        stroke: color,
        strokeWidth: isSelected ? 1.5 : 0.8,
        rx: 4,
        ry: 4,
      },
      labelBgPadding: [4, 2],
      style: {
        stroke: color,
        strokeWidth: isSelected ? 3 : 2,
        strokeDasharray: e.edgeType === "REFERENCES" ? "5,4" : undefined,
        opacity: selectedEdgeId && !isSelected ? 0.4 : 0.9,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: color,
        width: 14,
        height: 14,
      },
      data: {
        edgeType: e.edgeType,
        info: e.info,
      },
    };
  });
}

/**
 * Get pipeline status badge HTML for a given status.
 */
export function getPipelineStatusBadge(status) {
  const cls = STATUS_BADGE_CLASSES[status] || STATUS_BADGE_CLASSES.pending;
  return `<div className="${cls}">${status}</div>`;
}

/**
 * DependencyGraph — renders the 11-edge, 7-node artifact DAG matching Table 4.1.
 *
 * @param {Object} props
 * @param {Array}  props.artifacts - Artifact data from the API.
 * @param {Function} props.onNodeClick - Callback when a node is clicked.
 */
export default function DependencyGraph({ artifacts = [], onNodeClick }) {
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);

  const initialNodes = useMemo(() => buildNodes(artifacts, selectedNodeId), [artifacts, selectedNodeId]);
  const initialEdges = useMemo(() => buildEdges(selectedEdge?.id), [selectedEdge]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Synchronize live graph nodes whenever artifacts or selection change
  useEffect(() => {
    setNodes(buildNodes(artifacts, selectedNodeId));
  }, [artifacts, selectedNodeId, setNodes]);

  // Synchronize edges whenever edge selection changes
  useEffect(() => {
    setEdges(buildEdges(selectedEdge?.id));
  }, [selectedEdge, setEdges]);

  const handleNodeClick = useCallback(
    (event, node) => {
      setSelectedNodeId(node.id);
      setSelectedEdge(null);
      if (onNodeClick) onNodeClick(node.id);
    },
    [onNodeClick]
  );

  const handleEdgeClick = useCallback((event, edge) => {
    const edgeData = TYPE_LEVEL_EDGES.find((e) => e.id === edge.id);
    setSelectedEdge(edgeData || null);
  }, []);

  return (
    <div style={{ width: "100%", borderRadius: "12px", overflow: "hidden", background: "#0b0c16", border: "1px solid var(--border)" }}>
      {/* Table 4.1 Edge Semantics Legend Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
          padding: "10px 18px",
          background: "#131322",
          borderBottom: "1px solid #1e293b",
          fontSize: 11,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Table 4.1 Edge Types:
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#38bdf8", fontWeight: 600 }}>
            <span style={{ width: 14, height: 2, background: "#38bdf8", display: "inline-block" }} /> DERIVES (4)
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#c084fc", fontWeight: 600 }}>
            <span style={{ width: 14, height: 2, background: "#c084fc", display: "inline-block" }} /> DEPENDS_ON (2)
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#fbbf24", fontWeight: 600 }}>
            <span style={{ width: 14, height: 2, borderBottom: "2px dashed #fbbf24", display: "inline-block" }} /> REFERENCES (3)
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "#34d399", fontWeight: 600 }}>
            <span style={{ width: 14, height: 2, background: "#34d399", display: "inline-block" }} /> IMPLEMENTS (2)
          </span>
        </div>
        <div style={{ color: "var(--text-muted)", fontSize: 11, fontFamily: "var(--font-mono)" }}>
          11 Canonical DAG Edges • Click any edge to inspect payload
        </div>
      </div>

      {/* Selected Edge Inspection Drawer (shows Table 4.1 Information Flow) */}
      {selectedEdge && (
        <div
          style={{
            padding: "8px 18px",
            background: "linear-gradient(90deg, rgba(56, 189, 248, 0.08), rgba(168, 85, 247, 0.08))",
            borderBottom: "1px solid #1e293b",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: 11,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontWeight: 700, color: EDGE_TYPE_COLORS[selectedEdge.edgeType] }}>
              [{selectedEdge.edgeType}]
            </span>
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>
              {selectedEdge.source} ➔ {selectedEdge.target}:
            </span>
            <span style={{ color: "var(--text-secondary)" }}>
              {selectedEdge.info}
            </span>
          </div>
          <button
            onClick={() => setSelectedEdge(null)}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: 14,
              padding: "0 4px",
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Canvas */}
      <div style={{ width: "100%", height: "620px" }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onEdgeClick={handleEdgeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          attributionPosition="bottom-left"
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e293b" gap={20} />
          <Controls
            style={{ background: "#131322", borderColor: "#334155", color: "#e2e8f0" }}
          />
          <MiniMap
            nodeColor={(node) => {
              const status = node.style?.borderColor || STATUS_COLORS.pending;
              return status;
            }}
            style={{ background: "#0b0c16", borderColor: "#334155" }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
