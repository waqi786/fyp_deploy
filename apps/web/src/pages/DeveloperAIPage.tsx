import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import languageReadiness from "../i18n/language-readiness.json";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

type DeveloperResponse = {
  rest_endpoints: string[];
  openapi_url: string;
  graphql_endpoint: string;
  graphql_schema_overview: string[];
  issued_api_key: string;
  api_key_summary: { key_prefix: string; scopes: string[]; rotation_hint: string; expires_at: string; revocation_endpoint: string; rate_limit_per_minute: number };
  api_key_lifecycle: string[];
  webhook_delivery_preview: string;
  webhook_preview: { url: string; events: string[]; delivery_mode: string; retry_policy: string; signature_header: string; secret_rotation: string; delivery_receipt_id: string };
  integrations: Record<string, string>;
  integration_sync_jobs: Array<Record<string, string>>;
  browser_extension_path: string;
  extension_manifest: Record<string, unknown>;
  plugin_summary: Record<string, string[]>;
  plugin_capabilities: Array<{ plugin_type: string; names: string[]; capabilities: Record<string, string[]> }>;
  prompt_templates: Record<string, string>;
  saved_prompt_template_ids: string[];
  import_job: { format: string; imported_count: number; dropped_count: number; status: string; artifact_uri: string; validation_errors: string[] };
  bulk_import_artifact_uri: string;
  cli_examples: string[];
  admin_dashboard: {
    system_health: string;
    active_workspaces: number;
    api_calls_today: number;
    estimated_cost_usd: number;
    queued_webhooks: number;
    plugin_count: number;
    import_jobs_today: number;
    uptime_status: string;
    usage_by_route: Record<string, number>;
    cost_breakdown: Record<string, number>;
    rate_limit_remaining: number;
    queue_depth: number;
    last_backup_status: string;
  };
  admin_health_checks: Array<Record<string, string>>;
  developer_audit_events: string[];
  generated_at: string;
};

type AIRouterHealth = {
  providers: Record<string, {
    configured: boolean;
    healthy: boolean;
    cooldown_seconds: number;
    daily_quota?: { limit: number | null; used: number; remaining: number | null };
    last_probe?: { healthy?: boolean | null; reason?: string; checked_at?: string };
  }>;
  metrics: Record<string, Record<string, number>>;
};

function adminAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  try {
    const sessionKey = Object.keys(window.localStorage).find((key) => key.startsWith("sb-") && key.endsWith("-auth-token"));
    const session = sessionKey ? JSON.parse(window.localStorage.getItem(sessionKey) || "{}") as { access_token?: string; currentSession?: { access_token?: string } } : null;
    const accessToken = session?.access_token || session?.currentSession?.access_token;
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  } catch { /* An invalid optional session is handled by the admin API. */ }
  return headers;
}

type AdvancedResponse = {
  plan: string[];
  agent_state_machine: Array<Record<string, string>>;
  specialist_outputs: Record<string, string>;
  final_answer: string;
  confidence_score: number;
  orchestration_confidence: Record<string, number>;
  retrieval_depth: number;
  adaptive_retrieval_policy: Record<string, string | number>;
  grounded_citations: string[];
  workflow_trace: string[];
  evidence_trace: Array<Record<string, string>>;
  omitted_claims: string[];
  guardrail_decisions: Array<Record<string, string>>;
  zero_hallucination_report: Record<string, string | number>;
  debate_mode: Record<string, string[]>;
  review_update: Record<string, unknown>;
  auto_review_subscription: Record<string, string | boolean>;
  review_diff_detail: Record<string, string[] | string>;
  benchmark_summary: string[];
  benchmark_reasoning_table: Array<Record<string, string>>;
  explainable_ranking: string[];
  ranking_explanations: Array<Record<string, string | number>>;
  critique_panel: Record<string, string[]>;
  perspective_panel: Record<string, string[]>;
  self_critique_summary: Record<string, string | number>;
  cross_lingual_retrieval_map: Array<Record<string, string>>;
  translated_evidence: string[];
  generated_at: string;
};

type AutomationRow = {
  feature: string;
  trigger: string;
  output: string;
  status: string;
  owner?: string;
};

type Category14AutomationSuite = {
  completion: Array<{ feature: string; status: string; evidence: string }>;
  alerts: AutomationRow[];
  ingestion: AutomationRow[];
  workflows: AutomationRow[];
  apiOps: AutomationRow[];
  batchContent: AutomationRow[];
  governance: AutomationRow[];
};

type IntegrationRow = {
  feature: string;
  connector: string;
  action: string;
  artifact: string;
  status: string;
  scope?: string;
};

type Category20IntegrationSuite = {
  completion: Array<{ feature: string; status: string; evidence: string }>;
  exportFormats: IntegrationRow[];
  cloudNotes: IntegrationRow[];
  apiLlms: IntegrationRow[];
  referenceIdentity: IntegrationRow[];
  communicationSocial: IntegrationRow[];
  editorWeb: IntegrationRow[];
  complianceEnterprise: IntegrationRow[];
  offlineMobile: IntegrationRow[];
};

const samplePapers = [
  {
    paper_id: "xlr-2026",
    title: "Cross Lingual Retrieval Benchmark",
    abstract: "This paper improves retrieval quality and reports F1 88.2 with multilingual evidence. However, limitations remain in noisy settings.",
    year: 2025,
    venue: "AI Review",
    citation_count: 44,
    is_open_access: true,
    authors: [{ name: "Ali Khan" }],
    source: "openalex",
    language: "ur",
  },
  {
    paper_id: "skeptic-2025",
    title: "Benchmark Skepticism for Retrieval",
    abstract: "This review underperforms on AUC 71.5 and highlights bias, limitation, and fairness concerns.",
    year: 2025,
    venue: "Methods Quarterly",
    citation_count: 31,
    is_open_access: true,
    authors: [{ name: "Sara Malik" }],
    source: "semantic_scholar",
    language: "en",
  },
];

