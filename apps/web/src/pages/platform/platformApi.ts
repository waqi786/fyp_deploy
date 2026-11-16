/** API client for Plans & usage (billing), Teams and the research catalog (Insights). Same private identity as Library. */
import { comparisonHeaders } from "../compare/compareApi";
import { LibraryError, libraryApiBase } from "../library/libraryApi";

async function call<T>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST"): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${libraryApiBase}${path}`, { method, headers: { ...comparisonHeaders(), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) }, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new LibraryError("network");
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
    throw new LibraryError(typeof detail?.detail?.code === "string" ? detail.detail.code : response.status === 402 ? "limit_reached" : "unavailable", response.status);
  }
  return (await response.json()) as T;
}

const q = (value: string) => encodeURIComponent(value);

// ------------------------------------------------------------------ billing
export type Currency = "usd" | "pkr";
export type Interval = "month" | "year";
export type Limits = { session: number; week: number; month: number };
export type Plan = { id: "free" | "pro" | "team" | "institution"; rank: number; checkout: boolean; per_seat: boolean; min_seats: number; max_seats: number; trial_days: number; prices: Record<Currency, Record<Interval, number>>; features: string[]; limits: Limits };
export type Pack = { id: string; credits: number; prices: Record<Currency, number> };
export type Window = { scope: "session" | "week" | "month"; used: number; limit: number; remaining: number; percent: number; resets_at: string };
export type Subscription = { id: string; plan: Plan["id"]; interval: Interval; currency: Currency; seats: number; team_id?: string | null; status: "active" | "trialing" | "past_due" | "canceled"; current_period_start: string; current_period_end: string; cancel_at_period_end: number; pending_plan?: string | null; pending_interval?: string | null; pending_seats?: number | null; trial_end?: string | null; provider: string };
export type BillingMe = { plan: Plan["id"]; team_id?: string | null; seats: number; subscription: Subscription | null; usage: { plan: string; pooled: boolean; windows: Window[]; topup_balance: number }; history: Array<{ day: string; action: string; credits: number }>; topup_balance: number; provider: string; sandbox: boolean; costs: Record<string, number> };
export type Invoice = { id: string; number: string; kind: string; description: string; amount: number; currency: Currency; status: string; period_start?: string | null; period_end?: string | null; created_at: string };
export type CheckoutSession = { id: string; kind: "subscription" | "topup"; plan?: string | null; interval: Interval; currency: Currency; seats: number; pack?: string | null; amount: number; status: "open" | "completed" | "canceled" | "expired"; expires_at: string };

export const billingApi = {
  plans: () => call<{ plans: Plan[]; packs: Pack[]; currencies: Currency[]; provider: string; sandbox: boolean }>("/billing/plans"),
  me: () => call<BillingMe>("/billing/me"),
  checkout: (body: { kind: "subscription" | "topup"; plan?: string; interval?: Interval; currency: Currency; seats?: number; pack?: string; team_id?: string }) => call<{ session_id: string; url: string; amount: number; currency: Currency }>("/billing/checkout", body),
  session: (id: string) => call<CheckoutSession>(`/billing/checkout/${q(id)}`),
  sandbox: (id: string, decision: "complete" | "cancel") => call<CheckoutSession>(`/billing/sandbox/${q(id)}/${decision}`, {}),
  change: (plan: string, interval: Interval, seats = 1) => call<{ applied: "now" | "period_end"; prorated_amount: number; currency: Currency; effective_at?: string }>("/billing/subscription/change", { plan, interval, seats }),
  cancel: () => call<Subscription>("/billing/subscription/cancel", {}),
  resume: () => call<Subscription>("/billing/subscription/resume", {}),
  invoices: () => call<{ invoices: Invoice[] }>("/billing/invoices"),
  invoiceUrl: (id: string) => `${libraryApiBase}/billing/invoices/${q(id)}/document`,
};

