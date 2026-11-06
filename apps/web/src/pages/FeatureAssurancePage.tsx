import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

function resolveApiBaseUrl() {
  if (typeof window !== "undefined") {
    const override = new URLSearchParams(window.location.search).get("apiBaseUrl");
    if (override?.startsWith("http")) return override;
  }
  return import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";
}

const apiBaseUrl = resolveApiBaseUrl();

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

type ProposalObjective = {
  objective_key: string;
  proposal_text: string;
  implementation_status: string;
  product_route: string;
  verification_check: string;
  evidence: string;
  caveats: string[];
};

type ProposalAlignment = {
  project: string;
  source_document: string;
  summary: string;
  readiness_score: number;
  completed_count: number;
  partial_count: number;
  pending_count: number;
  objectives: ProposalObjective[];
};

type CompleteFeatureItem = {
  feature_id: string;
  module: string;
  title: string;
  implementation_status: string;
  production_status: string;
  mapped_route: string;
  verification_check: string;
  evidence: string;
  remediation?: string | null;
};

type CompleteFeatureChecklist = {
  project: string;
  source_document: string;
  total_features: number;
  implemented_count: number;
  partial_count: number;
  pending_count: number;
  production_ready_count: number;
  production_gap_count: number;
  summary: string;
  items: CompleteFeatureItem[];
};

type CommittedScopeItem = {
  item_number: number;
  title: string;
  phase: string;
  status_label: string;
  product_route: string;
  evidence: string;
  verification_command: string;
  unhappy_path: string;
  blocking: boolean;
};

type ScopeGuardrailItem = {
  rule: string;
  status_label: string;
  evidence: string;
  action: string;
};

type CommittedScope = {
  project: string;
  source_document: string;
  summary: string;
  done_count: number;
  partial_count: number;
  blocked_count: number;
  out_of_scope_items: string[];
  guardrails: ScopeGuardrailItem[];
  items: CommittedScopeItem[];
};

const fallbackMatrix: FeatureMatrix = {
  project: "Resora",
  summary: "Feature assurance matrix is available in demo mode while the API is unavailable. It keeps launch blockers visible instead of hiding readiness gaps.",
  total_features_checked: 353,
  passed_count: 347,
  pending_count: 6,
  items: [
    {
      feature_key: "search_discovery",
      feature_name: "Search & Discovery",
      category: "Core Research",
      status: "passed",
      enforcement_status: "DONE",
      evidence: "Federated sources, dedup, filters, exports, alerts, clustering and query intelligence are represented with smoke verification.",
      user_flow: "Researcher searches real papers, opens sources, saves alerts and exports result sets.",
      route: "/search",
      automated_check: "search_discovery_smoke",
      verification_command: "python -m pytest app/tests/test_search_discovery_and_summary_features.py -q",
      acceptance_criteria_count: 35,
      capabilities: ["8-source search", "dedup", "filters", "exports", "alerts"],
      production_notes: ["Live source quotas and API keys must be monitored after deployment."],
      blocking: false,
    },
    {
      feature_key: "public_launch_readiness",
      feature_name: "Public launch readiness",
      category: "Production Gate",
      status: "pending",
      enforcement_status: "BLOCKED",
      evidence: "Domain, HTTPS, provider delivery, backup restore, and 50+ concurrent-user validation are still external launch gates.",
      user_flow: "Founder reviews blockers before promising global SaaS launch.",
      route: "/assurance",
      automated_check: "launch_readiness_audit",
      verification_command: "python -m pytest app/tests/test_non_functional_requirements.py -q",
      acceptance_criteria_count: 6,
      capabilities: ["domain/HTTPS", "provider delivery", "backup restore", "50+ load test", "production env"],
      production_notes: ["Do not market as public-launch complete until these gates are closed."],
      blocking: true,
    },
  ],
};