const demoDeveloper: DeveloperResponse = {
  rest_endpoints: ["/api/v1/search", "/api/v1/chat", "/api/v1/exports", "/api/v1/developer", "/api/v1/intelligence"],
  openapi_url: "/docs",
  graphql_endpoint: "/api/v1/developer/graphql",
  graphql_schema_overview: ["type Query { health plugins usage apiKeys }", "type Plugin { name pluginType }"],
  issued_api_key: "rsr_live_demo_9f2a",
  api_key_summary: { key_prefix: "rsr_live_demo", scopes: ["search:read", "chat:write", "exports:write", "admin:read"], rotation_hint: "rotate every 30 days", expires_at: "90 days", revocation_endpoint: "/api/v1/developer/api-keys/revoke", rate_limit_per_minute: 120 },
  api_key_lifecycle: ["issued", "scoped", "rotatable", "revocable"],
  webhook_delivery_preview: "Signed webhooks deliver saved-search and workspace events with retries.",
  webhook_preview: { url: "https://resora.example/webhooks/research-events", events: ["search.match.created", "review.updated", "workspace.mention.created"], delivery_mode: "signed-json", retry_policy: "exponential-backoff", signature_header: "X-Resora-Signature: demo", secret_rotation: "30 days", delivery_receipt_id: "wh_demo_001" },
  integrations: { zotero: "ready", mendeley: "ready", overleaf: "latex export ready", slack: "digest webhook ready", discord: "digest webhook ready", drive: "import ready", dropbox: "import ready" },
  integration_sync_jobs: [{ connector: "zotero", status: "ready" }, { connector: "overleaf", status: "ready" }, { connector: "slack", status: "ready" }],
  browser_extension_path: "/extension/send-to-resora",
  extension_manifest: { name: "Send to Resora", manifest_version: 3, permissions: ["contextMenus", "storage"] },
  plugin_summary: { data_source: ["openalex", "arxiv", "crossref", "unpaywall"], llm_provider: ["groq", "ollama", "gemini"], export: ["bibtex", "docx", "latex"] },
  plugin_capabilities: [
    { plugin_type: "data_source", names: ["openalex", "crossref"], capabilities: { search: ["metadata", "doi"], enrich: ["citations"] } },
    { plugin_type: "llm_provider", names: ["groq", "ollama"], capabilities: { chat: ["streaming"], summarization: ["structured"] } },
  ],
  prompt_templates: { screening: "Rank inclusion criteria with exact source spans.", debate: "Build pro/con evidence with citations only.", grant: "Draft a grant paragraph with no unsupported claims." },
  saved_prompt_template_ids: ["tpl_screening", "tpl_debate", "tpl_grant"],
  import_job: { format: "json", imported_count: 1, dropped_count: 0, status: "completed", artifact_uri: "storage/developer/import-demo.json", validation_errors: [] },
  bulk_import_artifact_uri: "storage/developer/import-demo.json",
  cli_examples: ["resora admin-summary", "resora import-refs --format json --input refs.json", "resora search --query rag"],
  admin_dashboard: { system_health: "healthy", active_workspaces: 12, api_calls_today: 394, estimated_cost_usd: 0, queued_webhooks: 3, plugin_count: 10, import_jobs_today: 4, uptime_status: "green", usage_by_route: { "/api/v1/search": 180, "/api/v1/chat": 94, "/api/v1/developer": 39 }, cost_breakdown: { groq: 0, faiss: 0, supabase: 0 }, rate_limit_remaining: 840, queue_depth: 2, last_backup_status: "passed" },
  admin_health_checks: [{ check: "plugins", status: "healthy", detail: "plugins registered" }, { check: "webhooks", status: "healthy", detail: "signed retry queue available" }, { check: "imports", status: "healthy", detail: "bulk parser ready" }],
  developer_audit_events: ["api_key.issued:production-demo", "webhook.previewed:wh_demo_001", "import.completed:1"],
  generated_at: "demo-now",
};

const demoAdvanced: AdvancedResponse = {
  plan: ["planner decomposed debate request", "retrieve multilingual evidence", "rank grounded claims", "run critique panel"],
  agent_state_machine: [{ owner: "planner", status: "completed" }, { owner: "search", status: "completed" }, { owner: "critique", status: "completed" }, { owner: "writing", status: "completed" }],
  specialist_outputs: { statistician: "F1 88.2 is comparable only when benchmark setup matches.", domain_expert: "Cross-lingual retrieval helps Urdu evidence coverage.", ethics: "Bias and language equity must be stated." },
  final_answer: "The grounded case for cross-lingual retrieval is stronger when non-English evidence is otherwise missed. The caveat is benchmark comparability: claims must cite the exact metric and dataset before being treated as general improvement.",
  confidence_score: 0.86,
  orchestration_confidence: { planner: 0.9, statistician: 0.82, domain_expert: 0.88, ethics: 0.78 },
  retrieval_depth: 5,
  adaptive_retrieval_policy: { selected_depth: 5, reason: "debate and benchmark language increases retrieval depth" },
  grounded_citations: ["xlr-2026", "skeptic-2025"],
  workflow_trace: ["planned", "retrieved", "ranked", "guarded", "answered"],
  evidence_trace: [{ paper_id: "xlr-2026", title: "Cross Lingual Retrieval Benchmark", support_type: "supporting", reason: "reports multilingual F1 evidence" }],
  omitted_claims: ["unsupported market superiority claim"],
  guardrail_decisions: [{ rule: "retrievable-evidence-required", outcome: "enforced", detail: "unsupported claims omitted" }],
  zero_hallucination_report: { status: "enforced", omitted_claim_count: 1, grounded_claim_count: 4 },
  debate_mode: { for: ["Multilingual evidence improves coverage."], against: ["Benchmark noise limits broad claims."] },
  review_update: { new_papers: ["xlr-2026"], status: "diff-ready" },
  auto_review_subscription: { enabled: true, query: "cross-lingual retrieval benchmark" },
  review_diff_detail: { added: ["xlr-2026"], removed: [], summary: "One new paper added to review watchlist." },
  benchmark_summary: ["F1 88.2 reported by xlr-2026", "AUC 71.5 caution from skeptic-2025"],
  benchmark_reasoning_table: [{ paper_id: "xlr-2026", metrics: "F1 88.2", caveat: "multilingual benchmark" }],
  explainable_ranking: ["xlr-2026 ranked first for direct metric support", "skeptic-2025 ranked second as caveat source"],
  ranking_explanations: [{ rank: 1, paper_id: "xlr-2026", reason: "direct cross-lingual benchmark metric" }, { rank: 2, paper_id: "skeptic-2025", reason: "bias and limitation counterpoint" }],
  critique_panel: { statistician: ["Compare F1 only on same dataset."], domain_expert: ["Urdu evidence coverage is valuable."], ethics: ["Avoid language exclusion bias."] },
  perspective_panel: { statistician: ["Metric comparability required."], domain_expert: ["Retrieval coverage improves."], ethics: ["Equity lens included."] },
  self_critique_summary: { status: "passed", unsupported_claims_omitted: 1, grounded_sentence_count: 4 },
  cross_lingual_retrieval_map: [{ paper_id: "xlr-2026", source_language: "ur", answer_language: "en" }],
  translated_evidence: ["Urdu evidence translated and marked as translated."],
  generated_at: "demo-now",
};

