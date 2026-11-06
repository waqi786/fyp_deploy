import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

type Tone = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Tone; size?: Size };
const cx = (...values: Array<string | undefined | false>) => values.filter(Boolean).join(" ");
const buttonVariants: Record<Tone, string> = {
  primary: "bg-brand-accent text-brand-on-accent hover:brightness-95",
  secondary: "border border-brand-border bg-brand-surface text-brand-text hover:border-brand-accent",
  ghost: "bg-transparent text-brand-muted hover:bg-brand-surface-2 hover:text-brand-text",
  danger: "bg-brand-danger text-white hover:brightness-95",
};
const buttonSizes: Record<Size, string> = { sm: "min-h-9 px-3 text-xs", md: "min-h-11 px-4 text-sm", lg: "min-h-12 px-5 text-base" };

export function Button({ variant = "secondary", size = "md", className, ...props }: ButtonProps) {
  return <button {...props} className={cx("inline-flex items-center justify-center gap-2 rounded-full font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-accent disabled:cursor-not-allowed disabled:opacity-50", buttonVariants[variant], buttonSizes[size], className)} />;
}
export function IconButton({ "aria-label": ariaLabel, title, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  if (!ariaLabel) throw new Error("IconButton requires an aria-label.");
  return <button {...props} aria-label={ariaLabel} title={title || ariaLabel} className={cx("inline-grid size-11 place-items-center rounded-full border border-brand-border bg-brand-surface text-brand-muted transition hover:border-brand-accent hover:text-brand-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-accent", className)} />;
}
export function Pill({ children, className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span {...props} className={cx("inline-flex min-h-8 items-center rounded-full border border-brand-border px-3 text-xs text-brand-muted", className)}>{children}</span>;
}
export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: "neutral" | "success" | "warning" | "danger"; className?: string }) {
  const tones = { neutral: "border-brand-border text-brand-muted", success: "border-brand-success/40 text-brand-success", warning: "border-brand-warning/40 text-brand-warning", danger: "border-brand-danger/40 text-brand-danger" };
  return <span className={cx("inline-flex min-h-6 items-center rounded-full border px-2.5 text-xs", tones[tone], className)}>{children}</span>;
}
export function Card({ children, className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section {...props} className={cx("rounded-[18px] border border-brand-border bg-brand-surface p-5", className)}>{children}</section>;
}
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" {...props} className={cx("animate-pulse rounded-lg bg-brand-surface-2", className)} />;
}
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <section className="grid justify-items-center gap-3 px-5 py-12 text-center" aria-live="polite"><h2 className="font-display text-2xl text-brand-text">{title}</h2><p className="max-w-md text-sm text-brand-muted">{description}</p>{action}</section>;
}
export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <section role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-danger/40 bg-brand-surface p-4"><p className="text-sm text-brand-text">{message}</p><Button variant="secondary" onClick={onRetry}>Retry</Button></section>;
}
export function ProgressLine({ active = true, label = "Loading" }: { active?: boolean; label?: string }) {
  return active ? <div className="fixed inset-x-0 top-0 z-[100] h-1 overflow-hidden bg-brand-surface-2" role="progressbar" aria-label={label}><div className="h-full w-1/3 animate-pulse bg-brand-accent" /></div> : null;
}
export function SegmentedControl<T extends string>({ value, options, onChange, label }: { value: T; options: readonly { value: T; label: string }[]; onChange: (value: T) => void; label: string }) {
  return <div role="group" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full border border-brand-border bg-brand-surface p-1">{options.map((option) => <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)} className={cx("min-h-10 rounded-full px-4 text-sm transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-accent", value === option.value ? "bg-brand-accent text-brand-on-accent" : "text-brand-muted hover:text-brand-text")}>{option.label}</button>)}</div>;
}

