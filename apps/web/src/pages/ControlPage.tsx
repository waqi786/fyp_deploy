import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { TrustRing } from "../components/common/TrustRing";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
const apiRootUrl = apiBaseUrl.replace(/\/api\/v1$/, "");

type FeatureItem = {
  feature_key: string;
  feature_name: string;
  category: string;
  status: string;
  enforcement_status: string;
  evidence: string;
  user_flow: string;
  route: string;
  automated_check: string;
  verification_command: string;
  acceptance_criteria_count: number;
  capabilities: string[];
  production_notes: string[];
  blocking: boolean;
};

type FeatureMatrix = {
  project: string;
  summary: string;
  total_features_checked: number;
  passed_count: number;
  pending_count: number;
  items: FeatureItem[];
};

type LaunchCheck = {
  name: string;
  status: string;
  detail: string;
  blocking: boolean;
};

type LaunchReadiness = {
  overall_ready: boolean;
  release_stage: string;
  checks: LaunchCheck[];
  blocking_issues: string[];
  warnings: string[];
  required_user_inputs: string[];
  recommended_next_steps: string[];
};

type RoadmapPhase = {
  order: number;
  title: string;
  objective: string;
  status: string;
  dependencies: string[];
  deliverables: string[];
  verification_gate: string;
  notes: string;
};

type Roadmap = {
  project: string;
  current_focus: string;
  phases: RoadmapPhase[];
  completed_count: number;
  in_progress_count: number;
  pending_count: number;
};

type ControlState = {
  features: FeatureMatrix;
  readiness: LaunchReadiness;
  roadmap: Roadmap;
  openapi: { openapi?: string; info?: { title?: string }; paths?: Record<string, unknown> };
  health: string;
};

const fallbackState: ControlState = {
  health: "offline-preview",
  features: {
    project: "Resora",
    summary: "Fallback control snapshot keeps production blockers visible while API data is unavailable.",
    total_features_checked: 363,
    passed_count: 357,
    pending_count: 6,
    items: [
      {
        feature_key: "public_launch_readiness",
        feature_name: "Public launch readiness",
        category: "Production Gate",
        status: "pending",
        enforcement_status: "BLOCKED",
        evidence: "Domain, HTTPS, live provider delivery, backup restore, and 50+ load test still need public-production validation.",
        user_flow: "Operator checks launch readiness before allowing a public SaaS rollout.",
        route: "/control",
        automated_check: "launch_readiness_audit",
        verification_command: "python -m pytest app/tests/test_non_functional_requirements.py -q",
        acceptance_criteria_count: 6,
        capabilities: ["domain/HTTPS", "provider delivery", "backup restore", "50+ load test"],
        production_notes: ["Do not market as public production-ready until these gates pass."],
        blocking: true,
      },
    ],
  },
  readiness: {
    overall_ready: false,
    release_stage: "private_beta_only",
    checks: [
      { name: "API health", status: "passed", detail: "FastAPI route contract is available in local/dev.", blocking: false },
      { name: "Public launch gates", status: "blocked", detail: "External production validation remains required.", blocking: true },
    ],
    blocking_issues: ["Public domain/HTTPS not configured", "50+ user load test evidence not attached", "Backup restore drill not verified"],
    warnings: ["Demo/fallback snapshot active until API responds."],
    required_user_inputs: ["Production domain", "SMTP/provider credentials", "Staging load-test evidence", "Backup restore proof"],
    recommended_next_steps: ["Run production environment gate", "Attach load-test report", "Perform staging smoke test"],
  },
  roadmap: {
    project: "Resora",
    current_focus: "Production readiness validation",
    completed_count: 10,
    in_progress_count: 2,
    pending_count: 2,
    phases: [
      {
        order: 13,
        title: "CI/CD, scans, backups and monitoring",
        objective: "Close operational controls before public launch.",
        status: "in_progress",
        dependencies: ["production env"],
        deliverables: ["scan gate", "backup plan", "monitoring"],
        verification_gate: "All production env checks pass with no placeholders.",
        notes: "Fallback phase.",
      },
      {
        order: 14,
        title: "Final integration and load testing",
        objective: "Validate 50+ concurrent researcher flow.",
        status: "pending",
        dependencies: ["staging deployment"],
        deliverables: ["load report", "smoke report", "release checklist"],
        verification_gate: "50+ user test and end-to-end smoke pass.",
        notes: "Fallback phase.",
      },
    ],
  },
  openapi: { openapi: "3.x", info: { title: "Resora API" }, paths: {} },
};

