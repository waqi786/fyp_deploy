/** "Listen": reads text aloud with the browser's free speech synthesis, in any language the device has a voice for. */
import { useCallback, useEffect, useRef, useState } from "react";

export type SpeechState = "idle" | "speaking" | "paused";

/** Browsers cut very long utterances: speak sentence-sized pieces (≤ 220 characters). */
export function speechChunks(text: string): string[] {
  const sentences = text.replace(/\s+/g, " ").match(/[^.!?。！？؟۔]+[.!?。！？؟۔]*\s*/g) || [text];
  const chunks: string[] = [];
  let buffer = "";
  for (const sentence of sentences) {
    if ((buffer + sentence).length > 220 && buffer) {
      chunks.push(buffer.trim());
      buffer = "";
    }
    if (sentence.length > 220) {
      for (let index = 0; index < sentence.length; index += 200) chunks.push(sentence.slice(index, index + 200).trim());
    } else {
      buffer += sentence;
    }
  }
  if (buffer.trim()) chunks.push(buffer.trim());
  return chunks.filter(Boolean);
}

function pickVoice(language: string): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  const wanted = language.toLowerCase();
  const base = wanted.split("-")[0];
  return (
    voices.find((voice) => voice.lang.toLowerCase() === wanted) ||
    voices.find((voice) => voice.lang.toLowerCase().replace("_", "-").startsWith(`${base}-`)) ||
    voices.find((voice) => voice.lang.toLowerCase() === base) ||
    null
  );
}

export function useSpeech() {
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [state, setState] = useState<SpeechState>("idle");
  const [rate, setRate] = useState(1);
  const [activeId, setActiveId] = useState<string | null>(null);
  const queue = useRef<string[]>([]);
  const session = useRef(0);
  const voiceRef = useRef<SpeechSynthesisVoice | null>(null);
  const langRef = useRef("en");
  const rateRef = useRef(1);
  const speakNextRef = useRef<(token: number) => void>(() => undefined);

  useEffect(() => {
    rateRef.current = rate;
  }, [rate]);

  useEffect(() => {
    if (!supported) return;
    const warm = () => window.speechSynthesis.getVoices();
    warm();
    window.speechSynthesis.addEventListener?.("voiceschanged", warm);
    return () => {
      window.speechSynthesis.removeEventListener?.("voiceschanged", warm);
      window.speechSynthesis.cancel();
    };
  }, [supported]);

  const speakNext = useCallback((token: number) => {
    if (token !== session.current) return;
    const next = queue.current.shift();
    if (!next) {
      setState("idle");
      setActiveId(null);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(next);
    utterance.lang = langRef.current;
    if (voiceRef.current) utterance.voice = voiceRef.current;
    utterance.rate = rateRef.current;
    utterance.onend = () => speakNextRef.current(token);
    utterance.onerror = () => speakNextRef.current(token);
    window.speechSynthesis.speak(utterance);
  }, []);

  useEffect(() => {
    speakNextRef.current = speakNext;
  }, [speakNext]);

  /** Returns false when the device has no voice for this language (nothing is spoken). */
  const speak = useCallback((id: string, texts: string[], language: string) => {
    if (!supported) return false;
    const voice = pickVoice(language);
    if (!voice && language.split("-")[0] !== "en") return false;
    window.speechSynthesis.cancel();
    session.current += 1;
    voiceRef.current = voice;
    langRef.current = voice?.lang || language;
    queue.current = texts.flatMap(speechChunks);
    setActiveId(id);
    setState("speaking");
    speakNext(session.current);
    return true;
  }, [speakNext, supported]);

  const pause = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.pause();
    setState("paused");
  }, [supported]);

  const resume = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.resume();
    setState("speaking");
  }, [supported]);

  const stop = useCallback(() => {
    if (!supported) return;
    session.current += 1;
    queue.current = [];
    window.speechSynthesis.cancel();
    setState("idle");
    setActiveId(null);
  }, [supported]);

  return { supported, state, activeId, rate, setRate, speak, pause, resume, stop };
}
