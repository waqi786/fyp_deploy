/**
 * Adapter that gives the Reader the same small API it used before (speak / pause / resume / stop / rate), backed by
 * the global Listen player, so listening continues when the user leaves the Reader and resumes on any device.
 */
import { useCallback, useMemo } from "react";
import { pickDeviceVoice, RATES, useListen, type ListenKind } from "./ListenProvider";

export type SpeechState = "idle" | "speaking" | "paused";

export function useReaderListen(doc: { id: string; title: string; authors: string[] } | null) {
  const listen = useListen();
  const prefix = doc ? `${doc.id}:` : "";
  const activeId = listen.item && doc && listen.item.id.startsWith(prefix) ? listen.item.id.slice(prefix.length) : null;
  const state: SpeechState = listen.status === "playing" || listen.status === "loading" ? "speaking" : listen.status === "paused" ? "paused" : "idle";

  const speak = useCallback((id: string, texts: string[], language: string) => {
    if (!doc) return false;
    // Never read with a wrong-language voice: without a device or neural voice for this language, say so.
    if (!pickDeviceVoice(language) && !language.startsWith("en") && !listen.voices.some((voice) => voice.language === language.split("-")[0])) return false;
    const kind: ListenKind = id === "paper" ? "paper" : id === "translation" ? "translation" : id === "key_points" ? "key_points" : id === "selection" ? "text" : id.startsWith("answer") ? "answer" : "summary";
    void listen.play({
      id: `${prefix}${id}`, kind, title: doc.title, language, href: `/reader/${doc.id}`, resume: kind === "paper" || kind === "translation",
      source: { texts, authors: kind === "paper" ? doc.authors : undefined, translated_from: kind === "translation" ? "en" : undefined },
    });
    return true;
  }, [doc, listen, prefix]);

  const setRate = useCallback((next: number | ((value: number) => number)) => {
    const value = typeof next === "function" ? next(listen.rate) : next;
    listen.setRate(value > RATES[RATES.length - 1] ? RATES[0] : value);
  }, [listen]);

  return useMemo(() => ({
    supported: typeof window !== "undefined" && ("speechSynthesis" in window || listen.voices.length > 0),
    state: activeId ? state : ("idle" as SpeechState),
    activeId,
    rate: listen.rate,
    setRate,
    speak,
    pause: listen.pause,
    resume: listen.resume,
    stop: listen.close,
    listen,
  }), [activeId, listen, setRate, speak, state]);
}