const fallbackProposal: ProposalAlignment = {
  project: "Resora",
  source_document: "RESORA-Proposal-Final.pdf",
  summary: "9 proposal objectives are implemented, 1 is partial, and 0 are pending. OCR is intentionally marked partial until real Tesseract deployment is wired.",
  readiness_score: 95,
  completed_count: 9,
  partial_count: 1,
  pending_count: 0,
  objectives: [
    {
      objective_key: "multi_source_search",
      proposal_text: "Build a multi-source paper search system using free academic APIs.",
      implementation_status: "implemented",
      product_route: "/search",
      verification_check: "search_discovery_smoke",
      evidence: "OpenAlex, arXiv, Semantic Scholar, Crossref, CORE, PMC, Google Scholar, and Unpaywall are represented in the search workflow.",
      caveats: ["Live source quotas and API keys must be monitored after deployment."],
    },
    {
      objective_key: "pdf_ocr",
      proposal_text: "Extract text from normal PDFs and scanned PDFs using OCR.",
      implementation_status: "partial",
      product_route: "/multimodal",
      verification_check: "multimodal_extraction_smoke",
      evidence: "Scanned-payload detection, OCR fallback confidence, and processing notes are exposed.",
      caveats: ["Real Tesseract binary integration is still a deployment task."],
    },
    {
      objective_key: "literature_review_exports",
      proposal_text: "Generate literature review drafts with citations and export options.",
      implementation_status: "implemented",
      product_route: "/writing",
      verification_check: "writing_pipeline_smoke",
      evidence: "Drafting includes citations, critique trace, and Markdown, LaTeX, DOCX, PDF, BibTeX, EndNote, and RIS artifacts.",
      caveats: [],
    },
  ],
};

const fallbackCompleteList: CompleteFeatureChecklist = {
  project: "Resora",
  source_document: "docs/complete-feature-list.md",
  total_features: 209,
  implemented_count: 0,
  partial_count: 0,
  pending_count: 209,
  production_ready_count: 0,
  production_gap_count: 209,
  summary: "Complete list API unavailable; showing fallback counts until backend assurance loads.",
  items: [],
};

const fallbackCommittedScope: CommittedScope = {
  project: "Resora",
  source_document: "CODEX BUILD PROMPT — RESORA (COMMITTED FYP SCOPE)",
  summary: "Committed scope API unavailable; showing local fallback until backend assurance loads.",
  done_count: 0,
  partial_count: 0,
  blocked_count: 1,
  out_of_scope_items: ["Real-time collaboration", "Plagiarism checking", "Zotero/Mendeley integration", "Journal recommendation", "Trend prediction"],
  guardrails: [
    {
      rule: "Default search sources must be free/open APIs only.",
      status_label: "⚠️ PARTIAL",
      evidence: "Waiting for API assurance response.",
      action: "Load backend committed-scope matrix.",
    },
  ],
  items: [],
};

