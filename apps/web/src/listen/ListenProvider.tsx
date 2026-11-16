/**
 * The Listen player: one audio session for the whole app (Part 12A).
 *
 * - Keeps playing while the user moves between tabs (it lives above the routes).
 * - Plays a clean listening script (sections → sentences) built by the server, with an offline fallback.
 * - Two voice tiers: the device voice (free, private, every language the device supports) and self-hosted neural
 *   voices (credits per minute, reserved up front, charged per spoken chunk, refunded on stop).
 * - A language without a voice is never read with a wrong-language voice: the player says so instead.
 * - Saves the exact position (item, section, sentence, speed, voice) on this device and to the account, and
 *   restores it on reload / another device. Lock-screen and headphone keys work through the Media Session API.
 * - Speed changes use the playback rate for neural audio (no regeneration); the device voice restarts the
 *   current sentence at the new rate (the Web Speech API cannot change rate mid-utterance).
 */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { listenApi, localScript, ListenApiError, type ListenScript, type ListenSource, type NeuralVoice, type QueueEntry } from "./listenApi";

export type ListenKind = "paper" | "summary" | "key_points" | "section" | "text" | "answer" | "translation";
export type ListenItem = { id: string; kind: ListenKind; title: string; language: string; source: ListenSource; script: ListenScript; href?: string };
export type ListenStatus = "idle" | "loading" | "playing" | "paused";
export type SleepTimer = { kind: "minutes"; until: number } | { kind: "section"; section: number } | null;
export type ListenNotice = "" | "no_voice" | "limit_reached" | "neural_fallback" | "unavailable" | "nothing";
export type Position = { section: number; sentence: number };
export type PlayRequest = { id: string; kind: ListenKind; title: string; language: string; source: ListenSource; href?: string; start?: Position; resume?: boolean };

export const RATES = [0.75, 1, 1.25, 1.5, 1.75, 2] as const;
const STORAGE_KEY = "resora-listen-state";
const SETTINGS_KEY = "resora-listen-settings";
const CHARS_PER_SECOND = 15; // ~900 characters per minute at 1×
const SKIP_CHARACTERS = CHARS_PER_SECOND * 15; // "15 seconds"

export type ListenSettings = { readReferences: boolean; readCitations: boolean; readCaptions: boolean; autoScroll: boolean; voiceByLanguage: Record<string, string>; rate: number };
const DEFAULT_SETTINGS: ListenSettings = { readReferences: false, readCitations: false, readCaptions: true, autoScroll: true, voiceByLanguage: {}, rate: 1 };

type ListenContextValue = {
  item: ListenItem | null;
  status: ListenStatus;
  position: Position;
  rate: number;
  voice: string;
  voices: NeuralVoice[];
  deviceVoice: boolean;
  notice: ListenNotice;
  sleep: SleepTimer;
  queue: QueueEntry[];
  settings: ListenSettings;
  expanded: boolean;
  estimate: { minutes: number; credits: number } | null;
  play: (request: PlayRequest) => Promise<void>;
  pause: () => void;
  resume: () => void;
  toggle: () => void;
  stop: () => void;
  close: () => void;
  seekSentence: (position: Position) => void;
  skip: (direction: 1 | -1) => void;
  section: (direction: 1 | -1) => void;
  setRate: (rate: number) => void;
  setVoice: (voice: string) => void;
  setSleep: (timer: SleepTimer) => void;
  setExpanded: (open: boolean) => void;
  updateSettings: (patch: Partial<ListenSettings>) => void;
  enqueue: (request: Omit<PlayRequest, "start" | "resume">) => Promise<void>;
  dequeue: (id: string) => Promise<void>;
  clearNotice: () => void;
  progress: { done: number; total: number; secondsLeft: number; markers: number[] };
  currentSentence: string;
};

const ListenContext = createContext<ListenContextValue | null>(null);

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? ({ ...fallback, ...JSON.parse(raw) } as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: the player still works for this visit */
  }
}

/** Device voice for a language: exact locale > same language > none (never a wrong-language voice). */
export function pickDeviceVoice(language: string): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  const wanted = language.toLowerCase().replace("_", "-");
  const base = wanted.split("-")[0];
  const normalized = (voice: SpeechSynthesisVoice) => voice.lang.toLowerCase().replace("_", "-");
  return voices.find((voice) => normalized(voice) === wanted) || voices.find((voice) => normalized(voice).split("-")[0] === base) || null;
}

