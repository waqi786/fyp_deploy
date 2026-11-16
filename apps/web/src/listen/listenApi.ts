/** Listen API client: listening scripts, voices, neural speech sessions, resume positions and the queue. */
import { comparisonHeaders } from "../pages/compare/compareApi";

export const listenApiBase = `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1"}/listen`;

export type ScriptSection = { title: string; sentences: string[]; pages: number[] };
export type ListenScript = { language: string; sections: ScriptSection[]; characters: number; minutes: number; kind?: string };
export type NeuralVoice = { id: string; name: string; language: string; locale: string; gender: string; tier: "neural"; default: boolean };
export type VoiceListing = { language: string; neural_available: boolean; voices: NeuralVoice[]; browser: { id: "browser"; tier: "browser" } };
export type Estimate = { minutes: number; credits: number; tier: "browser" | "neural" };
export type SavedProgress = { item_id: string; kind: string; title: string; language: string; section: number; sentence: number; total_sections: number; percent: number; voice?: string | null; rate: number; updated_at: string };
export type QueueEntry = { id: string; item_id: string; kind: string; title: string; payload: ListenSource & { language?: string }; position: number; added_at: string };

/** What to read: a Reader document (the server builds the script from its pages) or plain texts. */
export type ListenSource = { document_id?: string; texts?: string[]; authors?: string[]; translated_from?: string };

export class ListenApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, status: number) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

async function call<T>(path: string, body?: unknown, method = body === undefined ? "GET" : "POST"): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${listenApiBase}${path}`, { method, headers: { ...comparisonHeaders(), ...(body !== undefined ? { "Content-Type": "application/json" } : {}) }, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new ListenApiError("network", 0);
  }
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
    throw new ListenApiError(detail?.detail?.code || (response.status === 402 ? "limit_reached" : "unavailable"), response.status);
  }
  return (await response.json()) as T;
}

export const listenApi = {
  script: (body: ListenSource & { kind: string; language?: string; title?: string; read_references?: boolean; read_citations?: boolean; read_captions?: boolean }) => call<ListenScript>("/script", body),
  voices: (language: string) => call<VoiceListing>(`/voices?language=${encodeURIComponent(language)}`),
  estimate: (characters: number, language: string, voice: string) => call<Estimate>("/estimate", { characters, language, voice }),
  start: (voice: string, language: string, characters: number) => call<{ session_id: string } & Estimate>("/sessions", { voice, language, characters }),
  finish: (sessionId: string) => call<{ charged: number; status: string }>(`/sessions/${encodeURIComponent(sessionId)}/finish`, {}),
  async speak(sessionId: string, text: string, signal?: AbortSignal): Promise<Blob> {
    const response = await fetch(`${listenApiBase}/sessions/${encodeURIComponent(sessionId)}/speak`, { method: "POST", headers: { ...comparisonHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ text }), signal });
    if (!response.ok) {
      const detail = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
      throw new ListenApiError(detail?.detail?.code || "unavailable", response.status);
    }
    return response.blob();
  },
  progress: (itemId?: string) => call<{ items: SavedProgress[] }>(`/progress${itemId ? `?item_id=${encodeURIComponent(itemId)}` : ""}`),
  saveProgress: (body: Omit<SavedProgress, "updated_at">) => call<SavedProgress>("/progress", body, "PUT"),
  queue: () => call<{ items: QueueEntry[] }>("/queue"),
  enqueue: (body: { item_id: string; kind: string; title: string; payload: ListenSource & { language?: string } }) => call<{ items: QueueEntry[] }>("/queue", body),
  dequeue: (id: string) => call<{ items: QueueEntry[] }>(`/queue/${encodeURIComponent(id)}`, undefined, "DELETE"),
};

/** Offline fallback when the script service cannot be reached: one section, sentences split per script. */
export function localScript(texts: string[], language: string, title = ""): ListenScript {
  const sentences = texts
    .flatMap((text) => text.replace(/\s+/g, " ").match(/[^.!?。！？؟۔।]+[.!?。！？؟۔।]*\s*/g) || [text])
    .map((sentence) => sentence.replace(/\s?\[\d{1,3}(?:[,–-]\s?\d{1,3})*\]/g, "").trim())
    .filter((sentence) => sentence.replace(/\W/g, "").length >= 2);
  const characters = sentences.reduce((sum, sentence) => sum + sentence.length, 0);
  return { language, sections: sentences.length ? [{ title, sentences, pages: [] }] : [], characters, minutes: Math.round((characters / 900) * 10) / 10 };
}
