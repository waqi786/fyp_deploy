import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { TrustRing } from "../components/common/TrustRing";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

type ChatResponse = {
  answer: string;
  confidence_score: number;
  citations: string[];
  source_spans?: string[];
  inline_citations: Array<{ marker: string; paper_id: string; title: string; exact_source: string }>;
  highlighted_source_spans: Array<{ paper_id: string; highlight: string; reason: string }>;
  retrieved_chunks?: string[];
  retrieval_mode: string;
  chat_scope: string;
  condensed_question?: string | null;
  follow_up_suggestions: string[];
  automatic_literature_suggestions: string[];
  citation_context_answers: string[];
  citation_sentiment_labels: Array<{ source_paper_id: string; target_paper_id: string; sentiment: string; context: string }>;
  comparison_from_chat?: string | null;
  voice_output_text?: string | null;
  feedback_token?: string | null;
  export_markdown?: string | null;
  shareable_thread_token?: string | null;
  traceability_coverage: number;
  traceability_passed?: boolean;
  traceable_sentences?: Array<{ sentence?: string; source_span?: string; traceable?: boolean }>;
  unsupported_sentences?: string[];
  fallback_reason?: string | null;
  session_turns?: number;
  generated_at?: string | null;
};

type ChatTurn = {
  question: string;
  answer: string;
  confidence: number;
  citations: string[];
  at: string;
};

const demoDocuments = [
  {
    paper_id: "p1",
    title: "Robust Deepfake Detection via Frequency-Aware Attention Networks",
    content:
      "Hybrid BM25 and dense retrieval improves grounded academic chat. Figure 1 shows robustness under JPEG recompression. Table 1 reports benchmark AUC gains. The equation score = bm25 + dense is used for reciprocal rank fusion. def rank(): return confidence.",
    figures: [{ figure_id: "fig-1", caption: "Figure 1: Accuracy under recompression", description: "AUC remains stable after JPEG recompression" }],
    tables: [{ table_id: "tab-1", caption: "Table 1: cross-dataset benchmark", summary: "Hybrid retrieval wins on grounded answer accuracy" }],
    equations: ["score = bm25 + dense"],
    code_snippets: ["def rank(answer): return answer.confidence"],
  },
  {
    paper_id: "p2",
    title: "Dense Retrieval Baseline for Research QA",
    content:
      "Dense retrieval is a semantic baseline for research question answering. It is cited as a comparison method when evaluating hybrid retrieval and source-grounded answers.",
  },
];

const demoEdges = [
  {
    source_paper_id: "p1",
    target_paper_id: "p2",
    context: "supports the dense retrieval baseline used for comparison",
    sentiment: "support",
  },
];

const demoChatResponse: ChatResponse = {
  answer:
    "Only one of the workspace papers tests recompression robustness directly. Chen et al. evaluate JPEG recompression and resizing, which approximates messaging-app pipelines, while the comparison baseline paper mainly supports the dense-retrieval setup rather than WhatsApp-style deployment evidence.",
  confidence_score: 0.88,
  citations: ["p1", "p2"],
  source_spans: ["p1: Figure 1 shows robustness under JPEG recompression.", "p2: Dense retrieval is cited as a comparison method."],
  inline_citations: [
    { marker: "[1]", paper_id: "p1", title: demoDocuments[0].title, exact_source: "Figure 1 shows robustness under JPEG recompression. Table 1 reports benchmark AUC gains." },
    { marker: "[2]", paper_id: "p2", title: demoDocuments[1].title, exact_source: "Dense retrieval is cited as a comparison method when evaluating hybrid retrieval." },
  ],
  highlighted_source_spans: [
    { paper_id: "p1", highlight: "Figure 1 shows robustness under JPEG recompression.", reason: "Direct evidence for the answer." },
  ],
  retrieved_chunks: ["Figure 1 shows robustness under JPEG recompression.", "Dense retrieval is cited as a comparison method."],
  retrieval_mode: "text+multimodal",
  chat_scope: "workspace-wide multi-paper",
  condensed_question: "Compare these papers and explain why p1 cites p2.",
  follow_up_suggestions: ["Show exact source spans", "Compare robustness claims", "Create a gap report"],
  automatic_literature_suggestions: ["Messaging-app recompression robustness", "Compression-aware forgery detection"],
  citation_context_answers: ["p1 cites p2 to position dense retrieval as a baseline for hybrid evidence retrieval."],
  citation_sentiment_labels: [
    { source_paper_id: "p1", target_paper_id: "p2", sentiment: "support", context: "supports the dense retrieval baseline used for comparison" },
  ],
  comparison_from_chat: "p1 has stronger multimodal evidence; p2 is mainly a retrieval baseline.",
  voice_output_text: "The answer is grounded in two source passages with high confidence.",
  feedback_token: "demo-feedback-token",
  export_markdown: "## Grounded answer\nOnly one paper tests recompression robustness directly.",
  shareable_thread_token: "demo-thread-token",
  traceability_coverage: 0.92,
  traceability_passed: true,
  unsupported_sentences: [],
  fallback_reason: null,
  session_turns: 1,
};

