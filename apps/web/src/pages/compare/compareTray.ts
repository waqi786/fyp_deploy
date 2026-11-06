/**
 * Compare tray: papers picked in Search or the Reader, waiting to be compared.
 * Kept in this browser (localStorage) so it survives navigation; the Compare page imports and clears it.
 */
import { useEffect, useState } from "react";
import type { PaperHandoff } from "../reader/readerApi";

export const MAX_COMPARE = 15;
const KEY = "resora-compare-tray";
const EVENT = "resora-compare-tray";

export type TrayItem = PaperHandoff & {
  key: string;
  /** Set when the paper is open in the Reader with a stored PDF: Compare uploads that exact PDF. */
  reader_doc_id?: string | null;
  has_pdf?: boolean;
};

export function readTray(): TrayItem[] {
  try {
    const items = JSON.parse(window.localStorage.getItem(KEY) || "[]") as TrayItem[];
    return Array.isArray(items) ? items.filter((item) => item && typeof item.key === "string" && typeof item.title === "string").slice(0, MAX_COMPARE) : [];
  } catch {
    return [];
  }
}

function write(items: TrayItem[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(items.slice(0, MAX_COMPARE)));
  } catch {
    /* storage blocked: the tray simply does not persist */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function inTray(key: string) {
  return readTray().some((item) => item.key === key);
}

/** Adds or removes a paper. Returns "added" | "removed" | "full". */
export function toggleTray(item: TrayItem): "added" | "removed" | "full" {
  const items = readTray();
  if (items.some((entry) => entry.key === item.key)) {
    write(items.filter((entry) => entry.key !== item.key));
    return "removed";
  }
  if (items.length >= MAX_COMPARE) return "full";
  write([...items, item]);
  return "added";
}

export function removeFromTray(key: string) {
  write(readTray().filter((item) => item.key !== key));
}

export function clearTray() {
  write([]);
}

/** Live tray contents for components (updates across tabs too). */
export function useTray() {
  const [items, setItems] = useState<TrayItem[]>(() => readTray());
  useEffect(() => {
    const sync = () => setItems(readTray());
    window.addEventListener(EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return items;
}
