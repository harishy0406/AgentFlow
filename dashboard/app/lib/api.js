/**
 * API Client — Phase 5
 * 
 * Centralized client for communicating with the AgentFlow FastAPI backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Generic fetch wrapper with error handling.
 */
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export async function createProject(name, brief, clarifications = null) {
  return request("/projects/", {
    method: "POST",
    body: JSON.stringify({ name, brief, clarifications }),
  });
}

export async function clarifyProject(brief) {
  return request("/projects/clarify", {
    method: "POST",
    body: JSON.stringify({ brief }),
  });
}

export async function listProjects() {
  return request("/projects");
}

export async function getProject(projectId) {
  return request(`/projects/${projectId}`);
}

export async function generateArtifacts(projectId) {
  return request(`/projects/${projectId}/generate`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Artifacts & Sections
// ---------------------------------------------------------------------------

export async function getArtifacts(projectId) {
  return request(`/projects/${projectId}/artifacts`);
}

export async function updateSection(sectionId, content) {
  return request(`/sections/${sectionId}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
}

export async function getSectionVersions(sectionId) {
  return request(`/sections/${sectionId}/versions`);
}

export async function rollbackSection(sectionId, targetVersion) {
  return request(`/sections/${sectionId}/rollback`, {
    method: "POST",
    body: JSON.stringify({ target_version: targetVersion }),
  });
}

// ---------------------------------------------------------------------------
// Graph & Regeneration
// ---------------------------------------------------------------------------

export async function getDependencyGraph() {
  return request("/graph");
}

// ---------------------------------------------------------------------------
// Audit & Drifts (Phase 4)
// ---------------------------------------------------------------------------

export async function triggerAudit(projectId) {
  return request(`/projects/${projectId}/audit`, { method: "POST" });
}

export async function listDrifts(projectId, status = null) {
  const query = status ? `?status=${status}` : "";
  return request(`/projects/${projectId}/drifts${query}`);
}

export async function fixDrift(projectId, driftId) {
  return request(`/projects/${projectId}/drifts/${driftId}/fix`, {
    method: "POST",
  });
}

export async function dismissDrift(projectId, driftId) {
  return request(`/projects/${projectId}/drifts/${driftId}/dismiss`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Metrics & Routing (Phase 3)
// ---------------------------------------------------------------------------

export async function getMetrics(projectId) {
  return request(`/projects/${projectId}/metrics`);
}

export async function getProviders() {
  return request("/providers");
}

export async function previewRouting(artifactType, contextSize = 1000) {
  return request(`/routing/preview/${artifactType}?context_size=${contextSize}`);
}

// ---------------------------------------------------------------------------
// Evaluation (Phase 6)
// ---------------------------------------------------------------------------

export async function triggerEvalRun(runName, baselineType, limit = 5) {
  return request(
    `/eval/run?run_name=${encodeURIComponent(runName)}&baseline_type=${encodeURIComponent(baselineType)}&limit=${limit}`,
    { method: "POST" }
  );
}

export async function listEvalRuns() {
  return request("/eval/runs");
}

// ---------------------------------------------------------------------------
// Export Specifications Bundle
// ---------------------------------------------------------------------------

export function getExportUrl(projectId, format = "markdown") {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return `${API_BASE}/projects/${projectId}/export?format=${format}`;
}

export async function exportProjectJson(projectId) {
  return request(`/projects/${projectId}/export?format=json`);
}

// ---------------------------------------------------------------------------
// Phase 7: Code Generation & ZIP Download
// ---------------------------------------------------------------------------

export function getDownloadZipUrl(projectId) {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return `${API_BASE}/projects/${projectId}/download-zip`;
}

export async function getCodeFiles(projectId) {
  return request(`/projects/${projectId}/code-files`);
}