type ManagedPopover = { id: string; close: () => void; trigger: HTMLButtonElement | null; panel: () => HTMLElement | null };
type PopoverManager = { activeId: string | null; activate: (entry: ManagedPopover) => void; dismiss: (restoreFocus?: boolean) => void };
const PopoverContext = createContext<PopoverManager | null>(null);
export function PopoverProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const activeRef = useRef<ManagedPopover | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const dismiss = useCallback((restoreFocus = false) => {
    const active = activeRef.current;
    activeRef.current = null;
    setActiveId(null);
    active?.close();
    if (restoreFocus) queueMicrotask(() => active?.trigger?.focus());
  }, []);
  const activate = useCallback((entry: ManagedPopover) => {
    if (activeRef.current && activeRef.current.id !== entry.id) activeRef.current.close();
    activeRef.current = entry;
    setActiveId(entry.id);
  }, []);
  useEffect(() => {
    const outside = (event: PointerEvent) => {
      const active = activeRef.current;
      if (!active || !(event.target instanceof Node)) return;
      if (active.trigger?.contains(event.target) || active.panel()?.contains(event.target)) return;
      dismiss(true);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && activeRef.current) { event.preventDefault(); dismiss(true); }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [dismiss]);
  useEffect(() => { dismiss(true); }, [location.pathname, location.search, dismiss]);
  return <PopoverContext.Provider value={{ activeId, activate, dismiss }}>{children}</PopoverContext.Provider>;
}
export function Popover({ label, trigger, children, className }: { label: string; trigger: ReactNode; children: ReactNode; className?: string }) {
  const context = useContext(PopoverContext);
  if (!context) throw new Error("Popover must be rendered inside PopoverProvider.");
  const id = useId();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const toggle = () => {
    if (open) context.dismiss(true);
    else {
      context.activate({ id, close: () => setOpen(false), trigger: triggerRef.current, panel: () => panelRef.current });
      setOpen(true);
    }
  };
  return <div className="relative inline-flex"><button ref={triggerRef} type="button" aria-haspopup="dialog" aria-expanded={open} aria-controls={id + "-panel"} onClick={toggle} className="inline-flex items-center gap-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-accent">{trigger}</button>{open ? <div id={id + "-panel"} ref={panelRef} role="dialog" aria-label={label} className={cx("absolute end-0 top-full z-50 mt-2 min-w-64 rounded-2xl border border-brand-border bg-brand-surface p-4 shadow-xl", className)}>{children}</div> : null}</div>;
}
export function Dialog({ open, title, children, onClose }: { open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return <div className="fixed inset-0 z-[90] grid place-items-center bg-black/50 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section role="dialog" aria-modal="true" aria-labelledby={titleId} className="w-full max-w-lg rounded-[20px] border border-brand-border bg-brand-surface p-6 shadow-2xl"><div className="mb-5 flex items-start justify-between gap-4"><h2 id={titleId} className="font-display text-2xl text-brand-text">{title}</h2><IconButton aria-label="Close dialog" onClick={onClose}>?</IconButton></div>{children}</section></div>;
}
export function Drawer({ open, title, children, onClose }: { open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return <div className="fixed inset-0 z-[80] bg-black/40" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside role="dialog" aria-labelledby={titleId} className="absolute inset-y-0 end-0 w-full max-w-xl overflow-y-auto rounded-s-[20px] border-s border-brand-border bg-brand-surface p-6 shadow-2xl"><header className="mb-6 flex items-center justify-between gap-4"><h2 id={titleId} className="font-display text-2xl text-brand-text">{title}</h2><IconButton aria-label="Close drawer" onClick={onClose}>?</IconButton></header>{children}</aside></div>;
}
export function BottomSheet({ open, title, children, onClose }: { open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  const titleId = useId();
  if (!open) return null;
  return <div className="fixed inset-0 z-[80] flex items-end bg-black/40 md:hidden" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section role="dialog" aria-labelledby={titleId} className="max-h-[85dvh] w-full overflow-y-auto rounded-t-[20px] border-t border-brand-border bg-brand-surface p-5"><div className="mb-4 flex justify-between"><h2 id={titleId} className="font-display text-xl">{title}</h2><IconButton aria-label="Close sheet" onClick={onClose}>?</IconButton></div>{children}</section></div>;
}
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return <span className="group relative inline-flex" title={label}>{children}<span role="tooltip" className="pointer-events-none absolute bottom-full start-1/2 z-50 mb-2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-brand-text px-2 py-1 text-xs text-brand-bg opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100">{label}</span></span>;
}
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return <header className="mb-6 flex flex-wrap items-end justify-between gap-4"><div><h1 className="font-display text-3xl text-brand-text">{title}</h1>{description ? <p className="mt-2 max-w-2xl text-sm text-brand-muted">{description}</p> : null}</div>{actions}</header>;
}
export function Section({ label, title, children, className }: { label?: string; title: string; children: ReactNode; className?: string }) {
  return <section className={cx("space-y-4", className)}>{label ? <p className="text-xs text-brand-muted">{label}</p> : null}<h2 className="font-display text-2xl text-brand-text">{title}</h2>{children}</section>;
}
export function DataTable({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("overflow-x-auto rounded-2xl border border-brand-border bg-brand-surface", className)}><table className="min-w-full border-collapse text-start text-sm">{children}</table></div>;
}

export function DropdownMenu({ label, items }: { label: string; items: Array<{ label: string; onSelect: () => void }> }) {
  const context = useContext(PopoverContext);
  if (!context) throw new Error("DropdownMenu must be rendered inside PopoverProvider.");
  const id = useId();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const toggle = () => {
    if (open) context.dismiss(true);
    else { context.activate({ id, close: () => setOpen(false), trigger: triggerRef.current, panel: () => panelRef.current }); setOpen(true); }
  };
  return <div className="relative inline-flex"><button ref={triggerRef} type="button" aria-haspopup="menu" aria-expanded={open} aria-controls={id + "-menu"} onClick={toggle} className="min-h-11 rounded-full border border-brand-border px-4 text-sm text-brand-text">{label}</button>{open ? <div id={id + "-menu"} ref={panelRef} role="menu" aria-label={label} className="absolute end-0 top-full z-50 mt-2 min-w-48 rounded-2xl border border-brand-border bg-brand-surface p-2 shadow-xl">{items.map((item) => <button key={item.label} role="menuitem" type="button" className="block min-h-10 w-full rounded-lg px-3 text-start text-sm text-brand-text hover:bg-brand-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-accent" onClick={() => { item.onSelect(); context.dismiss(true); }}>{item.label}</button>)}</div> : null}</div>;
}

export function Toast({ message, onClose, tone = "neutral" }: { message: string; onClose: () => void; tone?: "neutral" | "success" | "warning" | "danger" }) {
  return <div role={tone === "danger" ? "alert" : "status"} aria-live={tone === "danger" ? "assertive" : "polite"} className="flex items-center justify-between gap-4 rounded-xl border border-brand-border bg-brand-surface p-4 shadow-xl"><span className="text-sm text-brand-text">{message}</span><IconButton aria-label="Dismiss notification" onClick={onClose}>?</IconButton></div>;
}
export function Stepper({ steps, current }: { steps: readonly string[]; current: number }) {
  return <ol aria-label="Progress steps" className="flex flex-wrap gap-2">{steps.map((step, index) => <li key={step} aria-current={index === current ? "step" : undefined} className={cx("rounded-full border px-3 py-2 text-xs", index === current ? "border-brand-accent text-brand-text" : "border-brand-border text-brand-muted")}>{index + 1}. {step}</li>)}</ol>;
}
export function CitationMarker({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return <button type="button" onClick={onClick} className="inline-flex min-h-7 min-w-7 items-center justify-center rounded-full border border-brand-border px-2 text-xs text-brand-accent hover:border-brand-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-accent">{children}</button>;
}
export function ConfidenceDot({ level }: { level: "High" | "Medium" | "Low" }) {
  const tone = level === "High" ? "bg-brand-success" : level === "Medium" ? "bg-brand-warning" : "bg-brand-danger";
  return <span className="inline-flex items-center gap-2 text-xs text-brand-muted" title={level + " confidence"}><span aria-hidden="true" className={cx("size-2 rounded-full", tone)} />{level} confidence</span>;
}
export function Avatar({ name, className }: { name: string; className?: string }) {
  const initials = name.trim().split(/\\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  return <span aria-label={name} className={cx("inline-grid size-10 place-items-center rounded-full bg-brand-accent-soft text-xs font-semibold text-brand-accent", className)}>{initials || "?"}</span>;
}
export function CreditsPill({ balance }: { balance: number }) {
  return <Pill aria-label={balance + " credits available"}>{balance.toLocaleString()} credits</Pill>;
}
export function KeyboardShortcut({ children }: { children: string }) {
  return <kbd className="rounded-md border border-brand-border bg-brand-surface-2 px-1.5 py-1 font-mono text-xs text-brand-muted">{children}</kbd>;
}
export function LanguagePicker({ languages, value, onChange }: { languages: readonly { code: string; nativeName: string; englishName: string }[]; value: string; onChange: (code: string) => void }) {
  const [query, setQuery] = useState("");
  const matches = languages.filter((language) => (language.nativeName + " " + language.englishName).toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return <label className="grid gap-2 text-sm text-brand-muted"><span>Language</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a language" className="min-h-11 rounded-xl border border-brand-border bg-brand-surface px-3 text-brand-text" /><select value={value} onChange={(event) => onChange(event.target.value)} className="min-h-11 rounded-xl border border-brand-border bg-brand-surface px-3 text-brand-text">{matches.map((language) => <option key={language.code} value={language.code}>{language.nativeName} ({language.englishName})</option>)}</select></label>;
}
export function Tabs({ tabs, value, onChange }: { tabs: readonly { id: string; label: string }[]; value: string; onChange: (id: string) => void }) {
  return <div role="tablist" className="flex flex-wrap gap-1 rounded-full border border-brand-border bg-brand-surface p-1">{tabs.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={value === tab.id} onClick={() => onChange(tab.id)} className={cx("min-h-10 rounded-full px-4 text-sm", value === tab.id ? "bg-brand-accent text-brand-on-accent" : "text-brand-muted")}>{tab.label}</button>)}</div>;
}
export function EvidenceDrawer(props: { open: boolean; title: string; children: ReactNode; onClose: () => void }) {
  return <Drawer {...props} />;
}