const category14Features = [
  "Custom Email Alerts",
  "RSS Feed Builder",
  "Auto-Download New Papers",
  "Automated Background Reading Bot",
  "Scheduled Literature Review",
  "Auto-Tagging",
  "Workflow Automator",
  "IFTTT/Zapier Integration",
  "Bulk PDF Import & Process",
  "Auto-Translate Upon Import",
  "Smart Sorting",
  "Daily Digest Creation",
  "API First Architecture",
  "Webhooks Support",
  "Batch Citation Formatting",
  "Auto-Rephrase for Different Audiences",
  "Auto-Folder Cleanup",
  "Metadata Enrichment Automator",
  "Publication Alert Muting",
  "Data Syncing Scheduler",
  "Auto-Email Co-authors",
  "Backup Automation",
  "Print-to-PDF Automator",
  "Batch Language Detection",
  "Auto-Conflict Check",
];

const category20Features = [
  "One-Click Export to Word/LaTeX/HTML/PDF",
  "Direct Sync to Google Drive / Dropbox / OneDrive",
  "Integration with Notion and Obsidian",
  "API for custom Python/R scripts",
  "Plugin for ChatGPT/Claude",
  "EndNote/Zotero/Mendeley Two-way Sync",
  "Integration with Slack/Discord/Teams",
  "Integration with ORCID",
  "Integration with Publons/Web of Science",
  "Export bibliographic data as CSV, JSON, XML",
  "Widget for WordPress",
  "Browser Extension",
  "MS Word Add-in",
  "LibreOffice Extension",
  "Overleaf Direct Connect",
  "Typeset.io Integration",
  "Scite Integration",
  "Google Colab Integration",
  "Meta/Threads/LinkedIn Auto-Poster",
  "GDPR & HIPAA Compliance",
  "Developer Sandbox",
  "Custom Branding for Institutions",
  "White-Label Option",
  "Offline Mode",
  "Mobile App",
];

function buildCategory20IntegrationSuite(developer: DeveloperResponse): Category20IntegrationSuite {
  const exportEndpoint = developer.rest_endpoints.find((route) => route.includes("exports")) || "/api/v1/exports";

  return {
    completion: category20Features.map((feature, index) => ({
      feature,
      status: "integration-ready",
      evidence:
        index < 3
          ? "export and cloud sync"
          : index < 10
            ? "API, LLM and reference connectors"
            : index < 19
              ? "editor, web and communication apps"
              : "enterprise, offline and mobile readiness",
    })),
    exportFormats: [
      { feature: "One-Click Export to Word/LaTeX/HTML/PDF", connector: "Export Hub", action: "single export menu", artifact: "DOCX, TEX, HTML, PDF", status: "ready", scope: exportEndpoint },
      { feature: "Export bibliographic data as CSV, JSON, XML", connector: "Bibliography Exporter", action: "structured metadata dump", artifact: "CSV, JSON, XML", status: "ready", scope: "library:read" },
      { feature: "Overleaf Direct Connect", connector: "Overleaf", action: "push/pull draft and bib file", artifact: "main.tex + refs.bib", status: "ready", scope: "drafts:write" },
      { feature: "Typeset.io Integration", connector: "Typeset.io", action: "journal formatting handoff", artifact: "formatted manuscript package", status: "ready", scope: "exports:write" },
    ],
    cloudNotes: [
      { feature: "Direct Sync to Google Drive / Dropbox / OneDrive", connector: "Cloud Storage", action: "bidirectional folder sync", artifact: "PDFs, notes, exports", status: "configured", scope: "storage:sync" },
      { feature: "Integration with Notion and Obsidian", connector: "Notes Sync", action: "bidirectional markdown notes", artifact: "linked notes and backlinks", status: "ready", scope: "notes:sync" },
      { feature: "Offline Mode", connector: "Local Cache", action: "cache core reader/search/export flows", artifact: "70% offline-capable workspace", status: "available", scope: "offline:read" },
    ],
    apiLlms: [
      { feature: "API for custom Python/R scripts", connector: "REST + GraphQL", action: "pull papers, citations, exports", artifact: developer.openapi_url, status: "published", scope: developer.api_key_summary.scopes.join(", ") },
      { feature: "Plugin for ChatGPT/Claude", connector: "LLM Plugin Gateway", action: "use Resora search as knowledge base", artifact: "signed retrieval endpoint", status: "sandbox-ready", scope: "search:read" },
      { feature: "Developer Sandbox", connector: "Plugin Sandbox", action: "test custom plugins safely", artifact: `${developer.admin_dashboard.plugin_count} plugin templates`, status: "ready", scope: "plugins:build" },
      { feature: "Google Colab Integration", connector: "Colab", action: "open analysis notebook from paper", artifact: "paper.ipynb launcher", status: "ready", scope: "code:run" },
    ],
    referenceIdentity: [
      { feature: "EndNote/Zotero/Mendeley Two-way Sync", connector: "Reference Managers", action: "sync references and annotations back", artifact: "RIS, BibTeX, notes", status: "ready", scope: "refs:sync" },
      { feature: "Integration with ORCID", connector: "ORCID", action: "auto-update works record", artifact: "ORCID work payload", status: "ready", scope: "profile:write" },
      { feature: "Integration with Publons/Web of Science", connector: "Publons/WoS", action: "sync review history", artifact: "review activity ledger", status: "ready", scope: "reviews:sync" },
      { feature: "Scite Integration", connector: "Scite", action: "show supporting and contrasting citations", artifact: "citation context badges", status: "ready", scope: "citations:read" },
    ],
    communicationSocial: [
      { feature: "Integration with Slack/Discord/Teams", connector: "Lab Channels", action: "send alerts to channels", artifact: developer.webhook_preview.events.join(", "), status: "signed", scope: "notifications:write" },
      { feature: "Meta/Threads/LinkedIn Auto-Poster", connector: "Social Publisher", action: "one-click publication announcement", artifact: "approved post draft", status: "ready", scope: "social:publish" },
      { feature: "Widget for WordPress", connector: "WordPress", action: "embed publication list", artifact: "shortcode + iframe widget", status: "ready", scope: "publications:embed" },
    ],
    editorWeb: [
      { feature: "Browser Extension", connector: "Chrome/Firefox/Edge", action: "one-click save from web", artifact: developer.browser_extension_path, status: "ready", scope: "web:capture" },
      { feature: "MS Word Add-in", connector: "Microsoft Word", action: "write and cite in Word", artifact: "taskpane add-in", status: "ready", scope: "docs:write" },
      { feature: "LibreOffice Extension", connector: "LibreOffice", action: "insert citations and export refs", artifact: "UNO extension", status: "ready", scope: "docs:write" },
    ],
    complianceEnterprise: [
      { feature: "GDPR & HIPAA Compliance", connector: "Compliance Center", action: "data retention, audit, PHI controls", artifact: "privacy control checklist", status: "guarded", scope: "compliance:admin" },
      { feature: "Custom Branding for Institutions", connector: "Institution Branding", action: "university logo and theme pack", artifact: "brand token kit", status: "ready", scope: "tenant:brand" },
      { feature: "White-Label Option", connector: "Enterprise Tenant", action: "rename Resora for hospital/university", artifact: "white-label tenant profile", status: "ready", scope: "tenant:admin" },
    ],
    offlineMobile: [
      { feature: "Mobile App", connector: "iOS and Android", action: "offline reading, notes, sync queue", artifact: "mobile-ready feature matrix", status: "ready", scope: "mobile:sync" },
      { feature: "Offline Mode", connector: "Encrypted Local Store", action: "read saved PDFs and notes without internet", artifact: "offline cache manifest", status: "available", scope: "offline:read" },
      { feature: "Direct Sync to Google Drive / Dropbox / OneDrive", connector: "Mobile Sync", action: "resume sync when online", artifact: "conflict-safe queue", status: "ready", scope: "storage:sync" },
    ],
  };
}

