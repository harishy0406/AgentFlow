"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";

export default function NotFound() {
  const [pathname, setPathname] = useState("");
  const [copied, setCopied] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [pingLatency, setPingLatency] = useState(24);
  const [theme, setTheme] = useState("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (typeof window !== "undefined") {
      setPathname(window.location.pathname || "/unknown-route");
      const savedTheme = localStorage.getItem("agentflow-theme") || "dark";
      setTheme(savedTheme);
      document.documentElement.setAttribute("data-theme", savedTheme);
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", nextTheme);
      localStorage.setItem("agentflow-theme", nextTheme);
    }
  };

  const handlePing = () => {
    setPinging(true);
    const simulatedLatency = Math.floor(Math.random() * 25) + 15;
    setTimeout(() => {
      setPingLatency(simulatedLatency);
      setPinging(false);
    }, 450);
  };

  const handleCopyTrace = () => {
    const trace = [
      `=== AGENTFLOW ROUTE RESOLVER TRACE ===`,
      `Timestamp: ${new Date().toISOString()}`,
      `Requested URI: ${pathname || "/unknown-route"}`,
      `Status: 404 (ARTIFACT_NODE_NOT_FOUND)`,
      `DAG Topology: PRD -> SDD -> DB_SCHEMA -> API_SPEC -> USER_STORIES -> TASKS -> CODE`,
      `Engine: Multi-Agent Orchestration Kernel v0.8.0`,
      `Drift Detection: Active`,
      `Recommended Action: Return to Project Studio (/), select or seed a template.`,
    ].join("\n");

    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(trace);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const starterTemplates = [
    {
      id: "ai_code_reviewer",
      icon: "🛡️",
      title: "AI Code Reviewer",
      tag: "DevOps & AI",
      desc: "AST static analysis, OWASP scanning, inline GitHub PR suggestions.",
    },
    {
      id: "fintech_escrow",
      icon: "💳",
      title: "FinTech Escrow API",
      tag: "FinTech",
      desc: "Stripe Connect payouts, dual-entry accounting ledgers & KYC.",
    },
    {
      id: "healthcare_telehealth",
      icon: "🏥",
      title: "HIPAA Telehealth Suite",
      tag: "Healthcare",
      desc: "WebRTC encrypted consultation rooms, FHIR EHR & prescriptions.",
    },
    {
      id: "ecommerce_marketplace",
      icon: "🛍️",
      title: "Multi-Vendor Marketplace",
      tag: "E-Commerce",
      desc: "Redis cart reservation locks, merchant analytics & split checkout.",
    },
  ];

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
        display: "flex",
        flexDirection: "column",
        fontFamily: "var(--font-sans)",
        position: "relative",
        overflowX: "hidden",
      }}
    >
      {/* Background Cyber Mesh & Radial Glow */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          backgroundImage: `
            radial-gradient(circle at 50% 15%, rgba(0, 255, 102, 0.08) 0%, transparent 60%),
            linear-gradient(to right, var(--grid-line-color) 1px, transparent 1px),
            linear-gradient(to bottom, var(--grid-line-color) 1px, transparent 1px)
          `,
          backgroundSize: "100% 100%, 48px 48px, 48px 48px",
          opacity: 0.9,
          zIndex: 0,
        }}
      />

      {/* Top Brand Navigation Bar */}
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 20,
          background: "var(--navbar-bg)",
          backdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--border)",
          padding: "10px 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: "64px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Link
            href="/"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              textDecoration: "none",
              color: "inherit",
            }}
          >
            <img
              src="/logo.png"
              alt="AgentFlow Logo"
              style={{
                width: 30,
                height: 30,
                objectFit: "contain",
                filter: "drop-shadow(0 0 8px rgba(0, 255, 102, 0.5))",
                transition: "transform 0.2s ease",
              }}
            />
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span
                style={{
                  fontSize: 16,
                  fontWeight: 800,
                  letterSpacing: "-0.5px",
                  color: "var(--text-primary)",
                }}
              >
                AgentFlow
              </span>
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 700,
                  background: "var(--terminal-green-dim)",
                  color: "var(--terminal-green)",
                  border: "1px solid var(--terminal-green-border)",
                  borderRadius: 4,
                  padding: "1px 6px",
                  letterSpacing: "0.5px",
                }}
              >
                ORCHESTRATOR
              </span>
            </div>
          </Link>

          <span style={{ color: "var(--border)", fontSize: 14 }}>/</span>

          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              fontFamily: "var(--font-mono)",
              color: "var(--text-muted)",
              background: "var(--bg-card)",
              padding: "4px 10px",
              borderRadius: 6,
              border: "1px solid var(--border)",
            }}
          >
            <span>route:</span>
            <span style={{ color: "var(--accent-red)", fontWeight: 600 }}>404_unresolved</span>
          </div>
        </div>

        {/* Right Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Fleet Status Pill */}
          <div
            style={{
              display: "none",
              alignItems: "center",
              gap: 8,
              fontSize: 11,
              fontFamily: "var(--font-mono)",
              background: "var(--bg-secondary)",
              border: "1px solid var(--border)",
              padding: "5px 12px",
              borderRadius: 20,
              color: "var(--text-secondary)",
            }}
            className="status-pill-desktop"
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: "var(--terminal-green)",
                boxShadow: "0 0 8px var(--terminal-green)",
                display: "inline-block",
              }}
            />
            <span>FLEET: ONLINE ({pingLatency}ms)</span>
          </div>

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "Light" : "Dark"} mode`}
            style={{
              background: "var(--bg-secondary)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
              borderRadius: 8,
              padding: "6px 10px",
              cursor: "pointer",
              fontSize: 13,
              display: "flex",
              alignItems: "center",
              gap: 6,
              transition: "all 0.18s ease",
            }}
          >
            <span>{theme === "dark" ? "☀️" : "🌙"}</span>
            <span style={{ fontSize: 11, fontWeight: 600 }}>
              {theme === "dark" ? "Light" : "Dark"}
            </span>
          </button>

          {/* Direct Return Button */}
          <Link
            href="/"
            className="btn btn-primary"
            style={{
              fontSize: 12,
              fontWeight: 700,
              padding: "7px 14px",
              textDecoration: "none",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>🚀</span>
            <span>Studio</span>
          </Link>
        </div>
      </header>

      {/* Main Container */}
      <main
        style={{
          flex: 1,
          position: "relative",
          zIndex: 1,
          maxWidth: 1100,
          width: "100%",
          margin: "0 auto",
          padding: "48px 24px 80px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        {/* Top Glitch Status Badge */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            background: "rgba(255, 77, 77, 0.08)",
            border: "1px solid rgba(255, 77, 77, 0.25)",
            padding: "6px 14px",
            borderRadius: 30,
            marginBottom: 24,
            fontSize: 12,
            fontFamily: "var(--font-mono)",
            fontWeight: 600,
            color: "var(--accent-red)",
            letterSpacing: "0.5px",
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "var(--accent-red)",
              boxShadow: "0 0 8px rgba(255, 77, 77, 0.8)",
              display: "inline-block",
            }}
          />
          <span>HTTP 404: TOPOLOGICAL_DISCONNECT</span>
        </div>

        {/* Hero Visual Display */}
        <div
          style={{
            position: "relative",
            textAlign: "center",
            marginBottom: 20,
          }}
        >
          <div
            style={{
              fontSize: "clamp(88px, 16vw, 150px)",
              fontWeight: 900,
              fontFamily: "var(--font-mono)",
              lineHeight: 1,
              letterSpacing: "-4px",
              background: "linear-gradient(180deg, var(--text-primary) 30%, var(--text-muted) 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              userSelect: "none",
              textShadow: "0 0 60px rgba(0, 255, 102, 0.12)",
            }}
          >
            404
          </div>

          {/* Ambient Cyber Gridlines underneath 404 */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              fontSize: 13,
              fontFamily: "var(--font-mono)",
              fontWeight: 700,
              color: "var(--terminal-green)",
              letterSpacing: "4px",
              background: "var(--bg-card)",
              padding: "4px 16px",
              borderRadius: 6,
              border: "1px solid var(--terminal-green-border)",
              boxShadow: "0 0 20px rgba(0, 255, 102, 0.2)",
              pointerEvents: "none",
            }}
          >
            NODE_NOT_RESOLVED
          </div>
        </div>

        {/* Headline & Description */}
        <h1
          style={{
            fontSize: "clamp(20px, 4vw, 32px)",
            fontWeight: 800,
            textAlign: "center",
            marginBottom: 12,
            maxWidth: 680,
            letterSpacing: "-0.5px",
          }}
        >
          Execution Node Lost in Multi-Agent Topology
        </h1>

        <p
          style={{
            fontSize: 14,
            lineHeight: 1.6,
            color: "var(--text-secondary)",
            textAlign: "center",
            maxWidth: 620,
            marginBottom: 24,
          }}
        >
          The requested route does not correspond to any active engineering artifact, workspace
          pipeline, or mock API endpoint registered in AgentFlow&apos;s 7-agent DAG execution graph.
        </p>

        {/* Unresolved Route Chip */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: "var(--bg-secondary)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "8px 16px",
            marginBottom: 36,
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            maxWidth: "90%",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          <span style={{ color: "var(--text-muted)", fontSize: 11, fontWeight: 700 }}>
            TARGET_URI:
          </span>
          <code
            style={{
              color: "var(--terminal-green)",
              fontWeight: 600,
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {mounted ? pathname || "/" : "..."}
          </code>
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              background: "rgba(255, 77, 77, 0.15)",
              color: "var(--accent-red)",
              border: "1px solid rgba(255, 77, 77, 0.3)",
              padding: "2px 6px",
              borderRadius: 4,
            }}
          >
            UNREGISTERED
          </span>
        </div>

        {/* Primary Action Buttons */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            justifyContent: "center",
            marginBottom: 48,
            width: "100%",
            maxWidth: 600,
          }}
        >
          <Link
            href="/"
            className="btn btn-primary"
            style={{
              flex: "1 1 200px",
              height: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              fontSize: 13,
              fontWeight: 700,
              textDecoration: "none",
              borderRadius: 8,
              boxShadow: "0 4px 16px rgba(0, 255, 102, 0.2)",
            }}
          >
            <span>🚀</span>
            <span>Return to Project Studio</span>
          </Link>

          <button
            onClick={handlePing}
            className="btn btn-secondary"
            disabled={pinging}
            style={{
              flex: "1 1 160px",
              height: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              fontSize: 13,
              fontWeight: 600,
              borderRadius: 8,
              cursor: "pointer",
            }}
          >
            <span>{pinging ? "⏳" : "📡"}</span>
            <span>{pinging ? "Pinging..." : `Ping Fleet (${pingLatency}ms)`}</span>
          </button>

          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary"
            style={{
              flex: "1 1 160px",
              height: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              fontSize: 13,
              fontWeight: 600,
              textDecoration: "none",
              borderRadius: 8,
            }}
          >
            <span>📚</span>
            <span>API Docs (:8000)</span>
          </a>
        </div>

        {/* Diagnostic Cyber Terminal */}
        <div
          style={{
            width: "100%",
            maxWidth: 860,
            background: "var(--terminal-bg)",
            border: "1px solid var(--terminal-border)",
            borderRadius: 10,
            overflow: "hidden",
            boxShadow: "0 12px 32px rgba(0, 0, 0, 0.4)",
            marginBottom: 48,
          }}
        >
          {/* Terminal Window Header */}
          <div
            style={{
              background: "var(--terminal-header-bg)",
              borderBottom: "1px solid var(--terminal-border)",
              padding: "10px 16px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#FF5F56" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#FFBD2E" }} />
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#27C93F" }} />
              <span
                style={{
                  fontSize: 11,
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-muted)",
                  marginLeft: 8,
                }}
              >
                agentflow-kernel // telemetry-tracer
              </span>
            </div>

            <button
              onClick={handleCopyTrace}
              style={{
                background: "transparent",
                border: "1px solid var(--border)",
                borderRadius: 4,
                color: copied ? "var(--terminal-green)" : "var(--text-muted)",
                fontSize: 11,
                fontFamily: "var(--font-mono)",
                padding: "3px 8px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
                transition: "all 0.15s ease",
              }}
            >
              <span>{copied ? "✓" : "📋"}</span>
              <span>{copied ? "Trace Copied!" : "Copy Trace"}</span>
            </button>
          </div>

          {/* Terminal Body */}
          <div
            style={{
              padding: "18px 20px",
              fontFamily: "var(--font-mono)",
              fontSize: 12.5,
              lineHeight: 1.7,
              color: "var(--text-secondary)",
              overflowX: "auto",
            }}
          >
            <div>
              <span style={{ color: "var(--text-muted)" }}>[00:00:01] </span>
              <span style={{ color: "var(--terminal-green)", fontWeight: 700 }}>[ROUTE_RESOLVER] </span>
              <span>Ingress received URI query: </span>
              <span style={{ color: "var(--text-primary)" }}>&apos;{mounted ? pathname || "/" : "..."}&apos;</span>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)" }}>[00:00:02] </span>
              <span style={{ color: "var(--accent-blue)", fontWeight: 700 }}>[DAG_ENGINE] </span>
              <span>Scanning topological dependency order: </span>
              <span style={{ color: "var(--text-muted)" }}>PRD → SDD → DB_SCHEMA → API_SPEC → USER_STORIES → TASKS → CODE</span>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)" }}>[00:00:03] </span>
              <span style={{ color: "var(--accent-red)", fontWeight: 700 }}>[TRACE_ERROR] </span>
              <span>Target node identifier was not found in active project registry.</span>
            </div>
            <div>
              <span style={{ color: "var(--text-muted)" }}>[00:00:04] </span>
              <span style={{ color: "var(--accent-yellow)", fontWeight: 700 }}>[DRIFT_GUARD] </span>
              <span>Zero architectural drift registered. System health status: </span>
              <span style={{ color: "var(--terminal-green)", fontWeight: 600 }}>100% READY</span>
            </div>
            <div style={{ marginTop: 8, color: "var(--terminal-green)" }}>
              <span style={{ color: "var(--text-muted)" }}>&gt; </span>
              <span>Ready for commands. Return to Studio or select a starter architecture fleet below.</span>
            </div>
          </div>
        </div>

        {/* Explore Starter Architecture Templates Grid */}
        <div style={{ width: "100%", maxWidth: 860 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
            }}
          >
            <div>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                Starter Architecture Fleets
              </h3>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                Jump directly into one of our four verified autonomous templates
              </p>
            </div>
            <Link
              href="/"
              style={{
                fontSize: 12,
                color: "var(--terminal-green)",
                textDecoration: "none",
                fontWeight: 600,
              }}
            >
              Open Studio →
            </Link>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: 12,
            }}
          >
            {starterTemplates.map((t) => (
              <Link
                key={t.id}
                href="/"
                style={{
                  background: "var(--bg-secondary)",
                  border: "1px solid var(--border)",
                  borderRadius: 10,
                  padding: "14px",
                  textDecoration: "none",
                  color: "inherit",
                  display: "flex",
                  flexDirection: "column",
                  transition: "all 0.18s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "var(--terminal-green)";
                  e.currentTarget.style.transform = "translateY(-2px)";
                  e.currentTarget.style.boxShadow = "0 6px 16px rgba(0, 0, 0, 0.4)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "var(--border)";
                  e.currentTarget.style.transform = "none";
                  e.currentTarget.style.boxShadow = "none";
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 8,
                  }}
                >
                  <span style={{ fontSize: 20 }}>{t.icon}</span>
                  <span
                    style={{
                      fontSize: 9.5,
                      color: "var(--text-muted)",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      background: "var(--bg-card)",
                      padding: "2px 6px",
                      borderRadius: 4,
                      border: "1px solid var(--border)",
                    }}
                  >
                    {t.tag}
                  </span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
                  {t.title}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--text-secondary)",
                    marginTop: 6,
                    lineHeight: 1.4,
                  }}
                >
                  {t.desc}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid var(--border)",
          background: "var(--footer-bg)",
          padding: "20px 24px",
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          fontSize: 12,
          color: "var(--text-muted)",
          position: "relative",
          zIndex: 1,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img
            src="/logo.png"
            alt="AgentFlow"
            style={{ width: 18, height: 18, objectFit: "contain", opacity: 0.8 }}
          />
          <span>AgentFlow Autonomous Orchestration Platform</span>
          <span>•</span>
          <span style={{ color: "var(--terminal-green)" }}>v0.8.0</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <Link href="/" style={{ color: "var(--text-secondary)", textDecoration: "none" }}>
            Studio
          </Link>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--text-secondary)", textDecoration: "none" }}
          >
            Swagger Docs
          </a>
          <a
            href="http://localhost:8000/openapi.json"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--text-secondary)", textDecoration: "none" }}
          >
            OpenAPI Spec
          </a>
        </div>
      </footer>

      {/* Inline Responsive Styles */}
      <style jsx>{`
        @media (min-width: 640px) {
          .status-pill-desktop {
            display: inline-flex !important;
          }
        }
      `}</style>
    </div>
  );
}