function confidenceLabel(value: number) {
  return `${Math.round(value * 100)}%`;
}

function downloadTextFile(filename: string, body: string, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([body], { type: mime });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(href);
}

export function ChatPage() {
  const [question, setQuestion] = useState("Compare these papers and explain why p1 cites p2.");
  const [language, setLanguage] = useState("en");
  const [response, setResponse] = useState<ChatResponse | null>(demoChatResponse);
  const [streamed, setStreamed] = useState("");
  const [status, setStatus] = useState("Grounded answer ready");
  const [showWork, setShowWork] = useState(true);
  const [useWorkspaceDocs, setUseWorkspaceDocs] = useState(true);
  const [history, setHistory] = useState<ChatTurn[]>([
    {
      question: "Compare these papers and explain why p1 cites p2.",
      answer: demoChatResponse.answer,
      confidence: demoChatResponse.confidence_score,
      citations: demoChatResponse.citations,
      at: "demo",
    },
  ]);

  const chatHealth = useMemo(() => {
    if (!response) {
      return { label: "Not asked", tone: "neutral", explanation: "Ask a question to generate a grounded answer." };
    }
    if (response.fallback_reason) {
      return { label: "Needs sources", tone: "coral", explanation: response.fallback_reason };
    }
    if ((response.traceability_coverage || 0) >= 0.75 && response.confidence_score >= 0.7) {
      return { label: "High grounding", tone: "green", explanation: "Answer has strong retrieved-source coverage." };
    }
    return { label: "Review needed", tone: "gold", explanation: "Inspect source spans before trusting this answer." };
  }, [response]);

  async function askResora(options?: { withoutDocs?: boolean; nextQuestion?: string }) {
    const activeQuestion = options?.nextQuestion || question;
    setQuestion(activeQuestion);
    setStatus("Retrieving hybrid BM25+dense evidence...");
    setStreamed("");
    if (options?.withoutDocs || !useWorkspaceDocs) {
      const fallbackAnswer =
        language === "ur"
          ? "Mujhe abhi yaqeen se jawab dene ke liye document content chahiye. Paper text dein, phir main grounded jawab dunga."
          : "I am not sure yet because no document content was provided. Add paper text and I will ground the answer in retrieved chunks.";
      const fallback: ChatResponse = {
        answer: fallbackAnswer,
        confidence_score: 0,
        citations: [],
        source_spans: [],
        inline_citations: [],
        highlighted_source_spans: [],
        retrieved_chunks: [],
        retrieval_mode: "none",
        chat_scope: "none",
        condensed_question: activeQuestion,
        follow_up_suggestions: ["Add paper text for fully grounded RAG chat.", "Open workspace-wide chat after selecting papers."],
        automatic_literature_suggestions: ["Search fresh papers related to this question."],
        citation_context_answers: [],
        citation_sentiment_labels: [],
        comparison_from_chat: null,
        voice_output_text: fallbackAnswer,
        feedback_token: `local-fallback-${history.length}`,
        export_markdown: `## Question\n${activeQuestion}\n\n## Answer\n${fallbackAnswer}`,
        shareable_thread_token: `local-thread-${history.length}`,
        traceability_coverage: 0,
        traceability_passed: false,
        unsupported_sentences: [fallbackAnswer],
        fallback_reason: "NO_DOCUMENTS",
        session_turns: history.length + 1,
      };
      setResponse(fallback);
      setStatus("Fallback: NO_DOCUMENTS");
      setHistory((current) => [
        ...current.slice(-5),
        { question: activeQuestion, answer: fallbackAnswer, confidence: 0, citations: [], at: new Date().toLocaleTimeString() },
      ]);
      return;
    }
    const result = await fetch(`${apiBaseUrl}/chat/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: "browser-rag-demo",
        question: activeQuestion,
        language,
        show_your_work: showWork,
        voice_output: true,
        conversation_history: history.map((turn) => `${turn.question}\n${turn.answer}`).slice(-4),
        documents: demoDocuments,
        citation_edges: demoEdges,
      }),
    });
    const data = (await result.json()) as ChatResponse;
    setResponse(data);
    setStatus(data.fallback_reason ? `Fallback: ${data.fallback_reason}` : "Grounded answer ready");
    setHistory((current) => [
      ...current.slice(-5),
      {
        question: activeQuestion,
        answer: data.answer,
        confidence: data.confidence_score,
        citations: data.citations,
        at: new Date().toLocaleTimeString(),
      },
    ]);
  }

  async function streamAnswer() {
    setStreamed("");
    setStatus("Streaming answer tokens...");
    const result = await fetch(`${apiBaseUrl}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: "browser-rag-demo-stream",
        question,
        language,
        show_your_work: showWork,
        documents: useWorkspaceDocs ? demoDocuments : [],
        citation_edges: demoEdges,
      }),
    });
    const reader = result.body?.getReader();
    if (!reader) {
      setStatus("Streaming unavailable in this browser");
      return;
    }
    const decoder = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      setStreamed((current) => `${current}${decoder.decode(value)}`);
    }
    setStatus("Stream complete");
  }

  async function sendFeedback(rating: number) {
    if (!response?.feedback_token) {
      setStatus("Generate an answer before sending feedback");
      return;
    }
    await fetch(`${apiBaseUrl}/chat/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback_token: response.feedback_token, rating, helpful: rating >= 4, note: "Browser QA feedback" }),
    });
    setStatus(`Feedback stored: ${rating}/5`);
  }

  async function pinAnswer() {
    if (!response?.feedback_token || !response.shareable_thread_token) {
      setStatus("Generate an answer before pinning");
      return;
    }
    await fetch(`${apiBaseUrl}/chat/pin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        feedback_token: response.feedback_token,
        shareable_thread_token: response.shareable_thread_token,
        answer: response.answer,
        starred: true,
      }),
    });
    setStatus("Answer pinned and starred");
  }

  function speakAnswer() {
    if (!response?.voice_output_text || !("speechSynthesis" in window)) {
      setStatus("Voice output unavailable until an answer is generated");
      return;
    }
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(response.voice_output_text));
    setStatus("Voice output started");
  }

  function captureVoiceInput() {
    setStatus("Voice input listening or fallback ready");
    const SpeechRecognition = (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike }).SpeechRecognition ||
      (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike }).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setQuestion("Which figure or table best supports the answer?");
      setStatus("Voice input unavailable here, inserted a voice-style question");
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = language === "ur" ? "ur-PK" : "en-US";
    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      const transcript = event.results?.[0]?.[0]?.transcript;
      if (transcript) {
        setQuestion(transcript);
        setStatus("Voice transcript captured");
      }
    };
    recognition.onerror = () => {
      setQuestion("Which figure or table best supports the answer?");
      setStatus("Voice input unavailable here, inserted a voice-style question");
    };
    recognition.start();
  }

  async function copyShareLink() {
    const token = response?.shareable_thread_token || "no-thread";
    const shareText = `${window.location.origin}/chat?thread=${token}`;
    try {
      await navigator.clipboard?.writeText(shareText);
      setStatus("Shareable chat thread copied");
    } catch {
      setStatus(`Share token ready: ${token}`);
    }
  }

  function exportConversation() {
    const markdown = response?.export_markdown || history.map((turn) => `## ${turn.question}\n${turn.answer}`).join("\n\n");
    downloadTextFile("resora-chat-thread.md", markdown, "text/markdown;charset=utf-8");
    setStatus("Conversation exported as Markdown");
  }

  function handleFollowUp(item: string) {
    void askResora({ nextQuestion: item });
  }

  return (
    <div className="chat-shell">
      <motion.section initial={false} animate={{ opacity: 1, y: 0 }} className="chat-main space-y-5">
        <section className="chat-hero">
          <div>
            <div className="flex flex-wrap gap-2">
              <span className="status-pill status-pill-green">Hybrid RAG</span>
              <span className="status-pill status-pill-teal">Sources visible</span>
              <span className="status-pill status-pill-gold">Workspace chat</span>
            </div>
            <p className="chat-kicker">Paper chat</p>
            <h2 className="chat-title">Ask papers. Get cited answers.</h2>
            <p className="chat-subtitle">
              Clear answers with sources, confidence, and follow-up questions.
            </p>
          </div>
          <div className="chat-health-card">
            <p className="resora-label">Answer health</p>
            <strong>{chatHealth.label}</strong>
            <p>{chatHealth.explanation}</p>
            <div className="mt-4">
              <TrustRing value={Math.round((response?.confidence_score || 0) * 100)} max={100} suffix="%" tone={chatHealth.tone === "coral" ? "coral" : "teal"} />
            </div>
          </div>
        </section>

        <section className="panel-surface p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="resora-label">Ask</p>
              <h3 className="mt-2 font-display text-[24px] font-normal leading-tight text-text">Talk to your research</h3>
            </div>
            <span className={response?.fallback_reason ? "status-pill status-pill-coral" : "status-pill status-pill-gold"}>{status}</span>
          </div>

          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            className="resora-input min-h-[110px] resize-y"
            placeholder="Ask a single-paper or workspace-wide question..."
          />

          <div className="mt-4 grid gap-3 md:grid-cols-[160px_1fr]">
            <label className="grid gap-2">
              <span className="resora-label">Chat language</span>
              <select aria-label="Chat answer language" value={language} onChange={(event) => setLanguage(event.target.value)} className="resora-input">
                <option value="en">English</option>
                <option value="ur">Urdu</option>
              </select>
            </label>
            <div className="chat-toggle-row">
              <button type="button" onClick={() => setUseWorkspaceDocs((value) => !value)} className={useWorkspaceDocs ? "resora-button-primary" : "resora-button-secondary"}>
                {useWorkspaceDocs ? "Sources on" : "No sources"}
              </button>
              <button type="button" onClick={() => setShowWork((value) => !value)} className={showWork ? "resora-button-ai" : "resora-button-secondary"}>
                {showWork ? "Proof on" : "Proof off"}
              </button>
              <button type="button" onClick={captureVoiceInput} className="resora-button-secondary">
                Voice input
              </button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button type="button" onClick={() => void askResora()} className="resora-button-primary">
              Ask Resora
            </button>
            <button type="button" onClick={streamAnswer} className="resora-button-ai">
              Stream tokens
            </button>
            <button type="button" onClick={() => void askResora({ withoutDocs: true })} className="resora-button-danger">
              No-source test
            </button>
            <button type="button" onClick={speakAnswer} className="resora-button-secondary">
              Voice output
            </button>
          </div>
        </section>

        {streamed ? (
          <section className="paper-quote">
            <p className="resora-label">Streaming token output</p>
            <p className="mt-3 text-sm leading-7">{streamed}</p>
          </section>
        ) : null}

        {response ? (
          <section className="chat-answer-card">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="status-pill status-pill-gold">{response.chat_scope}</span>
                <span className="status-pill status-pill-neutral">{response.retrieval_mode}</span>
                <span className={response.traceability_passed ? "status-pill status-pill-green" : "status-pill status-pill-coral"}>
                  Trace {Math.round(response.traceability_coverage * 100)}%
                </span>
                <span className="status-pill status-pill-teal">{response.session_turns || history.length} turns</span>
              </div>
              <TrustRing value={Math.round(response.confidence_score * 100)} max={100} suffix="%" />
            </div>

            <div className="rounded-[18px] border border-border-hi bg-panel p-5">
              <p className="whitespace-pre-line text-sm leading-7 text-text">{response.answer}</p>
            </div>

            <div className="chat-action-grid mt-4">
              <button type="button" onClick={() => void sendFeedback(5)} className="resora-button-primary">
                Helpful 5/5
              </button>
              <button type="button" onClick={() => void sendFeedback(2)} className="resora-button-secondary">
                Needs work
              </button>
              <button type="button" onClick={() => void pinAnswer()} className="resora-button-secondary">
                Pin/star answer
              </button>
              <button type="button" onClick={exportConversation} className="resora-button-ai">
                Export thread
              </button>
              <button type="button" onClick={() => void copyShareLink()} className="resora-button-secondary">
                Share thread
              </button>
            </div>
          </section>
        ) : null}

        <section className="panel-surface p-5">
          <p className="resora-label">Recent chats</p>
          <div className="chat-history mt-4">
            {history.map((turn, index) => (
              <div key={`${turn.question}-${index}`}>
                <span>{turn.at}</span>
                <strong>{turn.question}</strong>
                <p>{turn.answer}</p>
                <em>{confidenceLabel(turn.confidence)} confidence | {turn.citations.join(", ") || "no citations"}</em>
              </div>
            ))}
          </div>
        </section>
      </motion.section>

      <aside className="chat-side space-y-4">
        <InfoPanel title="Citations">
          {response?.inline_citations?.length ? response.inline_citations.map((citation) => (
            <div key={`${citation.marker}-${citation.paper_id}`} className="rounded-[12px] border border-border bg-panel-raised p-3">
              <p className="font-mono text-[11px] text-gold-text">{citation.marker} {citation.paper_id}</p>
              <p className="mt-1 text-xs text-text">{citation.title}</p>
              <p className="mt-2 text-xs leading-5 text-text-dim">{citation.exact_source}</p>
            </div>
          )) : <p className="text-xs text-text-dim">Ask a sourced question to see citations.</p>}
        </InfoPanel>

        <InfoPanel title="Source trace">
          {(response?.highlighted_source_spans || []).map((span) => (
            <div key={`${span.paper_id}-${span.highlight}`} className="rounded-[12px] border border-border bg-panel-raised p-3">
              <p className="font-mono text-[11px] text-teal-text">{span.paper_id}</p>
              <p className="mt-2 text-xs leading-5 text-text-dim">{span.highlight}</p>
              <p className="mt-2 text-[11px] text-text-faint">{span.reason}</p>
            </div>
          ))}
          {(response?.retrieved_chunks || []).slice(0, 3).map((chunk, index) => (
            <p key={`${chunk}-${index}`} className="rounded-[10px] border border-border bg-panel p-3 text-xs leading-5 text-text-dim">
              Retrieved chunk {index + 1}: {chunk}
            </p>
          ))}
        </InfoPanel>

        <InfoPanel title="Context">
          {(response?.citation_context_answers || []).map((item) => (
            <p key={item} className="rounded-[10px] border border-border bg-panel-raised p-3 text-xs leading-5 text-text-dim">{item}</p>
          ))}
          {(response?.citation_sentiment_labels || []).map((edge) => (
            <p key={`${edge.source_paper_id}-${edge.target_paper_id}`} className="text-xs leading-6 text-text-dim">
              <span className="text-gold-text">{edge.sentiment}</span> {edge.source_paper_id} to {edge.target_paper_id}: {edge.context}
            </p>
          ))}
          {response?.comparison_from_chat ? <p className="mt-3 rounded-[10px] border border-border-hi p-3 text-xs text-text">{response.comparison_from_chat}</p> : null}
        </InfoPanel>

        <InfoPanel title="Next questions">
          {(response?.follow_up_suggestions || []).map((item) => (
            <button key={item} type="button" onClick={() => handleFollowUp(item)} className="focus-gold block w-full rounded-[12px] border border-border bg-panel-raised p-3 text-left text-xs leading-5 text-text-dim transition hover:border-gold hover:text-text">
              {item}
            </button>
          ))}
        </InfoPanel>

        <InfoPanel title="More papers">
          {(response?.automatic_literature_suggestions || []).map((item) => (
            <p key={item} className="rounded-[10px] border border-border bg-panel-raised p-3 text-xs leading-5 text-text-dim">{item}</p>
          ))}
        </InfoPanel>
      </aside>
    </div>
  );
}

type SpeechRecognitionEventLike = {
  results?: ArrayLike<ArrayLike<{ transcript: string }>>;
};

type SpeechRecognitionLike = {
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  start: () => void;
};

function InfoPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="panel-surface p-4">
      <p className="resora-label">{title}</p>
      <div className="mt-3 space-y-3">{children}</div>
    </div>
  );
}