function flatIndex(script: ListenScript, position: Position) {
  let index = 0;
  for (let section = 0; section < position.section && section < script.sections.length; section += 1) index += script.sections[section].sentences.length;
  return index + position.sentence;
}

function fromFlat(script: ListenScript, index: number): Position | null {
  let remaining = index;
  for (let section = 0; section < script.sections.length; section += 1) {
    const count = script.sections[section].sentences.length;
    if (remaining < count) return { section, sentence: Math.max(0, remaining) };
    remaining -= count;
  }
  return null;
}

function sentenceAt(script: ListenScript | undefined, position: Position) {
  return script?.sections[position.section]?.sentences[position.sentence] || "";
}

export function ListenProvider({ language, children }: { language: string; children: ReactNode }) {
  const saved = useMemo(() => (typeof window === "undefined" ? null : readJson<{ item: ListenItem | null; position: Position; voice: string } | null>(STORAGE_KEY, null)), []);
  const [settings, setSettings] = useState<ListenSettings>(() => (typeof window === "undefined" ? DEFAULT_SETTINGS : readJson(SETTINGS_KEY, DEFAULT_SETTINGS)));
  const [item, setItem] = useState<ListenItem | null>(saved?.item && saved.item.script?.sections?.length ? saved.item : null);
  const [position, setPosition] = useState<Position>(saved?.position || { section: 0, sentence: 0 });
  const [status, setStatus] = useState<ListenStatus>("idle");
  const [rate, setRateState] = useState<number>(settings.rate || 1);
  const [voice, setVoiceState] = useState<string>(saved?.voice || "device");
  const [voices, setVoices] = useState<NeuralVoice[]>([]);
  const [notice, setNotice] = useState<ListenNotice>("");
  const [sleep, setSleepState] = useState<SleepTimer>(null);
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [estimate, setEstimate] = useState<{ minutes: number; credits: number } | null>(null);
  const [deviceVoiceReady, setDeviceVoiceReady] = useState(false);

  // Mutable playback state (callbacks from speech/audio events read these, not stale React state).
  const live = useRef({ item, position, status, rate, voice, token: 0, session: "" as string, audio: null as HTMLAudioElement | null, prefetch: new Map<number, Promise<string>>(), sleep: null as SleepTimer });
  // Keep the mutable mirror in sync after every render (event callbacks read it later).
  useLayoutEffect(() => {
    live.current.item = item;
    live.current.rate = rate;
    live.current.voice = voice;
    live.current.sleep = sleep;
    live.current.status = status;
  });

  const supported = typeof window !== "undefined" && ("speechSynthesis" in window || typeof Audio !== "undefined");

  // -------------------------------------------------------------------------------------------- persistence
  const persistTimer = useRef<number | undefined>(undefined);
  const persist = useCallback((next: Position) => {
    const current = live.current.item;
    if (!current) return;
    writeJson(STORAGE_KEY, { item: current, position: next, voice: live.current.voice });
    window.clearTimeout(persistTimer.current);
    persistTimer.current = window.setTimeout(() => {
      const total = current.script.sections.reduce((sum, section) => sum + section.sentences.length, 0) || 1;
      listenApi.saveProgress({ item_id: current.id, kind: current.kind, title: current.title.slice(0, 300), language: current.language, section: next.section, sentence: next.sentence, total_sections: current.script.sections.length, percent: Math.min(1, flatIndex(current.script, next) / total), voice: live.current.voice, rate: live.current.rate }).catch(() => undefined);
    }, 2500);
  }, []);

  useEffect(() => writeJson(SETTINGS_KEY, { ...settings, rate }), [settings, rate]);

  // The queue is loaded when the player is first used (not on every page view).
  const queueLoaded = useRef(false);
  useEffect(() => {
    if (queueLoaded.current || (!item && !expanded)) return;
    queueLoaded.current = true;
    listenApi.queue().then(({ items }) => setQueue(Array.isArray(items) ? items : [])).catch(() => undefined);
  }, [expanded, item]);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const warm = () => setDeviceVoiceReady(window.speechSynthesis.getVoices().length > 0);
    warm();
    window.speechSynthesis.addEventListener?.("voiceschanged", warm);
    return () => window.speechSynthesis.removeEventListener?.("voiceschanged", warm);
  }, []);

  // Neural voices for the item's language (a voice is offered only in its own language).
  useEffect(() => {
    if (!item) return;
    const target = item.language || language;
    let cancelled = false;
    listenApi.voices(target).then((listing) => { if (!cancelled) setVoices(listing?.neural_available && Array.isArray(listing.voices) ? listing.voices : []); }).catch(() => { if (!cancelled) setVoices([]); });
    return () => { cancelled = true; };
  }, [item, language]);

  // -------------------------------------------------------------------------------------------- engines
  const haltEngines = useCallback(() => {
    live.current.token += 1;
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    const audio = live.current.audio;
    if (audio) {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
    }
  }, []);

  const finishSession = useCallback(() => {
    const session = live.current.session;
    live.current.session = "";
    live.current.prefetch.forEach((promise) => promise.then((url) => URL.revokeObjectURL(url)).catch(() => undefined));
    live.current.prefetch.clear();
    if (session) listenApi.finish(session).catch(() => undefined);
  }, []);

  const advanceRef = useRef<(token: number) => void>(() => undefined);
  const speakRef = useRef<(position: Position) => void>(() => undefined);

  const neuralUrl = useCallback((index: number): Promise<string> => {
    const { item: current, session } = live.current;
    const cached = live.current.prefetch.get(index);
    if (cached) return cached;
    const position = current ? fromFlat(current.script, index) : null;
    if (!current || !position || !session) return Promise.reject(new ListenApiError("nothing", 0));
    const promise = listenApi.speak(session, sentenceAt(current.script, position)).then((blob) => URL.createObjectURL(blob));
    live.current.prefetch.set(index, promise);
    promise.catch(() => live.current.prefetch.delete(index));
    return promise;
  }, []);

  const speakDevice = useCallback((target: Position, token: number) => {
    const current = live.current.item;
    if (!current) return;
    const deviceVoice = pickDeviceVoice(current.language);
    if (!deviceVoice && !(current.language.startsWith("en") && window.speechSynthesis.getVoices().length === 0)) {
      setStatus("paused");
      setNotice("no_voice");
      return;
    }
    const utterance = new SpeechSynthesisUtterance(sentenceAt(current.script, target));
    utterance.lang = deviceVoice?.lang || current.language;
    try {
      if (deviceVoice) utterance.voice = deviceVoice;
    } catch {
      /* some engines expose voices that cannot be assigned; the language tag still selects a matching voice */
    }
    utterance.rate = live.current.rate;
    utterance.onend = () => advanceRef.current(token);
    utterance.onerror = (event) => {
      if ((event as SpeechSynthesisErrorEvent).error === "interrupted" || (event as SpeechSynthesisErrorEvent).error === "canceled") return;
      advanceRef.current(token);
    };
    window.speechSynthesis.speak(utterance);
  }, []);

  const speakNeural = useCallback((target: Position, token: number) => {
    const current = live.current.item;
    if (!current) return;
    const index = flatIndex(current.script, target);
    neuralUrl(index)
      .then((url) => {
        if (token !== live.current.token) return;
        const audio = live.current.audio || new Audio();
        live.current.audio = audio;
        audio.src = url;
        audio.playbackRate = live.current.rate;
        audio.onended = () => {
          URL.revokeObjectURL(url);
          live.current.prefetch.delete(index);
          advanceRef.current(token);
        };
        audio.onerror = () => advanceRef.current(token);
        void audio.play().catch(() => undefined);
        neuralUrl(index + 1).catch(() => undefined); // keep two chunks buffered ahead: no gaps between sentences
        neuralUrl(index + 2).catch(() => undefined);
      })
      .catch((error: unknown) => {
        if (token !== live.current.token) return;
        if (error instanceof ListenApiError && (error.code === "session_exhausted" || error.code === "limit_reached")) {
          setStatus("paused");
          setNotice("limit_reached");
          return;
        }
        // Neural voice unavailable: continue with the device voice for the rest of this listen.
        finishSession();
        live.current.voice = "device";
        setVoiceState("device");
        setNotice("neural_fallback");
        speakDevice(target, token);
      });
  }, [finishSession, neuralUrl, speakDevice]);

  const speakImpl = (target: Position) => {
    const current = live.current.item;
    if (!current) return;
    haltEngines();
    const token = live.current.token;
    live.current.position = target;
    setPosition(target);
    persist(target);
    setStatus("playing");
    if (live.current.voice.startsWith("neural:") && live.current.session) speakNeural(target, token);
    else speakDevice(target, token);
  };

  const advanceImpl = (token: number) => {
    if (token !== live.current.token) return;
    const current = live.current.item;
    if (!current) return;
    const { section, sentence } = live.current.position;
    const sleepTimer = live.current.sleep;
    if (sleepTimer?.kind === "minutes" && Date.now() >= sleepTimer.until) {
      setSleepState(null);
      setStatus("paused");
      return;
    }
    const nextSentence = sentence + 1 < current.script.sections[section].sentences.length ? { section, sentence: sentence + 1 } : section + 1 < current.script.sections.length ? { section: section + 1, sentence: 0 } : null;
    if (sleepTimer?.kind === "section" && (!nextSentence || nextSentence.section !== sleepTimer.section)) {
      setSleepState(null);
      setStatus("paused");
      if (nextSentence) {
        live.current.position = nextSentence;
        setPosition(nextSentence);
        persist(nextSentence);
      }
      return;
    }
    if (nextSentence) {
      speakRef.current(nextSentence);
      return;
    }
    // Finished: mark complete, then play the next queued item.
    finishSession();
    setStatus("idle");
    const lastSection = current.script.sections[current.script.sections.length - 1];
    persist({ section: current.script.sections.length - 1, sentence: Math.max(0, (lastSection?.sentences.length || 1) - 1) });
    const next = queueRef.current.find((entry) => entry.item_id !== current.id);
    if (next) {
      void listenApi.dequeue(next.id).then(({ items }) => setQueue(Array.isArray(items) ? items : [])).catch(() => undefined);
      void playRef.current({ id: next.item_id, kind: (next.kind as ListenKind) || "paper", title: next.title, language: next.payload.language || current.language, source: next.payload });
    }
  };

  const queueRef = useRef(queue);

  // -------------------------------------------------------------------------------------------- actions
  const startNeuralSession = useCallback(async (script: ListenScript, from: Position) => {
    finishSession();
    if (!live.current.voice.startsWith("neural:")) return true;
    const remaining = script.sections.slice(from.section).reduce((sum, section, index) => sum + section.sentences.slice(index === 0 ? from.sentence : 0).reduce((total, sentence) => total + sentence.length, 0), 0);
    try {
      const session = await listenApi.start(live.current.voice, script.language, Math.max(1, remaining));
      live.current.session = session.session_id;
      return true;
    } catch (error) {
      if (error instanceof ListenApiError && error.code === "limit_reached") {
        setNotice("limit_reached");
        return false;
      }
      live.current.voice = "device";
      setVoiceState("device");
      setNotice("neural_fallback");
      return true;
    }
  }, [finishSession]);

  const play = useCallback(async (request: PlayRequest) => {
    haltEngines();
    setNotice("");
    setStatus("loading");
    let script: ListenScript;
    try {
      script = await listenApi.script({ ...request.source, kind: request.kind, language: request.language, title: request.kind === "paper" || request.kind === "translation" ? request.title : undefined, read_references: settings.readReferences, read_citations: settings.readCitations, read_captions: settings.readCaptions });
    } catch {
      script = localScript(request.source.texts || [], request.language, "");
    }
    if (!script.sections.length) {
      setStatus("idle");
      setNotice("nothing");
      return;
    }
    const next: ListenItem = { id: request.id, kind: request.kind, title: request.title, language: script.language || request.language, source: request.source, script, href: request.href };
    let start = request.start || { section: 0, sentence: 0 };
    if (request.resume) {
      const local = readJson<{ item: ListenItem | null; position: Position } | null>(STORAGE_KEY, null);
      if (local?.item?.id === request.id) start = local.position;
      else {
        const remote = await listenApi.progress(request.id).then(({ items }) => items[0]).catch(() => undefined);
        if (remote && remote.percent < 0.98) start = { section: remote.section, sentence: remote.sentence };
      }
    }
    if (!sentenceAt(script, start)) start = { section: 0, sentence: 0 };
    const preferred = settings.voiceByLanguage[next.language.split("-")[0]];
    if (preferred && (preferred === "device" || voices.some((option) => option.id === preferred))) {
      live.current.voice = preferred;
      setVoiceState(preferred);
    } else if (live.current.voice.startsWith("neural:") && !voices.some((option) => option.id === live.current.voice && option.language === next.language.split("-")[0])) {
      live.current.voice = "device"; // never keep a voice of another language
      setVoiceState("device");
    }
    live.current.item = next;
    setItem(next);
    const ok = await startNeuralSession(script, start);
    if (!ok) {
      setStatus("paused");
      live.current.position = start;
      setPosition(start);
      return;
    }
    speakRef.current(start);
  }, [haltEngines, settings, startNeuralSession, voices]);

  const playRef = useRef(play);
  useLayoutEffect(() => {
    speakRef.current = speakImpl;
    advanceRef.current = advanceImpl;
    queueRef.current = queue;
    playRef.current = play;
  });

  const pause = useCallback(() => {
    haltEngines();
    setStatus((current) => (current === "idle" ? current : "paused"));
  }, [haltEngines]);

  const resume = useCallback(() => {
    const current = live.current.item;
    if (!current) return;
    setNotice("");
    if (live.current.voice.startsWith("neural:") && !live.current.session) {
      void startNeuralSession(current.script, live.current.position).then((ok) => { if (ok) speakRef.current(live.current.position); });
      return;
    }
    speakRef.current(live.current.position);
  }, [startNeuralSession]);

  const toggle = useCallback(() => {
    if (live.current.status === "playing") pause();
    else resume();
  }, [pause, resume]);

  const stop = useCallback(() => {
    haltEngines();
    finishSession();
    setStatus("paused");
  }, [finishSession, haltEngines]);

  const close = useCallback(() => {
    haltEngines();
    finishSession();
    setStatus("idle");
    setItem(null);
    setExpanded(false);
    setSleepState(null);
    writeJson(STORAGE_KEY, null);
  }, [finishSession, haltEngines]);

  const seekSentence = useCallback((target: Position) => {
    const current = live.current.item;
    if (!current || !sentenceAt(current.script, target)) return;
    if (live.current.status === "playing") speakRef.current(target);
    else {
      live.current.position = target;
      setPosition(target);
      persist(target);
    }
  }, [persist]);

  const skip = useCallback((direction: 1 | -1) => {
    const current = live.current.item;
    if (!current) return;
    let index = flatIndex(current.script, live.current.position);
    let moved = 0;
    while (moved < SKIP_CHARACTERS) {
      const nextIndex = index + direction;
      const target = fromFlat(current.script, nextIndex);
      if (!target || nextIndex < 0) break;
      index = nextIndex;
      moved += sentenceAt(current.script, target).length || 1;
    }
    const target = fromFlat(current.script, index);
    if (target) seekSentence(target);
  }, [seekSentence]);

  const section = useCallback((direction: 1 | -1) => {
    const current = live.current.item;
    if (!current) return;
    const { section: at, sentence } = live.current.position;
    // "Previous" restarts the current section unless we are at its very beginning.
    const target = direction < 0 && sentence > 0 ? at : Math.min(current.script.sections.length - 1, Math.max(0, at + direction));
    seekSentence({ section: target, sentence: 0 });
  }, [seekSentence]);

  const setRate = useCallback((next: number) => {
    const clamped = RATES.reduce((best, option) => (Math.abs(option - next) < Math.abs(best - next) ? option : best), 1 as number);
    live.current.rate = clamped;
    setRateState(clamped);
    if (live.current.audio && live.current.voice.startsWith("neural:")) live.current.audio.playbackRate = clamped; // no regeneration
    else if (live.current.status === "playing") speakRef.current(live.current.position);
  }, []);

  const setVoice = useCallback((next: string) => {
    const current = live.current.item;
    live.current.voice = next;
    setVoiceState(next);
    if (current) setSettings((value) => ({ ...value, voiceByLanguage: { ...value.voiceByLanguage, [current.language.split("-")[0]]: next } }));
    if (current && live.current.status === "playing") {
      haltEngines();
      void startNeuralSession(current.script, live.current.position).then((ok) => { if (ok) speakRef.current(live.current.position); });
    }
  }, [haltEngines, startNeuralSession]);

  const setSleep = useCallback((timer: SleepTimer) => setSleepState(timer), []);
  const updateSettings = useCallback((patch: Partial<ListenSettings>) => setSettings((value) => ({ ...value, ...patch })), []);

  const enqueue = useCallback(async (request: Omit<PlayRequest, "start" | "resume">) => {
    const payload = { ...request.source, language: request.language };
    try {
      const { items } = await listenApi.enqueue({ item_id: request.id, kind: request.kind, title: request.title, payload });
      if (!Array.isArray(items)) throw new Error("queue");
      setQueue(items);
    } catch {
      setQueue((items) => (items.some((entry) => entry.item_id === request.id) ? items : [...items, { id: `local-${request.id}`, item_id: request.id, kind: request.kind, title: request.title, payload, position: items.length, added_at: new Date().toISOString() }]));
    }
  }, []);

  const dequeue = useCallback(async (id: string) => {
    setQueue((items) => items.filter((entry) => entry.id !== id));
    await listenApi.dequeue(id).then(({ items }) => setQueue(Array.isArray(items) ? items : [])).catch(() => undefined);
  }, []);

  // Credits estimate for a neural voice (shown before / while listening).
  useEffect(() => {
    if (!item || !voice.startsWith("neural:")) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    listenApi.estimate(item.script.characters, item.language, voice).then((quote) => { if (!cancelled) setEstimate({ minutes: quote.minutes, credits: quote.credits }); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [item, voice]);

  // -------------------------------------------------------------------------------------------- Media Session, layout, cleanup
  const currentSentence = sentenceAt(item?.script, position);
  const sectionTitle = item?.script.sections[position.section]?.title || "";

  useEffect(() => {
    if (typeof navigator === "undefined" || !("mediaSession" in navigator)) return;
    const session = navigator.mediaSession;
    if (!item) {
      session.metadata = null;
      return;
    }
    try {
      session.metadata = new MediaMetadata({ title: item.title, artist: sectionTitle || "Resora", album: "Resora", artwork: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }] });
      session.playbackState = status === "playing" ? "playing" : "paused";
      const handlers: Array<[MediaSessionAction, MediaSessionActionHandler]> = [
        ["play", () => resume()], ["pause", () => pause()], ["stop", () => stop()],
        ["seekbackward", () => skip(-1)], ["seekforward", () => skip(1)],
        ["previoustrack", () => section(-1)], ["nexttrack", () => section(1)],
      ];
      for (const [action, handler] of handlers) {
        try {
          session.setActionHandler(action, handler);
        } catch {
          /* action not supported by this browser */
        }
      }
    } catch {
      /* Media Session unavailable */
    }
  }, [item, pause, resume, section, sectionTitle, skip, status, stop]);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (item) document.body.dataset.listening = "1";
    else delete document.body.dataset.listening;
  }, [item]);

  useEffect(() => () => {
    haltEngines();
  }, [haltEngines]);

  useEffect(() => {
    const onUnload = () => {
      const session = live.current.session;
      if (session && navigator.sendBeacon) navigator.sendBeacon(`${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1"}/listen/sessions/${session}/finish`);
    };
    window.addEventListener("pagehide", onUnload);
    return () => window.removeEventListener("pagehide", onUnload);
  }, []);

  // Sleep timer (minutes) also stops playback when nothing is being advanced (e.g. a long sentence).
  useEffect(() => {
    if (sleep?.kind !== "minutes") return;
    const timer = window.setTimeout(() => {
      pause();
      setSleepState(null);
    }, Math.max(0, sleep.until - Date.now()));
    return () => window.clearTimeout(timer);
  }, [pause, sleep]);

  const progress = useMemo(() => {
    if (!item) return { done: 0, total: 0, secondsLeft: 0, markers: [] as number[] };
    let total = 0;
    let done = 0;
    const markers: number[] = [];
    item.script.sections.forEach((entry, sectionIndex) => {
      markers.push(total);
      entry.sentences.forEach((sentence, sentenceIndex) => {
        if (sectionIndex < position.section || (sectionIndex === position.section && sentenceIndex < position.sentence)) done += sentence.length;
        total += sentence.length;
      });
    });
    return { done, total, secondsLeft: Math.round((total - done) / (CHARS_PER_SECOND * rate)), markers: markers.map((value) => (total ? value / total : 0)) };
  }, [item, position, rate]);

  const value = useMemo<ListenContextValue>(() => ({
    item, status, position, rate, voice, voices, deviceVoice: supported && deviceVoiceReady, notice, sleep, queue, settings, expanded, estimate,
    play, pause, resume, toggle, stop, close, seekSentence, skip, section, setRate, setVoice, setSleep, setExpanded, updateSettings, enqueue, dequeue,
    clearNotice: () => setNotice(""), progress, currentSentence,
  }), [item, status, position, rate, voice, voices, supported, deviceVoiceReady, notice, sleep, queue, settings, expanded, estimate, play, pause, resume, toggle, stop, close, seekSentence, skip, section, setRate, setVoice, setSleep, updateSettings, enqueue, dequeue, progress, currentSentence]);

  return <ListenContext.Provider value={value}>{children}</ListenContext.Provider>;
}

export function useListen() {
  const context = useContext(ListenContext);
  if (!context) throw new Error("useListen must be used inside <ListenProvider>");
  return context;
}

/** Same as useListen but returns null outside the provider (components used in isolation, tests). */
export function useOptionalListen() {
  return useContext(ListenContext);
}
