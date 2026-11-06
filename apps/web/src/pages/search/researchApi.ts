/** API client for Research with Resora, Ask about results, identifier lookup, credits and saved searches. */

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

export type ResearchStepId = "understand" | "search" | "read" | "answer";
export type StepStatus = "pending" | "active" | "done";
export type EvidenceLevel = "strong" | "moderate" | "limited" | "hypothesis";

export type ResearchFinding = { text: string; paper_ids: string[] };
export type ResearchAnswer = {
  answer: string;
  evidence_ids: string[];
  approaches: Array<{ label: string; paper_ids: string[] }>;
  emerging: ResearchFinding[];
  conflicting: ResearchFinding[];
  gaps: Array<ResearchFinding & { evidence_level: EvidenceLevel }>;
  insufficient_evidence: boolean;
  language: string;
  credits_used: number;
};

export type QueryUnderstanding = {
  original_query?: string;
  query?: string;
  year_from?: number | null;
  open_access_only?: boolean;
  author?: string | null;
  reviews_only?: boolean;
};

export type CreditEstimate = { research_credits: number; ask_credits: number };

export type SavedSearch = {
  id: string;
  name: string;
  query: string;
  alert_enabled: boolean;
  alert_cadence: string;
  new_match_count?: number;
};

export type ResearchRequestBody = {
  query: string;
  language: string;
  year_from: number | null;
  year_to: number | null;
  open_access_only: boolean;
  peer_reviewed_only: boolean;
  preprint_only: boolean;
  include_retracted: boolean;
  study_type: string | null;
  paper_language: string | null;
  min_citations: number;
  author: string | null;
  venue: string | null;
};

export type ResearchPapersEvent<P> = {
  papers: P[];
  total: number;
  query_understanding?: QueryUnderstanding;
  translation_retry_ids?: string[];
};

type Handlers<P> = {
  onStep: (step: ResearchStepId, status: StepStatus) => void;
  onPapers: (event: ResearchPapersEvent<P>) => void;
  onAnswer: (answer: ResearchAnswer) => void;
  onAnswerError: () => void;
};

