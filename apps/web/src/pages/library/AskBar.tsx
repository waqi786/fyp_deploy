/** "Ask your library": answers only from the owner's saved papers, notes and ideas, with numbered sources. */
import { Fragment, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { libraryApi, type AskResult, type AskSource } from "./libraryApi";
import { CloseGlyph, SparkGlyph, useDismiss, useLib } from "./ui";

export function AskBar({ projectId }: { projectId?: string }) {
  const { t, language, items, toast, openItem, errorText } = useLib();
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [busy, setBusy] = useState(false);
  const zone = useRef<HTMLDivElement>(null);
  useDismiss(Boolean(result), [zone], () => setResult(null));

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (text.length < 2 || busy) return;
    setBusy(true);
    try {
      setResult(await libraryApi.ask(text, language, projectId));
      setAsked(text);
    } catch (caught) {
      toast(errorText(caught));
    } finally {
      setBusy(false);
    }
  }

  function openSource(source: AskSource) {
    const item = items.find((entry) => entry.id === (source.kind === "paper" ? source.id : source.item_id));
    if (item) openItem(item);
  }

  function withMarkers(text: string): ReactNode {
    return text.split(/(\[\d{1,2}\])/g).map((part, index) => {
      const match = part.match(/^\[(\d{1,2})\]$/);
      const source = match ? result?.sources.find((entry) => entry.n === Number(match[1])) : undefined;
      return source ? <button key={index} type="button" className="lb-marker" onClick={() => openSource(source)} title={source.title} aria-label={t("libOpenSource", { n: source.n, title: source.title })}>{source.n}</button> : <Fragment key={index}>{part}</Fragment>;
    });
  }

  if (!items.length) return null;
  return (
    <div ref={zone} className="lb-ask-zone">
      {result ? (
        <section className="lb-ask-result" aria-live="polite" aria-label={t("libAskAnswer")}>
          <div className="lb-ask-head">
            <p className="lb-ask-question" dir="auto">{asked}</p>
            <button type="button" className="lb-icon-button" aria-label={t("libClose")} title={t("libClose")} onClick={() => setResult(null)}><CloseGlyph /></button>
          </div>
          {result.mode === "answer" && result.answer ? <p className="lb-ask-answer" dir="auto">{withMarkers(result.answer)}</p> : null}
          {!result.sources.length ? <p className="lb-ask-empty">{t("libAskNothing")}</p> : null}
          {result.sources.length ? (
            <>
              <p className="lb-ask-label">{result.mode === "answer" ? t("libAskSources") : t("libAskClosest")}</p>
              <ol className="lb-ask-sources">
                {result.sources.map((source) => (
                  <li key={`${source.kind}-${source.id}`}>
                    <button type="button" onClick={() => openSource(source)} disabled={source.kind !== "paper" && !source.item_id}>
                      <span className="lb-ask-n">{source.n}</span>
                      <span className="lb-ask-text">
                        <bdi className="lb-ask-title">{source.title}</bdi>
                        <span className="lb-ask-kind">{source.kind === "paper" ? t("libSourcePaper") : source.kind === "idea" ? t("libSourceIdea") : t("libSourceNote")}{source.snippet ? ` · ${source.snippet}` : ""}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            </>
          ) : null}
          <p className="lb-ask-note">{result.mode === "answer" ? t("libAskGrounded") : t("libAskMatchesOnly")}</p>
        </section>
      ) : null}
      <form className="lb-ask" onSubmit={(event) => void ask(event)} role="search">
        <span className="lb-ask-icon" aria-hidden="true"><SparkGlyph /></span>
        <input value={question} maxLength={1000} dir="auto" onChange={(event) => setQuestion(event.target.value)} placeholder={projectId ? t("libAskProjectPlaceholder") : t("libAskPlaceholder")} aria-label={t("libAskLabel")} />
        <button type="submit" className="lb-button lb-button-primary" disabled={question.trim().length < 2 || busy}>{busy ? t("libAsking") : t("libAsk")}</button>
      </form>
    </div>
  );
}
