"use client";

import { useState, useCallback, useEffect } from "react";
import DependencyGraph from "./components/DependencyGraph";
import DiffViewer from "./components/DiffViewer";
import {
  createProject,
  clarifyProject,
  generateArtifacts,
  getArtifacts,
  listProjects,
  triggerAudit,
  listDrifts,
  fixDrift,
  dismissDrift,
  triggerEvalRun,
  listEvalRuns,
  updateSection,
  getSectionVersions,
  rollbackSection,
  getExportUrl,
  getDownloadZipUrl,
  getCodeFiles,
  updateCodeFile,
} from "./lib/api";

export default function Home() {
  const [activeTab, setActiveTab] = useState("create");
  const [projectName, setProjectName] = useState("");
  const [projectBrief, setProjectBrief] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentProject, setCurrentProject] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const [toast, setToast] = useState(null);
  const [projects, setProjects] = useState([]);

  // HITL clarification state
  const [clarifyStep, setClarifyStep] = useState("brief"); // 'brief' | 'questions' | 'generating'
  const [clarifyQuestions, setClarifyQuestions] = useState("");
  const [clarifyAnswers, setClarifyAnswers] = useState("");

  // Drift state
  const [drifts, setDrifts] = useState([]);
  const [driftLoading, setDriftLoading] = useState(false);

  // Eval state
  const [evalRuns, setEvalRuns] = useState([]);

  // Phase 7: Codebase explorer state
  const [codeData, setCodeData] = useState(null);
  const [selectedCodeFile, setSelectedCodeFile] = useState(null);
  const [codeLoading, setCodeLoading] = useState(false);
  const [isEditingCode, setIsEditingCode] = useState(false);
  const [editingCodeContent, setEditingCodeContent] = useState("");
  const [savingCode, setSavingCode] = useState(false);

  // Section editing & version history state
  const [activeArtifactType, setActiveArtifactType] = useState("PRD");
  const [editingSectionId, setEditingSectionId] = useState(null);
  const [editingContent, setEditingContent] = useState("");
  const [savingSection, setSavingSection] = useState(false);
  const [sectionVersions, setSectionVersions] = useState([]);
  const [historySectionId, setHistorySectionId] = useState(null);
  const [diffTargetSnapshot, setDiffTargetSnapshot] = useState(null);

  const showToast = useCallback((message, type = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  // Real-time WebSocket connection for live graph status transitions
  useEffect(() => {
    if (!currentProject?.id) return;

    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
    const wsUrl = `${wsBase}/ws/${currentProject.id}`;
    let ws;
    try {
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "artifact_status") {
            setArtifacts((prev) =>
              prev.map((art) =>
                art.artifact_type === msg.artifact_type
                  ? { ...art, status: msg.status }
                  : art
              )
            );
          } else if (msg.type === "pipeline_completed" || msg.type === "regeneration_completed") {
            getArtifacts(currentProject.id).then((arts) => setArtifacts(arts)).catch(() => {});
            if (msg.message) showToast(msg.message, "success");
          } else if (msg.type === "pipeline_error") {
            showToast(msg.error || "Generation error", "error");
          }
        } catch (e) {
          console.error("WS message parse error:", e);
        }
      };
    } catch (e) {
      console.warn("WebSocket connection notice:", e);
    }

    return () => {
      if (ws) ws.close();
    };
  }, [currentProject?.id, showToast]);

  // ---- HITL: Step 1 — Get clarification questions ----
  const handleClarify = async (e) => {
    e.preventDefault();
    if (!projectName.trim() || !projectBrief.trim()) return;

    setLoading(true);
    try {
      const res = await clarifyProject(projectBrief);
      setClarifyQuestions(res.questions);
      setClarifyStep("questions");
      showToast("Agent has a few questions before proceeding.", "info");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  // ---- HITL: Step 2 — Submit answers & generate ----
  const handleCreateWithClarifications = async () => {
    setLoading(true);
    setClarifyStep("generating");
    try {
      const clarifications = `Questions:\n${clarifyQuestions}\n\nAnswers:\n${clarifyAnswers}`;
      const project = await createProject(projectName, projectBrief, clarifications);
      setCurrentProject(project);
      showToast("Project created! Generating artifacts...", "success");

      await generateArtifacts(project.id);
      const arts = await getArtifacts(project.id);
      setArtifacts(arts);
      setActiveTab("graph");
      setClarifyStep("brief");
      setProjectName("");
      setProjectBrief("");
      setClarifyQuestions("");
      setClarifyAnswers("");
      showToast("All artifacts generated successfully!", "success");
    } catch (err) {
      showToast(err.message, "error");
      setClarifyStep("questions");
    } finally {
      setLoading(false);
    }
  };

  // ---- Skip clarification and generate directly ----
  const handleSkipClarify = async () => {
    setLoading(true);
    setClarifyStep("generating");
    try {
      const project = await createProject(projectName, projectBrief);
      setCurrentProject(project);
      showToast("Skipped clarifications. Generating artifacts...", "info");

      await generateArtifacts(project.id);
      const arts = await getArtifacts(project.id);
      setArtifacts(arts);
      setActiveTab("graph");
      setClarifyStep("brief");
      setProjectName("");
      setProjectBrief("");
      showToast("All artifacts generated successfully!", "success");
    } catch (err) {
      showToast(err.message, "error");
      setClarifyStep("brief");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadProjects = async () => {
    try {
      const projs = await listProjects();
      setProjects(projs);
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  const handleSelectProject = async (project) => {
    setCurrentProject(project);
    try {
      const arts = await getArtifacts(project.id);
      setArtifacts(arts);
      setActiveTab("graph");
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  const handleNodeClick = useCallback(
    (artifactType) => {
      const artifact = artifacts.find((a) => a.artifact_type === artifactType);
      setSelectedArtifact(artifact || null);
    },
    [artifacts]
  );

  return (
    <div className="dashboard">
      {/* Navbar */}
      <nav className="navbar">
        <div className="navbar-brand">
          <h1>⚡ AgentFlow</h1>
          <span className="navbar-version">v0.6.0</span>
        </div>
        {currentProject && (
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              Project: <strong style={{ color: "var(--text-primary)" }}>{currentProject.name}</strong>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <a
                href={getDownloadZipUrl(currentProject.id)}
                className="btn btn-primary btn-sm"
                style={{
                  textDecoration: "none",
                  fontSize: 12,
                  padding: "5px 12px",
                  background: "#2ea043",
                  color: "#ffffff",
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                📦 Download Code (.zip)
              </a>
              <a
                href={getExportUrl(currentProject.id, "markdown")}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary btn-sm"
                style={{ textDecoration: "none", fontSize: 12, padding: "5px 10px" }}
              >
                📥 Specs (.md)
              </a>
              <a
                href={getExportUrl(currentProject.id, "json")}
                target="_blank"
                rel="noreferrer"
                className="btn btn-secondary btn-sm"
                style={{ textDecoration: "none", fontSize: 12, padding: "5px 10px" }}
              >
                📥 JSON
              </a>
            </div>
          </div>
        )}
      </nav>

      {/* Main Content */}
      <div className="main-content">
        {/* Tab Bar */}
        <div className="tabs">
          <button
            className={`tab ${activeTab === "create" ? "active" : ""}`}
            onClick={() => setActiveTab("create")}
          >
            New Project
          </button>
          <button
            className={`tab ${activeTab === "projects" ? "active" : ""}`}
            onClick={() => { setActiveTab("projects"); handleLoadProjects(); }}
          >
            Projects
          </button>
          <button
            className={`tab ${activeTab === "graph" ? "active" : ""}`}
            onClick={() => setActiveTab("graph")}
            disabled={!currentProject}
          >
            Dependency Graph
          </button>
          <button
            className={`tab ${activeTab === "artifacts" ? "active" : ""}`}
            onClick={() => setActiveTab("artifacts")}
            disabled={!currentProject}
          >
            Artifacts
          </button>
          <button
            className={`tab ${activeTab === "code" ? "active" : ""}`}
            onClick={async () => {
              setActiveTab("code");
              if (currentProject) {
                setCodeLoading(true);
                try {
                  const res = await getCodeFiles(currentProject.id);
                  setCodeData(res);
                  if (res.files && res.files.length > 0) {
                    setSelectedCodeFile(res.files[0]);
                  }
                } catch (err) {
                  showToast(err.message, "error");
                } finally {
                  setCodeLoading(false);
                }
              }
            }}
            disabled={!currentProject}
          >
            Codebase
          </button>
          <button
            className={`tab ${activeTab === "drifts" ? "active" : ""}`}
            onClick={() => setActiveTab("drifts")}
            disabled={!currentProject}
          >
            Drifts
          </button>
          <button
            className={`tab ${activeTab === "metrics" ? "active" : ""}`}
            onClick={() => setActiveTab("metrics")}
            disabled={!currentProject}
          >
            Metrics
          </button>
          <button
            className={`tab ${activeTab === "evaluations" ? "active" : ""}`}
            onClick={() => setActiveTab("evaluations")}
          >
            Evaluations
          </button>
        </div>

        {/* Tab: Create Project (with HITL Clarification) */}
        {activeTab === "create" && (
          <div className="card">
            <h2 className="card-title">Create New Project</h2>

            {/* Step 1: Brief Input */}
            {clarifyStep === "brief" && (
              <form onSubmit={handleClarify}>
                <div className="form-group">
                  <label className="form-label">Project Name</label>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="e.g. E-Commerce Platform"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Project Brief</label>
                  <textarea
                    className="form-textarea"
                    placeholder="Describe what you want to build. The more detail you provide, the better the generated artifacts will be..."
                    value={projectBrief}
                    onChange={(e) => setProjectBrief(e.target.value)}
                    required
                  />
                </div>
                <div style={{ display: "flex", gap: 12 }}>
                  <button type="submit" className="btn btn-primary" disabled={loading}>
                    {loading ? (<><span className="spinner" /> Thinking...</>) : "🧠 Get Clarifying Questions"}
                  </button>
                  <button type="button" className="btn btn-secondary" disabled={loading} onClick={handleSkipClarify}>
                    ⚡ Skip & Generate Directly
                  </button>
                </div>
              </form>
            )}

            {/* Step 2: Clarification Q&A */}
            {clarifyStep === "questions" && (
              <div>
                <div className="form-group">
                  <label className="form-label">🤖 Agent's Clarifying Questions</label>
                  <div className="artifact-content" style={{ marginBottom: 16, whiteSpace: "pre-wrap" }}>
                    {clarifyQuestions}
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Your Answers</label>
                  <textarea
                    className="form-textarea"
                    placeholder="Answer each question. e.g.&#10;1. We target mobile users aged 18-35...&#10;2. We need Stripe and PayPal..."
                    value={clarifyAnswers}
                    onChange={(e) => setClarifyAnswers(e.target.value)}
                    rows={8}
                  />
                </div>
                <div style={{ display: "flex", gap: 12 }}>
                  <button className="btn btn-primary" disabled={loading} onClick={handleCreateWithClarifications}>
                    {loading ? (<><span className="spinner" /> Generating...</>) : "🚀 Create & Generate"}
                  </button>
                  <button className="btn btn-secondary" onClick={() => setClarifyStep("brief")}>
                    ← Back
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Generating */}
            {clarifyStep === "generating" && (
              <div style={{ textAlign: "center", padding: 40 }}>
                <span className="spinner" style={{ width: 32, height: 32 }} />
                <p style={{ color: "var(--text-secondary)", marginTop: 16 }}>
                  Generating all 6 artifacts through the pipeline...
                </p>
              </div>
            )}
          </div>
        )}

        {/* Tab: Projects List */}
        {activeTab === "projects" && (
          <div className="card">
            <h2 className="card-title">Your Projects</h2>
            {projects.length === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>No projects yet. Create one to get started.</p>
            ) : (
              projects.map((p) => (
                <div
                  key={p.id}
                  className="drift-item"
                  style={{ cursor: "pointer" }}
                  onClick={() => handleSelectProject(p)}
                >
                  <div className="drift-item-body">
                    <strong>{p.name}</strong>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                      {p.brief?.substring(0, 120)}...
                    </div>
                  </div>
                  <button className="btn btn-secondary btn-sm">Open →</button>
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab: Dependency Graph */}
        {activeTab === "graph" && currentProject && (
          <div className="card">
            <h2 className="card-title">Dependency Graph</h2>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
              Click on any node to view its artifact content.
            </p>
            <DependencyGraph
              artifacts={artifacts}
              onNodeClick={handleNodeClick}
            />
            {selectedArtifact && (
              <div style={{ marginTop: 24 }}>
                <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>
                  {selectedArtifact.artifact_type.replace("_", " ")}
                  <span className={`badge badge-${selectedArtifact.status}`} style={{ marginLeft: 12 }}>
                    {selectedArtifact.status}
                  </span>
                </h3>
                <div className="artifact-content">
                  {selectedArtifact.sections?.map((s) => s.content).join("\n\n") ||
                    "No content generated yet."}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab: Artifacts (Phase 2 + 5 — Full Implementation) */}
        {activeTab === "artifacts" && currentProject && (
          <div className="card">
            <h2 className="card-title">Artifacts & Section Editor</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 16 }}>
              Select an artifact below to inspect sections, perform edits that trigger selective regeneration, or rollback to previous versions.
            </p>

            {/* Artifact Sub-Navigation Pills */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 20 }}>
              {["PRD", "SDD", "DB_SCHEMA", "API_SPEC", "USER_STORIES", "TASKS"].map((type) => {
                const node = artifacts.find((a) => a.artifact_type === type);
                const isSelected = activeArtifactType === type;
                return (
                  <button
                    key={type}
                    onClick={() => {
                      setActiveArtifactType(type);
                      setEditingSectionId(null);
                      setHistorySectionId(null);
                    }}
                    className={`tab ${isSelected ? "active" : ""}`}
                    style={{ padding: "6px 14px", fontSize: 12, borderRadius: 20 }}
                  >
                    {type.replace("_", " ")}
                    {node && (
                      <span
                        className={`badge badge-${node.status}`}
                        style={{ marginLeft: 8, fontSize: 10 }}
                      >
                        v{node.version}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Selected Artifact Node Details */}
            {(() => {
              const currentArt = artifacts.find((a) => a.artifact_type === activeArtifactType);
              if (!currentArt) {
                return (
                  <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                    No content generated for {activeArtifactType.replace("_", " ")} yet.
                  </p>
                );
              }

              return (
                <div>
                  {/* Artifact Meta Header */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      background: "var(--bg-secondary)",
                      padding: "12px 16px",
                      borderRadius: 8,
                      marginBottom: 20,
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div>
                      <strong style={{ fontSize: 15, color: "var(--text-primary)" }}>
                        {currentArt.artifact_type.replace("_", " ")}
                      </strong>
                      <span className={`badge badge-${currentArt.status}`} style={{ marginLeft: 10 }}>
                        {currentArt.status}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                      Version: <strong>v{currentArt.version}</strong> • Quality:{" "}
                      <strong>
                        {currentArt.quality_signal_score != null
                          ? `${(currentArt.quality_signal_score * 100).toFixed(0)}%`
                          : "N/A"}
                      </strong>{" "}
                      • Model: <span style={{ color: "var(--accent-purple)" }}>{currentArt.generated_by_model || "claude-3-haiku"}</span>
                    </div>
                  </div>

                  {/* Sections List */}
                  {currentArt.sections && currentArt.sections.length > 0 ? (
                    currentArt.sections.map((sec) => {
                      const isEditing = editingSectionId === sec.id;
                      const isViewingHistory = historySectionId === sec.id;

                      return (
                        <div
                          key={sec.id}
                          className="stat-card"
                          style={{ textAlign: "left", marginBottom: 16, border: isEditing ? "1px solid var(--accent-blue)" : "1px solid var(--border)" }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              marginBottom: 10,
                            }}
                          >
                            <div>
                              <span
                                style={{
                                  background: "var(--bg-hover)",
                                  color: "var(--accent-blue)",
                                  padding: "3px 8px",
                                  borderRadius: 4,
                                  fontFamily: "monospace",
                                  fontSize: 12,
                                  fontWeight: 600,
                                }}
                              >
                                § {sec.section_key}
                              </span>
                              <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 10 }}>
                                Hash: {sec.content_hash?.substring(0, 10)}...
                              </span>
                            </div>
                            <div style={{ display: "flex", gap: 8 }}>
                              {!isEditing && (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => {
                                    setEditingSectionId(sec.id);
                                    setEditingContent(sec.content);
                                    setHistorySectionId(null);
                                  }}
                                >
                                  ✏️ Edit
                                </button>
                              )}
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={async () => {
                                  if (isViewingHistory) {
                                    setHistorySectionId(null);
                                  } else {
                                    try {
                                      const hist = await getSectionVersions(sec.id);
                                      setSectionVersions(hist);
                                      setHistorySectionId(sec.id);
                                    } catch (err) {
                                      showToast(err.message, "error");
                                    }
                                  }
                                }}
                              >
                                {isViewingHistory ? "✕ Close History" : "📜 History"}
                              </button>
                            </div>
                          </div>

                          {/* Inline Section Editor */}
                          {isEditing ? (
                            <div>
                              <textarea
                                className="form-textarea"
                                value={editingContent}
                                onChange={(e) => setEditingContent(e.target.value)}
                                rows={10}
                                style={{ fontFamily: "monospace", fontSize: 13, marginBottom: 12 }}
                              />
                              <div style={{ display: "flex", gap: 10 }}>
                                <button
                                  className="btn btn-primary btn-sm"
                                  disabled={savingSection}
                                  onClick={async () => {
                                    setSavingSection(true);
                                    try {
                                      await updateSection(sec.id, editingContent);
                                      const updated = await getArtifacts(currentProject.id);
                                      setArtifacts(updated);
                                      setEditingSectionId(null);
                                      showToast("Section updated! Selective regeneration completed.", "success");
                                    } catch (err) {
                                      showToast(err.message, "error");
                                    } finally {
                                      setSavingSection(false);
                                    }
                                  }}
                                >
                                  {savingSection ? (<><span className="spinner" /> Regenerating downstream...</>) : "⚡ Save & Trigger Selective Regeneration"}
                                </button>
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => setEditingSectionId(null)}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : (
                            <div
                              className="artifact-content"
                              style={{ maxHeight: 250, overflowY: "auto", fontSize: 13, whiteSpace: "pre-wrap" }}
                            >
                              {sec.content}
                            </div>
                          )}

                          {/* Version History Sub-Panel */}
                          {isViewingHistory && (
                            <div
                              style={{
                                marginTop: 14,
                                paddingTop: 14,
                                borderTop: "1px solid var(--border)",
                                background: "var(--bg-secondary)",
                                padding: 12,
                                borderRadius: 6,
                              }}
                            >
                              <h4 style={{ fontSize: 13, fontWeight: 700, marginBottom: 10, color: "var(--text-secondary)" }}>
                                📜 Version Snapshots for § {sec.section_key}
                              </h4>
                              {sectionVersions.length === 0 ? (
                                <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
                                  No prior snapshots recorded yet.
                                </p>
                              ) : (
                                sectionVersions.map((v) => (
                                  <div
                                    key={v.id}
                                    style={{
                                      padding: "8px 0",
                                      borderBottom: "1px solid var(--border)",
                                    }}
                                  >
                                    <div
                                      style={{
                                        display: "flex",
                                        justifyContent: "space-between",
                                        alignItems: "center",
                                      }}
                                    >
                                      <div>
                                        <strong style={{ fontSize: 12 }}>Snapshot v{v.version}</strong>
                                        <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 10 }}>
                                          {new Date(v.created_at).toLocaleString()}
                                        </span>
                                      </div>
                                      <div style={{ display: "flex", gap: 8 }}>
                                        <button
                                          className={`btn btn-secondary btn-sm ${diffTargetSnapshot?.id === v.id ? "active" : ""}`}
                                          style={{ fontSize: 11, padding: "3px 8px" }}
                                          onClick={() =>
                                            setDiffTargetSnapshot(diffTargetSnapshot?.id === v.id ? null : v)
                                          }
                                        >
                                          {diffTargetSnapshot?.id === v.id ? "✕ Hide Diff" : "🔍 Diff"}
                                        </button>
                                        <button
                                          className="btn btn-secondary btn-sm"
                                          style={{ fontSize: 11, padding: "3px 8px" }}
                                          onClick={async () => {
                                            try {
                                              await rollbackSection(sec.id, v.version);
                                              const updated = await getArtifacts(currentProject.id);
                                              setArtifacts(updated);
                                              setHistorySectionId(null);
                                              setDiffTargetSnapshot(null);
                                              showToast(`Rolled back § ${sec.section_key} to v${v.version}!`, "success");
                                            } catch (err) {
                                              showToast(err.message, "error");
                                            }
                                          }}
                                        >
                                          ↩️ Rollback
                                        </button>
                                      </div>
                                    </div>

                                    {/* Inline visual diff comparison */}
                                    {diffTargetSnapshot?.id === v.id && (
                                      <DiffViewer
                                        oldContent={v.content}
                                        newContent={sec.content}
                                        oldLabel={`Snapshot v${v.version}`}
                                        newLabel={`Current v${currentArt.version}`}
                                        onClose={() => setDiffTargetSnapshot(null)}
                                      />
                                    )}
                                  </div>
                                ))
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })
                  ) : (
                    <div className="artifact-content">No sections found for this artifact.</div>
                  )}
                </div>
              );
            })()}
          </div>
        )}

        {/* Tab: Codebase (Phase 7 — Scaffolding & Code Explorer) */}
        {activeTab === "code" && currentProject && (
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div>
                <h2 className="card-title" style={{ marginBottom: 4 }}>
                  🚀 Generated Codebase
                </h2>
                <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                  Executable project files generated by the Software Engineer Agent.
                </p>
              </div>
              <a
                href={getDownloadZipUrl(currentProject.id)}
                className="btn btn-primary"
                style={{
                  textDecoration: "none",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  background: "#2ea043",
                  color: "#fff",
                  fontWeight: 600,
                }}
              >
                📦 Download Complete (.zip)
              </a>
            </div>

            {/* Local path info banner */}
            {codeData?.local_path && (
              <div
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  padding: "10px 14px",
                  fontSize: 12,
                  marginBottom: 20,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <span>📁</span>
                <span style={{ color: "var(--text-secondary)" }}>Local Disk Location:</span>
                <code style={{ color: "var(--accent-blue)", fontWeight: 600 }}>{codeData.local_path}</code>
              </div>
            )}

            {codeLoading ? (
              <div style={{ textAlign: "center", padding: 40 }}>
                <span className="spinner" style={{ width: 28, height: 28 }} />
                <p style={{ color: "var(--text-secondary)", marginTop: 12 }}>Loading generated code files...</p>
              </div>
            ) : !codeData?.files || codeData.files.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                No code files generated yet. Run generation on this project to scaffold the repository.
              </p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16, minHeight: 400 }}>
                {/* File Tree List */}
                <div
                  style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 10,
                    overflowY: "auto",
                  }}
                >
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-muted)", padding: "4px 8px", textTransform: "uppercase" }}>
                    Files ({codeData.files.length})
                  </div>
                  {codeData.files.map((file) => {
                    const isSelected = selectedCodeFile?.path === file.path;
                    return (
                      <div
                        key={file.path}
                        onClick={() => setSelectedCodeFile(file)}
                        style={{
                          padding: "8px 10px",
                          borderRadius: 6,
                          fontSize: 13,
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          background: isSelected ? "var(--bg-hover)" : "transparent",
                          color: isSelected ? "var(--accent-blue)" : "var(--text-primary)",
                          fontWeight: isSelected ? 600 : 400,
                          marginBottom: 2,
                        }}
                      >
                        <span>{file.path.endsWith(".py") ? "🐍" : file.path.endsWith(".jsx") || file.path.endsWith(".js") ? "⚛️" : file.path.endsWith(".md") ? "📝" : "📄"}</span>
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {file.path}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Code Content Viewer & Editor */}
                {selectedCodeFile ? (
                  <div
                    style={{
                      background: "#0d1117",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      overflow: "hidden",
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    <div
                      style={{
                        padding: "8px 14px",
                        background: "#161b22",
                        borderBottom: "1px solid #30363d",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <strong style={{ fontSize: 13, color: "#c9d1d9", fontFamily: "monospace" }}>
                        {selectedCodeFile.path}
                      </strong>
                      <div style={{ display: "flex", gap: 8 }}>
                        {!isEditingCode ? (
                          <>
                            <button
                              className="btn btn-secondary btn-sm"
                              style={{ fontSize: 11, padding: "3px 8px" }}
                              onClick={() => {
                                setIsEditingCode(true);
                                setEditingCodeContent(selectedCodeFile.content);
                              }}
                            >
                              ✏️ Edit File
                            </button>
                            <button
                              className="btn btn-secondary btn-sm"
                              style={{ fontSize: 11, padding: "3px 8px" }}
                              onClick={() => {
                                navigator.clipboard.writeText(selectedCodeFile.content);
                                showToast("Copied file content to clipboard!", "success");
                              }}
                            >
                              📋 Copy
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              className="btn btn-primary btn-sm"
                              disabled={savingCode}
                              style={{ fontSize: 11, padding: "3px 10px", background: "#2ea043" }}
                              onClick={async () => {
                                setSavingCode(true);
                                try {
                                  await updateCodeFile(currentProject.id, selectedCodeFile.path, editingCodeContent);
                                  selectedCodeFile.content = editingCodeContent;
                                  if (codeData?.files) {
                                    const match = codeData.files.find((f) => f.path === selectedCodeFile.path);
                                    if (match) match.content = editingCodeContent;
                                  }
                                  setIsEditingCode(false);
                                  showToast(`Saved '${selectedCodeFile.path}' to local disk!`, "success");
                                } catch (err) {
                                  showToast(err.message, "error");
                                } finally {
                                  setSavingCode(false);
                                }
                              }}
                            >
                              {savingCode ? "Saving..." : "💾 Save to Disk"}
                            </button>
                            <button
                              className="btn btn-secondary btn-sm"
                              disabled={savingCode}
                              style={{ fontSize: 11, padding: "3px 8px" }}
                              onClick={() => setIsEditingCode(false)}
                            >
                              Cancel
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {isEditingCode ? (
                      <textarea
                        value={editingCodeContent}
                        onChange={(e) => setEditingCodeContent(e.target.value)}
                        style={{
                          width: "100%",
                          minHeight: 450,
                          padding: 16,
                          background: "#0d1117",
                          color: "#e6edf3",
                          border: "none",
                          outline: "none",
                          fontSize: 13,
                          lineHeight: 1.5,
                          fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                          resize: "vertical",
                        }}
                      />
                    ) : (
                      <pre
                        style={{
                          margin: 0,
                          padding: 16,
                          color: "#e6edf3",
                          fontSize: 13,
                          lineHeight: 1.5,
                          fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                          overflowX: "auto",
                          maxHeight: 500,
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {selectedCodeFile.content}
                      </pre>
                    )}
                  </div>
                ) : (
                  <div style={{ color: "var(--text-muted)", padding: 20 }}>Select a file from the tree to preview or edit.</div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Tab: Drifts (Phase 4 — Full Implementation) */}
        {activeTab === "drifts" && currentProject && (
          <div className="card">
            <h2 className="card-title">Consistency Drifts</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 16 }}>
              Run an audit to detect cross-artifact inconsistencies. Fix or dismiss individual drifts.
            </p>
            <div style={{ display: "flex", gap: 12, marginBottom: 24 }}>
              <button
                className="btn btn-primary"
                disabled={driftLoading}
                onClick={async () => {
                  setDriftLoading(true);
                  try {
                    await triggerAudit(currentProject.id);
                    const d = await listDrifts(currentProject.id);
                    setDrifts(d);
                    showToast(`Audit complete. ${d.length} drift(s) found.`, d.length > 0 ? "warning" : "success");
                  } catch (err) {
                    showToast(err.message, "error");
                  } finally {
                    setDriftLoading(false);
                  }
                }}
              >
                {driftLoading ? (<><span className="spinner" /> Auditing...</>) : "🔍 Run Audit"}
              </button>
              <button
                className="btn btn-secondary"
                onClick={async () => {
                  try {
                    const d = await listDrifts(currentProject.id);
                    setDrifts(d);
                  } catch (err) { showToast(err.message, "error"); }
                }}
              >
                🔄 Refresh List
              </button>
            </div>

            {drifts.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                No drifts detected yet. Run an audit to check for inconsistencies.
              </p>
            ) : (
              drifts.map((d) => (
                <div key={d.id} className="drift-item" style={{ marginBottom: 12 }}>
                  <div className="drift-item-body">
                    <div>
                      <span className={`badge badge-${d.severity === "high" ? "drifted" : d.severity === "medium" ? "stale" : "fresh"}`}>
                        {d.severity}
                      </span>
                      <strong style={{ marginLeft: 8 }}>{d.description}</strong>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                      Status: <strong>{d.status}</strong> • Detected: {new Date(d.detected_at).toLocaleString()}
                    </div>
                  </div>
                  {d.status === "open" && (
                    <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={async () => {
                          try {
                            await fixDrift(currentProject.id, d.id);
                            const updated = await listDrifts(currentProject.id);
                            setDrifts(updated);
                            showToast("Drift auto-fixed via micro-regeneration!", "success");
                          } catch (err) { showToast(err.message, "error"); }
                        }}
                      >
                        🔧 Auto-Fix
                      </button>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={async () => {
                          try {
                            await dismissDrift(currentProject.id, d.id);
                            const updated = await listDrifts(currentProject.id);
                            setDrifts(updated);
                            showToast("Drift dismissed.", "info");
                          } catch (err) { showToast(err.message, "error"); }
                        }}
                      >
                        ✕ Dismiss
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Tab: Metrics (Phase 3 — Full Implementation) */}
        {activeTab === "metrics" && currentProject && (
          <div className="card">
            <h2 className="card-title">Project Metrics</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
              Per-artifact cost, quality signals, and model routing decisions.
            </p>

            {/* Summary Stats */}
            <div className="grid-3" style={{ marginBottom: 24 }}>
              <div className="stat-card">
                <div className="stat-value">
                  {artifacts.length > 0
                    ? `$${artifacts.reduce((sum, a) => sum + (a.quality_signal_score ? 0.02 : 0), 0).toFixed(2)}`
                    : "$0.00"}
                </div>
                <div className="stat-label">Estimated Total Cost</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">
                  {artifacts.length > 0
                    ? `${(
                        (artifacts.reduce((sum, a) => sum + (a.quality_signal_score || 0), 0) /
                          artifacts.filter((a) => a.quality_signal_score != null).length) *
                        100
                      ).toFixed(0)}%`
                    : "N/A"}
                </div>
                <div className="stat-label">Avg Quality Score</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{artifacts.length}</div>
                <div className="stat-label">Artifacts Generated</div>
              </div>
            </div>

            {/* Routing Log Table */}
            <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Routing Log</h3>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    <th style={{ padding: "8px 12px", textAlign: "left" }}>Artifact</th>
                    <th style={{ padding: "8px 12px", textAlign: "left" }}>Model Used</th>
                    <th style={{ padding: "8px 12px", textAlign: "center" }}>Version</th>
                    <th style={{ padding: "8px 12px", textAlign: "center" }}>Quality</th>
                    <th style={{ padding: "8px 12px", textAlign: "center" }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {artifacts.map((a) => (
                    <tr key={a.id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "8px 12px", fontWeight: 600 }}>
                        {a.artifact_type.replace("_", " ")}
                      </td>
                      <td style={{ padding: "8px 12px", color: "var(--accent-purple)" }}>
                        {a.generated_by_model || "default"}
                      </td>
                      <td style={{ padding: "8px 12px", textAlign: "center" }}>v{a.version}</td>
                      <td style={{ padding: "8px 12px", textAlign: "center" }}>
                        {a.quality_signal_score != null
                          ? `${(a.quality_signal_score * 100).toFixed(0)}%`
                          : "—"}
                      </td>
                      <td style={{ padding: "8px 12px", textAlign: "center" }}>
                        <span className={`badge badge-${a.status}`}>{a.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab: Evaluations (Phase 6) */}
        {activeTab === "evaluations" && (
          <div className="card">
            <h2 className="card-title">Evaluation Runs (Phase 6 Benchmarking)</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 16 }}>
              Run automated benchmarking across the test corpus to compare AgentFlow vs baselines.
            </p>

            {/* Trigger Buttons */}
            <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap" }}>
              {["agentflow", "single-llm", "multi-agent-no-graph"].map((bt) => (
                <button
                  key={bt}
                  className="btn btn-primary"
                  onClick={async () => {
                    try {
                      showToast(`Starting ${bt} evaluation run...`, "info");
                      await triggerEvalRun(`run-${Date.now()}`, bt, 5);
                      const runs = await listEvalRuns();
                      setEvalRuns(runs);
                      showToast(`${bt} evaluation completed!`, "success");
                    } catch (err) { showToast(err.message, "error"); }
                  }}
                >
                  🚀 Run: {bt}
                </button>
              ))}
              <button
                className="btn btn-secondary"
                onClick={async () => {
                  try {
                    const runs = await listEvalRuns();
                    setEvalRuns(runs);
                  } catch (err) { showToast(err.message, "error"); }
                }}
              >
                🔄 Load Past Runs
              </button>
            </div>

            {/* Results Table */}
            {evalRuns.length > 0 && (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                      <th style={{ padding: "8px 12px", textAlign: "left" }}>Run Name</th>
                      <th style={{ padding: "8px 12px", textAlign: "left" }}>Baseline</th>
                      <th style={{ padding: "8px 12px", textAlign: "center" }}>Cost (USD)</th>
                      <th style={{ padding: "8px 12px", textAlign: "center" }}>Latency (ms)</th>
                      <th style={{ padding: "8px 12px", textAlign: "center" }}>Avg Quality</th>
                      <th style={{ padding: "8px 12px", textAlign: "center" }}>Drifts</th>
                      <th style={{ padding: "8px 12px", textAlign: "center" }}>Projects</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evalRuns.map((run) => (
                      <tr key={run.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "8px 12px", fontWeight: 600 }}>{run.run_name}</td>
                        <td style={{ padding: "8px 12px" }}>
                          <span className={`badge badge-${run.baseline_type === "agentflow" ? "fresh" : "stale"}`}>
                            {run.baseline_type}
                          </span>
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "center" }}>
                          ${run.total_cost_usd?.toFixed(3) || "0.000"}
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "center" }}>
                          {run.total_latency_ms?.toLocaleString() || "—"}
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "center" }}>
                          {run.avg_quality_score != null
                            ? `${(run.avg_quality_score * 100).toFixed(0)}%`
                            : "—"}
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "center" }}>
                          {run.total_drifts}
                        </td>
                        <td style={{ padding: "8px 12px", textAlign: "center" }}>
                          {run.results?.length || 0}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {evalRuns.length === 0 && (
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                No evaluation runs yet. Trigger a run above to benchmark.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className={`toast toast-${toast.type}`}>{toast.message}</div>
      )}
    </div>
  );
}