export function FeatureAssurancePage() {
  const [matrix, setMatrix] = useState<FeatureMatrix>(fallbackMatrix);
  const [proposal, setProposal] = useState<ProposalAlignment>(fallbackProposal);
  const [completeList, setCompleteList] = useState<CompleteFeatureChecklist>(fallbackCompleteList);
  const [committedScope, setCommittedScope] = useState<CommittedScope>(fallbackCommittedScope);
  const [status, setStatus] = useState("Assurance matrix ready");
  const [proposalStatus, setProposalStatus] = useState("Proposal alignment ready");
  const [completeListStatus, setCompleteListStatus] = useState("Complete feature list ready");
  const [scopeStatus, setScopeStatus] = useState("Committed FYP scope ready");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const focus = useMemo(() => new URLSearchParams(window.location.search).get("focus") || "", []);

  useEffect(() => {
    let ignore = false;
    async function loadMatrix() {
      setStatus("Loading assurance matrix...");
      try {
        const response = await fetch(`${apiBaseUrl}/verification/features`);
        if (!response.ok) throw new Error(`Verification API ${response.status}`);
        const data = (await response.json()) as FeatureMatrix;
        if (!ignore) {
          setMatrix(data);
          setStatus("Feature assurance loaded from API");
        }
      } catch (caught) {
        if (!ignore) {
          setMatrix(fallbackMatrix);
          setStatus(caught instanceof Error ? `Demo assurance restored: ${caught.message}` : "Demo assurance restored");
        }
      }
    }
    void loadMatrix();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadCompleteList() {
      setCompleteListStatus("Loading complete feature list...");
      try {
        const response = await fetch(`${apiBaseUrl}/verification/complete-list`);
        if (!response.ok) throw new Error(`Complete list API ${response.status}`);
        const data = (await response.json()) as CompleteFeatureChecklist;
        if (!ignore) {
          setCompleteList(data);
          setCompleteListStatus("Complete feature list loaded from API");
        }
      } catch (caught) {
        if (!ignore) {
          setCompleteList(fallbackCompleteList);
          setCompleteListStatus(caught instanceof Error ? `Fallback complete list: ${caught.message}` : "Fallback complete list");
        }
      }
    }
    void loadCompleteList();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadProposalAlignment() {
      setProposalStatus("Loading proposal alignment...");
      try {
        const response = await fetch(`${apiBaseUrl}/verification/proposal`);
        if (!response.ok) throw new Error(`Proposal API ${response.status}`);
        const data = (await response.json()) as ProposalAlignment;
        if (!ignore) {
          setProposal(data);
          setProposalStatus("Proposal alignment loaded from API");
        }
      } catch (caught) {
        if (!ignore) {
          setProposal(fallbackProposal);
          setProposalStatus(caught instanceof Error ? `Demo proposal restored: ${caught.message}` : "Demo proposal restored");
        }
      }
    }
    void loadProposalAlignment();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;
    async function loadCommittedScope() {
      setScopeStatus("Loading committed FYP scope...");
      try {
        const response = await fetch(`${apiBaseUrl}/verification/committed-scope`);
        if (!response.ok) throw new Error(`Committed scope API ${response.status}`);
        const data = (await response.json()) as CommittedScope;
        if (!ignore) {
          setCommittedScope(data);
          setScopeStatus("Committed FYP scope loaded from API");
        }
      } catch (caught) {
        if (!ignore) {
          setCommittedScope(fallbackCommittedScope);
          setScopeStatus(caught instanceof Error ? `Fallback committed scope: ${caught.message}` : "Fallback committed scope");
        }
      }
    }
    void loadCommittedScope();
    return () => {
      ignore = true;
    };
  }, []);

  const categories = useMemo(() => ["All", ...Array.from(new Set(matrix.items.map((item) => item.category)))], [matrix.items]);
  const blockers = useMemo(() => matrix.items.filter((item) => item.blocking), [matrix.items]);
  const coverageScore = Math.round((matrix.passed_count / Math.max(1, matrix.total_features_checked)) * 100);

  const filtered = useMemo(() => {
    const needle = query.toLowerCase().trim();
    return matrix.items.filter((item) => {
      const matchesCategory = category === "All" || item.category === category;
      const haystack = [item.feature_name, item.category, item.evidence, item.user_flow, item.route, item.automated_check, ...item.capabilities].join(" ").toLowerCase();
      return matchesCategory && (!needle || haystack.includes(needle));
    });
  }, [category, matrix.items, query]);

  function exportMatrix() {
    const blob = new Blob([JSON.stringify(matrix, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "resora-feature-assurance-matrix.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Feature assurance matrix exported");
  }

  return (
    <section className={focus === "committed-scope" ? "assurance-shell assurance-shell-focus-committed" : "assurance-shell"}>
      <section className="assurance-hero">
        <div>
          <div className="flex flex-wrap gap-2">
            <span className="status-pill status-pill-green">{matrix.passed_count} passed</span>
            <span className="status-pill status-pill-coral">{matrix.pending_count} pending</span>
            <span className="status-pill status-pill-gold">{matrix.total_features_checked} checked</span>
          </div>
          <p className="assurance-kicker">Launch QA</p>
          <h1 className="assurance-title">See what is ready before launch.</h1>
          <p className="assurance-subtitle">A simple checklist for features, proposal goals, and release blockers.</p>
          <div className="assurance-action-row">
            <button type="button" onClick={exportMatrix} className="resora-button-primary">Export matrix</button>
            <Link to="/control" className="resora-button-ai">Open control</Link>
            <Link to="/developer-ai" className="resora-button-secondary">Open Dev AI</Link>
          </div>
        </div>
        <div className="assurance-score-card">
          <p className="resora-label">Coverage score</p>
          <strong>{coverageScore}%</strong>
          <span>{status}</span>
          <div className="assurance-score-grid">
            <Metric label="checked" value={String(matrix.total_features_checked)} />
            <Metric label="pending" value={String(matrix.pending_count)} />
            <Metric label="blockers" value={String(blockers.length)} />
          </div>
        </div>
      </section>

      <section id="committed-scope" className="assurance-committed-board">
        <div className="assurance-card-head">
          <div>
            <p className="resora-label">Committed FYP scope | {committedScope.source_document}</p>
            <h2>Supervisor-facing scope lock and self-QA evidence.</h2>
          </div>
          <span className="status-pill status-pill-green">{committedScope.done_count} done</span>
        </div>
        <p className="assurance-flow">{committedScope.summary}</p>
        <p className="assurance-evidence">{scopeStatus}</p>
        <div className="assurance-score-grid">
          <Metric label="done" value={String(committedScope.done_count)} />
          <Metric label="partial" value={String(committedScope.partial_count)} />
          <Metric label="blocked" value={String(committedScope.blocked_count)} />
        </div>
        <div className="assurance-committed-guardrails">
          {committedScope.guardrails.map((guardrail) => (
            <article key={guardrail.rule}>
              <span className={guardrail.status_label.startsWith("✅") ? "status-pill status-pill-green" : "status-pill status-pill-gold"}>{guardrail.status_label}</span>
              <strong>{guardrail.rule}</strong>
              <p>{guardrail.evidence}</p>
              <em>{guardrail.action}</em>
            </article>
          ))}
        </div>
      </section>

      <section className="assurance-committed-grid">
        {committedScope.items.map((item) => <CommittedScopeCard key={item.item_number} item={item} />)}
      </section>

      <section className="assurance-outscope-strip">
        <div>
          <p className="resora-label">Out of committed FYP scope</p>
          <h2>Do not present these as defended deliverables.</h2>
        </div>
        <div>
          {committedScope.out_of_scope_items.map((item) => <span key={item}>{item}</span>)}
        </div>
      </section>

      <section className="assurance-card">
        <div className="assurance-card-main">
          <div className="assurance-card-head">
            <div>
              <p className="resora-label">Proposal match | {proposal.source_document}</p>
              <h2>Proposal goals are mapped to product screens.</h2>
            </div>
            <span className="status-pill status-pill-gold">{proposal.readiness_score}% ready</span>
          </div>
          <p className="assurance-flow">{proposal.summary}</p>
          <p className="assurance-evidence">{proposalStatus}</p>
          <div className="assurance-chip-row">
            <span>{proposal.completed_count} implemented</span>
            <span>{proposal.partial_count} partial</span>
            <span>{proposal.pending_count} pending</span>
          </div>
        </div>
        <aside className="assurance-card-side">
          <Metric label="objectives" value={`${proposal.objectives.length}`} />
          <Metric label="source" value="proposal" />
          <Link to="/multimodal" className="resora-button-secondary">Open OCR</Link>
        </aside>
      </section>

      <section className="assurance-grid">
        {proposal.objectives.map((item) => <ProposalCard key={item.objective_key} item={item} />)}
      </section>

      <section className="assurance-card">
        <div className="assurance-card-main">
          <div className="assurance-card-head">
            <div>
              <p className="resora-label">Feature list | {completeList.source_document}</p>
              <h2>Key product features are checked for launch.</h2>
            </div>
            <span className="status-pill status-pill-gold">{completeList.total_features} features</span>
          </div>
          <p className="assurance-flow">{completeList.summary}</p>
          <p className="assurance-evidence">{completeListStatus}</p>
          <div className="assurance-chip-row">
            <span>{completeList.implemented_count} implemented</span>
            <span>{completeList.partial_count} hardening</span>
            <span>{completeList.pending_count} pending</span>
            <span>{completeList.production_gap_count} production gaps</span>
          </div>
        </div>
        <aside className="assurance-card-side">
          <Metric label="ready" value={`${completeList.production_ready_count}`} />
          <Metric label="gaps" value={`${completeList.production_gap_count}`} />
          <Metric label="total" value={`${completeList.total_features}`} />
        </aside>
      </section>

      <section className="assurance-grid">
        {completeList.items.slice(0, 8).map((item) => <CompleteFeatureCard key={`${item.feature_id}-${item.title}`} item={item} />)}
      </section>

      {blockers.length ? (
        <section className="assurance-blocker-strip">
          <div>
            <p className="resora-label">Launch blockers</p>
            <h2>{blockers.length} item{blockers.length === 1 ? "" : "s"} need final validation.</h2>
          </div>
          <div>
            {blockers.slice(0, 4).map((item) => <span key={item.feature_key}>{item.feature_name}</span>)}
          </div>
        </section>
      ) : null}

      <section className="assurance-toolbar">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search features..."
          className="resora-input"
        />
        <div className="assurance-category-row">
          {categories.slice(0, 8).map((item) => (
            <button key={item} type="button" onClick={() => setCategory(item)} className={category === item ? "resora-button-primary" : "resora-button-secondary"}>
              {item}
            </button>
          ))}
        </div>
      </section>

      <section className="assurance-grid">
        {filtered.map((item) => <FeatureCard key={item.feature_key} item={item} />)}
      </section>
    </section>
  );
}

function FeatureCard({ item }: { item: FeatureItem }) {
  return (
    <article className={item.blocking ? "assurance-card assurance-card-blocking" : "assurance-card"}>
      <div className="assurance-card-main">
        <div className="assurance-card-head">
          <div>
            <p className="resora-label">{item.category} · {item.automated_check}</p>
            <h2>{item.feature_name}</h2>
          </div>
          <span className={item.enforcement_status === "DONE" ? "status-pill status-pill-green" : "status-pill status-pill-coral"}>{item.enforcement_status}</span>
        </div>
        <p className="assurance-flow">{item.user_flow}</p>
        <p className="assurance-evidence">{item.evidence}</p>
        <div className="assurance-chip-row">
          {item.capabilities.slice(0, 8).map((capability) => <span key={capability}>{capability}</span>)}
        </div>
      </div>
      <aside className="assurance-card-side">
        <Metric label="criteria" value={`${item.acceptance_criteria_count}`} />
        <Metric label="status" value={item.status} />
        <Link to={item.route} className="resora-button-secondary">Open {item.route}</Link>
        <div className="assurance-command">
          <p className="resora-label">Verification command</p>
          <code>{item.verification_command}</code>
        </div>
        <div className="assurance-notes">
          <p className="resora-label">Production notes</p>
          {item.production_notes.slice(0, 3).map((note) => <span key={note}>{note}</span>)}
        </div>
      </aside>
    </article>
  );
}

function CommittedScopeCard({ item }: { item: CommittedScopeItem }) {
  const done = item.status_label.startsWith("✅");
  const partial = item.status_label.startsWith("⚠️");
  return (
    <article className={done ? "assurance-card assurance-committed-card" : "assurance-card assurance-card-blocking assurance-committed-card"}>
      <div className="assurance-card-main">
        <div className="assurance-card-head">
          <div>
            <p className="resora-label">Item {item.item_number} | {item.phase}</p>
            <h2>{item.title}</h2>
          </div>
          <span className={done ? "status-pill status-pill-green" : partial ? "status-pill status-pill-gold" : "status-pill status-pill-coral"}>{item.status_label}</span>
        </div>
        <p className="assurance-evidence">{item.evidence}</p>
        <p className="assurance-flow">{item.unhappy_path}</p>
      </div>
      <aside className="assurance-card-side">
        <Metric label="phase" value={item.phase.replace("Phase ", "P")} />
        <Link to={item.product_route} className="resora-button-secondary">Open {item.product_route}</Link>
        <div className="assurance-command">
          <p className="resora-label">Regression command</p>
          <code>{item.verification_command}</code>
        </div>
      </aside>
    </article>
  );
}

function ProposalCard({ item }: { item: ProposalObjective }) {
  const done = item.implementation_status === "implemented";
  return (
    <article className={done ? "assurance-card" : "assurance-card assurance-card-blocking"}>
      <div className="assurance-card-main">
        <div className="assurance-card-head">
          <div>
            <p className="resora-label">{item.objective_key} | {item.verification_check}</p>
            <h2>{item.proposal_text}</h2>
          </div>
          <span className={done ? "status-pill status-pill-green" : "status-pill status-pill-gold"}>{item.implementation_status}</span>
        </div>
        <p className="assurance-evidence">{item.evidence}</p>
        {item.caveats.length ? (
          <div className="assurance-notes">
            <p className="resora-label">Caveats</p>
            {item.caveats.slice(0, 3).map((note) => <span key={note}>{note}</span>)}
          </div>
        ) : null}
      </div>
      <aside className="assurance-card-side">
        <Metric label="status" value={item.implementation_status} />
        <Link to={item.product_route} className="resora-button-secondary">Open {item.product_route}</Link>
      </aside>
    </article>
  );
}

function CompleteFeatureCard({ item }: { item: CompleteFeatureItem }) {
  const ready = item.production_status === "production_ready" && item.implementation_status === "implemented";
  return (
    <article className={ready ? "assurance-card" : "assurance-card assurance-card-blocking"}>
      <div className="assurance-card-main">
        <div className="assurance-card-head">
          <div>
            <p className="resora-label">{item.feature_id} | {item.module}</p>
            <h2>{item.title}</h2>
          </div>
          <span className={ready ? "status-pill status-pill-green" : "status-pill status-pill-gold"}>{item.implementation_status}</span>
        </div>
        <p className="assurance-evidence">{item.evidence}</p>
        {item.remediation ? <p className="assurance-flow">{item.remediation}</p> : null}
      </div>
      <aside className="assurance-card-side">
        <Metric label="production" value={item.production_status.replace("_", " ")} />
        <Link to={item.mapped_route} className="resora-button-secondary">Open {item.mapped_route}</Link>
      </aside>
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="assurance-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
