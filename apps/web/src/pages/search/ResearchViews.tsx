import { FormEvent, Fragment, ReactNode, useState } from "react";
import type { EvidenceLevel, ResearchAnswer, ResearchStepId, StepStatus } from "./researchApi";

/** Loose translator type so these views can be reused by any page catalog. */
export type Translate = (key: string, values?: Record<string, string | number>) => string;

type PaperRef = { paper_id: string; title: string };

const CITATION = /\[(\d+(?:\s*[,،、]\s*\d+)*)\]/g;
const NATIVE_DIGITS: Record<string, string> = {
  "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
  "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
};

function asciiDigits(value: string) {
  return value.replace(/[٠-٩۰-۹]/g, (digit) => NATIVE_DIGITS[digit] || digit);
}

/* ------------------------------------------------------------------ steps */

const STEP_ORDER: ResearchStepId[] = ["understand", "search", "read", "answer"];
const STEP_KEYS: Record<ResearchStepId, string> = {
  understand: "stepUnderstand",
  search: "stepSearch",
  read: "stepRead",
  answer: "stepAnswer",
};

export function ResearchSteps({ steps, t }: { steps: Partial<Record<ResearchStepId, StepStatus>>; t: Translate }) {
  return (
    <ol className="rs-steps" aria-label={t("searching")}>
      {STEP_ORDER.map((step) => {
        const status = steps[step] || "pending";
        return (
          <li key={step} className={status === "done" ? "is-done" : status === "active" ? "is-active" : ""} aria-current={status === "active" ? "step" : undefined}>
            <span className="rs-step-dot" aria-hidden="true">{status === "done" ? <SmallCheck /> : null}</span>
            {t(STEP_KEYS[step])}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ answer */

function CitedText({ text, evidence, onOpenPaper, t }: { text: string; evidence: PaperRef[]; onOpenPaper: (paperId: string) => void; t: Translate }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const index = match.index ?? 0;
    if (index > last) parts.push(text.slice(last, index));
    const numbers = asciiDigits(match[1]).split(/[,،、]/).map((value) => Number(value.trim())).filter((value) => value >= 1 && value <= evidence.length);
    parts.push(
      <span key={`c${index}`} className="rs-cites">
        {numbers.map((number) => {
          const paper = evidence[number - 1];
          return (
            <button
              key={number}
              type="button"
              className="rs-cite"
              onClick={() => onOpenPaper(paper.paper_id)}
              title={paper.title}
              aria-label={t("citeSource", { n: number, title: paper.title })}
            >
              {number}
            </button>
          );
        })}
      </span>,
    );
    last = index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts.map((part, index) => <Fragment key={index}>{part}</Fragment>)}</>;
}

function RefChips({ ids, evidence, onOpenPaper, t }: { ids: string[]; evidence: PaperRef[]; onOpenPaper: (paperId: string) => void; t: Translate }) {
  if (!ids.length) return null;
  return (
    <span className="rs-cites">
      {ids.map((id) => {
        const number = evidence.findIndex((paper) => paper.paper_id === id) + 1;
        if (number < 1) return null;
        const paper = evidence[number - 1];
        return (
          <button key={id} type="button" className="rs-cite" onClick={() => onOpenPaper(id)} title={paper.title} aria-label={t("citeSource", { n: number, title: paper.title })}>
            {number}
          </button>
        );
      })}
    </span>
  );
}

const LEVEL_KEYS: Record<EvidenceLevel, string> = {
  strong: "evidenceStrong",
  moderate: "evidenceModerate",
  limited: "evidenceLimited",
  hypothesis: "evidenceHypothesis",
};

export function AnswerCard({
  answer,
  papers,
  onOpenPaper,
  onClose,
  title,
  t,
}: {
  answer: ResearchAnswer;
  papers: PaperRef[];
  onOpenPaper: (paperId: string) => void;
  onClose?: () => void;
  title: string;
  t: Translate;
}) {
  const evidence = answer.evidence_ids.map((id) => papers.find((paper) => paper.paper_id === id) || { paper_id: id, title: "" });

  const findingList = (label: string, rows: Array<{ text: string; paper_ids: string[]; evidence_level?: EvidenceLevel }>) =>
    rows.length ? (
      <section className="rs-answer-section">
        <h3>{label}</h3>
        <ul>
          {rows.map((row) => (
            <li key={row.text}>
              <span>{row.text}</span> <RefChips ids={row.paper_ids} evidence={evidence} onOpenPaper={onOpenPaper} t={t} />
              {row.evidence_level ? <span className={`rs-level rs-level-${row.evidence_level}`}>{t(LEVEL_KEYS[row.evidence_level])}</span> : null}
            </li>
          ))}
        </ul>
      </section>
    ) : null;

  return (
    <article className="rs-answer" aria-label={title}>
      <header className="rs-answer-head">
        <span className="rs-answer-label"><SparkGlyph />{title}</span>
        {onClose ? (
          <button type="button" className="rs-icon-button rs-icon-small" onClick={onClose} aria-label={t("closeAnswer")} title={t("closeAnswer")}>
            <SmallClose />
          </button>
        ) : null}
      </header>
      {answer.insufficient_evidence && !/\[\s*[\d٠-٩۰-۹]/.test(answer.answer) ? (
        <p className="rs-answer-text">{answer.answer || t("insufficientEvidence")}</p>
      ) : (
        <p className="rs-answer-text" dir="auto">
          <CitedText text={answer.answer} evidence={evidence} onOpenPaper={onOpenPaper} t={t} />
        </p>
      )}
      {answer.approaches.length ? (
        <section className="rs-answer-section">
          <h3>{t("researchApproaches")}</h3>
          <div className="rs-approaches">
            {answer.approaches.map((approach) => (
              <span key={approach.label} className="rs-approach">
                <bdi>{approach.label}</bdi>
                <RefChips ids={approach.paper_ids} evidence={evidence} onOpenPaper={onOpenPaper} t={t} />
              </span>
            ))}
          </div>
        </section>
      ) : null}
      {findingList(t("researchEmerging"), answer.emerging)}
      {findingList(t("researchConflicting"), answer.conflicting)}
      {findingList(t("researchGaps"), answer.gaps)}
      <p className="rs-answer-note">{t("aiNote", { count: answer.evidence_ids.length })}</p>
    </article>
  );
}

export function AnswerSkeleton({ label }: { label: string }) {
  return (
    <div className="rs-answer rs-answer-loading" role="status" aria-label={label}>
      <i className="rs-sk rs-sk-meta" />
      <i className="rs-sk rs-sk-line" />
      <i className="rs-sk rs-sk-line" />
      <i className="rs-sk rs-sk-line rs-sk-short" />
    </div>
  );
}

/* ------------------------------------------------------------------ ask bar */

export function AskBar({
  onAsk,
  loading,
  credits,
  t,
}: {
  onAsk: (question: string) => void;
  loading: boolean;
  credits: number | null;
  t: Translate;
}) {
  const [question, setQuestion] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = question.trim();
    if (value.length < 2 || loading) return;
    onAsk(value);
  }

  return (
    <form className="rs-ask" onSubmit={submit} role="search" aria-label={t("askPlaceholder")}>
      <SparkGlyph />
      <input
        className="rs-ask-input"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder={t("askPlaceholder")}
        aria-label={t("askPlaceholder")}
        dir="auto"
        maxLength={500}
        autoComplete="off"
      />
      {credits !== null ? <span className="rs-ask-credits">{credits === 1 ? t("creditsEstimateOne") : t("creditsEstimate", { count: credits })}</span> : null}
      <button type="submit" className="rs-button rs-button-primary rs-button-small" disabled={loading || question.trim().length < 2} aria-busy={loading}>
        {loading ? <span className="rs-spinner" aria-hidden="true" /> : null}
        {t("askButton")}
      </button>
    </form>
  );
}

/* ------------------------------------------------------------------ icons */

function SparkGlyph() {
  return (
    <svg viewBox="0 0 24 24" width={15} height={15} fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    </svg>
  );
}
function SmallCheck() {
  return (
    <svg viewBox="0 0 24 24" width={11} height={11} fill="none" stroke="currentColor" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}
function SmallClose() {
  return (
    <svg viewBox="0 0 24 24" width={15} height={15} fill="none" stroke="currentColor" strokeWidth={2.1} strokeLinecap="round" aria-hidden="true" focusable="false">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}
