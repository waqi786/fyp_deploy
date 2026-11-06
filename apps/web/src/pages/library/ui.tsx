/** Small building blocks shared by the Library views: menus that close on outside click / Esc, icons, empty and
 *  loading states, date helpers. Everything uses the --rs-* design tokens through LibraryPage.css. */
import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import type { SearchCopyKey, SearchT } from "../search/copy";
import type { LibraryItem, LibraryList, Overview } from "./libraryApi";

export type LibraryCtx = {
  t: SearchT;
  language: string;
  items: LibraryItem[];
  lists: LibraryList[];
  overview: Overview | null;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  setItems: (update: (items: LibraryItem[]) => LibraryItem[]) => void;
  toast: (message: string) => void;
  openItem: (item: LibraryItem) => void;
  errorText: (error: unknown) => string;
};

export const LibraryContext = createContext<LibraryCtx | null>(null);

export function useLib() {
  const value = useContext(LibraryContext);
  if (!value) throw new Error("LibraryContext missing");
  return value;
}

/** Close on outside pointer, Esc, or when another menu opens. Scrollbar clicks are ignored. */
export function useDismiss(open: boolean, refs: Array<RefObject<HTMLElement | null>>, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (target === document.documentElement || event.clientX >= document.documentElement.clientWidth) return;
      if (refs.some((ref) => ref.current?.contains(target))) return;
      onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, onClose]);
}

let openMenuClose: (() => void) | null = null;

export type MenuEntry =
  | { kind?: "item"; label: string; onSelect: () => void; checked?: boolean; danger?: boolean; disabled?: boolean }
  | { kind: "label"; label: string }
  | { kind: "divider" };