function humanize(value: string | undefined) {
  return String(value || "unknown").replace(/_/g, " ");
}

function badgeClass(status: string | boolean | undefined) {
  if (status === true || status === "passed" || status === "healthy" || status === "completed" || status === "DONE") {
    return "status-pill status-pill-green";
  }
  if (status === "pending" || status === "needs_attention" || status === "in_progress") {
    return "status-pill status-pill-gold";
  }
  return "status-pill status-pill-coral";
}

function gateTone(status: string | boolean | undefined): "gold" | "teal" | "coral" {
  if (status === true || status === "passed" || status === "healthy" || status === "completed") return "teal";
  if (status === "pending" || status === "in_progress") return "gold";
  return "coral";
}

export function ControlPage() {
  const [snapshot, setSnapshot] = useState<ControlState>(fallbackState);
  const [status, setStatus] = useState("Loading production control snapshot");
  const [selectedGate, setSelectedGate] = useState("launch");
  const [lastSynced, setLastSynced] = useState("not synced yet");

  async function loadControlSnapshot() {
    setStatus("Refreshing launch control data");
    try {
      const [featuresResponse, readinessResponse, roadmapResponse, healthResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/verification/features`),
        fetch(`${apiBaseUrl}/quality/launch-readiness`),
        fetch(`${apiBaseUrl}/roadmap/`),
        fetch(`${apiBaseUrl}/health`),
      ]);

      if (![featuresResponse, readinessResponse, roadmapResponse, healthResponse].every((item) => item.ok)) {
        throw new Error("One or more control APIs returned an error");
      }

      const [features, readiness, roadmap, health] = await Promise.all([
        featuresResponse.json(),
        readinessResponse.json(),
        roadmapResponse.json(),
        healthResponse.json(),
      ]);

      setSnapshot({ features, readiness, roadmap, openapi: fallbackState.openapi, health: health.status || "healthy" });
      setStatus("Control snapshot loaded from live API");
      setLastSynced(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));

      void fetch(`${apiRootUrl}/openapi.json`)
        .then((response) => (response.ok ? response.json() : fallbackState.openapi))
        .then((openapi) => setSnapshot((current) => ({ ...current, openapi })))
        .catch(() => undefined);
    } catch (caught) {
      setSnapshot(fallbackState);
      setStatus(caught instanceof Error ? `Fallback active: ${caught.message}` : "Fallback active: API unavailable");
      setLastSynced("fallback");
    }
  }

  useEffect(() => {
    void loadControlSnapshot();
  }, []);

  const blockers = snapshot.readiness.blocking_issues || [];
  const warnings = snapshot.readiness.warnings || [];
  const passedItems = snapshot.features.items.filter((item) => item.status === "passed");
  const pendingItems = snapshot.features.items.filter((item) => item.status !== "passed" || item.blocking);
  const currentPhase = snapshot.roadmap.phases.find((phase) => phase.status === "in_progress") || snapshot.roadmap.phases[0];
  const endpointCount = Object.keys(snapshot.openapi.paths || {}).length;
  const coverageScore = Math.round((snapshot.features.passed_count / Math.max(1, snapshot.features.total_features_checked)) * 100);
  const launchScore = Math.max(0, Math.min(100, coverageScore - blockers.length * 8));

  const selectedChecks = useMemo(() => {
    if (selectedGate === "api") return snapshot.readiness.checks.filter((check) => /api|openapi|route|docs/i.test(check.name + check.detail));
    if (selectedGate === "risk") return snapshot.readiness.checks.filter((check) => check.blocking || /risk|domain|production|load|backup|monitor/i.test(check.name + check.detail));
    return snapshot.readiness.checks;
  }, [selectedGate, snapshot.readiness.checks]);

  function exportControlPacket() {
    const payload = {
      generated_at: new Date().toISOString(),
      status,
      last_synced: lastSynced,
      snapshot,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "resora-control-readiness-packet.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Control readiness packet exported");
  }

  return (
    <section className="control-shell">
      <motion.section className="control-hero" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
        <div className="control-hero-copy">
          <div className="control-pill-row">
            <span className="status-pill status-pill-green">Live control room</span>
            <span className="status-pill status-pill-teal">API {snapshot.health}</span>
            <span className={blockers.length ? "status-pill status-pill-coral" : "status-pill status-pill-gold"}>{blockers.length} launch blockers</span>
          </div>
          <p className="control-kicker">Control room</p>
          <h1 className="control-title">Know what is ready to ship.</h1>
          <p className="control-subtitle">
            Review health, roadmap, blockers, and next actions from one screen.
          </p>
          <div className="control-action-row">
            <button type="button" onClick={() => void loadControlSnapshot()} className="resora-button-primary">Run launch audit</button>
            <button type="button" onClick={exportControlPacket} className="resora-button-ai">Export readiness packet</button>
            <Link to="/assurance" className="resora-button-secondary">Open assurance matrix</Link>
          </div>
        </div>

        <aside className="control-score-card">
          <p className="resora-label">Launch score</p>
          <div className="control-score-main">
            <TrustRing value={launchScore / 10} tone={blockers.length ? "coral" : "teal"} size="md" />
            <div>
              <strong>{launchScore}%</strong>
              <span>{snapshot.readiness.overall_ready ? "ready for public release" : "private beta gate active"}</span>
            </div>
          </div>
          <div className="control-score-grid">
            <Metric label="checked" value={String(snapshot.features.total_features_checked)} />
            <Metric label="passed" value={String(snapshot.features.passed_count)} />
            <Metric label="pending" value={String(snapshot.features.pending_count)} />
            <Metric label="routes" value={String(endpointCount)} />
          </div>
        </aside>
      </motion.section>

      <section className="control-command-strip">
        <span>{status}</span>
        <button type="button" onClick={() => setSelectedGate("launch")} className={selectedGate === "launch" ? "resora-button-primary" : "resora-button-secondary"}>Launch gates</button>
        <button type="button" onClick={() => setSelectedGate("api")} className={selectedGate === "api" ? "resora-button-primary" : "resora-button-secondary"}>API surface</button>
        <button type="button" onClick={() => setSelectedGate("risk")} className={selectedGate === "risk" ? "resora-button-primary" : "resora-button-secondary"}>Risk only</button>
      </section>

      <section className="control-grid control-grid-top">
        <article className="control-panel control-release-panel">
          <PanelHeader eyebrow="Release state" title={humanize(snapshot.readiness.release_stage)} pill={snapshot.readiness.overall_ready ? "ready" : "blocked"} />
          <div className="control-release-list">
            <ReleaseRow label="Current phase" value={currentPhase?.title || "No active phase"} tone="teal" />
            <ReleaseRow label="Last sync" value={lastSynced} tone="gold" />
            <ReleaseRow label="Coverage" value={`${coverageScore}% feature assurance`} tone="green" />
          </div>
          <div className="control-required">
            <p className="resora-label">Operator inputs still needed</p>
            {snapshot.readiness.required_user_inputs.map((input) => <span key={input}>{input}</span>)}
          </div>
        </article>

        <article className="control-panel control-blockers">
          <PanelHeader eyebrow="Launch blockers" title={blockers.length ? "Do not public-launch yet" : "No blocking gate open"} pill={`${blockers.length} open`} />
          <div className="control-blocker-list">
            {blockers.map((blocker) => <div key={blocker} className="control-blocker">{blocker}</div>)}
            {warnings.map((warning) => <div key={warning} className="control-warning">{warning}</div>)}
          </div>
        </article>
      </section>

      <section className="control-panel">
        <PanelHeader eyebrow="Gate audit" title="Every readiness check is visible and inspectable" pill={`${selectedChecks.length} checks`} />
        <div className="control-check-grid">
          {selectedChecks.map((check) => (
            <button key={`${check.name}-${check.detail}`} type="button" className="control-check-card" onClick={() => setStatus(`${check.name}: ${check.detail}`)}>
              <TrustRing value={check.status === "passed" ? 9 : check.status === "pending" ? 6 : 2} tone={gateTone(check.status)} size="sm" />
              <div>
                <strong>{check.name}</strong>
                <span className={badgeClass(check.status)}>{humanize(check.status)}</span>
                <p>{check.detail}</p>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="control-grid control-grid-wide">
        <article className="control-panel">
          <PanelHeader eyebrow="Roadmap control" title="Phase-by-phase execution gates" pill={`${snapshot.roadmap.completed_count}/${snapshot.roadmap.phases.length} complete`} />
          <div className="control-roadmap">
            {snapshot.roadmap.phases.map((phase) => (
              <button key={phase.order} type="button" className="control-phase" onClick={() => setStatus(`Phase ${phase.order}: ${phase.verification_gate}`)}>
                <span className="control-phase-number">{phase.order}</span>
                <div>
                  <strong>{phase.title}</strong>
                  <p>{phase.objective}</p>
                  <small>{phase.verification_gate}</small>
                </div>
                <span className={badgeClass(phase.status)}>{humanize(phase.status)}</span>
              </button>
            ))}
          </div>
        </article>

        <article className="control-panel">
          <PanelHeader eyebrow="Verified vs pending" title="Feature slices linked to product routes" pill={`${passedItems.length} verified`} />
          <div className="control-feature-stack">
            {[...pendingItems.slice(0, 4), ...passedItems.slice(0, 4)].map((item) => (
              <Link key={item.feature_key} to={item.route || "/assurance"} className={item.blocking ? "control-feature control-feature-blocking" : "control-feature"}>
                <div>
                  <strong>{item.feature_name}</strong>
                  <p>{item.evidence}</p>
                </div>
                <span className={badgeClass(item.enforcement_status || item.status)}>{humanize(item.enforcement_status || item.status)}</span>
              </Link>
            ))}
          </div>
        </article>
      </section>

      <section className="control-grid control-grid-bottom">
        <article className="control-panel">
          <PanelHeader eyebrow="API and docs" title="Route contract and operator entry points" pill={snapshot.openapi.openapi || "openapi"} />
          <div className="control-api-grid">
            <Metric label="API title" value={snapshot.openapi.info?.title || "Resora API"} />
            <Metric label="OpenAPI paths" value={String(endpointCount)} />
            <Metric label="Health" value={snapshot.health} />
            <Metric label="Docs" value="/docs" />
          </div>
          <div className="control-action-row control-action-row-compact">
            <a href={`${apiRootUrl}/docs`} target="_blank" rel="noreferrer" className="resora-button-primary">Open API docs</a>
            <Link to="/developer-ai" className="resora-button-secondary">Dev platform</Link>
          </div>
        </article>

        <article className="control-panel control-next-steps">
          <PanelHeader eyebrow="Next actions" title="What the launch manager should do next" pill="operator queue" />
          <div className="control-step-list">
            {snapshot.readiness.recommended_next_steps.map((step, index) => (
              <button key={step} type="button" onClick={() => setStatus(`Queued step ${index + 1}: ${step}`)}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{step}</strong>
              </button>
            ))}
          </div>
        </article>
      </section>
    </section>
  );
}

function PanelHeader({ eyebrow, title, pill }: { eyebrow: string; title: string; pill: string }) {
  return (
    <div className="control-panel-header">
      <div>
        <p className="resora-label">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      <span className="status-pill status-pill-gold">{pill}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="control-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ReleaseRow({ label, value, tone }: { label: string; value: string; tone: "gold" | "teal" | "green" }) {
  return (
    <div className={`control-release-row control-release-row-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
