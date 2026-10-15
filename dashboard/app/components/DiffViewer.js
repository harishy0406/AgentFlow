"use client";

import { useMemo, useState } from "react";

/**
 * Computes a line-by-line diff between two strings using Myers-style LCS.
 */
function computeLineDiff(oldText = "", newText = "") {
  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");

  const m = oldLines.length;
  const n = newLines.length;

  // DP table for LCS
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1));

  for (let i = 0; i < m; i++) {
    for (let j = 0; j < n; j++) {
      if (oldLines[i] === newLines[j]) {
        dp[i + 1][j + 1] = dp[i][j] + 1;
      } else {
        dp[i + 1][j + 1] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  // Backtrack to find diff
  const diff = [];
  let i = m;
  let j = n;

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldLines[i - 1] === newLines[j - 1]) {
      diff.unshift({ type: "same", value: oldLines[i - 1] });
      i--;
      j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      diff.unshift({ type: "added", value: newLines[j - 1] });
      j--;
    } else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
      diff.unshift({ type: "removed", value: oldLines[i - 1] });
      i--;
    }
  }

  return diff;
}

export default function DiffViewer({
  oldContent = "",
  newContent = "",
  oldLabel = "Previous Snapshot",
  newLabel = "Current Version",
  onClose,
}) {
  const [viewMode, setViewMode] = useState("unified"); // 'unified' | 'split'
  const [copiedPatch, setCopiedPatch] = useState(false);

  const diffLines = useMemo(() => {
    return computeLineDiff(oldContent, newContent);
  }, [oldContent, newContent]);

  const stats = useMemo(() => {
    let added = 0;
    let removed = 0;
    diffLines.forEach((l) => {
      if (l.type === "added") added++;
      if (l.type === "removed") removed++;
    });
    return { added, removed };
  }, [diffLines]);

  const annotatedDiffLines = useMemo(() => {
    let oldNum = 1;
    let newNum = 1;
    return diffLines.map((line) => {
      let oldDisplay = "";
      let newDisplay = "";
      if (line.type === "same") {
        oldDisplay = oldNum++;
        newDisplay = newNum++;
      } else if (line.type === "added") {
        newDisplay = newNum++;
      } else if (line.type === "removed") {
        oldDisplay = oldNum++;
      }
      return {
        ...line,
        oldNum: oldDisplay,
        newNum: newDisplay,
      };
    });
  }, [diffLines]);

  const handleCopyPatch = () => {
    const patchHeader = `--- ${oldLabel}\n+++ ${newLabel}\n@@ -1,${oldContent.split("\n").length} +1,${newContent.split("\n").length} @@\n`;
    const patchBody = diffLines.map((l) => {
      if (l.type === "added") return `+${l.value}`;
      if (l.type === "removed") return `-${l.value}`;
      return ` ${l.value}`;
    }).join("\n");
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(patchHeader + patchBody);
      setCopiedPatch(true);
      setTimeout(() => setCopiedPatch(false), 2000);
    }
  };

  return (
    <div
      style={{
        marginTop: 12,
        marginBottom: 16,
        background: "#0d1117",
        border: "1px solid #30363d",
        borderRadius: 8,
        overflow: "hidden",
        fontFamily: "ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, Liberation Mono, monospace",
        fontSize: 12,
      }}
    >
      {/* Diff Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "8px 14px",
          background: "#161b22",
          borderBottom: "1px solid #30363d",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <strong style={{ color: "#c9d1d9", fontSize: 13 }}>
            🔍 Diff: {oldLabel} ➔ {newLabel}
          </strong>
          <span style={{ color: "#3fb950", fontWeight: 600 }}>+{stats.added}</span>
          <span style={{ color: "#f85149", fontWeight: 600 }}>-{stats.removed}</span>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            className="btn btn-secondary btn-sm"
            style={{
              fontSize: 11,
              padding: "3px 8px",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              color: copiedPatch ? "#3fb950" : "#c9d1d9",
              borderColor: copiedPatch ? "#238636" : "#30363d",
            }}
            onClick={handleCopyPatch}
            title="Copy standard git unified diff patch to clipboard"
          >
            {copiedPatch ? "✓ Copied" : "📋 Copy Patch"}
          </button>
          <button
            className={`btn btn-secondary btn-sm ${viewMode === "unified" ? "active" : ""}`}
            style={{ fontSize: 11, padding: "3px 8px" }}
            onClick={() => setViewMode("unified")}
          >
            Unified
          </button>
          <button
            className={`btn btn-secondary btn-sm ${viewMode === "split" ? "active" : ""}`}
            style={{ fontSize: 11, padding: "3px 8px" }}
            onClick={() => setViewMode("split")}
          >
            Split
          </button>
          {onClose && (
            <button
              onClick={onClose}
              style={{
                background: "transparent",
                border: "none",
                color: "#8b949e",
                cursor: "pointer",
                fontSize: 14,
                marginLeft: 8,
              }}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Unified Diff View */}
      {viewMode === "unified" && (
        <div style={{ maxHeight: 320, overflowY: "auto", padding: "8px 0" }}>
          {annotatedDiffLines.map((line, idx) => {
            let bg = "transparent";
            let color = "#c9d1d9";
            let symbol = " ";

            if (line.type === "added") {
              bg = "rgba(46, 160, 67, 0.15)";
              color = "#3fb950";
              symbol = "+";
            } else if (line.type === "removed") {
              bg = "rgba(248, 81, 73, 0.15)";
              color = "#f85149";
              symbol = "-";
            }

            return (
              <div
                key={idx}
                style={{
                  display: "flex",
                  alignItems: "center",
                  background: bg,
                  color: color,
                  padding: "1px 12px",
                  lineHeight: "19px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                <span
                  style={{
                    width: 32,
                    userSelect: "none",
                    textAlign: "right",
                    paddingRight: 6,
                    color: "#484f58",
                    fontFamily: "monospace",
                    fontSize: 10,
                  }}
                >
                  {line.oldNum}
                </span>
                <span
                  style={{
                    width: 32,
                    userSelect: "none",
                    textAlign: "right",
                    paddingRight: 8,
                    color: "#484f58",
                    fontFamily: "monospace",
                    fontSize: 10,
                    borderRight: "1px solid #30363d",
                    marginRight: 8,
                  }}
                >
                  {line.newNum}
                </span>
                <span
                  style={{
                    width: 16,
                    userSelect: "none",
                    opacity: 0.7,
                    fontWeight: "bold",
                  }}
                >
                  {symbol}
                </span>
                <span style={{ flex: 1 }}>{line.value || " "}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Side-by-Side Split View */}
      {viewMode === "split" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", maxHeight: 320, overflowY: "auto" }}>
          <div style={{ padding: "8px 12px", borderRight: "1px solid #30363d", background: "#0d1117" }}>
            <div style={{ color: "#8b949e", fontWeight: 600, marginBottom: 6, fontSize: 11 }}>
              {oldLabel} (Before)
            </div>
            <pre style={{ margin: 0, color: "#f85149", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {oldContent}
            </pre>
          </div>
          <div style={{ padding: "8px 12px", background: "#0d1117" }}>
            <div style={{ color: "#8b949e", fontWeight: 600, marginBottom: 6, fontSize: 11 }}>
              {newLabel} (After)
            </div>
            <pre style={{ margin: 0, color: "#3fb950", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {newContent}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
