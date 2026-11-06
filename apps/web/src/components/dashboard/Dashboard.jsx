import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { TrustRing } from "../common/TrustRing";
import { CitationMeshPreview } from "./CitationMeshPreview";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
const apiRootUrl = apiBaseUrl.replace(/\/api\/v1$/, "");

const emptyState = {
  loading: true,
  error: "",
  features: null,
  readiness: null,
  roadmap: null,
  openapi: null,
};

function humanizeStatus(value) {
  return String(value || "").split("_").join(" ");
}

function badgeClass(status) {
  if (status === "passed" || status === "healthy" || status === true) {
    return "status-pill status-pill-green";
  }
  if (status === "pending" || status === "needs_attention" || status === "in_progress") {
    return "status-pill status-pill-gold";
  }
  return "status-pill status-pill-coral";
}

export function Dashboard() {
  const [state, setState] = useState(emptyState);

  useEffect(() => {
    let ignore = false;

    async function loadDashboard() {
      try {
        const [featuresResponse, readinessResponse, roadmapResponse, openapiResponse] = await Promise.all([
          fetch(`${apiBaseUrl}/verification/features`),
          fetch(`${apiBaseUrl}/quality/launch-readiness`),
          fetch(`${apiBaseUrl}/roadmap/`),
          fetch(`${apiRootUrl}/openapi.json`),
        ]);

        const [features, readiness, roadmap, openapi] = await Promise.all([
          featuresResponse.json(),
          readinessResponse.json(),
          roadmapResponse.json(),
          openapiResponse.json(),
        ]);

        if (!ignore) {
          setState({
            loading: false,
            error: "",
            features,
            readiness,
            roadmap,
            openapi,
          });
        }
      } catch (error) {
        if (!ignore) {
          setState({
            ...emptyState,
            loading: false,
            error: error instanceof Error ? error.message : "Unable to load dashboard data.",
          });
        }
      }
    }

    void loadDashboard();
    return () => {
      ignore = true;
    };
  }, []);

  const livePhase = useMemo(() => {
    const phases = state.roadmap?.phases || [];
    return phases.find((phase) => phase.status === "in_progress") || phases.find((phase) => phase.status === "pending");
  }, [state.roadmap]);

  const endpointCount = Object.keys(state.openapi?.paths || {}).length;
  const blockingItems = state.readiness?.blocking_issues || [];
  const warningItems = state.readiness?.warnings || [];
  const featureItems = state.features?.items || [];
  const passedItems = featureItems.filter((item) => item.status === "passed");
  const pendingItems = featureItems.filter((item) => item.status !== "passed");

  if (state.loading) {
    return (
      <section className="panel-surface p-6">
        <p className="resora-label">Loading</p>
        <h2 className="mt-3 font-display text-[24px] font-normal text-text">Building your control center snapshot</h2>
      </section>
    );
  }

  if (state.error) {
    return (
      <section className="panel-surface p-6">
        <p className="resora-label">Dashboard error</p>
        <h2 className="mt-3 font-display text-[24px] font-normal text-text">Live product signals could not be loaded</h2>
        <p className="mt-4 text-[13px] leading-7 text-text-dim">{state.error}</p>
      </section>
    );
  }

  return (
    <section className="grid gap-5">
      <motion.article
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="panel-surface overflow-hidden"
      >
        <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="border-b border-border px-6 py-6 xl:border-b-0 xl:border-r">
            <p className="resora-label">Resora control center</p>
            <h2 className="mt-3 max-w-4xl font-display text-[24px] font-normal leading-tight text-text md:text-[34px]">
              Real implementation status, launch blockers, roadmap progress, and verified product slices.
            </h2>
            <p className="mt-4 max-w-3xl text-[13px] leading-7 text-text-dim">
              This screen is wired to backend verification services so we can see what is genuinely implemented, what is
              partial, and what still blocks a true public launch.
            </p>
          </div>

          <aside>
            <div className="border-b border-border px-5 py-5">
              <p className="resora-label">Release stage</p>
              <p className="mt-3 font-display text-[16px] font-normal text-text">{humanizeStatus(state.readiness.release_stage)}</p>
            </div>
            <div className="border-b border-border px-5 py-5">
              <p className="resora-label">Current phase</p>
              <p className="mt-3 text-[13px] leading-6 text-text-dim">{livePhase?.title || "No active phase found"}</p>
            </div>
            <div className="px-5 py-5">
              <p className="resora-label">Open blockers</p>
              <div className="mt-3 inline-flex items-center gap-3">
                <TrustRing value={Math.max(0, 10 - blockingItems.length)} tone={blockingItems.length ? "coral" : "gold"} size="md" />
                <div>
                  <p className="text-[13px] text-text">{blockingItems.length}</p>
                  <p className="text-[12.5px] text-text-dim">items before production launch</p>
                </div>
              </div>
            </div>
          </aside>
        </div>
      </motion.article>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          { label: "Passed slices", value: state.features.passed_count, tone: "teal" },
          { label: "Pending slices", value: state.features.pending_count, tone: "gold" },
          { label: "Blocking issues", value: blockingItems.length, tone: blockingItems.length ? "coral" : "gold" },
          { label: "API routes", value: endpointCount, tone: "gold" },
        ].map((metric) => (
          <article key={metric.label} className="panel-surface p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="resora-label">{metric.label}</p>
                <p className="mt-3 font-display text-[22px] font-normal text-text">{metric.value}</p>
              </div>
              <TrustRing value={Math.min(9.9, Number(metric.value) || 0)} tone={metric.tone} size="sm" />
            </div>
          </article>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <article className="panel-surface p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="resora-label">Implemented slices</p>
              <h3 className="mt-2 font-display text-[22px] font-normal text-text">What is already working</h3>
            </div>
            <span className="status-pill status-pill-teal">{passedItems.length} verified</span>
          </div>

          <div className="mt-5 space-y-3">
            {passedItems.slice(0, 6).map((item) => (
              <div key={item.feature_key} className="rounded-[10px] border border-border bg-panel px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4 className="text-[13px] font-medium text-text">{item.feature_name}</h4>
                  <span className={badgeClass(item.status)}>{item.status}</span>
                </div>
                <p className="mt-2 text-[12.5px] leading-6 text-text-dim">{item.user_flow}</p>
                <p className="mt-3 text-[12.5px] leading-6 text-gold-text">{item.evidence}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="panel-surface p-5">
          <p className="resora-label">Launch blockers</p>
          <h3 className="mt-2 font-display text-[22px] font-normal text-text">Why this is not yet public-production-ready</h3>
          <div className="mt-5 space-y-3">
            {blockingItems.map((item) => (
              <div key={item} className="rounded-[10px] border border-coral bg-coral-soft px-4 py-4 text-[13px] leading-7 text-coral-text">
                {item}
              </div>
            ))}
            {warningItems.map((item) => (
              <div key={item} className="rounded-[10px] border border-border bg-panel px-4 py-4 text-[13px] leading-7 text-text-dim">
                {item}
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <article className="panel-surface p-5">
          <p className="resora-label">Roadmap</p>
          <h3 className="mt-2 font-display text-[22px] font-normal text-text">Execution phases</h3>
          <div className="mt-5 space-y-3">
            {state.roadmap.phases.map((phase) => (
              <div key={phase.order} className="rounded-[10px] border border-border bg-panel px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <strong className="text-[13px] font-medium text-text">
                    {phase.order}. {phase.title}
                  </strong>
                  <span className={badgeClass(phase.status)}>{humanizeStatus(phase.status)}</span>
                </div>
                <p className="mt-2 text-[12.5px] leading-6 text-text-dim">{phase.objective}</p>
                <p className="mt-3 text-[12.5px] leading-6 text-gold-text">{phase.verification_gate}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="panel-surface p-5">
          <p className="resora-label">Pending work</p>
          <h3 className="mt-2 font-display text-[22px] font-normal text-text">What still needs implementation or validation</h3>
          <div className="mt-5 space-y-3">
            {pendingItems.slice(0, 6).map((item) => (
              <div key={item.feature_key} className="rounded-[10px] border border-border bg-panel px-4 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4 className="text-[13px] font-medium text-text">{item.feature_name}</h4>
                  <span className={badgeClass(item.status)}>{item.status}</span>
                </div>
                <p className="mt-2 text-[12.5px] leading-6 text-text-dim">{item.user_flow}</p>
                <p className="mt-3 text-[12.5px] leading-6 text-gold-text">{item.evidence}</p>
              </div>
            ))}
          </div>
        </article>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.92fr_1.08fr]">
        <CitationMeshPreview />

        <article className="panel-surface p-5">
          <p className="resora-label">API surface</p>
          <h3 className="mt-2 font-display text-[22px] font-normal text-text">Developer and operator snapshot</h3>
          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <div className="glass-surface p-4">
              <p className="resora-label">OpenAPI version</p>
              <p className="mt-3 text-[13px] text-text">{state.openapi.openapi}</p>
            </div>
            <div className="glass-surface p-4">
              <p className="resora-label">API title</p>
              <p className="mt-3 text-[13px] text-text">{state.openapi.info?.title}</p>
            </div>
            <div className="glass-surface p-4 md:col-span-2">
              <p className="resora-label">Key operator needs before launch</p>
              <div className="mt-3 space-y-2">
                {state.readiness.required_user_inputs.map((input) => (
                  <div key={input} className="text-[13px] leading-7 text-text-dim">
                    {input}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
