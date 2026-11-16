/** The slim "Now listening" bar at the bottom of every page, and its expandable sheet (sections, sleep timer, queue). */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSearchCopy, type SearchT } from "../pages/search/copy";
import { RATES, useListen, type SleepTimer } from "./ListenProvider";
import "./listen.css";

function formatTime(seconds: number, language: string) {
  const minutes = Math.floor(seconds / 60);
  const rest = Math.max(0, seconds % 60);
  const format = (value: number) => new Intl.NumberFormat(language, { minimumIntegerDigits: 2 }).format(value);
  return minutes >= 60 ? `${new Intl.NumberFormat(language).format(Math.floor(minutes / 60))}:${format(minutes % 60)}:${format(rest)}` : `${new Intl.NumberFormat(language).format(minutes)}:${format(rest)}`;
}

const Icon = {
  play: <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" fill="currentColor" /></svg>,
  pause: <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" /></svg>,
  back: <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" /><text x="12" y="15.5" fontSize="7" textAnchor="middle" fill="currentColor" stroke="none">15</text></svg>,
  forward: <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 12a8 8 0 1 1-2.4-5.7M20 4v4h-4" /><text x="12" y="15.5" fontSize="7" textAnchor="middle" fill="currentColor" stroke="none">15</text></svg>,
  prev: <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h2v14H6zM19 5.5v13L9.5 12z" fill="currentColor" /></svg>,
  next: <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 5h2v14h-2zM5 5.5v13l9.5-6.5z" fill="currentColor" /></svg>,
  close: <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 6l12 12M18 6L6 18" /></svg>,
  expand: <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 15l6-6 6 6" /></svg>,
  text: <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 6h14M5 10h14M5 14h9M5 18h6" /></svg>,
  headphones: <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 15v-3a8 8 0 0 1 16 0v3" /><rect x="3" y="14" width="4" height="6" rx="1.5" /><rect x="17" y="14" width="4" height="6" rx="1.5" /></svg>,
};

function Menu({ label, trigger, children, className = "" }: { label: string; trigger: React.ReactNode; children: (close: () => void) => React.ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className={`ls-menu ${className}`} ref={ref}>
      <button type="button" className="ls-chip" aria-haspopup="menu" aria-expanded={open} aria-label={label} title={label} onClick={() => setOpen((value) => !value)}>{trigger}</button>
      {open ? <div className="ls-menu-pop" role="menu" aria-label={label}>{children(() => setOpen(false))}</div> : null}
    </div>
  );
}

function VoiceMenu({ t }: { t: SearchT }) {
  const listen = useListen();
  const current = listen.voice === "device" ? t("lisVoiceDevice") : listen.voices.find((voice) => voice.id === listen.voice)?.name || t("lisVoiceDevice");
  return (
    <Menu label={t("lisVoice")} trigger={<span className="ls-chip-text">{current}</span>} className="ls-voice">
      {(close) => (
        <>
          <button type="button" role="menuitemradio" aria-checked={listen.voice === "device"} onClick={() => { listen.setVoice("device"); close(); }}>
            <b>{t("lisVoiceDevice")}</b><span>{t("lisVoiceDeviceNote")}</span>
          </button>
          {listen.voices.map((voice) => (
            <button key={voice.id} type="button" role="menuitemradio" aria-checked={listen.voice === voice.id} onClick={() => { listen.setVoice(voice.id); close(); }}>
              <b>{voice.name}</b><span>{t("lisVoiceNeuralNote")}</span>
            </button>
          ))}
          {!listen.voices.length ? <p className="ls-menu-note">{t("lisNoNeuralVoice")}</p> : null}
        </>
      )}
    </Menu>
  );
}

function SpeedMenu({ t, language }: { t: SearchT; language: string }) {
  const listen = useListen();
  const label = (rate: number) => `${new Intl.NumberFormat(language, { maximumFractionDigits: 2 }).format(rate)}×`;
  return (
    <Menu label={t("lisSpeed")} trigger={<span className="ls-chip-text">{label(listen.rate)}</span>}>
      {(close) => RATES.map((rate) => (
        <button key={rate} type="button" role="menuitemradio" aria-checked={listen.rate === rate} onClick={() => { listen.setRate(rate); close(); }}>{label(rate)}</button>
      ))}
    </Menu>
  );
}

function NoticeLine({ t }: { t: SearchT }) {
  const listen = useListen();
  if (!listen.notice) return null;
  const key = { no_voice: "lisNoticeNoVoice", limit_reached: "lisNoticeLimit", neural_fallback: "lisNoticeFallback", unavailable: "lisNoticeUnavailable", nothing: "lisNoticeNothing" }[listen.notice] as Parameters<SearchT>[0];
  return (
    <p className="ls-notice" role="status">
      {t(key)}
      <button type="button" className="ls-link" onClick={listen.clearNotice}>{t("lisDismiss")}</button>
    </p>
  );
}