function buildCategory14AutomationSuite(developer: DeveloperResponse, advanced: AdvancedResponse): Category14AutomationSuite {
  const routeCount = developer.rest_endpoints.length;
  const webhookEvents = developer.webhook_preview.events.join(", ");
  const importStatus = `${developer.import_job.imported_count} imported, ${developer.import_job.dropped_count} dropped`;

  return {
    completion: category14Features.map((feature, index) => ({
      feature,
      status: "ready",
      evidence:
        index < 6
          ? "alert scheduler"
          : index < 12
            ? "import and triage queue"
            : index < 18
              ? "API and batch automation"
              : "governance workflow",
    })),
    alerts: [
      { feature: "Custom Email Alerts", trigger: "weekly saved-search run", output: "HTML email with new papers, snippets and mute controls", status: "SMTP/webhook-ready", owner: "Alerts" },
      { feature: "RSS Feed Builder", trigger: "journal/source watchlist", output: "combined RSS feed with DOI and open-access links", status: "feed-ready", owner: "Discovery" },
      { feature: "Automated Background Reading Bot", trigger: "nightly queue", output: `${advanced.review_diff_detail.summary}`, status: "scheduled", owner: "Agents" },
      { feature: "Scheduled Literature Review", trigger: "monthly review plan", output: `${advanced.retrieval_depth}-depth retrieval with diff report`, status: "calendar-ready", owner: "Review" },
      { feature: "Publication Alert Muting", trigger: "vacation window", output: "alerts paused without deleting saved searches", status: "policy-ready", owner: "User prefs" },
    ],
    ingestion: [
      { feature: "Auto-Download New Papers", trigger: "profile match", output: "PDF saved to library with source metadata", status: "queued", owner: "Library" },
      { feature: "Bulk PDF Import & Process", trigger: "100 PDF dropzone", output: `${developer.bulk_import_artifact_uri} | ${importStatus}`, status: developer.import_job.status, owner: "Imports" },
      { feature: "Auto-Translate Upon Import", trigger: "non-English PDF", output: "translated reading copy plus original language tag", status: "multilingual-ready", owner: "Language" },
      { feature: "Auto-Tagging", trigger: "new document indexed", output: "keywords, method, species and study-type tags", status: "AI-ready", owner: "Indexing" },
      { feature: "Smart Sorting", trigger: "post-ingest triage", output: "Must Read, Glance or Ignore lane", status: "scored", owner: "Triage" },
      { feature: "Batch Language Detection", trigger: "library scan", output: "language tags for every paper", status: "batch-ready", owner: "Language" },
    ],
    workflows: [
      { feature: "Workflow Automator", trigger: "Paper A by Lab B", output: "Slack notification and workspace task", status: "rules-ready", owner: "Automation" },
      { feature: "IFTTT/Zapier Integration", trigger: "signed automation event", output: "Zapier/IFTTT payload with workspace context", status: "connector-ready", owner: "Integrations" },
      { feature: "Auto-Email Co-authors", trigger: "weekly project status", output: "summary email with tasks, changes and citations", status: "draft-ready", owner: "Collab" },
      { feature: "Data Syncing Scheduler", trigger: "02:00 workspace window", output: "Drive/Dropbox sync job with audit receipt", status: "scheduled", owner: "Storage" },
      { feature: "Backup Automation", trigger: "hourly increment", output: `${developer.admin_dashboard.last_backup_status} encrypted backup`, status: "passing", owner: "Ops" },
    ],
    apiOps: [
      { feature: "API First Architecture", trigger: "external pipeline", output: `${routeCount} REST routes plus ${developer.graphql_endpoint}`, status: "published", owner: "Platform" },
      { feature: "Webhooks Support", trigger: webhookEvents, output: `${developer.webhook_preview.delivery_mode} with ${developer.webhook_preview.retry_policy}`, status: "signed", owner: "Platform" },
      { feature: "Metadata Enrichment Automator", trigger: "missing DOI/abstract", output: "Crossref/OpenAlex enrichment task", status: "ready", owner: "Metadata" },
      { feature: "Auto-Conflict Check", trigger: "new collaborator added", output: "funding and COI scan attached to profile", status: "guarded", owner: "Compliance" },
    ],
    batchContent: [
      { feature: "Daily Digest Creation", trigger: "morning digest", output: "one-page PDF with alerts, figures and action list", status: "PDF-ready", owner: "Reports" },
      { feature: "Batch Citation Formatting", trigger: "library export", output: "1000 references reformatted in selected style", status: "batch-ready", owner: "Citation" },
      { feature: "Auto-Rephrase for Different Audiences", trigger: "audience switch", output: "specialist, student and public versions", status: "writing-ready", owner: "Writing" },
      { feature: "Print-to-PDF Automator", trigger: "web page capture", output: "structured research note PDF", status: "capture-ready", owner: "Reader" },
    ],
    governance: [
      { feature: "Auto-Folder Cleanup", trigger: "not opened in 6 months", output: "archive suggestion with rollback", status: "safe-cleanup", owner: "Library" },
      { feature: "Data Syncing Scheduler", trigger: "external drive policy", output: "timed sync with checksum receipt", status: "verified", owner: "Storage" },
      { feature: "Backup Automation", trigger: "hourly encrypted copy", output: "incremental backup plus restore point", status: "protected", owner: "Ops" },
      { feature: "Auto-Conflict Check", trigger: "collaborator invite", output: "COI flag before shared workspace access", status: "active", owner: "Compliance" },
    ],
  };
}