export async function openInvoice(id: string) {
  const response = await fetch(billingApi.invoiceUrl(id), { headers: comparisonHeaders() });
  if (!response.ok) throw new LibraryError("unavailable", response.status);
  const url = URL.createObjectURL(new Blob([await response.text()], { type: "text/html" }));
  window.open(url, "_blank", "noopener");
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function money(amount: number, currency: Currency, language: string) {
  try {
    return new Intl.NumberFormat(language, { style: "currency", currency: currency.toUpperCase(), maximumFractionDigits: amount % 100 ? 2 : 0 }).format(amount / 100);
  } catch {
    return `${currency.toUpperCase()} ${(amount / 100).toFixed(2)}`;
  }
}

// ------------------------------------------------------------------ teams
export type Role = "owner" | "admin" | "supervisor" | "member" | "viewer";
export type TeamSummary = { id: string; name: string; description?: string | null; owner_id: string; role: Role; member_count: number; project_count: number; unread: number; updated_at: string };
export type Member = { user_id: string; role: Role; display_name: string; joined_at: string };
export type Team = { id: string; name: string; description?: string | null; owner_id: string; my_role: Role; my_user_id: string; members: Member[]; counts: { projects: number; papers: number; pending_reviews: number }; subscription?: Subscription | null };
export type Invite = { id: string; role: Role; email?: string | null; created_at: string; expires_at: string; max_uses: number; uses: number; revoked: number; active: boolean; token?: string };
export type TeamProject = { id: string; name: string; description?: string | null; paper_count: number; done_count: number; comment_count: number; updated_at: string };
export type TeamPaper = { id: string; title: string; authors: string[]; year?: number | null; venue?: string | null; doi?: string | null; url?: string | null; abstract?: string | null; status: "to_read" | "reading" | "done"; assignee_id?: string | null; added_by: string; added_at: string; comment_count: number };
export type ProjectDetail = TeamProject & { papers: TeamPaper[] };
export type Comment = { id: string; author_id: string; author_name?: string | null; body: string; mentions: string[]; parent_id?: string | null; created_at: string; edited_at?: string | null; deleted: number };
export type Review = { id: string; document_id: string; title: string; requested_by: string; requester_name?: string; reviewer_id?: string | null; status: "pending" | "approved" | "changes_requested"; created_at: string; decided_at?: string | null; round: number; comment_count?: number; snapshot?: string; decision_note?: string | null; can_decide?: boolean };
export type Activity = { id: string; actor_id: string; actor_name?: string | null; action: string; target_type?: string | null; summary: string; created_at: string };
export type Notification = { id: string; team_id: string; team_name?: string | null; kind: string; payload: Record<string, string>; is_read: boolean; created_at: string };

const team = (id: string) => `/teams/${q(id)}`;
export const teamsApi = {
  list: () => call<{ teams: TeamSummary[] }>("/teams"),
  create: (name: string, description: string, display_name: string) => call<Team>("/teams", { name, description, display_name }),
  get: (id: string) => call<Team>(team(id)),
  update: (id: string, changes: { name?: string; description?: string }) => call<Team>(team(id), changes, "PATCH"),
  remove: (id: string) => call<void>(team(id), undefined, "DELETE"),
  transfer: (id: string, user_id: string) => call<Team>(`${team(id)}/transfer`, { user_id }),
  updateMember: (id: string, userId: string, changes: { role?: Role; display_name?: string }) => call<Team>(`${team(id)}/members/${q(userId)}`, changes, "PATCH"),
  removeMember: (id: string, userId: string) => call<void>(`${team(id)}/members/${q(userId)}`, undefined, "DELETE"),
  invites: (id: string) => call<{ invites: Invite[] }>(`${team(id)}/invites`),
  invite: (id: string, role: Role, days: number, max_uses: number) => call<Invite>(`${team(id)}/invites`, { role, days, max_uses }),
  revokeInvite: (id: string, inviteId: string) => call<void>(`${team(id)}/invites/${q(inviteId)}`, undefined, "DELETE"),
  previewInvite: (token: string) => call<{ team: { id: string; name: string; description?: string | null }; role: Role; members: number; expires_at: string }>(`/teams/invites/${q(token)}`),
  acceptInvite: (token: string, display_name: string) => call<{ team_id: string; already_member: boolean }>(`/teams/invites/${q(token)}/accept`, { display_name }),
  projects: (id: string) => call<{ projects: TeamProject[] }>(`${team(id)}/projects`),
  createProject: (id: string, name: string, description: string) => call<ProjectDetail>(`${team(id)}/projects`, { name, description }),
  project: (id: string, projectId: string) => call<ProjectDetail>(`${team(id)}/projects/${q(projectId)}`),
  updateProject: (id: string, projectId: string, changes: { name?: string; description?: string }) => call<ProjectDetail>(`${team(id)}/projects/${q(projectId)}`, changes, "PATCH"),
  removeProject: (id: string, projectId: string) => call<void>(`${team(id)}/projects/${q(projectId)}`, undefined, "DELETE"),
  addPapers: (id: string, projectId: string, item_ids: string[]) => call<{ added: number; skipped: number; project: ProjectDetail }>(`${team(id)}/projects/${q(projectId)}/papers`, { item_ids }),
  updatePaper: (id: string, projectId: string, paperId: string, changes: { status?: TeamPaper["status"]; assignee_id?: string; clear_assignee?: boolean }) => call<ProjectDetail>(`${team(id)}/projects/${q(projectId)}/papers/${q(paperId)}`, changes, "PATCH"),
  removePaper: (id: string, projectId: string, paperId: string) => call<void>(`${team(id)}/projects/${q(projectId)}/papers/${q(paperId)}`, undefined, "DELETE"),
  comments: (id: string, targetType: string, targetId: string) => call<{ comments: Comment[] }>(`${team(id)}/comments?target_type=${q(targetType)}&target_id=${q(targetId)}`),
  comment: (id: string, body: { target_type: string; target_id: string; body: string; parent_id?: string }) => call<Comment>(`${team(id)}/comments`, body),
  editComment: (id: string, commentId: string, changes: { body?: string; delete?: boolean }) => call<void>(`${team(id)}/comments/${q(commentId)}`, changes, "PATCH"),
  reviews: (id: string) => call<{ reviews: Review[] }>(`${team(id)}/reviews`),
  requestReview: (id: string, document_id: string, reviewer_id?: string) => call<Review>(`${team(id)}/reviews`, { document_id, reviewer_id: reviewer_id || null }),
  review: (id: string, reviewId: string) => call<Review>(`${team(id)}/reviews/${q(reviewId)}`),
  decide: (id: string, reviewId: string, status: "approved" | "changes_requested", note: string) => call<Review>(`${team(id)}/reviews/${q(reviewId)}/decision`, { status, note }),
  activity: (id: string) => call<{ activity: Activity[] }>(`${team(id)}/activity`),
  usage: (id: string) => call<{ pooled: boolean; plan: string; seats: number; members: number; usage: { windows: Window[] } | null; subscription: Subscription | null }>(`${team(id)}/usage`),
  notifications: () => call<{ notifications: Notification[] }>("/teams/notifications/me"),
  markRead: (ids?: string[]) => call<{ updated: number }>("/teams/notifications/read", { ids: ids || null }),
};

// ------------------------------------------------------------------ research catalog (Big Data pipeline)
export type CatalogPaper = { paper_id: string; doi?: string | null; arxiv_id?: string | null; title: string; abstract?: string | null; year?: number | null; venue?: string | null; authors: Array<{ name: string; orcid?: string | null; affiliations?: string[] }>; topics: string[]; citation_count: number; is_open_access: boolean; pdf_url?: string | null; oa_url?: string | null; sources: string[]; source_records: string[]; duplicate_count: number; match?: { score: number; matched: Array<"keyword" | "semantic">; keyword_score?: number | null; semantic_score?: number | null } };
export type CatalogRun = { run_id: string; engine: string; status: "running" | "succeeded" | "failed"; started_at: string; finished_at?: string | null; params: { queries?: string[]; sources?: string[]; max_records?: number }; stats: { etl?: { raw_records?: number; unique_papers?: number; duplicates_merged?: number; duplicate_rate?: number; seconds?: number } }; error?: string | null };
export type CatalogOverview = { papers: number; raw_records?: number | null; duplicates_merged?: number | null; duplicate_rate?: number | null; papers_per_source: Record<string, number>; unique_to_source: Record<string, number>; papers_by_source_count: Record<string, number>; last_run?: CatalogRun | null; running: string[]; index?: { papers: number; embedder: string; faiss: boolean } | null };
export type CatalogAnalytics = {
  paper_count: number;
  publication_trends?: Array<{ year: number; papers: number; citations: number; open_access: number }>;
  topic_trends?: Array<{ topic: string; total: number; by_year: Record<string, number> }>;
  hot_topics?: Array<{ topic: string; status: "emerging" | "growing"; recent: number; prior: number; growth: number; recent_years: number[]; prior_years: number[] }>;
  citation_patterns?: { by_year: Array<{ year: number; median: number; p90: number; max: number; papers: number }>; uncited_share?: number; top_decile_share?: number; most_cited?: Array<{ paper_id: string; title: string; year?: number; citation_count: number }> };
  collaboration?: { top_authors: Array<{ name: string; papers: number; citations: number }>; top_institutions: Array<{ name: string; papers: number }>; median_team_size: number };
  gap_candidates?: Array<{ topics: string[]; papers_a: number; papers_b: number; together: number; expected: number; lift: number; level: "strong" | "moderate" | "limited" }>;
};

export const catalogApi = {
  overview: () => call<CatalogOverview>("/catalog/overview"),
  analytics: () => call<CatalogAnalytics>("/catalog/analytics"),
  search: (query: string, options: { yearFrom?: number; openAccess?: boolean } = {}) => call<{ results: CatalogPaper[]; index_ready: boolean }>(`/catalog/search?q=${q(query)}&limit=20${options.yearFrom ? `&year_from=${options.yearFrom}` : ""}${options.openAccess ? "&open_access=true" : ""}`),
  runs: () => call<{ runs: CatalogRun[] }>("/catalog/runs"),
  startRun: (queries: string[], sources: string[], max_records: number, engine: "local" | "spark") => call<{ run_id: string }>("/catalog/runs", { queries, sources, max_records, engine }),
};