function Sheet({ t, language }: { t: SearchT; language: string }) {
  const listen = useListen();
  const navigate = useNavigate();
  const item = listen.item!;
  const sleepOptions: Array<[string, SleepTimer]> = [
    [t("lisSleepOff"), null],
    [t("lisSleepMinutes", { count: 15 }), { kind: "minutes", until: Date.now() + 15 * 60_000 }],
    [t("lisSleepMinutes", { count: 30 }), { kind: "minutes", until: Date.now() + 30 * 60_000 }],
    [t("lisSleepMinutes", { count: 60 }), { kind: "minutes", until: Date.now() + 60 * 60_000 }],
    [t("lisSleepSection"), { kind: "section", section: listen.position.section }],
  ];
  const sleepLabel = (timer: SleepTimer) => (timer === null ? "off" : timer.kind === "section" ? "section" : String(Math.round((timer.until - Date.now()) / 60_000 / 15) * 15));
  return (
    <div className="ls-sheet" role="dialog" aria-label={t("lisNowListening")}>
      <div className="ls-sheet-grid">
        <section aria-labelledby="ls-sections">
          <h2 id="ls-sections">{t("lisSections")}</h2>
          <ol className="ls-sections">
            {item.script.sections.map((section, index) => (
              <li key={`${index}-${section.title}`}>
                <button type="button" className={index === listen.position.section ? "is-current" : ""} aria-current={index === listen.position.section ? "true" : undefined} onClick={() => listen.seekSentence({ section: index, sentence: 0 })}>
                  <span>{section.title || (index === 0 ? t("lisIntro") : t("lisSectionNumber", { number: index }))}</span>
                  <small>{t("lisSentences", { count: section.sentences.length })}</small>
                </button>
              </li>
            ))}
          </ol>
        </section>
        <section aria-labelledby="ls-queue">
          <div className="ls-sheet-row"><SpeedMenu t={t} language={language} /><VoiceMenu t={t} /></div>
          <h2 id="ls-queue">{t("lisQueue")}</h2>
          {listen.queue.length ? (
            <ol className="ls-queue">
              {listen.queue.map((entry) => (
                <li key={entry.id}>
                  <span><bdi>{entry.title}</bdi></span>
                  <button type="button" className="ls-link" onClick={() => void listen.play({ id: entry.item_id, kind: (entry.kind as never) || "paper", title: entry.title, language: entry.payload.language || item.language, source: entry.payload, resume: true }).then(() => listen.dequeue(entry.id))}>{t("lisPlayNow")}</button>
                  <button type="button" className="ls-link" onClick={() => void listen.dequeue(entry.id)}>{t("lisRemove")}</button>
                </li>
              ))}
            </ol>
          ) : <p className="ls-muted">{t("lisQueueEmpty")}</p>}
          <h2>{t("lisSleep")}</h2>
          <div className="ls-sleep" role="radiogroup" aria-label={t("lisSleep")}>
            {sleepOptions.map(([label, timer]) => (
              <button key={label} type="button" role="radio" aria-checked={sleepLabel(listen.sleep) === sleepLabel(timer)} onClick={() => listen.setSleep(timer)}>{label}</button>
            ))}
          </div>
          <h2>{t("lisSettings")}</h2>
          <div className="ls-toggles">
            {([["readReferences", "lisReadReferences"], ["readCitations", "lisReadCitations"], ["readCaptions", "lisReadCaptions"], ["autoScroll", "lisAutoScroll"]] as const).map(([key, label]) => (
              <label key={key}><input type="checkbox" checked={listen.settings[key]} onChange={(event) => listen.updateSettings({ [key]: event.target.checked })} /><span>{t(label)}</span></label>
            ))}
          </div>
          <p className="ls-muted">{t("lisSettingsNote")}</p>
          {listen.estimate ? <p className="ls-estimate">{t("lisEstimate", { minutes: new Intl.NumberFormat(language).format(listen.estimate.minutes), credits: new Intl.NumberFormat(language).format(listen.estimate.credits) })}</p> : null}
          {item.href ? <button type="button" className="ls-text-button" onClick={() => { listen.setExpanded(false); navigate(item.href!); }}>{Icon.text}{t("lisOpenText")}</button> : null}
        </section>
      </div>
    </div>
  );
}