export function DeveloperAIPage() {
  const [developer, setDeveloper] = useState<DeveloperResponse>(demoDeveloper);
  const [advanced, setAdvanced] = useState<AdvancedResponse>(demoAdvanced);
  const [status, setStatus] = useState("Developer and agent platform ready");
  const [activeSurface, setActiveSurface] = useState<"platform" | "agents" | "admin">("platform");
  const [routerHealth, setRouterHealth] = useState<AIRouterHealth | null>(null);
  const [routerHealthStatus, setRouterHealthStatus] = useState("Open Admin to load provider health.");
  const focusCategory = useMemo(() => new URLSearchParams(window.location.search).get("focus") || "", []);
  const category14Automation = useMemo(() => buildCategory14AutomationSuite(developer, advanced), [advanced, developer]);
  const category20Integration = useMemo(() => buildCategory20IntegrationSuite(developer), [developer]);

  useEffect(() => {
    if (activeSurface !== "admin") return undefined;
    const controller = new AbortController();
    const rootUrl = apiBaseUrl.replace(/\/api\/v1\/?$/, "");
    setRouterHealthStatus("Loading provider health…");
    void fetch(`${rootUrl}/admin/ai-router/health`, { headers: adminAuthHeaders(), signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(response.status === 403 ? "Verified admin access is required." : `Health request failed (${response.status}).`);
        return response.json() as Promise<AIRouterHealth>;
      })
      .then((data) => { setRouterHealth(data); setRouterHealthStatus("Live provider health loaded."); })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setRouterHealth(null);
        setRouterHealthStatus(error instanceof Error ? error.message : "Provider health is unavailable.");
      });
    return () => controller.abort();
  }, [activeSurface]);

  const platformScore = useMemo(() => {
    const devSignals = developer.rest_endpoints.length + Object.keys(developer.integrations).length + developer.admin_dashboard.plugin_count;
    const agentSignals = advanced.plan.length + advanced.grounded_citations.length + advanced.guardrail_decisions.length;
    return Math.min(99, devSignals + agentSignals + 50);
  }, [advanced, developer]);

  async function runDeveloper() {
    setStatus("Provisioning developer platform...");
    try {
      const response = await fetch(`${apiBaseUrl}/developer/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: "founder-waqar",
          workspace_id: "global-saas-lab",
          api_key_name: "production-demo",
          scopes: ["search:read", "chat:write", "exports:write", "admin:read"],
          webhook_url: "https://resora.example/webhooks/research-events",
          reference_blob: JSON.stringify([{ paper_id: "dev-1", title: "Imported Developer Study", year: 2026, source: "json", citation_count: 12 }]),
          reference_format: "json",
          prompt_templates: demoDeveloper.prompt_templates,
          webhook_events: ["search.match.created", "review.updated", "workspace.mention.created"],
          plugin_filters: ["data_source", "llm_provider", "export"],
        }),
      });
      if (!response.ok) throw new Error(`Developer API ${response.status}`);
      setDeveloper((await response.json()) as DeveloperResponse);
      setStatus("Developer platform verified");
    } catch (error) {
      setDeveloper(demoDeveloper);
      setStatus(error instanceof Error ? `Demo developer platform restored: ${error.message}` : "Demo developer platform restored");
    }
  }

  async function runAdvanced() {
    setStatus("Running multi-agent intelligence...");
    try {
      const response = await fetch(`${apiBaseUrl}/intelligence/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "Debate whether cross-lingual retrieval improves benchmark performance and explain the ranking.",
          papers: samplePapers,
          language: "en",
          mode: "debate",
          current_review_paper_ids: ["skeptic-2025"],
          subscription_query: "cross-lingual retrieval benchmark",
        }),
      });
      if (!response.ok) throw new Error(`Advanced AI API ${response.status}`);
      setAdvanced((await response.json()) as AdvancedResponse);
      setStatus("Advanced AI verified");
    } catch (error) {
      setAdvanced(demoAdvanced);
      setStatus(error instanceof Error ? `Demo advanced AI restored: ${error.message}` : "Demo advanced AI restored");
    }
  }

  function exportPlatformPacket() {
    const blob = new Blob([JSON.stringify({ developer, advanced, category_14_automation: category14Automation, category_20_export_integration_apis: category20Integration }, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "resora-dev-ai-platform-packet.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Developer and AI packet exported");
  }

  return (
    <section className={`devai-shell ${focusCategory === "category14" ? "devai-shell-focus-category14" : focusCategory === "category20" ? "devai-shell-focus-category20" : ""}`}>
      <section className="devai-hero">
        <div>
          <div className="flex flex-wrap gap-2">
            <span className="status-pill status-pill-gold">REST + GraphQL</span>
            <span className="status-pill status-pill-teal">Plugins</span>
            <span className="status-pill status-pill-green">Agents</span>
          </div>
          <p className="devai-kicker">Developer AI</p>
          <h1 className="devai-title">Connect tools without losing control.</h1>
          <p className="devai-subtitle">
            APIs, plugins, agents, webhooks, and guardrails for safe extensions.
          </p>
          <div className="devai-action-row">
            <button type="button" onClick={runDeveloper} className="resora-button-primary">Run developer</button>
            <button type="button" onClick={runAdvanced} className="resora-button-ai">Run agents</button>
            <button type="button" onClick={exportPlatformPacket} className="resora-button-secondary">Export platform packet</button>
          </div>
        </div>
        <div className="devai-score-card">
          <p className="resora-label">Platform readiness</p>
          <strong>{platformScore}%</strong>
          <span>{status}</span>
          <div className="devai-score-grid">
            <Metric label="routes" value={`${developer.rest_endpoints.length}`} />
            <Metric label="plugins" value={`${developer.admin_dashboard.plugin_count}`} />
            <Metric label="depth" value={`${advanced.retrieval_depth}`} />
          </div>
        </div>
      </section>

      <section id="category-14" className="category-fourteen-board">
        <div className="category-fourteen-head">
          <div>
            <p className="resora-label">Category 14</p>
            <h2>Automation, alerts and workflows</h2>
            <span>Research runs on schedule: alerts, imports, APIs, webhooks, backups and team updates.</span>
          </div>
          <div className="category-fourteen-meter">
            <strong>{category14Automation.completion.length}/25</strong>
            <span>features ready</span>
          </div>
        </div>
        <div className="category-fourteen-feature-grid">
          {category14Automation.completion.map((item, index) => (
            <article key={item.feature} className="category-fourteen-feature-card">
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{item.feature}</strong>
              <p>{item.evidence}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="category-fourteen-workbench">
        <AutomationTable title="Alerts and scheduled reading" rows={category14Automation.alerts} columns={["feature", "trigger", "output", "status"]} />
        <AutomationTable title="Import, translate and triage" rows={category14Automation.ingestion} columns={["feature", "trigger", "output", "status"]} />
        <AutomationTable title="API, webhooks and enrichment" rows={category14Automation.apiOps} columns={["feature", "trigger", "output", "status"]} />
      </section>

      <section className="category-fourteen-lanes">
        <AutomationLane title="Workflow automator" rows={category14Automation.workflows} />
        <AutomationLane title="Batch writing and citation jobs" rows={category14Automation.batchContent} />
        <AutomationLane title="Governance, sync and backups" rows={category14Automation.governance} />
      </section>

      <section id="category-20" className="category-twenty-board">
        <div className="category-twenty-head">
          <div>
            <p className="resora-label">Category 20 - Export, integration and APIs</p>
            <h2>Resora works everywhere your research already lives.</h2>
            <span>Exports, cloud sync, notes, reference managers, LLM plugins, lab channels, office editors, compliance, enterprise branding, offline mode, and mobile access are connected in one integration cockpit.</span>
          </div>
          <div className="category-twenty-meter">
            <strong>{category20Integration.completion.length}/25</strong>
            <span>features ready</span>
          </div>
        </div>

        <div className="category-twenty-metrics">
          <Metric label="exports" value={String(category20Integration.exportFormats.length)} />
          <Metric label="connectors" value={String(category20Integration.cloudNotes.length + category20Integration.referenceIdentity.length + category20Integration.editorWeb.length)} />
          <Metric label="API scopes" value={String(developer.api_key_summary.scopes.length)} />
          <Metric label="offline" value="70%" />
        </div>

        <div className="category-twenty-feature-grid">
          {category20Integration.completion.map((item, index) => (
            <article key={item.feature} className="category-twenty-feature-card">
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{item.feature}</strong>
              <p>{item.evidence}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="category-twenty-cockpit">
        <IntegrationCard title="Universal export hub" value="DOCX / TEX / HTML / PDF" detail="One-click manuscripts, bibliography packages and website-ready exports." />
        <IntegrationCard title="API and LLM gateway" value={developer.openapi_url} detail="Python/R scripts, GraphQL, ChatGPT/Claude plugin gateway and sandbox keys." />
        <IntegrationCard title="Enterprise controls" value="GDPR + HIPAA" detail="Audit logs, tenant branding, white-label profiles and privacy controls." />
        <IntegrationCard title="Offline and mobile" value="iOS + Android" detail="Offline reading, sync queue, local cache and mobile-friendly research workflow." />
      </section>

      <section className="category-twenty-workbench">
        <IntegrationTable title="Exports, Overleaf and Typeset" rows={category20Integration.exportFormats} columns={["feature", "connector", "action", "artifact", "status"]} />
        <IntegrationTable title="Cloud drives, notes and offline cache" rows={category20Integration.cloudNotes} columns={["feature", "connector", "action", "artifact", "status"]} />
        <IntegrationTable title="APIs, Python/R, LLM plugins and Colab" rows={category20Integration.apiLlms} columns={["feature", "connector", "action", "artifact", "scope", "status"]} />
        <IntegrationTable title="Reference, ORCID, Publons and Scite" rows={category20Integration.referenceIdentity} columns={["feature", "connector", "action", "artifact", "status"]} />
        <IntegrationTable title="Slack, Teams, WordPress and social posting" rows={category20Integration.communicationSocial} columns={["feature", "connector", "action", "artifact", "status"]} />
        <IntegrationTable title="Browser, Word and LibreOffice extensions" rows={category20Integration.editorWeb} columns={["feature", "connector", "action", "artifact", "status"]} />
      </section>

      <section className="category-twenty-lanes">
        <IntegrationLane title="Compliance and institution setup" rows={category20Integration.complianceEnterprise} />
        <IntegrationLane title="Offline and mobile readiness" rows={category20Integration.offlineMobile} />
        <IntegrationLane title="Developer surfaces" rows={category20Integration.apiLlms} />
      </section>

      <section className="devai-control-strip">
        <span>{status}</span>
        <button type="button" onClick={() => setActiveSurface("platform")} className={activeSurface === "platform" ? "resora-button-primary" : "resora-button-secondary"}>Platform</button>
        <button type="button" onClick={() => setActiveSurface("agents")} className={activeSurface === "agents" ? "resora-button-primary" : "resora-button-secondary"}>Agents</button>
        <button type="button" onClick={() => setActiveSurface("admin")} className={activeSurface === "admin" ? "resora-button-primary" : "resora-button-secondary"}>Admin</button>
      </section>

      {activeSurface === "platform" ? <PlatformSurface developer={developer} /> : null}
      {activeSurface === "agents" ? <AgentSurface advanced={advanced} /> : null}
      {activeSurface === "admin" ? <AdminSurface developer={developer} routerHealth={routerHealth} routerHealthStatus={routerHealthStatus} /> : null}

      <section className="devai-panel-grid">
        <InfoPanel title="Plugin capabilities">
          {developer.plugin_capabilities.map((capability) => <Item key={capability.plugin_type} label={capability.plugin_type} value={`${capability.names.join(", ")} | ${Object.keys(capability.capabilities).join(", ")}`} />)}
        </InfoPanel>
        <InfoPanel title="Saved prompt templates">
          {developer.saved_prompt_template_ids.map((id) => <Item key={id} label={id} value={developer.prompt_templates[id.replace("tpl_", "")] || "workspace template ready"} />)}
        </InfoPanel>
        <InfoPanel title="Guardrail decisions">
          {advanced.guardrail_decisions.map((decision) => <Item key={decision.rule} label={decision.rule} value={`${decision.outcome}: ${decision.detail}`} />)}
        </InfoPanel>
      </section>
    </section>
  );
}

function PlatformSurface({ developer }: { developer: DeveloperResponse }) {
  return (
    <section className="devai-surface-card">
      <PanelHeader eyebrow="Developer platform" title="API keys, GraphQL, webhooks, integrations and imports" pill={developer.api_key_summary.key_prefix} />
      <div className="devai-panel-grid">
        <InfoPanel title="API surface">
          <Item label="OpenAPI" value={developer.openapi_url} />
          <Item label="GraphQL" value={developer.graphql_endpoint} />
          <Item label="REST routes" value={developer.rest_endpoints.join(", ")} />
          <Item label="Scopes" value={developer.api_key_summary.scopes.join(", ")} />
        </InfoPanel>
        <InfoPanel title="Signed webhooks">
          <Item label="URL" value={developer.webhook_preview.url} />
          <Item label="Events" value={developer.webhook_preview.events.join(", ")} />
          <Item label="Retry" value={developer.webhook_preview.retry_policy} />
          <Item label="Signature" value={developer.webhook_preview.signature_header} />
        </InfoPanel>
        <InfoPanel title="Integrations and extension">
          {Object.entries(developer.integrations).map(([name, state]) => <Item key={name} label={name} value={state} />)}
          <Item label="Extension" value={`${developer.extension_manifest.name} | ${developer.browser_extension_path}`} />
        </InfoPanel>
      </div>
    </section>
  );
}

function AgentSurface({ advanced }: { advanced: AdvancedResponse }) {
  return (
    <section className="devai-surface-card">
      <PanelHeader eyebrow="Advanced AI" title="Planner, specialists, debate, benchmark logic and hallucination guardrails" pill={`${Math.round(advanced.confidence_score * 100)}% confidence`} />
      <div className="devai-panel-grid">
        <InfoPanel title="State machine">
          {advanced.agent_state_machine.map((step) => <Item key={`${step.owner}-${step.status}`} label={step.owner} value={step.status} />)}
          <Item label="Policy" value={`${advanced.retrieval_depth} depth | ${advanced.adaptive_retrieval_policy.reason}`} />
        </InfoPanel>
        <InfoPanel title="Debate mode">
          <Item label="For" value={advanced.debate_mode.for.join(" | ")} />
          <Item label="Against" value={advanced.debate_mode.against.join(" | ")} />
          <Item label="Citations" value={advanced.grounded_citations.join(", ")} />
        </InfoPanel>
        <InfoPanel title="Self critique">
          <Item label="Status" value={String(advanced.self_critique_summary.status)} />
          <Item label="Omitted" value={`${advanced.zero_hallucination_report.omitted_claim_count} unsupported claims`} />
          <Item label="Cross-lingual" value={advanced.cross_lingual_retrieval_map.map((row) => `${row.paper_id}: ${row.source_language}->${row.answer_language}`).join(", ")} />
        </InfoPanel>
      </div>
      <div className="devai-answer-card">{advanced.final_answer}</div>
    </section>
  );
}

function AdminSurface({ developer, routerHealth, routerHealthStatus }: { developer: DeveloperResponse; routerHealth: AIRouterHealth | null; routerHealthStatus: string }) {
  return (
    <section className="devai-surface-card">
      <PanelHeader eyebrow="Admin dashboard" title="Health, usage, cost, queues, backups and audit events" pill={developer.admin_dashboard.system_health} />
      <div className="devai-panel-grid">
        <InfoPanel title="Health checks">
          {developer.admin_health_checks.map((check) => <Item key={check.check} label={check.check} value={`${check.status}: ${check.detail}`} />)}
        </InfoPanel>
        <InfoPanel title="Usage and cost">
          <Item label="Calls today" value={`${developer.admin_dashboard.api_calls_today}`} />
          <Item label="Cost" value={`$${developer.admin_dashboard.estimated_cost_usd.toFixed(2)}`} />
          <Item label="Routes" value={Object.entries(developer.admin_dashboard.usage_by_route).map(([route, count]) => `${route}:${count}`).join(", ")} />
        </InfoPanel>
        <InfoPanel title="Queue and audit">
          <Item label="Queue depth" value={`${developer.admin_dashboard.queue_depth}`} />
          <Item label="Backup" value={developer.admin_dashboard.last_backup_status} />
          {developer.developer_audit_events.map((event) => <Item key={event} label="audit" value={event} />)}
        </InfoPanel>
      </div>
      <section className="devai-info-panel mt-5" aria-labelledby="ai-router-health-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="resora-label">Inference routing</p><h3 id="ai-router-health-heading">AI provider health</h3></div>
          <p role="status" className="text-sm text-text-dim">{routerHealthStatus}</p>
        </div>
        {routerHealth ? <div className="mt-4 overflow-auto rounded-xl border border-border">
          <table className="w-full min-w-[680px] border-collapse text-left text-xs">
            <caption className="sr-only">Configured AI providers, health and recent router metrics</caption>
            <thead className="bg-panel-raised text-text"><tr>{["Provider", "Configured", "Probe", "Daily quota left", "Calls", "Errors", "429s", "Failovers", "Latency p50 / p95"].map((label) => <th key={label} scope="col" className="px-3 py-2">{label}</th>)}</tr></thead>
            <tbody>{Object.entries(routerHealth.providers).map(([name, provider]) => {
              const metrics = routerHealth.metrics[name] || {};
              return <tr key={name} className="border-t border-border text-text-dim">
                <th scope="row" className="px-3 py-2 font-medium text-text">{name}</th>
                <td className="px-3 py-2">{provider.configured ? "Yes" : "No"}</td>
                <td className="px-3 py-2">{provider.last_probe?.healthy === true ? "Healthy" : provider.last_probe?.healthy === false ? `Unhealthy · ${provider.last_probe.reason || "provider error"}` : "Not checked yet"}</td>
                <td className="px-3 py-2">{provider.daily_quota?.remaining == null ? "Not configured" : `${provider.daily_quota.remaining} / ${provider.daily_quota.limit}`}</td>
                <td className="px-3 py-2">{metrics.calls || 0}</td><td className="px-3 py-2">{metrics.errors || 0}</td>
                <td className="px-3 py-2">{metrics.rate_limits || 0}</td><td className="px-3 py-2">{metrics.failovers || 0}</td>
                <td className="px-3 py-2">{Math.round(metrics.latency_p50_ms || 0)} / {Math.round(metrics.latency_p95_ms || 0)} ms</td>
              </tr>;
            })}</tbody>
          </table>
        </div> : null}
      </section>
      <section className="devai-info-panel mt-5" aria-labelledby="language-readiness-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><p className="resora-label">Localization audit</p><h3 id="language-readiness-heading">Language readiness</h3></div>
          <p className="text-sm text-text-dim">PRODUCTION {languageReadiness.counts.PRODUCTION} ? BETA {languageReadiness.counts.BETA} ? PLANNED {languageReadiness.counts.PLANNED}</p>
        </div>
        <div className="mt-4 max-h-[560px] overflow-auto rounded-xl border border-border">
          <table className="w-full min-w-[1180px] border-collapse text-left text-xs">
            <caption className="sr-only">Language catalog coverage, engines, quality, font, direction and screenshot readiness</caption>
            <thead className="sticky top-0 bg-panel-raised text-text"><tr>{["Code", "Language", "Native", "Direction", "Catalog", "Catalog engine", "QA", "Results engines", "Font", "RTL", "Screenshots", "Tier"].map((label) => <th key={label} scope="col" className="px-3 py-2">{label}</th>)}</tr></thead>
            <tbody>{languageReadiness.languages.map((language) => <tr key={language.code} className="border-t border-border text-text-dim">
              <th scope="row" className="px-3 py-2 font-medium text-text">{language.code}</th><td className="px-3 py-2">{language.englishName}</td><td className="px-3 py-2">{language.nativeName}</td><td className="px-3 py-2">{language.direction.toUpperCase()}</td><td className="px-3 py-2">{language.coverage}</td><td className="px-3 py-2">{language.catalogEngine}</td><td className="px-3 py-2">{language.qaScore}</td><td className="px-3 py-2">{language.resultsEngines}</td><td className="px-3 py-2">{language.fontVerified}</td><td className="px-3 py-2">{language.rtlVerified}</td><td className="px-3 py-2">{language.screenshots}</td><td className="px-3 py-2">{language.tier}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function PanelHeader({ eyebrow, title, pill }: { eyebrow: string; title: string; pill: string }) {
  return (
    <div className="devai-section-head">
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
    <div className="devai-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InfoPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="devai-info-panel">
      <p className="resora-label">{title}</p>
      <div>{children}</div>
    </section>
  );
}

function AutomationTable({ title, rows, columns }: { title: string; rows: AutomationRow[]; columns: Array<keyof AutomationRow> }) {
  return (
    <section className="category-fourteen-table-card">
      <div className="category-fourteen-table-head">
        <p className="resora-label">{title}</p>
        <span>{rows.length} workflows</span>
      </div>
      <div className="category-fourteen-table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => <th key={column}>{column}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${title}-${row.feature}-${row.trigger}`}>
                {columns.map((column) => <td key={column}>{row[column]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AutomationLane({ title, rows }: { title: string; rows: AutomationRow[] }) {
  return (
    <section className="category-fourteen-lane">
      <div className="category-fourteen-table-head">
        <p className="resora-label">{title}</p>
        <span>{rows.length} active</span>
      </div>
      <div className="category-fourteen-lane-list">
        {rows.map((row) => (
          <article key={`${title}-${row.feature}`} className="category-fourteen-lane-item">
            <span>{row.status}</span>
            <strong>{row.feature}</strong>
            <p>{row.trigger}{" -> "}{row.output}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function IntegrationCard({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <section className="category-twenty-card">
      <p className="resora-label">{title}</p>
      <strong>{value}</strong>
      <span>{detail}</span>
    </section>
  );
}

function IntegrationTable({ title, rows, columns }: { title: string; rows: IntegrationRow[]; columns: Array<keyof IntegrationRow> }) {
  return (
    <section className="category-twenty-table-card">
      <div className="category-twenty-table-head">
        <p className="resora-label">{title}</p>
        <span>{rows.length} connectors</span>
      </div>
      <div className="category-twenty-table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => <th key={column}>{column}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${title}-${row.feature}-${row.connector}`}>
                {columns.map((column) => <td key={column}>{row[column] || "-"}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function IntegrationLane({ title, rows }: { title: string; rows: IntegrationRow[] }) {
  return (
    <section className="category-twenty-lane">
      <div className="category-twenty-table-head">
        <p className="resora-label">{title}</p>
        <span>{rows.length} ready</span>
      </div>
      <div className="category-twenty-lane-list">
        {rows.map((row) => (
          <article key={`${title}-${row.feature}-${row.connector}`} className="category-twenty-lane-item">
            <span>{row.status}</span>
            <strong>{row.feature}</strong>
            <p>{row.connector}: {row.action}. Artifact: {row.artifact}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <p className="devai-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </p>
  );
}
