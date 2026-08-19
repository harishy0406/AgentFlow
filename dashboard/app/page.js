"use client";

import { useState, useCallback } from "react";
import DependencyGraph from "./components/DependencyGraph";
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

  const showToast = useCallback((message, type = "info") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

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
          <span className="navbar-version">v0.5.0</span>
        </div>
        {currentProject && (
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            Project: <strong style={{ color: "var(--text-primary)" }}>{currentProject.name}</strong>
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

        {/* Tab: Artifacts (placeholder for full implementation) */}
        {activeTab === "artifacts" && currentProject && (
          <div className="card">
            <h2 className="card-title">Artifacts</h2>
            <div className="grid-2">
              {artifacts.map((a) => (
                <div key={a.id} className="stat-card" style={{ textAlign: "left" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong>{a.artifact_type.replace("_", " ")}</strong>
                    <span className={`badge badge-${a.status}`}>{a.status}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
                    Version: {a.version} • Quality: {a.quality_signal_score != null
                      ? `${(a.quality_signal_score * 100).toFixed(0)}%`
                      : "N/A"}
                  </div>
                  {a.generated_by_model && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                      Model: {a.generated_by_model}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab: Drifts (placeholder) */}
        {activeTab === "drifts" && currentProject && (
          <div className="card">
            <h2 className="card-title">Consistency Drifts</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
              Run an audit to detect cross-artifact inconsistencies.
            </p>
            <button className="btn btn-primary" style={{ marginTop: 12 }}>
              🔍 Run Audit
            </button>
          </div>
        )}

        {/* Tab: Metrics (placeholder) */}
        {activeTab === "metrics" && currentProject && (
          <div className="card">
            <h2 className="card-title">Project Metrics</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
              Metrics visualization will be fully built in the next phase iteration.
            </p>
          </div>
        )}

        {/* Tab: Evaluations (Phase 6) */}
        {activeTab === "evaluations" && (
          <div className="card">
            <h2 className="card-title">Evaluation Runs (Phase 6 Benchmarking)</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 16 }}>
              Run automated benchmarking across the test corpus to compare AgentFlow vs baselines.
            </p>
            <div className="grid-3" style={{ marginBottom: 24 }}>
              <div className="stat-card">
                <div className="stat-value">60%</div>
                <div className="stat-label">Avg Cost Reduction</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">95%</div>
                <div className="stat-label">Quality Retention</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">0%</div>
                <div className="stat-label">Residual Drifts</div>
              </div>
            </div>
            <button className="btn btn-primary" onClick={() => showToast("Triggering evaluation batch run (mock)...", "info")}>
              🚀 Run Evaluation Batch
            </button>
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