/** A button that opens a small menu. One menu is open at a time; focus returns to the trigger. */
export function Menu({ label, trigger, entries, align = "end", className = "", icon = false, disabled = false, up = false }: {
  /** Open above the trigger (for bars pinned to the bottom of the screen). */
  up?: boolean;
  label: string;
  trigger: ReactNode;
  entries: MenuEntry[];
  align?: "start" | "end";
  className?: string;
  icon?: boolean;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = () => {
    setOpen(false);
    if (openMenuClose === closeRef.current) openMenuClose = null;
  };
  const closeRef = useRef(close);
  closeRef.current = close;
  useDismiss(open, [buttonRef, panelRef], close);
  useEffect(() => {
    if (open) panelRef.current?.querySelector<HTMLElement>("[role=menuitem]:not(:disabled), [role=menuitemcheckbox]:not(:disabled)")?.focus();
  }, [open]);
  const toggle = () => {
    if (open) return close();
    openMenuClose?.();
    openMenuClose = () => closeRef.current();
    setOpen(true);
  };
  const choose = (entry: Extract<MenuEntry, { label: string; onSelect: () => void }>) => {
    close();
    buttonRef.current?.focus();
    entry.onSelect();
  };
  return (
    <div className={`lb-menu ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        className={icon ? "lb-icon-button" : "lb-button lb-button-quiet"}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label={icon ? label : undefined}
        title={icon ? label : undefined}
        disabled={disabled}
        onClick={toggle}
      >
        {trigger}
      </button>
      {open ? (
        <div
          ref={panelRef}
          id={id}
          role="menu"
          aria-label={label}
          className={`lb-menu-panel lb-menu-${align}${up ? " lb-menu-up" : ""}`}
          onKeyDown={(event) => {
            const options = [...(panelRef.current?.querySelectorAll<HTMLElement>("[role^=menuitem]:not(:disabled)") || [])];
            const index = options.indexOf(document.activeElement as HTMLElement);
            if (event.key === "ArrowDown") { event.preventDefault(); options[(index + 1) % options.length]?.focus(); }
            if (event.key === "ArrowUp") { event.preventDefault(); options[(index - 1 + options.length) % options.length]?.focus(); }
            if (event.key === "Tab") close();
          }}
        >
          {entries.map((entry, index) => {
            if (entry.kind === "divider") return <hr key={`d${index}`} className="lb-menu-divider" />;
            if (entry.kind === "label") return <p key={`l${index}`} className="lb-menu-label">{entry.label}</p>;
            const checkable = entry.checked !== undefined;
            return (
              <button
                key={`${entry.label}-${index}`}
                type="button"
                role={checkable ? "menuitemcheckbox" : "menuitem"}
                aria-checked={checkable ? entry.checked : undefined}
                className={`lb-menu-item${entry.danger ? " is-danger" : ""}${entry.checked ? " is-checked" : ""}`}
                disabled={entry.disabled}
                onClick={() => choose(entry)}
              >
                <span className="lb-menu-check" aria-hidden="true">{entry.checked ? <CheckGlyph /> : null}</span>
                <bdi>{entry.label}</bdi>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export type SelectOption = { value: string; label: string };

/**
 * Token-styled dropdown that replaces the native <select> (master prompt Part 1A #8).
 * Listbox semantics, arrow / Home / End / type-ahead keys, closes on outside click, Esc, Tab and when another
 * menu opens; long lists get a filter box. The trigger keeps the accessible name passed in `label`.
 */
export function Select({ value, options, onChange, label, className = "", disabled = false, filterLabel, up = false, align = "start" }: {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  label: string;
  className?: string;
  disabled?: boolean;
  /** Placeholder for the filter box shown when there are more than 12 options. */
  filterLabel?: string;
  up?: boolean;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const typed = useRef({ text: "", at: 0 });
  const selected = options.find((option) => option.value === value) || options[0];
  const needle = query.trim().toLocaleLowerCase();
  const shown = needle ? options.filter((option) => option.label.toLocaleLowerCase().includes(needle)) : options;
  const close = () => {
    setOpen(false);
    setQuery("");
    if (openMenuClose === closeRef.current) openMenuClose = null;
  };
  const closeRef = useRef(close);
  closeRef.current = close;
  useDismiss(open, [buttonRef, panelRef], close);
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    const filter = panel?.querySelector<HTMLInputElement>("input");
    (filter || panel?.querySelector<HTMLElement>("[aria-selected=true]") || panel?.querySelector<HTMLElement>("[role=option]"))?.focus();
  }, [open]);
  const toggle = () => {
    if (open) return close();
    openMenuClose?.();
    openMenuClose = () => closeRef.current();
    setOpen(true);
  };
  const choose = (next: string) => {
    close();
    buttonRef.current?.focus();
    if (next !== value) onChange(next);
  };
  const optionEls = () => [...(panelRef.current?.querySelectorAll<HTMLElement>("[role=option]") || [])];
  return (
    <div className={`lb-menu lb-dropdown ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        className="lb-button lb-button-quiet lb-dropdown-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label={`${label}: ${selected?.label || ""}`}
        title={selected?.label}
        disabled={disabled}
        onClick={toggle}
        onKeyDown={(event) => {
          if ((event.key === "ArrowDown" || event.key === "ArrowUp") && !open) { event.preventDefault(); toggle(); }
        }}
      >
        <bdi>{selected?.label || ""}</bdi>
        <ChevronGlyph />
      </button>
      {open ? (
        <div
          ref={panelRef}
          className={`lb-menu-panel lb-menu-${align}${up ? " lb-menu-up" : ""}`}
          onKeyDown={(event) => {
            const all = optionEls();
            const index = all.indexOf(document.activeElement as HTMLElement);
            if (event.key === "ArrowDown") { event.preventDefault(); all[Math.min(all.length - 1, index + 1)]?.focus(); }
            else if (event.key === "ArrowUp") { event.preventDefault(); if (index <= 0) panelRef.current?.querySelector<HTMLInputElement>("input")?.focus(); else all[index - 1]?.focus(); }
            else if (event.key === "Home" && index >= 0) { event.preventDefault(); all[0]?.focus(); }
            else if (event.key === "End" && index >= 0) { event.preventDefault(); all[all.length - 1]?.focus(); }
            else if (event.key === "Tab") close();
            else if (event.key.length === 1 && index >= 0 && !event.ctrlKey && !event.metaKey) {
              const now = Date.now();
              typed.current = { text: (now - typed.current.at < 700 ? typed.current.text : "") + event.key.toLocaleLowerCase(), at: now };
              all.find((element) => (element.textContent || "").trim().toLocaleLowerCase().startsWith(typed.current.text))?.focus();
            }
          }}
        >
          {options.length > 12 ? (
            <input className="lb-dropdown-filter" value={query} dir="auto" placeholder={filterLabel || label} aria-label={filterLabel || label} onChange={(event) => setQuery(event.target.value)} />
          ) : null}
          <div id={id} role="listbox" aria-label={label}>
            {shown.map((option) => (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                className={`lb-menu-item${option.value === value ? " is-checked" : ""}`}
                onClick={() => choose(option.value)}
              >
                <span className="lb-menu-check" aria-hidden="true">{option.value === value ? <CheckGlyph /> : null}</span>
                <bdi>{option.label}</bdi>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon?: ReactNode; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="lb-empty">
      {icon ? <span className="lb-empty-icon" aria-hidden="true">{icon}</span> : null}
      <p className="lb-empty-title">{title}</p>
      {body ? <p className="lb-empty-body">{body}</p> : null}
      {action ? <div className="lb-empty-action">{action}</div> : null}
    </div>
  );
}

export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="lb-skeletons" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="lb-skeleton-row">
          <span className="lb-sk lb-sk-box" />
          <span className="lb-sk-lines"><span className="lb-sk lb-sk-title" /><span className="lb-sk lb-sk-meta" /></span>
        </div>
      ))}
    </div>
  );
}

export function ErrorLine({ message, onRetry, t }: { message: string; onRetry?: () => void; t: SearchT }) {
  return (
    <div className="lb-alert" role="alert">
      <span>{message}</span>
      {onRetry ? <button type="button" className="lb-text-button" onClick={onRetry}>{t("libRetry")}</button> : null}
    </div>
  );
}

/** Two-step delete: the first press arms the button, the second confirms. Disarms on blur. */
export function ConfirmButton({ label, confirmLabel, onConfirm, className = "lb-button lb-button-quiet" }: { label: string; confirmLabel: string; onConfirm: () => void; className?: string }) {
  const [armed, setArmed] = useState(false);
  return (
    <button
      type="button"
      className={`${className}${armed ? " is-armed" : ""}`}
      onClick={() => (armed ? (setArmed(false), onConfirm()) : setArmed(true))}
      onBlur={() => window.setTimeout(() => setArmed(false), 150)}
    >
      {armed ? confirmLabel : label}
    </button>
  );
}

/** "1 paper" / "3 papers": the catalog has a singular and a plural label. */
export function countLabel(t: SearchT, count: number, one: SearchCopyKey, many: SearchCopyKey, language: string) {
  return t(count === 1 ? one : many, { count: formatNumber(count, language) });
}

export const STATUS_KEYS: Record<LibraryItem["status"], SearchCopyKey> = { to_read: "libStatusToRead", reading: "libStatusReading", read: "libStatusRead" };

export function today() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function formatDay(iso: string, language: string) {
  const date = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(date.getTime())) return "";
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return new Intl.DateTimeFormat(language, { day: "numeric", month: "short", ...(sameYear ? {} : { year: "numeric" }) }).format(date);
}

export function formatNumber(value: number, language: string) {
  return new Intl.NumberFormat(language).format(value);
}

export function authorLine(item: Pick<LibraryItem, "authors">, t: SearchT) {
  if (!item.authors.length) return "";
  const first = item.authors[0].includes(",") ? item.authors[0].split(",")[0].trim() : item.authors[0];
  return item.authors.length > 2 ? t("libEtAl", { name: first }) : item.authors.map((name) => (name.includes(",") ? name.split(",")[0].trim() : name)).join(", ");
}

export function directionOf(code: string) {
  return ["ar", "ur", "fa", "he", "ps", "sd", "ug", "yi", "dv", "ckb"].includes(code.split("-")[0]) ? "rtl" : "ltr";
}

// ---------------------------------------------------------------- icons (stroke icons, 1.8px, currentColor)

function Svg({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{children}</svg>;
}
export const CheckGlyph = () => <Svg size={15}><path d="m5 12.5 4.5 4.5L19 7.5" /></Svg>;
export const StarGlyph = ({ filled = false }: { filled?: boolean }) => <Svg><path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8L3.5 9.7l5.9-.9L12 3.5Z" fill={filled ? "currentColor" : "none"} /></Svg>;
export const MoreGlyph = () => <Svg><circle cx="5.5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="18.5" cy="12" r="1.2" /></Svg>;
export const SearchGlyph = () => <Svg size={15}><circle cx="11" cy="11" r="7" /><path d="m20 20-4.2-4.2" /></Svg>;
export const PlusGlyph = () => <Svg size={15}><path d="M12 5v14M5 12h14" /></Svg>;
export const CloseGlyph = () => <Svg size={15}><path d="M6 6l12 12M18 6 6 18" /></Svg>;
export const ChevronGlyph = () => <Svg size={14}><path d="m6 9 6 6 6-6" /></Svg>;
export const BackGlyph = () => <Svg size={16}><path d="M15 6l-6 6 6 6" /></Svg>;
export const BookGlyph = () => <Svg size={22}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5v-15Z" /><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5" /></Svg>;
export const FolderGlyph = () => <Svg size={22}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" /></Svg>;
export const NoteGlyph = () => <Svg size={22}><path d="M6 3h9l5 5v13H6z" /><path d="M14 3v6h6M9 13h7M9 17h5" /></Svg>;
export const BulbGlyph = () => <Svg size={22}><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z" /></Svg>;
export const TaskGlyph = () => <Svg size={22}><rect x="4" y="4" width="16" height="16" rx="3" /><path d="m8.5 12 2.5 2.5 4.5-5" /></Svg>;
export const QuoteGlyph = () => <Svg size={22}><path d="M7 7h4v4c0 3-1.5 5-4 6M14 7h4v4c0 3-1.5 5-4 6" /></Svg>;
export const ClockGlyph = () => <Svg size={22}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></Svg>;
export const UploadGlyph = () => <Svg size={16}><path d="M12 16V4M7 9l5-5 5 5M5 20h14" /></Svg>;
export const SparkGlyph = () => <Svg size={16}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></Svg>;
export const CopyGlyph = () => <Svg size={15}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></Svg>;
export const CompareGlyph = () => <Svg size={15}><path d="M8 4v16M16 4v16M4 8h4M16 16h4" /></Svg>;