export function MiniPlayer({ language }: { language: string }) {
  const listen = useListen();
  const t = useSearchCopy(language);
  const navigate = useNavigate();
  const [announce, setAnnounce] = useState("");
  const item = listen.item;
  const sectionTitle = item?.script.sections[listen.position.section]?.title || "";

  useEffect(() => {
    if (sectionTitle) setAnnounce(t("lisNowSection", { section: sectionTitle }));
  }, [sectionTitle, t]);

  // L toggles play / pause anywhere outside text fields (the Reader also starts the paper with it).
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (!item || event.metaKey || event.ctrlKey || event.altKey || (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)))) return;
      if (event.key === "l" || event.key === "L") {
        event.preventDefault();
        listen.toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, listen]);

  if (!item) return null;
  const playing = listen.status === "playing" || listen.status === "loading";
  const percent = listen.progress.total ? (listen.progress.done / listen.progress.total) * 100 : 0;

  return (
    <div className={`ls-player${listen.expanded ? " is-expanded" : ""}`} data-no-translate="" lang={language} dir={language === "ur" || language === "ar" || language === "fa" ? "rtl" : "ltr"} role="region" aria-label={t("lisNowListening")}>
      <div className="ls-live rs-visually-hidden" aria-live="polite">{announce}</div>
      {listen.expanded ? <Sheet t={t} language={language} /> : null}
      <div className="ls-bar">
        <div className="ls-info">
          <span className="ls-badge">{Icon.headphones}</span>
          <div className="ls-titles">
            <b className="ls-title"><bdi>{item.title}</bdi></b>
            <span className="ls-section"><bdi>{sectionTitle || t("lisIntro")}</bdi></span>
          </div>
        </div>
        <div className="ls-controls">
          <button type="button" className="ls-icon" aria-label={t("lisPreviousSection")} title={t("lisPreviousSection")} onClick={() => listen.section(-1)}>{Icon.prev}</button>
          <button type="button" className="ls-icon" aria-label={t("lisBack15")} title={t("lisBack15")} onClick={() => listen.skip(-1)}>{Icon.back}</button>
          <button type="button" className={`ls-play${listen.status === "loading" ? " is-loading" : ""}`} aria-label={playing ? t("lisPause") : t("lisPlay")} title={playing ? t("lisPause") : t("lisPlay")} onClick={listen.toggle}>{playing ? Icon.pause : Icon.play}</button>
          <button type="button" className="ls-icon" aria-label={t("lisForward15")} title={t("lisForward15")} onClick={() => listen.skip(1)}>{Icon.forward}</button>
          <button type="button" className="ls-icon" aria-label={t("lisNextSection")} title={t("lisNextSection")} onClick={() => listen.section(1)}>{Icon.next}</button>
        </div>
        <div className="ls-progress">
          <div className="ls-track" role="progressbar" aria-label={t("lisProgress")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}>
            <span className="ls-fill" style={{ inlineSize: `${percent}%` }} />
            {listen.progress.markers.slice(1).map((marker, index) => <i key={index} className="ls-marker" style={{ insetInlineStart: `${marker * 100}%` }} />)}
          </div>
          <span className="ls-time">{t("lisTimeLeft", { time: formatTime(listen.progress.secondsLeft, language) })}</span>
        </div>
        <div className="ls-extra">
          <SpeedMenu t={t} language={language} />
          <VoiceMenu t={t} />
          {item.href ? <button type="button" className="ls-chip" onClick={() => navigate(item.href!)}>{Icon.text}<span className="ls-chip-text">{t("lisText")}</span></button> : null}
          <button type="button" className="ls-icon" aria-expanded={listen.expanded} aria-label={listen.expanded ? t("lisCollapse") : t("lisExpand")} title={listen.expanded ? t("lisCollapse") : t("lisExpand")} onClick={() => listen.setExpanded(!listen.expanded)}><span className={listen.expanded ? "ls-flip" : ""}>{Icon.expand}</span></button>
          <button type="button" className="ls-icon" aria-label={t("lisClose")} title={t("lisClose")} onClick={listen.close}>{Icon.close}</button>
        </div>
      </div>
      <NoticeLine t={t} />
    </div>
  );
}

/** The outline "Listen" button with a menu of what to read (Whole paper · Summary · Key points · From here …). */
export function ListenMenuButton({ t, options, disabled }: { t: SearchT; options: Array<{ key: string; label: string; onSelect: () => void }>; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    window.addEventListener("pointerdown", onPointer);
    return () => window.removeEventListener("pointerdown", onPointer);
  }, [open]);
  return (
    <div className="ls-menu ls-listen-menu" ref={ref}>
      <button type="button" className="rd-button rd-button-quiet" aria-haspopup="menu" aria-expanded={open} disabled={disabled} onClick={() => setOpen((value) => !value)}>
        {Icon.headphones}{t("lisListen")}
      </button>
      {open ? (
        <div className="ls-menu-pop" role="menu" aria-label={t("lisListen")}>
          {options.map((option) => (
            <button key={option.key} type="button" role="menuitem" onClick={() => { setOpen(false); option.onSelect(); }}>{option.label}</button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