/** Read a server-sent-event response and call `onEvent` for every complete frame. */
export async function readEventStream(response: Response, onEvent: (event: string, data: unknown) => void) {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  const consume = (frame: string) => {
    const lines = frame.split("\n");
    const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
    const data = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
    if (!event || !data) return;
    try {
      onEvent(event, JSON.parse(data));
    } catch (error) {
      if (error instanceof SyntaxError) return;
      throw error;
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    pending += decoder.decode(value, { stream: !done });
    const frames = pending.split("\n\n");
    pending = frames.pop() || "";
    frames.forEach(consume);
    if (done) break;
  }
  if (pending.trim()) consume(pending);
}

export async function streamResearch<P>(body: ResearchRequestBody, handlers: Handlers<P>, signal: AbortSignal) {
  const response = await fetch(`${apiBaseUrl}/search/research/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new Error(`research ${response.status}`);
  let failed = false;
  let limit: UsageLimit | null = null;
  await readEventStream(response, (event, data) => {
    const payload = data as Record<string, unknown>;
    if (event === "step") handlers.onStep(payload.step as ResearchStepId, payload.status as StepStatus);
    else if (event === "papers") handlers.onPapers(payload as unknown as ResearchPapersEvent<P>);
    else if (event === "answer") handlers.onAnswer(payload as unknown as ResearchAnswer);
    else if (event === "answer_error") handlers.onAnswerError();
    else if (event === "limit") limit = payload as unknown as UsageLimit;
    else if (event === "error") failed = true;
  });
  if (limit) throw new CreditLimitError(limit);
  if (failed) throw new Error("research stream error");
}

export async function askAboutResults(body: {
  question: string;
  language: string;
  papers: Array<{ paper_id: string; title: string; abstract?: string | null; year?: number | null; venue?: string | null }>;
}, signal?: AbortSignal): Promise<ResearchAnswer> {
  const response = await fetch(`${apiBaseUrl}/search/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (response.status === 402) {
    const body = (await response.json().catch(() => ({}))) as { detail?: UsageLimit };
    if (body.detail?.scope) throw new CreditLimitError(body.detail);
  }
  if (!response.ok) throw new Error(`ask ${response.status}`);
  return (await response.json()) as ResearchAnswer;
}

const IDENTIFIER = /^(?:(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)?10\.\d{4,9}\/\S+|(?:arxiv:\s*|https?:\/\/arxiv\.org\/(?:abs|pdf)\/)?\d{4}\.\d{4,5}(?:v\d+)?)$/i;

export function looksLikeIdentifier(value: string) {
  return IDENTIFIER.test(value.trim());
}

export async function resolveIdentifier<P>(value: string, language: string, signal?: AbortSignal): Promise<P | null> {
  const params = new URLSearchParams({ q: value.trim(), language });
  const response = await fetch(`${apiBaseUrl}/search/resolve?${params.toString()}`, { signal });
  if (!response.ok) return null;
  const data = (await response.json()) as { paper?: P | null };
  return data.paper || null;
}

export async function fetchCreditEstimate(): Promise<CreditEstimate | null> {
  try {
    const response = await fetch(`${apiBaseUrl}/search/research/estimate`);
    if (!response.ok) return null;
    const data = (await response.json()) as Partial<CreditEstimate> | null;
    // Show a cost only when the server sent real numbers.
    return data && Number.isFinite(data.research_credits) && Number.isFinite(data.ask_credits)
      ? { research_credits: Number(data.research_credits), ask_credits: Number(data.ask_credits) }
      : null;
  } catch {
    return null;
  }
}

export async function fetchSavedSearches(): Promise<SavedSearch[]> {
  try {
    const response = await fetch(`${apiBaseUrl}/search/saved`);
    if (!response.ok) return [];
    const items = (await response.json()) as SavedSearch[];
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

/* ------------------------------------------------------------------ usage limits */

export type UsageLimit = { code?: string; scope: "session" | "week" | "month"; resets_at: string };
export type UsageWindow = { scope: "session" | "week" | "month"; used: number; limit: number; remaining: number; percent: number; resets_at: string };
export type Usage = { plan: string; windows: UsageWindow[] };

export class CreditLimitError extends Error {
  limit: UsageLimit;
  constructor(limit: UsageLimit) {
    super(`${limit.scope} limit reached`);
    this.name = "CreditLimitError";
    this.limit = limit;
  }
}

export async function fetchUsage(): Promise<Usage | null> {
  try {
    const response = await fetch(`${apiBaseUrl}/search/usage`);
    if (!response.ok) return null;
    const data = (await response.json()) as Partial<Usage> | null;
    return data && Array.isArray(data.windows) ? { plan: String(data.plan || "free"), windows: data.windows } : null;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ saved searches */

export async function updateSavedSearch(id: string, changes: { name?: string; alert_enabled?: boolean; alert_cadence?: "daily" | "weekly" }): Promise<SavedSearch> {
  const response = await fetch(`${apiBaseUrl}/search/saved/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  if (!response.ok) throw new Error(`saved ${response.status}`);
  return (await response.json()) as SavedSearch;
}

export async function deleteSavedSearch(id: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/search/saved/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok && response.status !== 404) throw new Error(`saved ${response.status}`);
}

/* ------------------------------------------------------------------ researchers & institutions */

export type EntitySummary = { id: string; kind: "researcher" | "institution"; name: string; subtitle?: string | null; works_count: number; cited_by_count: number };
export type EntityMatches = { researchers: EntitySummary[]; institutions: EntitySummary[] };
export type WorkItem = { title: string; translated_title?: string | null; year?: number | null; venue?: string | null; citation_count: number; doi?: string | null; url?: string | null; is_open_access: boolean };
export type YearCount = { year: number; works: number; citations: number };
export type Topic = { name: string; translated_name?: string | null; count: number };
export type PersonLink = { id?: string | null; name: string; subtitle?: string | null; count: number };
export type ResearcherProfile = {
  id: string; name: string; affiliations: string[]; orcid?: string | null; works_count: number; cited_by_count: number; h_index?: number | null;
  topics: Topic[]; timeline: YearCount[]; top_works: WorkItem[]; recent_works: WorkItem[]; collaborators: PersonLink[];
};
export type InstitutionProfile = {
  id: string; name: string; country?: string | null; type?: string | null; homepage?: string | null; works_count: number; cited_by_count: number;
  topics: Topic[]; timeline: YearCount[]; top_researchers: PersonLink[]; top_works: WorkItem[];
};

export async function findEntities(query: string, signal?: AbortSignal): Promise<EntityMatches> {
  try {
    const response = await fetch(`${apiBaseUrl}/search/entities?${new URLSearchParams({ q: query.trim() })}`, { signal });
    if (!response.ok) return { researchers: [], institutions: [] };
    const data = (await response.json()) as Partial<EntityMatches>;
    return { researchers: data.researchers || [], institutions: data.institutions || [] };
  } catch {
    return { researchers: [], institutions: [] };
  }
}

export class ProfileNotFound extends Error {}

export async function fetchProfile<T>(kind: "researchers" | "institutions", id: string, language: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}/search/${kind}/${encodeURIComponent(id)}?${new URLSearchParams({ language })}`, { signal });
  if (response.status === 404) throw new ProfileNotFound(id);
  if (!response.ok) throw new Error(`profile ${response.status}`);
  return (await response.json()) as T;
}