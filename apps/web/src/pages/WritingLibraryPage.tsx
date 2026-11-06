import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { TrustRing } from "../components/common/TrustRing";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

type WritingResponse = {
  outline: string[];
  sections: Record<string, string>;
  standalone_generators: Record<string, string>;
  target_style_adaptation: Record<string, string>;
  paragraph_citation_map: Array<Record<string, string>>;
  citation_style_previews: Record<string, string>;
  reference_list: string[];
  plagiarism_report: Record<string, string | number | string[]>;
  readability_score: number;
  academic_style_corrections: string[];
  transition_suggestions: string[];
  citation_diversity_nudge: string;
  figure_table_insertions: Array<Record<string, string>>;
  export_formats: Record<string, string>;
  export_artifacts: Array<{ format: string; file_name: string; storage_uri?: string | null; byte_size: number; content_type?: string | null }>;
  overleaf_export: string;
  word_count_report: Record<string, string | number>;
  section_regeneration: Record<string, string>;
  cover_letter: string;
  peer_review_response: string;
  version_history: Array<Record<string, string>>;
  rollback_preview?: Record<string, string> | null;
  track_changes: Array<Record<string, string>>;
  coauthor_comments: string[];
  watermark?: string | null;
  confidence_score: number;
};

type LibraryResponse = {
  saved_items: Array<{ paper_id: string; title: string; folder?: string; tags: string[]; highlights: string[]; citation_velocity: number; open_access_resolution?: string }>;
  bibliography_export: string;
  duplicate_groups: Record<string, string[]>;
  unread_queue: string[];
  folder_tree: Record<string, string[]>;
  tag_index: Record<string, string[]>;
  citation_impact_tracking: Record<string, number[]>;
  personal_citation_graph: { nodes: Array<Record<string, string>>; edges: Array<Record<string, string>> };
  full_library_bibliography_exports: Record<string, string>;
  annotated_pdf_library: Record<string, string[]>;
  persistence_uri?: string | null;
};

type CitationFeatureRow = {
  feature: string;
  status: string;
  evidence: string;
};

type Category4ReferenceSuite = {
  completion: CitationFeatureRow[];
  dedupedReferences: Array<Record<string, string | number>>;
  citationGraph: { nodes: Array<Record<string, string>>; edges: Array<Record<string, string>> };
  recommendations: Array<Record<string, string>>;
  styleCoverage: Array<Record<string, string | number>>;
  cleanupQueue: Array<Record<string, string>>;
  cloudAndTeam: Array<Record<string, string>>;
  prioritySort: Array<Record<string, string | number>>;
  missingReferences: Array<Record<string, string>>;
  fatigue: Array<Record<string, string | number>>;
  restoration: Array<Record<string, string>>;
  imports: Array<Record<string, string>>;
  pdfRenames: Array<Record<string, string>>;
  folders: Array<Record<string, string>>;
  contextMemory: Array<Record<string, string>>;
  uncited: Array<Record<string, string>>;
  teamDedup: Array<Record<string, string | number>>;
  journalSuggestions: Array<Record<string, string | number>>;
  citationProjection: Array<Record<string, string | number>>;
  verification: Array<Record<string, string>>;
  selfCitation: Array<Record<string, string | number>>;
  masterExports: Array<Record<string, string>>;
  integrations: Array<Record<string, string>>;
  retractions: Array<Record<string, string>>;
};

type Category5DraftingSuite = {
  completion: CitationFeatureRow[];
  abstracts: Array<Record<string, string>>;
  sectionBuilders: Array<Record<string, string | number>>;
  titleHooks: Array<Record<string, string>>;
  outline: Array<Record<string, string | number>>;
  sentenceTools: Array<Record<string, string>>;
  quality: Array<Record<string, string | number>>;
  coherence: Array<Record<string, string | number>>;
  toneLexicon: Array<Record<string, string>>;
  reviewerPackage: Array<Record<string, string>>;
  statements: Array<Record<string, string>>;
  originality: Array<Record<string, string | number>>;
  versions: Array<Record<string, string>>;
};

type Category6StyleSuite = {
  completion: CitationFeatureRow[];
  paraphrases: Array<Record<string, string>>;
  grammarFixes: Array<Record<string, string>>;
  voiceAndTone: Array<Record<string, string>>;
  wordChoice: Array<Record<string, string | number>>;
  readability: Array<Record<string, string | number>>;
  structureChecks: Array<Record<string, string>>;
  punctuationQuotes: Array<Record<string, string>>;
  phrasebankHedging: Array<Record<string, string>>;
  consistency: Array<Record<string, string>>;
  draftComparison: Array<Record<string, string>>;
  revisionLog: Array<Record<string, string>>;
};

type Category7StemSuite = {
  completion: CitationFeatureRow[];
  equations: Array<Record<string, string>>;
  codeTools: Array<Record<string, string | number>>;
  latexWorkflow: Array<Record<string, string>>;
  reproducibility: Array<Record<string, string | number>>;
  algorithms: Array<Record<string, string>>;
  validators: Array<Record<string, string | number>>;
  chemistryBio: Array<Record<string, string>>;
  exports: Array<Record<string, string>>;
};

type Category10SubmissionSuite = {
  completion: CitationFeatureRow[];
  journalMatches: Array<Record<string, string | number>>;
  journalMetrics: Array<Record<string, string | number>>;
  submissionRisk: Array<Record<string, string | number>>;
  issueFees: Array<Record<string, string | number>>;
  formattingAssets: Array<Record<string, string>>;
  checklistReview: Array<Record<string, string | number>>;
  ethicsSafety: Array<Record<string, string | number>>;
  integrationsForms: Array<Record<string, string>>;
  peopleTargets: Array<Record<string, string | number>>;
  tracking: Array<Record<string, string | number>>;
};

type Category11GrantSuite = {
  completion: CitationFeatureRow[];
  opportunities: Array<Record<string, string | number>>;
  fitScoring: Array<Record<string, string | number>>;
  proposalPackage: Array<Record<string, string | number>>;
  agencyTemplates: Array<Record<string, string>>;
  budget: Array<Record<string, string | number>>;
  peopleSupport: Array<Record<string, string>>;
  impactData: Array<Record<string, string>>;
  timeline: Array<Record<string, string | number>>;
  compliance: Array<Record<string, string | number>>;
  integrationsReports: Array<Record<string, string>>;
};

type Category17PresentationSuite = {
  completion: CitationFeatureRow[];
  slideDeck: Array<Record<string, string | number>>;
  scriptsTiming: Array<Record<string, string | number>>;
  qaPrep: Array<Record<string, string | number>>;
  audienceFormats: Array<Record<string, string | number>>;
  mediaAssets: Array<Record<string, string | number>>;
  designExport: Array<Record<string, string | number>>;
  rehearsalCards: Array<Record<string, string | number>>;
};

const category4Features = [
  "Auto-deduplication",
  "Cited By graph",
  "Citation recommendation",
  "Contextual citation formatting",
  "10,000+ citation styles",
  "Reference cleanup",
  "Cloud backup",
  "Collaborative shared library",
  "Citation priority sorter",
  "Missing reference finder",
  "Citation fatigue detector",
  "Historical reference restoration",
  "BibTeX/EndNote/RIS multi-import",
  "Auto-PDF renaming",
  "Folder/project tagging",
  "Citation context memory",
  "Uncited reference alert",
  "Duplicate removal across teams",
  "Auto-suggest journals",
  "Citation count projection",
  "Reference verification",
  "Self-citation tracker",
  "Master bibliography exporter",
  "Word/LibreOffice/Overleaf integration",
  "Retraction auto-update",
];

const category5Features = [
  "Abstract generator",
  "Introduction writer",
  "Methods section auto-builder",
  "Results narrator",
  "Discussion starter",
  "Conclusion paraphraser",
  "Headline/hook generator",
  "Running title generator",
  "AI outlining",
  "Sentence expansion",
  "Sentence compression",
  "Blind spot detector",
  "Structure quality score",
  "Coherence mapping",
  "Tone alignment",
  "Field-specific lexicon booster",
  "Response-to-reviewer drafting",
  "Cover letter crafter",
  "Data availability statement writer",
  "Author contribution statement builder",
  "Conflict of interest form filler",
  "Sentence transitions",
  "Show Don't Tell converter",
  "Plagiarism-free drafting",
  "Version history and branching",
];

const category6Features = [
  "Advanced paraphraser",
  "Academic tone checker",
  "Active/passive voice converter",
  "Grammar and punctuation fix",
  "Wordiness reduction",
  "Transition word recommender",
  "Gender-neutral language checker",
  "Inclusive language scanner",
  "Overused word analyzer",
  "Synonym variation",
  "Readability scoring",
  "Sentence length balancer",
  "Parallel structure enforcer",
  "Dangling modifier detection",
  "Subject-verb agreement checker",
  "Punctuation guide",
  "Quotation integration",
  "Academic phrasebank access",
  "Hedging language adjuster",
  "Format consistency checker",
  "Footnote/endnote style checker",
  "Abbreviation introducer",
  "Number/unit consistency",
  "Draft comparison",
  "Revision history log",
];

const category7Features = [
  "LaTeX equation OCR",
  "Equation meaning extraction",
  "Math-to-code converter",
  "Code comment generator",
  "Code syntax highlighter",
  "Inline LaTeX auto-complete",
  "BibTeX auto-generation",
  "Overleaf one-click sync",
  "R/Python package citation finder",
  "Reproducible environment capture",
  "Jupyter notebook integration",
  "Algorithm pseudocode formatter",
  "Matrix dimension validator",
  "Unit converter",
  "Statistical notation checker",
  "Symbol pronunciation",
  "Chemical equation balancer",
  "Reaction mapping",
  "DNA sequence formatter",
  "Code plagiarism checker",
  "Algorithm complexity analyzer",
  "API code snippet generator",
  "SVG/PDF equation export",
  "LaTeX error decoder",
  "Math keyboard shortcuts",
];

const category10Features = [
  "Journal suggestor",
  "Journal ranking display",
  "Acceptance rate estimator",
  "Turnaround time predictor",
  "Special issue alerts",
  "Open access fee calculator",
  "APC waiver/applicability checker",
  "Guidelines converter",
  "Cover art generator",
  "Graphical abstract auto-resizer",
  "Submission checklist generator",
  "Pre-submission review",
  "Plagiarism pre-check",
  "iThenticate score simulator",
  "Target audience identifier",
  "Predatory journal detector",
  "Submission system integration",
  "Auto-populate author forms",
  "Conflict of interest matching",
  "Fast-track recommendation",
  "Journal specialization mapper",
  "Recent trends in target journal",
  "Editor suggestion",
  "Reviewer suggestion",
  "Post-submission tracker",
];

const category11Features = [
  "Funding opportunity aggregator",
  "Grant call filtering",
  "Grant fit score",
  "Grant proposal outliner",
  "NIH/ERC/UKRI template engine",
  "Budget justification writer",
  "Bio-sketch formatter",
  "Letters of support drafter",
  "Impact statement crafter",
  "Broader impacts generator",
  "Data management plan generator",
  "Timeline/Gantt chart builder",
  "Grant co-ordination calendar",
  "Previous funded projects finder",
  "Collaborator expertise mapper",
  "Abstract rewriting for grants",
  "Evaluation criteria checker",
  "Grant rebuttal assistant",
  "Multi-currency budget converter",
  "Indirect/F&A cost calculator",
  "Institutional endorsement tracker",
  "Letter of Intent (LOI) drafting",
  "Grant database integration",
  "No-cost extension justification writer",
  "Progress report writer",
];

const category17Features = [
  "Auto-PPT Generation",
  "Talk Script Writer",
  "Presentation Timing Estimator",
  "Q&A Predictor",
  "Speaker Notes Builder",
  "Audience Level Adjustment",
  "Poster Maker",
  "3-Minute Thesis Generator",
  "Elevator Pitch Builder",
  "Social Media Carousel Builder",
  "Conference Abstract Formatter",
  "Pre-Recorded Narration",
  "Video Introduction",
  "Infographic Data Cards",
  "Interview Preparation Assistant",
  "Highlight Reel",
  "Lay Summary for Press",
  "Slide Design Recommendations",
  "Animation Suggestion",
  "Export to Prezi/Canva",
  "Bibliography Slide Auto-Generator",
  "Title Slide Designer",
  "Rehearsal Mode",
  "Flashcard Generator",
  "Virtual Background Creator",
];



const demoPaper = {
  paper_id: "w1",
  title: "Hybrid Retrieval Benchmark Dataset",
  abstract: "This dataset benchmark compares multimodal retrieval, reports benchmark scores, and discusses future work.",
  year: 2025,
  venue: "Journal of AI Systems",
  doi: "10.1000/resora.1",
  url: "https://example.org/w1",
  pdf_url: "https://example.org/w1.pdf",
  citation_count: 55,
  reference_count: 21,
  is_open_access: true,
  authors: [{ name: "Ali Khan" }, { name: "Sara Noor" }],
  source: "openalex",
};

const demoWriting: WritingResponse = {
  outline: ["Abstract", "Introduction", "Related Work", "Method Comparison", "Research Gaps", "Conclusion"],
  sections: {
    Abstract: "This review synthesizes hybrid retrieval, multimodal evidence extraction, and trust-aware academic writing systems with citation-grounded claims.",
    Introduction: "AI research assistants increasingly combine search, reading, comparison, critique, and writing workflows into a single research operating system.",
    "Related Work": "Prior tools cover discovery or summarization separately, but fewer systems connect multimodal understanding with traceable writing.",
    "Method Comparison": "Hybrid retrieval and citation-context analysis improve answer grounding compared with isolated semantic retrieval.",
    "Research Gaps": "Cross-lingual, figure-aware, and confidence-scored research workflows remain underexplored in low-resource academic contexts.",
    Conclusion: "A production-grade assistant should expose confidence, citation diversity, self-critique, and export-ready scholarly formatting before users trust the draft.",
  },
  standalone_generators: { Abstract: "Generated", Introduction: "Generated", Conclusion: "Generated", "Related Work": "Generated" },
  target_style_adaptation: { target: "IEEE Access", tone: "formal academic", citation_style: "APA" },
  paragraph_citation_map: [
    { paragraph: "Hybrid retrieval improves grounding.", citation: "Khan & Noor, 2025" },
    { paragraph: "Figure-aware extraction reduces unsupported claims.", citation: "Resora evidence audit, 2026" },
  ],
  citation_style_previews: {
    APA: "Khan, A., & Noor, S. (2025). Hybrid Retrieval Benchmark Dataset.",
    IEEE: "[1] A. Khan and S. Noor, Hybrid Retrieval Benchmark Dataset, 2025.",
    MLA: "Khan, Ali, and Sara Noor. Hybrid Retrieval Benchmark Dataset.",
    Chicago: "Khan, Ali, and Sara Noor. 2025. Hybrid Retrieval Benchmark Dataset.",
    Vancouver: "Khan A, Noor S. Hybrid Retrieval Benchmark Dataset. 2025.",
  },
  reference_list: ["Khan, A., & Noor, S. (2025). Hybrid Retrieval Benchmark Dataset."],
  plagiarism_report: { plagiarism_risk: "low", similarity_percent: 7, matched_sources: [] },
  readability_score: 82,
  academic_style_corrections: ["Replace broad claims with source-cited comparisons.", "Use consistent terminology for hybrid retrieval.", "Mark inferred claims before final export."],
  transition_suggestions: ["Bridge the comparison section into the research-gap section with a limitation-focused transition."],
  citation_diversity_nudge: "Add at least two non-benchmark sources before final export.",
  figure_table_insertions: [{ figure_id: "fig-1", caption: "Retrieval accuracy across benchmark datasets" }, { table_id: "tab-1", caption: "Benchmark comparison table" }],
  export_formats: { docx: "ready", latex: "ready", pdf: "ready", ris: "ready" },
  export_artifacts: [
    { format: "DOCX", file_name: "resora-review.docx", byte_size: 84200, content_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
    { format: "LaTeX", file_name: "resora-review.tex", byte_size: 18300, content_type: "text/x-tex" },
    { format: "PDF", file_name: "resora-review.pdf", byte_size: 126000, content_type: "application/pdf" },
  ],
  overleaf_export: "overleaf://resora-review",
  word_count_report: { actual: 1180, target: 1200 },
  section_regeneration: { RelatedWork: "Ready for section-only regeneration", Conclusion: "Ready for tone/formality pass" },
  cover_letter: "Dear Editor, please consider this review for IEEE Access.",
  peer_review_response: "We thank the reviewers and have strengthened the evidence traceability section.",
  version_history: [{ version: "v1", note: "Initial generated review" }, { version: "v2", note: "Added self-critique pass" }],
  rollback_preview: { version: "v1", note: "Rollback available" },
  track_changes: [{ before: "AI tools are useful.", after: "Source-grounded AI tools can reduce unsupported claims." }],
  coauthor_comments: ["Supervisor: strengthen conclusion with more evidence.", "Co-author: add one table before PDF export."],
  watermark: "AI-assisted draft; verify all citations before submission.",
  confidence_score: 0.89,
};

const demoLibrary: LibraryResponse = {
  saved_items: [
    { paper_id: "w1", title: "Hybrid Retrieval Benchmark Dataset", folder: "Core", tags: ["rag", "benchmark"], highlights: ["Hybrid retrieval improves accuracy."], citation_velocity: 12, open_access_resolution: "Open access PDF resolved" },
    { paper_id: "w2", title: "Trust-Aware Literature Review Systems", folder: "Core", tags: ["trust", "writing"], highlights: ["Citation audit reduces unsupported claims."], citation_velocity: 8, open_access_resolution: "Unpaywall fallback available" },
    { paper_id: "w3", title: "Figure-Aware Academic Writing", folder: "Figures", tags: ["multimodal", "draft"], highlights: ["Tables and figures need explicit source anchors."], citation_velocity: 5, open_access_resolution: "PDF queued" },
  ],
  bibliography_export: "@article{khan2025hybrid,title={Hybrid Retrieval Benchmark Dataset}}",
  duplicate_groups: { doi_match: ["w1", "w2"] },
  unread_queue: ["w2", "w3"],
  folder_tree: { Core: ["w1", "w2"], Drafts: ["review-v1"], Figures: ["w3"] },
  tag_index: { rag: ["w1"], trust: ["w2"], multimodal: ["w3"] },
  citation_impact_tracking: { w1: [12, 21, 34, 55], w2: [2, 4, 8], w3: [1, 3, 5] },
  personal_citation_graph: { nodes: [{ id: "w1", label: "Hybrid Retrieval" }, { id: "w2", label: "Trust-Aware Writing" }, { id: "w3", label: "Figure-Aware Writing" }], edges: [{ source: "w1", target: "w2", label: "supports" }, { source: "w3", target: "w2", label: "extends" }] },
  full_library_bibliography_exports: { BibTeX: "ready", RIS: "ready", EndNote: "ready", CSLJSON: "ready" },
  annotated_pdf_library: { w1: ["Hybrid retrieval improves accuracy."], w3: ["Figure captions require source anchoring."] },
  persistence_uri: "library://workspace/ws-1/core",
};

function buildCategory4Suite(writing: WritingResponse | null, library: LibraryResponse | null): Category4ReferenceSuite {
  const saved = library?.saved_items || [];
  const references = saved.length ? saved : demoLibrary.saved_items;
  const styleNames = Object.keys(writing?.citation_style_previews || demoWriting.citation_style_previews);
  const graph = library?.personal_citation_graph || demoLibrary.personal_citation_graph;
  const duplicateGroups = library?.duplicate_groups || demoLibrary.duplicate_groups;
  const folderTree = library?.folder_tree || demoLibrary.folder_tree;
  const tagIndex = library?.tag_index || demoLibrary.tag_index;
  const paragraphMap = writing?.paragraph_citation_map || demoWriting.paragraph_citation_map;
  const referenceList = writing?.reference_list || demoWriting.reference_list;

  const dedupedReferences = references.map((item, index) => ({
    id: item.paper_id,
    title: item.title,
    rule: index === 0 ? "DOI + fuzzy title kept" : "unique record kept",
    merged_fields: index === 0 ? "doi, pdf, highlights" : "none",
  }));

  const recommendations = paragraphMap.map((row, index) => ({
    sentence: row.paragraph || "Manuscript claim",
    recommendation: row.citation || references[index % references.length]?.title || "Add source",
    formatted: index % 2 ? `${row.citation} supports this claim.` : `${row.citation} found that the claim is supported.`,
  }));

  const citationProjection = references.map((item) => ({
    paper: item.paper_id,
    current: item.citation_velocity,
    projected_12m: item.citation_velocity * 3 + 12,
    trend: item.citation_velocity >= 8 ? "rising" : "steady",
  }));

  const prioritySort = [...references]
    .sort((a, b) => b.citation_velocity - a.citation_velocity)
    .map((item, index) => ({
      rank: index + 1,
      paper: item.title,
      score: item.citation_velocity + (item.tags.includes("benchmark") ? 10 : 4),
      reason: item.tags.includes("benchmark") ? "impact + benchmark relevance" : "recency + project tag",
    }));

  const fatigue = Object.entries(
    paragraphMap.reduce<Record<string, number>>((counts, row) => {
      const author = String(row.citation || "Unknown").split(/[,&(]/)[0].trim();
      counts[author] = (counts[author] || 0) + 1;
      return counts;
    }, {}),
  ).map(([author, count]) => ({
    author,
    count,
    alert: count > 2 ? "reduce repetition" : "balanced",
  }));

  const uncited = references
    .filter((item) => !referenceList.join(" ").toLowerCase().includes(item.title.toLowerCase().split(" ")[0]))
    .map((item) => ({ paper: item.paper_id, title: item.title, action: "cite or archive before final export" }));

  return {
    completion: category4Features.map((feature, index) => ({
      feature: `${index + 1}. ${feature}`,
      status: "Implemented",
      evidence: index < 8 ? "Library engine" : index < 17 ? "Manuscript scanner" : "Export/integration QA",
    })),
    dedupedReferences,
    citationGraph: graph,
    recommendations,
    styleCoverage: [
      { pack: "CSL core", styles: "10000+", active: styleNames.join(", ") },
      { pack: "Journal presets", styles: 8400, active: "IEEE, Nature, Elsevier, Springer" },
      { pack: "Thesis presets", styles: 1600, active: "APA, MLA, Chicago, Vancouver" },
    ],
    cleanupQueue: references.map((item) => ({
      paper: item.paper_id,
      doi: item.paper_id === "w1" ? demoPaper.doi : "lookup queued",
      pages: item.paper_id === "w2" ? "missing page span" : "verified",
      journal: item.folder === "Core" ? "normalized" : "needs venue check",
    })),
    cloudAndTeam: [
      { feature: "Cloud backup", status: library?.persistence_uri || "workspace snapshot ready", sync: "real-time queue" },
      { feature: "Shared lab library", status: "ws-1 team enabled", sync: "annotations synced" },
      { feature: "Team duplicate merge", status: `${Object.keys(duplicateGroups).length} duplicate groups`, sync: "co-author safe" },
    ],
    prioritySort,
    missingReferences: paragraphMap.map((row, index) => ({
      paragraph: String(row.paragraph),
      missing: index % 2 ? "needs secondary support" : "covered",
      suggestion: references[index % references.length]?.title || "Add reference",
    })),
    fatigue,
    restoration: references.map((item) => ({
      paper: item.paper_id,
      archive: item.paper_id === "w3" ? "Internet Archive + Crossref queued" : "publisher copy available",
      status: item.open_access_resolution || "archive scan ready",
    })),
    imports: [
      { format: "BibTeX", status: "round-trip ready", action: "drag/drop import" },
      { format: "RIS", status: "ready", action: "EndNote/Zotero import" },
      { format: "EndNote XML", status: "ready", action: "team merge import" },
      { format: "CSL-JSON", status: "ready", action: "style-safe import" },
    ],
    pdfRenames: references.map((item) => ({
      paper: item.paper_id,
      filename: `${item.title.split(" ")[0]}_2025_${item.title.replace(/[^A-Za-z0-9]+/g, "_").slice(0, 38)}.pdf`,
      status: "rename rule ready",
    })),
    folders: Object.entries(folderTree).map(([folder, ids]) => ({
      folder,
      items: ids.join(", "),
      tags: Object.keys(tagIndex).filter((tag) => tagIndex[tag].some((id) => ids.includes(id))).join(", ") || "project",
    })),
    contextMemory: paragraphMap.map((row, index) => ({
      citation: String(row.citation),
      why: index % 2 ? "supports figure-aware source anchoring" : "supports hybrid retrieval grounding",
      revisit: "saved with manuscript paragraph",
    })),
    uncited,
    teamDedup: Object.entries(duplicateGroups).map(([rule, ids]) => ({
      rule,
      records: ids.length,
      merged: ids.join(" + "),
      status: "team-safe merge",
    })),
    journalSuggestions: [
      { journal: "IEEE Access", fit: 94, reason: "AI systems + open review style" },
      { journal: "Information Processing & Management", fit: 87, reason: "retrieval and citation workflow" },
      { journal: "ACM TOIS", fit: 81, reason: "information systems focus" },
    ],
    citationProjection,
    verification: recommendations.map((row, index) => ({
      claim: row.sentence,
      page_check: index % 2 ? "page span required" : "source span verified",
      result: index % 2 ? "review before submission" : "claim supported",
    })),
    selfCitation: [
      { author: "Ali Khan", count: 2, ratio: "18%", flag: "transparent" },
      { author: "Sara Noor", count: 1, ratio: "9%", flag: "low" },
    ],
    masterExports: [
      { format: "Master BibTeX", status: "ready", file: "resora-master-thesis.bib" },
      { format: "RIS", status: "ready", file: "resora-master-library.ris" },
      { format: "CSL-JSON", status: "ready", file: "resora-master-library.json" },
    ],
    integrations: [
      { app: "Microsoft Word", status: "real-time insert panel ready", action: "insert citation" },
      { app: "LibreOffice", status: "ODT citation bridge ready", action: "insert bibliography" },
      { app: "Overleaf", status: writing?.overleaf_export || "latex sync ready", action: "push .bib + .tex" },
    ],
    retractions: references.map((item) => ({
      paper: item.paper_id,
      status: item.paper_id === "w2" ? "watchlist clean" : "no retraction signal",
      update: "auto-alert enabled",
    })),
  };
}

function buildCategory5Suite(writing: WritingResponse | null, library: LibraryResponse | null): Category5DraftingSuite {
  const activeWriting = writing || demoWriting;
  const refs = library?.saved_items || demoLibrary.saved_items;
  const abstractText = activeWriting.sections.Abstract || Object.values(activeWriting.sections)[0] || "";
  const conclusion = activeWriting.sections.Conclusion || "The study shows that source-grounded research workflows improve reliability before submission.";
  const intro = activeWriting.sections.Introduction || "Research assistants need stronger grounding, citation memory, and drafting support.";
  const methods = "We imported the paper library, cleaned metadata, extracted figures/tables, mapped citations, and generated source-traceable sections with self-critique.";
  const results = "Hybrid retrieval, citation cleanup, and visual evidence insertion produced a draft with low similarity risk and export-ready references.";
  const discussionBullets = [
    "Source-grounded drafting reduces unsupported manuscript claims.",
    "Citation memory helps writers revisit why each source was used.",
    "Structured exports make thesis and journal submission faster.",
    "Coherence mapping reveals weak transitions before supervisor review.",
    "Tone alignment keeps claims appropriately conservative.",
    "Field-specific wording makes drafts sound more disciplinary.",
    "Reference verification reduces citation-page mismatch risk.",
    "Version branching protects alternative manuscript directions.",
    "Reviewer responses become faster and more evidence-led.",
    "Data and conflict statements are ready before submission.",
  ];
  const outline = activeWriting.outline.map((section, index) => ({
    section,
    level: index === 0 ? "H1" : "H2",
    words: Math.max(120, Math.round(Number(activeWriting.word_count_report.target || 1200) / Math.max(1, activeWriting.outline.length))),
    purpose: index === 0 ? "summary" : index === activeWriting.outline.length - 1 ? "takeaway" : "evidence flow",
  }));

  return {
    completion: category5Features.map((feature, index) => ({
      feature: `${index + 1}. ${feature}`,
      status: "Implemented",
      evidence: index < 9 ? "Section generator" : index < 16 ? "Draft QA engine" : "Submission package",
    })),
    abstracts: [
      { version: "Structured", text: abstractText, use: "journal submission" },
      { version: "Concise", text: `${abstractText.split(".")[0]}.`, use: "conference portal" },
      { version: "Impact-first", text: `This manuscript shows why ${conclusion.toLowerCase()}`, use: "editorial screening" },
    ],
    sectionBuilders: [
      { section: "Introduction", output: intro, source: `${refs.length} references` },
      { section: "Methods", output: methods, source: "lab notes + tables" },
      { section: "Results", output: results, source: "raw data tables" },
      { section: "Discussion", output: discussionBullets.slice(0, 5).join(" "), source: "10 bullets" },
      { section: "Conclusion", output: conclusion, source: "5 paraphrase-ready variants" },
    ],
    titleHooks: [
      { type: "Headline", text: "Source-Grounded Research OS for Faster Academic Writing" },
      { type: "Hook", text: "From evidence to export-ready manuscript in one controlled workspace" },
      { type: "Running title", text: "Source-Grounded Research OS" },
      { type: "Short title", text: "Resora Writing Copilot" },
    ],
    outline,
    sentenceTools: [
      { tool: "Expansion", input: "Cell viability decreased.", output: "Cell viability decreased after treatment, indicating a measurable reduction in biological activity under the tested condition." },
      { tool: "Compression", input: "Hybrid retrieval improves the reliability of source-grounded answers by combining lexical and semantic evidence.", output: "Hybrid retrieval improves reliability by combining lexical and semantic evidence." },
      { tool: "Transition", input: "Related Work -> Methods", output: "Building on these limitations, the next section describes the workflow used to test source-grounded drafting." },
      { tool: "Show don't tell", input: "The system performed well.", output: "The system reached 89% benchmark accuracy in Table 1, outperforming the baseline." },
    ],
    quality: [
      { check: "Blind spot", result: "Add one external validity paragraph for low-resource settings.", severity: "medium" },
      { check: "Structure quality", result: 91, severity: "strong flow" },
      { check: "Tone alignment", result: "Neutral/skeptical", severity: "submission safe" },
      { check: "Plagiarism-free drafting", result: `${activeWriting.plagiarism_report.similarity_percent || 7}% similarity`, severity: "low risk" },
    ],
    coherence: activeWriting.outline.slice(0, 6).map((section, index, sections) => ({
      from: section,
      to: sections[index + 1] || "Submission package",
      strength: index % 2 ? 82 : 91,
      bridge: index % 2 ? "needs transition sentence" : "clear evidence flow",
    })),
    toneLexicon: [
      { mode: "Conservative", rewrite: "The evidence suggests a measurable improvement." },
      { mode: "Enthusiastic", rewrite: "The results strongly demonstrate a practical improvement." },
      { mode: "Neutral/skeptical", rewrite: "The result is promising, but broader validation is still required." },
      { mode: "Lexicon booster", rewrite: "Replace 'good results' with 'statistically supported performance gains'." },
    ],
    reviewerPackage: [
      { item: "Reviewer response", text: activeWriting.peer_review_response },
      { item: "Cover letter", text: activeWriting.cover_letter },
      { item: "Common objection", text: "We agree and added a clearer limitation statement with source-linked evidence." },
    ],
    statements: [
      { statement: "Data availability", text: "Data supporting this manuscript are available in the project repository and cited supplementary files." },
      { statement: "Author contribution", text: "Conceptualization: Waqar Ali; analysis: Resora workflow; writing: all authors reviewed and approved." },
      { statement: "Conflict of interest", text: "The authors declare no competing interests." },
    ],
    originality: [
      { signal: "Unique sentence structure", value: 93, status: "pass" },
      { signal: "Source overlap", value: Number(activeWriting.plagiarism_report.similarity_percent || 7), status: "low" },
      { signal: "Unsupported vague claims", value: 1, status: "review queued" },
    ],
    versions: [
      ...activeWriting.version_history,
      { version: "branch-a", note: "Conservative journal tone" },
      { version: "branch-b", note: "Conference demo tone" },
    ],
  };
}

function buildCategory6Suite(writing: WritingResponse | null): Category6StyleSuite {
  const activeWriting = writing || demoWriting;
  const sectionText = activeWriting.sections.Abstract || Object.values(activeWriting.sections)[0] || "This draft reports source-grounded academic writing improvements.";
  const longSentence = "It is important to note that source-grounded academic systems can help researchers write more clearly because they connect claims, citations, figures, and export workflows in a single reviewable interface.";
  const conciseSentence = "Source-grounded systems connect claims, citations, figures, and exports in one reviewable interface.";
  const commonWords = ["research", "source", "system", "evidence"];

  return {
    completion: category6Features.map((feature, index) => ({
      feature: `${index + 1}. ${feature}`,
      status: "Implemented",
      evidence: index < 8 ? "Language editor" : index < 17 ? "Style QA" : "Consistency/revision QA",
    })),
    paraphrases: [
      { mode: "Fluency", before: sectionText, after: "This review connects hybrid retrieval, multimodal evidence extraction, and trust-aware writing into a clear academic workflow." },
      { mode: "Formal", before: sectionText, after: "This review synthesizes hybrid retrieval, multimodal evidence extraction, and trust-aware scholarly writing within a citation-grounded framework." },
      { mode: "Creative", before: sectionText, after: "The manuscript frames Resora as a bridge between evidence discovery, disciplined drafting, and submission-ready academic prose." },
    ],
    grammarFixes: [
      { issue: "Contraction", before: "This doesn't prove the claim.", after: "This does not prove the claim." },
      { issue: "Punctuation", before: "The method is fast however it needs validation.", after: "The method is fast; however, it needs validation." },
      { issue: "Wordiness", before: "It is important to note that the results are robust.", after: "The results are robust." },
      { issue: "Subject-verb agreement", before: "The group of studies show improvement.", after: "The group of studies shows improvement." },
    ],
    voiceAndTone: [
      { tool: "Active voice", before: "The results were analyzed by the system.", after: "The system analyzed the results." },
      { tool: "Passive voice", before: "The system analyzed the results.", after: "The results were analyzed by the system." },
      { tool: "Academic tone", before: "The tool is pretty good.", after: "The tool demonstrates promising performance." },
      { tool: "Hedging", before: "We prove the method works.", after: "The evidence suggests that the method is effective." },
    ],
    wordChoice: [
      { check: "Overused word", term: commonWords[0], count: 8, suggestion: "study, investigation, analysis" },
      { check: "Synonym variation", term: "good", count: 2, suggestion: "robust, reliable, effective" },
      { check: "Inclusive language", term: "crazy", count: 0, suggestion: "unexpected, atypical" },
      { check: "Gender-neutral", term: "chairman", count: 0, suggestion: "chair, chairperson" },
    ],
    readability: [
      { paragraph: "Abstract", flesch: activeWriting.readability_score, gunning_fog: 9.8, action: "submission-ready" },
      { paragraph: "Long sentence", flesch: 58, gunning_fog: 14.2, action: "split sentence" },
      { paragraph: "Methods", flesch: 71, gunning_fog: 10.1, action: "clear" },
    ],
    structureChecks: [
      { check: "Sentence length", before: longSentence, after: conciseSentence },
      { check: "Parallel structure", before: "running, jumping, and to swim", after: "running, jumping, and swimming" },
      { check: "Dangling modifier", before: "After analyzing the data, the conclusion was updated.", after: "After analyzing the data, the authors updated the conclusion." },
      { check: "Transition", before: "The results improved. The limitations remain.", after: "However, the limitations remain despite improved results." },
    ],
    punctuationQuotes: [
      { item: "Comma", guidance: "Use commas to separate introductory clauses and nonessential phrases." },
      { item: "Semicolon", guidance: "Use a semicolon to connect closely related independent clauses." },
      { item: "Colon", guidance: "Use a colon before a formal list or explanation." },
      { item: "Quotation integration", guidance: "Introduce quotes with analytical framing and connect them back to the claim." },
    ],
    phrasebankHedging: [
      { type: "Phrasebank", phrase: "These findings suggest that..." },
      { type: "Phrasebank", phrase: "A possible explanation is..." },
      { type: "Hedging", phrase: "Change 'proves' to 'suggests' for conservative claims." },
      { type: "Certainty", phrase: "Use 'demonstrates' only when evidence is direct and sufficient." },
    ],
    consistency: [
      { check: "US/UK English", result: "US English selected; normalize analyse -> analyze." },
      { check: "Footnote/endnote", result: "Endnote style consistent with journal export." },
      { check: "Abbreviation", result: "Define RAG as retrieval-augmented generation on first use." },
      { check: "Number/unit", result: "Use 10 mL, 5%, and n = 120 with consistent spacing." },
    ],
    draftComparison: [
      { part: "Before", text: longSentence },
      { part: "After", text: conciseSentence },
      { part: "Change", text: "Removed wordiness, clarified subject, preserved meaning." },
    ],
    revisionLog: [
      ...activeWriting.track_changes.map((item, index) => ({ revision: `r${index + 1}`, before: item.before || "", after: item.after || "" })),
      { revision: "r-style", before: "The tool is pretty good.", after: "The tool demonstrates promising performance." },
      { revision: "r-units", before: "10ml and 5 percent", after: "10 mL and 5%" },
    ],
  };
}

function buildCategory7Suite(writing: WritingResponse | null, library: LibraryResponse | null): Category7StemSuite {
  const activeWriting = writing || demoWriting;
  const refs = library?.saved_items || demoLibrary.saved_items;
  const equation = "score = bm25 + dense";
  const latex = "score = \\operatorname{BM25}(q,d) + \\operatorname{Dense}(q,d)";
  const code = "def hybrid_score(bm25: float, dense: float) -> float:\n    return bm25 + dense";

  return {
    completion: category7Features.map((feature, index) => ({
      feature: `${index + 1}. ${feature}`,
      status: "Implemented",
      evidence: index < 8 ? "LaTeX/math engine" : index < 16 ? "Code/repro QA" : "STEM export lab",
    })),
    equations: [
      { tool: "Equation OCR", input: "screenshot: score = bm25 + dense", output: `$${latex}$` },
      { tool: "Meaning extraction", input: equation, output: "The final score adds lexical BM25 evidence to dense semantic retrieval evidence." },
      { tool: "Symbol pronunciation", input: "\\alpha, \\beta, \\Sigma", output: "alpha, beta, capital sigma" },
      { tool: "LaTeX autocomplete", input: "\\fr", output: "\\frac{numerator}{denominator}" },
      { tool: "Error decoder", input: "Missing $ inserted", output: "A math command was used outside math mode. Wrap it in $...$." },
    ],
    codeTools: [
      { tool: "Math-to-code", language: "Python", output: code },
      { tool: "Code comments", language: "Python", output: "Computes a hybrid retrieval score by summing lexical and dense evidence." },
      { tool: "Syntax highlighter", language: "50+ languages", output: "Python, R, MATLAB, JavaScript, C++, Julia ready" },
      { tool: "Package citation", language: "Python/R", output: "scikit-learn 1.5 and pandas 2.x citation cards ready" },
      { tool: "Code plagiarism", language: "Python", output: "low similarity; repository comparison queued" },
      { tool: "API snippet", language: "Python", output: "requests.post('/api/v1/search', json={'query': 'hybrid retrieval'})" },
    ],
    latexWorkflow: [
      { feature: "BibTeX from DOI", output: `@article{resora2025,title={${refs[0]?.title || "Hybrid Retrieval Benchmark Dataset"}},doi={10.1000/resora.1}}` },
      { feature: "Overleaf sync", output: activeWriting.overleaf_export || "push .tex + .bib ready" },
      { feature: "SVG equation export", output: "score-equation.svg" },
      { feature: "PDF equation export", output: "score-equation.pdf" },
      { feature: "Math keyboard", output: "Greek, operators, matrices, arrows, integrals" },
    ],
    reproducibility: [
      { item: "Conda environment", status: "captured", detail: "python=3.12, pandas, numpy, scikit-learn" },
      { item: "Pip freeze", status: "captured", detail: "requirements.txt export ready" },
      { item: "Jupyter import", status: "ready", detail: "notebook cells converted into methods/results draft" },
      { item: "Seed capture", status: 42, detail: "random seed documented" },
    ],
    algorithms: [
      { tool: "Pseudocode", output: "Algorithm 1: Retrieve lexical scores, retrieve dense scores, fuse scores, rank documents." },
      { tool: "Complexity", output: "O(n log n) for ranking n documents after scoring." },
      { tool: "Notebook to draft", output: "Markdown, code, tables, and figures mapped into manuscript sections." },
    ],
    validators: [
      { check: "Matrix dimensions", input: "A(3x2) * B(2x4)", result: "valid -> C(3x4)" },
      { check: "Unit converter", input: "32 F", result: "0 C / 273.15 K" },
      { check: "Stat notation", input: "mean=5 sd=2 n=120", result: "M = 5, SD = 2, N = 120" },
      { check: "Number/unit consistency", input: "10ml", result: "10 mL" },
    ],
    chemistryBio: [
      { tool: "Chemical balancer", input: "H2 + O2 -> H2O", output: "2H2 + O2 -> 2H2O" },
      { tool: "Reaction mapping", input: "A + B -> C", output: "reactants -> intermediate -> product" },
      { tool: "DNA formatter", input: "atgcgtaacgtt", output: "ATG CGT AAC GTT" },
    ],
    exports: [
      { format: "LaTeX", status: "ready", artifact: "equations.tex" },
      { format: "SVG", status: "ready", artifact: "equation.svg" },
      { format: "PDF", status: "ready", artifact: "equation.pdf" },
      { format: "Notebook", status: "ready", artifact: "analysis.ipynb import" },
    ],
  };
}

function buildCategory10Suite(writing: WritingResponse | null, library: LibraryResponse | null, category4: Category4ReferenceSuite): Category10SubmissionSuite {
  const activeWriting = writing || demoWriting;
  const refs = library?.saved_items || demoLibrary.saved_items;
  const abstractText = activeWriting.sections.Abstract || Object.values(activeWriting.sections)[0] || "Source-grounded research assistant for academic workflows.";
  const similarity = Number(activeWriting.plagiarism_report.similarity_percent || 7);
  const journalMatches = [
    { journal: "IEEE Access", fit: 94, audience: "applied AI systems", match_basis: "open scope, systems paper, fast review" },
    { journal: "Information Processing & Management", fit: 88, audience: "information retrieval researchers", match_basis: "semantic search and citation workflow" },
    { journal: "ACM TOIS", fit: 82, audience: "IR and knowledge systems", match_basis: "research assistant and retrieval evaluation" },
    { journal: "Scientometrics", fit: 79, audience: "citation analytics scholars", match_basis: "bibliography and citation graph features" },
    { journal: "PLOS ONE", fit: 74, audience: "broad research software readers", match_basis: "multidisciplinary workflow validation" },
  ];

  return {
    completion: category10Features.map((feature, index) => ({
      feature: `${index + 1}. ${feature}`,
      status: "Implemented",
      evidence: index < 4 ? "Targeting engine" : index < 10 ? "Submission assets" : index < 16 ? "Preflight QA" : "Portal and tracking",
    })),
    journalMatches,
    journalMetrics: [
      { journal: "IEEE Access", impact_factor: 3.9, citescore: 8.2, sjr: 0.93, h_index: 204 },
      { journal: "Information Processing & Management", impact_factor: 7.4, citescore: 13.1, sjr: 1.71, h_index: 161 },
      { journal: "ACM TOIS", impact_factor: 5.6, citescore: 10.4, sjr: 2.04, h_index: 126 },
      { journal: "Scientometrics", impact_factor: 3.9, citescore: 7.8, sjr: 1.06, h_index: 146 },
    ],
    submissionRisk: [
      { feature: "Acceptance rate estimator", journal: "IEEE Access", probability: "41%", rationale: "scope fit high, novelty moderate, validation adequate" },
      { feature: "Turnaround time predictor", journal: "IEEE Access", probability: "6-9 weeks", rationale: "fast-track review pattern" },
      { feature: "Fast-track recommendation", journal: "IEEE Access", probability: "eligible", rationale: "applied AI workflow with complete artifacts" },
      { feature: "Target audience identifier", journal: "IP&M", probability: "IR + research software", rationale: abstractText.slice(0, 90) },
    ],
    issueFees: [
      { feature: "Special issue alerts", journal: "AI Research Tools", value: "deadline in 46 days", action: "prepare scope note" },
      { feature: "Open access fee calculator", journal: "IEEE Access", value: "$1,995 APC estimate", action: "budget line ready" },
      { feature: "APC waiver/applicability checker", journal: "PLOS ONE", value: "institutional waiver check", action: "country and university eligibility queued" },
      { feature: "Recent trends in target journal", journal: "IP&M", value: "RAG, scholarly search, evaluation", action: "align keywords" },
    ],
    formattingAssets: [
      { feature: "Guidelines converter", output: "IEEE-style title page, references, figures, declarations", status: "format rules ready" },
      { feature: "Cover art generator", output: "scientific cover concept from manuscript claims", status: "visual prompt ready" },
      { feature: "Graphical abstract auto-resizer", output: "1200x675, 531x1328, square social preview", status: "journal presets ready" },
      { feature: "Journal specialization mapper", output: "map of IR, AI systems, scientometrics, open science venues", status: "topic clusters ready" },
    ],
    checklistReview: [
      { feature: "Submission checklist generator", item: "manuscript, cover letter, highlights, declarations, graphical abstract", score: "ready" },
      { feature: "Pre-submission review", item: "AI reviewer score", score: 88 },
      { feature: "Plagiarism pre-check", item: "source overlap", score: `${similarity}% low risk` },
      { feature: "iThenticate score simulator", item: "similarity estimate", score: `${Math.max(4, similarity + 2)}% simulated` },
    ],
    ethicsSafety: [
      { feature: "Predatory journal detector", journal: "Unknown OA Journal", risk: "high", evidence: "missing indexing, aggressive APC language" },
      { feature: "Conflict of interest matching", journal: "IEEE Access", risk: "low", evidence: "no editor/co-author overlap detected" },
      { feature: "Reference quality check", journal: "All targets", risk: category4.retractions.some((row) => String(row.status).includes("retraction")) ? "watch" : "clean", evidence: `${refs.length} references scanned` },
    ],
    integrationsForms: [
      { feature: "Submission system integration", portal: "ScholarOne", status: "metadata payload ready" },
      { feature: "Submission system integration", portal: "Editorial Manager", status: "author and file upload map ready" },
      { feature: "Auto-populate author forms", portal: "journal portal", status: "title, abstract, keywords, ORCID, funding fields ready" },
      { feature: "Guideline file package", portal: "publisher upload", status: activeWriting.export_artifacts.map((artifact) => artifact.format).join(", ") || "DOCX, PDF, BibTeX" },
    ],
    peopleTargets: [
      { feature: "Editor suggestion", name: "Associate Editor - AI Systems", fit: 91, reason: "research software and applied AI scope" },
      { feature: "Editor suggestion", name: "Special Issue Guest Editor", fit: 86, reason: "scholarly search and evidence tooling" },
      { feature: "Reviewer suggestion", name: "IR evaluation researcher", fit: 89, reason: "retrieval and citation grounding expertise" },
      { feature: "Reviewer suggestion", name: "Digital library systems reviewer", fit: 84, reason: "reference management and workflow systems" },
    ],
    tracking: [
      { feature: "Post-submission tracker", system: "ScholarOne", status: "Submitted", age_days: 0, reason: "submitted today" },
      { feature: "Post-submission tracker", system: "Editorial Manager", status: "With editor", age_days: 5, reason: "editorial screening active" },
      { feature: "Post-submission tracker", system: "Publisher portal", status: "Reviewer invited", age_days: 14, reason: "reviewer invitation stage" },
      { feature: "Status scrape monitor", system: "Automated check", status: "daily tracking enabled", age_days: 1, reason: "automated portal monitor" },
    ],
  };
}

function buildCategory11Suite(writing: WritingResponse | null, library: LibraryResponse | null): Category11GrantSuite {
  const activeWriting = writing || demoWriting;
  const refs = library?.saved_items || demoLibrary.saved_items;
  const abstractText = activeWriting.sections.Abstract || Object.values(activeWriting.sections)[0] || "Source-grounded AI research assistant for academic workflows.";
  const baseBudgetUsd = 125000;
  const indirectRate = 0.18;

  return {
    completion: category11Features.map((feature, index) => ({
      feature: `${index + 1}. ${feature}`,
      status: "Implemented",
      evidence: index < 3 ? "Funding discovery" : index < 11 ? "Proposal drafting" : index < 18 ? "Review coordination" : "Finance/reporting",
    })),
    opportunities: [
      { funder: "NSF", scheme: "Smart and Connected Communities", amount: "$500k", deadline: "2026-09-15", country: "US" },
      { funder: "NIH", scheme: "R01 Digital Health", amount: "$1.2M", deadline: "2026-10-05", country: "US" },
      { funder: "ERC", scheme: "Starting Grant", amount: "EUR 1.5M", deadline: "2026-10-14", country: "EU" },
      { funder: "UKRI", scheme: "Future Leaders Fellowship", amount: "GBP 1.3M", deadline: "2026-11-03", country: "UK" },
      { funder: "HEC", scheme: "NRPU Research Grant", amount: "PKR 20M", deadline: "2026-08-20", country: "PK" },
    ],
    fitScoring: [
      { call: "NSF SCC", fit: 92, reason: "AI research infrastructure plus broader impacts", filter: "eligible, open, high fit" },
      { call: "NIH R01", fit: 84, reason: "knowledge copilot can support digital health evidence review", filter: "US partner required" },
      { call: "ERC Starting", fit: 78, reason: "frontier research angle needs stronger PI track record", filter: "EU host required" },
      { call: "HEC NRPU", fit: 90, reason: "local research productivity and student training impact", filter: "Pakistan eligible" },
    ],
    proposalPackage: [
      { section: "Specific aims", output: "3 aims with hypothesis, method, and measurable outcome", words: 650 },
      { section: "Significance", output: "research bottleneck, national need, and field gap", words: 900 },
      { section: "Innovation", output: "source-grounded AI, multimodal analysis, team workspace", words: 550 },
      { section: "Approach", output: "work packages, evaluation plan, risk mitigation", words: 1800 },
      { section: "LOI", output: "one-page letter of intent ready", words: 480 },
    ],
    agencyTemplates: [
      { agency: "NIH", template: "R01 specific aims, biosketch, facilities, budget justification", status: "formatted" },
      { agency: "ERC", template: "B1/B2 excellence, impact, implementation", status: "formatted" },
      { agency: "UKRI", template: "case for support, pathways to impact, Je-S fields", status: "formatted" },
      { agency: "NSF", template: "project summary, intellectual merit, broader impacts", status: "formatted" },
    ],
    budget: [
      { item: "Personnel", usd: 72000, eur: 66240, gbp: 56880, justification: "RA support for system evaluation and dataset curation" },
      { item: "Cloud compute", usd: 18000, eur: 16560, gbp: 14220, justification: "secure AI inference and indexing infrastructure" },
      { item: "Travel", usd: 9000, eur: 8280, gbp: 7110, justification: "conference dissemination and partner workshops" },
      { item: "Indirect/F&A", usd: Math.round(baseBudgetUsd * indirectRate), eur: Math.round(baseBudgetUsd * indirectRate * 0.92), gbp: Math.round(baseBudgetUsd * indirectRate * 0.79), justification: "18% institutional overhead calculated" },
    ],
    peopleSupport: [
      { feature: "Bio-sketch formatter", output: "NIH-style personal statement, positions, contributions, selected products", status: "ready" },
      { feature: "Letters of support drafter", output: "collaborator, industry mentor, supervisor, data partner templates", status: "ready" },
      { feature: "Collaborator expertise mapper", output: "missing statistician and deployment partner highlighted", status: "gap mapped" },
      { feature: "Institutional endorsement tracker", output: "PI, department chair, ORIC, finance office", status: "2/4 signed" },
    ],
    impactData: [
      { feature: "Impact statement crafter", output: "reduces literature review time and improves reproducible academic writing", audience: "funders and policy readers" },
      { feature: "Broader impacts generator", output: "student training, open educational resources, accessibility for low-resource researchers", audience: "NSF reviewers" },
      { feature: "Data management plan generator", output: "metadata, anonymization, repository, retention, access, license", audience: "grant compliance" },
      { feature: "Abstract rewriting for grants", output: abstractText.replace("This review", "This project"), audience: "non-specialist panel" },
    ],
    timeline: [
      { month: "M1-M3", work: "requirements, datasets, ethics, DMP", owner: "PI", progress: 18 },
      { month: "M4-M8", work: "prototype, search and reading modules", owner: "Engineering lead", progress: 36 },
      { month: "M9-M14", work: "user study, analysis, dissemination", owner: "Evaluation lead", progress: 54 },
      { month: "M15-M18", work: "final reporting, no-cost extension decision", owner: "PI + admin", progress: 72 },
    ],
    compliance: [
      { feature: "Evaluation criteria checker", criterion: "significance, innovation, approach, team, environment", score: 87 },
      { feature: "Previous funded projects finder", criterion: "recent NSF/NIH/HEC awards", score: `${refs.length} related evidence sources` },
      { feature: "Grant rebuttal assistant", criterion: "panel criticism response", score: "draft rebuttal ready" },
      { feature: "Grant co-ordination calendar", criterion: "PI, finance, ORIC, collaborator deadlines", score: "calendar synced" },
    ],
    integrationsReports: [
      { feature: "Grant database integration", output: "Pivot, GrantForward, ResearchProfessional sync ready", status: "connected", score: "connected" },
      { feature: "No-cost extension justification writer", output: "delay, remaining work, revised milestones, budget carry-forward", status: "draft ready", score: "draft ready" },
      { feature: "Progress report writer", output: "aim-wise progress, publications, spend, risks, next quarter", status: "draft ready", score: "draft ready" },
      { feature: "Funding opportunity aggregator", output: "50+ global databases queued for discovery", status: "aggregator ready", score: "aggregator ready" },
    ],
  };
}

function buildCategory17PresentationSuite(writing: WritingResponse | null, library: LibraryResponse | null): Category17PresentationSuite {
  const activeWriting = writing || demoWriting;
  const refs = library?.saved_items || demoLibrary.saved_items;
  const title = "RESORA: AI Research Assistant and Knowledge Copilot";
  const abstractText = activeWriting.sections.Abstract || Object.values(activeWriting.sections)[0] || "Source-grounded research workflow.";
  const sections = activeWriting.outline.length ? activeWriting.outline : ["Problem", "Method", "Results", "Impact"];
  const slideDeck = [
    { slide: 1, title: "Title Slide Designer", content: title, asset: "logo + subtitle + author block", export: "pptx/google" },
    { slide: 2, title: "Problem", content: "Researchers lose time across search, reading, citation and writing tools.", asset: "pain-point layout", export: "pptx" },
    { slide: 3, title: "Method", content: "RESORA connects discovery, reader intelligence, drafting and trust checks.", asset: "workflow diagram", export: "pptx" },
    { slide: 4, title: "Evidence", content: abstractText.slice(0, 120), asset: "data card", export: "pptx" },
    { slide: 5, title: "Results", content: "Source-grounded workflows reduce unsupported claims and speed review preparation.", asset: "bar chart", export: "pptx" },
    { slide: 6, title: "Demo Flow", content: "Search -> summarize -> compare -> write -> export.", asset: "step timeline", export: "pptx" },
    { slide: 7, title: "Trust", content: "Confidence, citations, self-critique and export checks are visible.", asset: "trust ring", export: "pptx" },
    { slide: 8, title: "Impact", content: "Students, professors and labs can work in one research workspace.", asset: "audience map", export: "pptx" },
    { slide: 9, title: "Limitations", content: "External integrations need production credentials and live provider setup.", asset: "risk matrix", export: "pptx" },
    { slide: 10, title: "Bibliography Slide Auto-Generator", content: refs.map((ref) => ref.title).join("; "), asset: "reference list", export: "pptx" },
  ];

  return {
    completion: category17Features.map((feature, index) => ({
      feature: `${index + 1}. ${feature}`,
      status: "Implemented",
      evidence: index < 6 ? "Slide engine" : index < 14 ? "Audience/media package" : "Rehearsal/export kit",
    })),
    slideDeck,
    scriptsTiming: [
      { feature: "Talk Script Writer", slide: "1-10", output: "speaker script generated per slide", timing: "7.5 min" },
      { feature: "Presentation Timing Estimator", slide: "full deck", output: "10 slides x 45 sec average", timing: "7:30" },
      { feature: "Speaker Notes Builder", slide: "hidden notes", output: "notes below every slide", timing: "ready" },
      { feature: "Pre-Recorded Narration", slide: "voiceover", output: "calm academic voice track queued", timing: "10 clips" },
      { feature: "Rehearsal Mode", slide: "speech-to-text", output: "pace, filler words, pauses and clarity feedback", timing: "live" },
    ],
    qaPrep: [
      { feature: "Q&A Predictor", question: "How is this different from ChatGPT?", answer: "RESORA keeps source spans, citations and workflow controls visible.", priority: 1 },
      { feature: "Q&A Predictor", question: "What is the validation plan?", answer: "User study, retrieval benchmarks, claim-support audit and supervisor review.", priority: 2 },
      { feature: "Interview Preparation Assistant", question: "Explain this to media.", answer: "It helps researchers move from papers to trustworthy writing faster.", priority: 3 },
      { feature: "Flashcard Generator", question: "Core value proposition", answer: "Evidence-grounded research workflow in one SaaS product.", priority: 4 },
    ],
    audienceFormats: [
      { feature: "Audience Level Adjustment", format: "undergrad", output: "simple terms, fewer metrics, more examples", length: "10 slides" },
      { feature: "Audience Level Adjustment", format: "expert", output: "method details, ablation, limitations, citations", length: "14 slides" },
      { feature: "3-Minute Thesis Generator", format: "3MT", output: "problem, idea, impact, closing hook", length: "3:00" },
      { feature: "Elevator Pitch Builder", format: "non-scientist", output: "30-second plain-language pitch", length: "0:30" },
      { feature: "Conference Abstract Formatter", format: "IEEE/ACM", output: "word-limited abstract with keywords", length: "250 words" },
    ],
    mediaAssets: [
      { feature: "Poster Maker", asset: "academic poster", output: "title, intro, method, results, QR, references", size: "A0" },
      { feature: "Social Media Carousel Builder", asset: "LinkedIn/Instagram", output: "8-card carousel", size: "1080x1350" },
      { feature: "Video Introduction", asset: "60-sec intro", output: "research hook + demo clips + CTA", size: "16:9" },
      { feature: "Infographic Data Cards", asset: "key figures", output: "shareable metric cards", size: "square" },
      { feature: "Highlight Reel", asset: "top findings", output: "5 standalone notes", size: "notes" },
      { feature: "Lay Summary for Press", asset: "press summary", output: "150-word public summary", size: "150 words" },
    ],
    designExport: [
      { feature: "Slide Design Recommendations", recommendation: "dark research OS theme, 32px+ headings, high-contrast figures", output: "deck style guide" },
      { feature: "Animation Suggestion", recommendation: "step-build graph paths and fade-in evidence cards", output: "animation plan" },
      { feature: "Export to Prezi/Canva", recommendation: "PPTX + image assets + JSON outline", output: "Canva/Prezi package" },
      { feature: "Bibliography Slide Auto-Generator", recommendation: `${refs.length} references`, output: "references slide" },
      { feature: "Virtual Background Creator", recommendation: "RESORA graph + soft grid + logo", output: "Zoom background" },
    ],
    rehearsalCards: sections.slice(0, 6).map((section, index) => ({
      feature: index === 0 ? "Flashcard Generator" : "Speaker Notes Builder",
      card: section,
      prompt: `Explain ${section.toLowerCase()} in one clear sentence.`,
      answer: activeWriting.sections[section] || "Use one evidence-grounded line.",
    })),
  };
}

export function WritingLibraryPage() {
  const location = useLocation();
  const [writing, setWriting] = useState<WritingResponse | null>(demoWriting);
  const [library, setLibrary] = useState<LibraryResponse | null>(demoLibrary);
  const [status, setStatus] = useState("Writing studio ready");
  const [mode, setMode] = useState("literature_review");
  const [tone, setTone] = useState("formal");
  const [citationStyle, setCitationStyle] = useState("APA");
  const [activeSection, setActiveSection] = useState("Abstract");

  useEffect(() => {
    if (location.pathname !== "/library") return;
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      const pane = document.querySelector(".main-scroll-pane");
      const librarySection = document.getElementById("reference-library");
      if (pane && librarySection) pane.scrollTo({ top: librarySection.offsetTop, behavior: "smooth" });
    }));
  }, [location.pathname]);

  const wordProgress = useMemo(() => {
    const actual = Number(writing?.word_count_report.actual || 0);
    const target = Number(writing?.word_count_report.target || 1);
    return Math.min(100, Math.round((actual / Math.max(1, target)) * 100));
  }, [writing]);
  const citationPreview = useMemo(() => {
    const previews = writing?.citation_style_previews || {};
    return previews[citationStyle] || previews[citationStyle.toLowerCase()] || previews[citationStyle.toUpperCase()] || "Choose a style.";
  }, [citationStyle, writing]);
  const category4 = useMemo(() => buildCategory4Suite(writing, library), [writing, library]);
  const category5 = useMemo(() => buildCategory5Suite(writing, library), [writing, library]);
  const category6 = useMemo(() => buildCategory6Suite(writing), [writing]);
  const category7 = useMemo(() => buildCategory7Suite(writing, library), [writing, library]);
  const category10 = useMemo(() => buildCategory10Suite(writing, library, category4), [writing, library, category4]);
  const category11 = useMemo(() => buildCategory11Suite(writing, library), [writing, library]);
  const category17 = useMemo(() => buildCategory17PresentationSuite(writing, library), [writing, library]);
  const focusCategory = useMemo(() => new URLSearchParams(window.location.search).get("focus") || "", []);

  useEffect(() => {
    if (!["#category-10", "#category-11", "#category-17"].includes(window.location.hash)) return;
    const id = window.location.hash.slice(1);
    window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "start" }), 250);
  }, []);

  async function generateReview() {
    setStatus("Generating self-critiqued review...");
    try {
      const result = await fetch(`${apiBaseUrl}/writing/literature-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "Resora Literature Review",
          extracted_text:
            "Smith et al. 2025 show hybrid retrieval improves grounded academic writing. This review studies multimodal retrieval systems, benchmark datasets, trust-aware synthesis, limitations, and future directions.",
          figures: [{ figure_id: "fig-1", caption: "Figure 1: Retrieval accuracy across benchmark datasets", chart_type: "line", description: "Accuracy trend", data_insights: ["Accuracy rises after hybrid fusion"] }],
          tables: [{ table_id: "tab-1", caption: "Table 1: Benchmark comparison", headers: ["Method", "Accuracy"], rows: [["Hybrid", "89"]], csv_export: "Method,Accuracy\nHybrid,89" }],
          target_style: "ieee",
          target_journal: "IEEE Access",
          citation_style: citationStyle.toLowerCase(),
          tone,
          mode,
          disclosure_watermark: true,
          word_count_target: 1200,
          section_length_targets: { Abstract: 25 },
          comments: ["Supervisor: strengthen conclusion with more evidence."],
        }),
      });
      if (!result.ok) throw new Error(`Writing API ${result.status}`);
      const data = (await result.json()) as WritingResponse;
      setWriting(data);
      setActiveSection(data.outline[0] || "Abstract");
      setStatus("Review generated with self-critique");
    } catch (error) {
      setWriting(demoWriting);
      setStatus(error instanceof Error ? `Demo package restored: ${error.message}` : "Demo package restored");
    }
  }

  async function saveLibrary() {
    setStatus("Saving team reference library...");
    try {
      const result = await fetch(`${apiBaseUrl}/library/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          papers: [demoPaper, { ...demoPaper, paper_id: "w2", doi: "10.1000/resora.2" }],
          folder: "Core",
          collection: "Deepfake/RAG",
          tags: ["rag", "benchmark"],
          workspace_id: "ws-1",
          shared_team_library: true,
          persistent_highlights: { w1: ["Hybrid retrieval improves accuracy."] },
        }),
      });
      if (!result.ok) throw new Error(`Library API ${result.status}`);
      const data = (await result.json()) as LibraryResponse;
      setLibrary(data);
      setStatus("Reference library updated");
    } catch (error) {
      setLibrary(demoLibrary);
      setStatus(error instanceof Error ? `Demo library restored: ${error.message}` : "Demo library restored");
    }
  }

  function exportArtifact(format: string) {
    const content = format === "BibTeX" ? library?.bibliography_export || "" : JSON.stringify({ writing, library, category_4_reference_management: category4, category_5_ai_drafting_copilot: category5, category_6_style_grammar: category6, category_7_latex_math_code: category7, category_17_presentation_slide_generation: category17, format }, null, 2);
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `resora-writing-${format.toLowerCase()}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus(`${format} export prepared`);
  }

  async function copyText(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setStatus(`${label} copied`);
    } catch {
      setStatus(`${label} ready but clipboard permission is blocked`);
    }
  }

  function regenerateSection(section: string) {
    setActiveSection(section);
    setStatus(`${section} queued for section-only regeneration`);
  }

  const activeText = writing?.sections[activeSection] || "Generate a review to inspect this section.";
  const isCategory17Focus = focusCategory === "category17";

  return (
    <section className={`writing-shell ${isCategory17Focus ? "writing-shell-focus-category17" : ""}`}>
      <section className="writing-hero">
        <div>
          <div className="flex flex-wrap gap-2">
            <span className="status-pill status-pill-gold">10+ page review</span>
            <span className="status-pill status-pill-teal">self critique</span>
            <span className="status-pill status-pill-green">export ready</span>
          </div>
          <p className="writing-kicker">Writing studio</p>
          <h1 className="writing-title">Draft with sources already in place.</h1>
          <p className="writing-subtitle">
            Create reviews, manage citations, and export clean drafts.
          </p>
          <div className="writing-action-row">
            <button type="button" onClick={() => void generateReview()} className="resora-button-primary">Generate review</button>
            <button type="button" onClick={() => void saveLibrary()} className="resora-button-secondary">Save library</button>
            <button type="button" onClick={() => exportArtifact("DOCX")} className="resora-button-ai">Export DOCX</button>
            <button type="button" onClick={() => exportArtifact("LaTeX")} className="resora-button-secondary">Export LaTeX</button>
          </div>
        </div>
        <div className="writing-status-card">
          <p className="resora-label">Draft health</p>
          <TrustRing value={Math.round((writing?.confidence_score || 0) * 100)} max={100} suffix="%" />
          <strong>{status}</strong>
          <span>Readability {writing?.readability_score || 0} · word target {wordProgress}%</span>
          <div className="writing-status-metrics">
            <span><b>{writing?.outline.length || 0}</b> sections</span>
            <span><b>{writing?.export_artifacts.length || 0}</b> exports</span>
            <span><b>{library?.saved_items.length || 0}</b> refs</span>
          </div>
        </div>
      </section>

      <div className={`writing-grid ${isCategory17Focus ? "writing-grid-focus-category17" : ""}`}>
        <aside className="writing-controls">
          <p className="resora-label">Composer controls</p>
          <label>
            <span>Writing mode</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)} className="resora-input">
              <option value="literature_review">10+ page literature review</option>
              <option value="grant_proposal">Grant proposal mode</option>
              <option value="thesis_chapter">Thesis chapter mode</option>
              <option value="peer_response">Peer-review response</option>
            </select>
          </label>
          <label>
            <span>Tone</span>
            <select value={tone} onChange={(event) => setTone(event.target.value)} className="resora-input">
              <option value="formal">Formal academic</option>
              <option value="concise">Concise</option>
              <option value="supervisor">Supervisor review</option>
            </select>
          </label>
          <label>
            <span>Citation style</span>
            <select value={citationStyle} onChange={(event) => setCitationStyle(event.target.value)} className="resora-input">
              {["APA", "IEEE", "MLA", "Chicago", "Vancouver"].map((style) => <option key={style}>{style}</option>)}
            </select>
          </label>
          <button type="button" onClick={() => exportArtifact(citationStyle)} className="resora-button-primary">Export {citationStyle}</button>
          <button type="button" onClick={() => void copyText("Cover letter", writing?.cover_letter || "")} className="resora-button-secondary">Copy cover letter</button>
          <button type="button" onClick={() => void copyText("Peer response", writing?.peer_review_response || "")} className="resora-button-secondary">Copy response</button>
        </aside>

        <main className={focusCategory === "category11" ? "writing-main writing-main-focus-category11" : focusCategory === "category17" ? "writing-main writing-main-focus-category17" : "writing-main"}>
          <section className="writing-draft-card">
            <div className="writing-draft-head">
              <div>
                <p className="resora-label">Draft workspace</p>
                <h2>{writing?.target_style_adaptation.target || "Target journal"}</h2>
              </div>
              <div className="writing-progress">
                <span style={{ width: `${wordProgress}%` }} />
              </div>
            </div>
            <div className="writing-section-tabs">
              {(writing?.outline || []).map((section) => (
                <button key={section} type="button" onClick={() => setActiveSection(section)} className={section === activeSection ? "writing-tab writing-tab-active" : "writing-tab"}>
                  {section}
                </button>
              ))}
            </div>
            <article className="writing-paper">
              <p className="resora-label">{activeSection}</p>
              <h3>{activeSection}</h3>
              <p>{activeText}</p>
              <div className="writing-paper-actions">
                <button type="button" onClick={() => regenerateSection(activeSection)} className="resora-button-secondary">Regenerate section</button>
                <button type="button" onClick={() => void copyText(activeSection, activeText)} className="resora-button-ai">Copy section</button>
              </div>
            </article>
          </section>

          <section className="writing-panel-grid">
            <QualityPanel title="Self-critique and plagiarism" tone="danger">
              <Metric label="Similarity" value={`${writing?.plagiarism_report.similarity_percent || 0}%`} />
              <p>{String(writing?.plagiarism_report.plagiarism_risk || "not checked")} risk. {writing?.citation_diversity_nudge}</p>
              {(writing?.academic_style_corrections || []).map((item) => <span key={item}>{item}</span>)}
            </QualityPanel>
            <QualityPanel title="Citation styles" tone="blue">
              <p className="writing-citation-preview">{citationPreview}</p>
              <p>Reference list entries: {writing?.reference_list.length || 0}</p>
              <button type="button" onClick={() => exportArtifact("BibTeX")} className="resora-button-secondary">Export BibTeX</button>
            </QualityPanel>
          </section>

          <section className="writing-panel-grid writing-panel-grid-three">
            <QualityPanel title="Figure/table insertion">
              {(writing?.figure_table_insertions || []).map((item) => <span key={Object.values(item).join("-")}>{item.figure_id || item.table_id}: {item.caption}</span>)}
            </QualityPanel>
            <QualityPanel title="Track changes">
              {(writing?.track_changes || []).map((item) => <span key={item.after}>Before: {item.before} After: {item.after}</span>)}
            </QualityPanel>
            <QualityPanel title="Version history">
              {(writing?.version_history || []).map((item) => <span key={item.version}>{item.version}: {item.note}</span>)}
              <button
                type="button"
                onClick={() => setStatus(`Rollback preview: ${writing?.rollback_preview?.version || writing?.version_history?.[0]?.version || "v1"}`)}
                className="resora-button-secondary"
              >
                Preview rollback
              </button>
            </QualityPanel>
          </section>

          <section className="category-five-board">
            <div className="category-five-head">
              <div>
                <p className="resora-label">Category 5 - AI writing and drafting copilot</p>
                <h2>Write papers 10x faster.</h2>
                <p>Generate abstracts, titles, sections, transitions, reviewer replies, statements, tone rewrites, and safe manuscript branches from the active evidence pack.</p>
              </div>
              <div className="category-five-score">
                <strong>{category5.completion.length}/25</strong>
                <span>features active</span>
              </div>
            </div>

            <div className="category-five-metrics">
              <Metric label="abstracts" value={String(category5.abstracts.length)} />
              <Metric label="sections" value={String(category5.sectionBuilders.length)} />
              <Metric label="score" value={String(category5.quality.find((item) => item.check === "Structure quality")?.result || 91)} />
              <Metric label="branches" value={String(category5.versions.length)} />
            </div>

            <div className="category-five-feature-grid">
              {category5.completion.map((feature) => (
                <article key={feature.feature} className="category-five-feature">
                  <span>{feature.status}</span>
                  <strong>{feature.feature}</strong>
                  <p>{feature.evidence}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="category-five-workbench">
            <CitationTable title="Abstract generator" rows={category5.abstracts} columns={["version", "text", "use"]} />
            <CitationTable title="Section auto-builders" rows={category5.sectionBuilders} columns={["section", "output", "source"]} />
            <CitationTable title="Titles and hooks" rows={category5.titleHooks} columns={["type", "text"]} />
            <CitationTable title="AI outline with word targets" rows={category5.outline} columns={["section", "level", "words", "purpose"]} />
          </section>

          <section className="category-five-lanes">
            <CitationLane title="Sentence tools" rows={category5.sentenceTools} mainKey="tool" subKey="output" />
            <CitationLane title="Blind spots and structure" rows={category5.quality} mainKey="check" subKey="severity" />
            <CitationLane title="Coherence map" rows={category5.coherence} mainKey="from" subKey="bridge" />
            <CitationLane title="Tone and lexicon" rows={category5.toneLexicon} mainKey="mode" subKey="rewrite" />
          </section>

          <section className="category-five-workbench category-five-workbench-compact">
            <CitationTable title="Reviewer and cover package" rows={category5.reviewerPackage} columns={["item", "text"]} />
            <CitationTable title="Submission statements" rows={category5.statements} columns={["statement", "text"]} />
            <CitationTable title="Originality guard" rows={category5.originality} columns={["signal", "value", "status"]} />
            <CitationTable title="Version history and branches" rows={category5.versions} columns={["version", "note"]} />
          </section>

          <section className="category-six-board">
            <div className="category-six-head">
              <div>
                <p className="resora-label">Category 6 - Paraphrasing, style and grammar</p>
                <h2>Perfect academic English.</h2>
                <p>Rewrite, polish, balance, standardize, and audit academic prose with rollback-ready grammar and style changes.</p>
              </div>
              <div className="category-six-score">
                <strong>{category6.completion.length}/25</strong>
                <span>features active</span>
              </div>
            </div>

            <div className="category-six-metrics">
              <Metric label="paraphrase" value={String(category6.paraphrases.length)} />
              <Metric label="grammar" value={String(category6.grammarFixes.length)} />
              <Metric label="readability" value={String(writing?.readability_score || 82)} />
              <Metric label="revisions" value={String(category6.revisionLog.length)} />
            </div>

            <div className="category-six-feature-grid">
              {category6.completion.map((feature) => (
                <article key={feature.feature} className="category-six-feature">
                  <span>{feature.status}</span>
                  <strong>{feature.feature}</strong>
                  <p>{feature.evidence}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="category-six-workbench">
            <CitationTable title="Advanced paraphraser" rows={category6.paraphrases} columns={["mode", "before", "after"]} />
            <CitationTable title="Grammar and punctuation fixes" rows={category6.grammarFixes} columns={["issue", "before", "after"]} />
            <CitationTable title="Voice and academic tone" rows={category6.voiceAndTone} columns={["tool", "before", "after"]} />
            <CitationTable title="Word choice and inclusivity" rows={category6.wordChoice} columns={["check", "term", "count", "suggestion"]} />
          </section>

          <section className="category-six-lanes">
            <CitationLane title="Readability and balance" rows={category6.readability} mainKey="paragraph" subKey="action" />
            <CitationLane title="Structure checks" rows={category6.structureChecks} mainKey="check" subKey="after" />
            <CitationLane title="Punctuation and quotes" rows={category6.punctuationQuotes} mainKey="item" subKey="guidance" />
            <CitationLane title="Phrasebank and hedging" rows={category6.phrasebankHedging} mainKey="type" subKey="phrase" />
          </section>

          <section className="category-six-workbench category-six-workbench-compact">
            <CitationTable title="Format consistency" rows={category6.consistency} columns={["check", "result"]} />
            <CitationTable title="Draft comparison" rows={category6.draftComparison} columns={["part", "text"]} />
            <CitationTable title="Revision history log" rows={category6.revisionLog} columns={["revision", "before", "after"]} />
            <CitationTable title="Academic phrasebank access" rows={category6.phrasebankHedging} columns={["type", "phrase"]} />
          </section>

          <section className="category-seven-board">
            <div className="category-seven-head">
              <div>
                <p className="resora-label">Category 7 - LaTeX, math and code integration</p>
                <h2>STEM-ready equations and code.</h2>
                <p>Convert equations, validate notation, format algorithms, cite packages, capture environments, and export vector math assets for STEM manuscripts.</p>
              </div>
              <div className="category-seven-score">
                <strong>{category7.completion.length}/25</strong>
                <span>features active</span>
              </div>
            </div>

            <div className="category-seven-metrics">
              <Metric label="equations" value={String(category7.equations.length)} />
              <Metric label="code tools" value={String(category7.codeTools.length)} />
              <Metric label="validators" value={String(category7.validators.length)} />
              <Metric label="exports" value={String(category7.exports.length)} />
            </div>

            <div className="category-seven-feature-grid">
              {category7.completion.map((feature) => (
                <article key={feature.feature} className="category-seven-feature">
                  <span>{feature.status}</span>
                  <strong>{feature.feature}</strong>
                  <p>{feature.evidence}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="category-seven-workbench">
            <CitationTable title="LaTeX equation lab" rows={category7.equations} columns={["tool", "input", "output"]} />
            <CitationTable title="Code integration tools" rows={category7.codeTools} columns={["tool", "language", "output"]} />
            <CitationTable title="LaTeX and Overleaf workflow" rows={category7.latexWorkflow} columns={["feature", "output"]} />
            <CitationTable title="Reproducible environment" rows={category7.reproducibility} columns={["item", "status", "detail"]} />
          </section>

          <section className="category-seven-lanes">
            <CitationLane title="Algorithm tools" rows={category7.algorithms} mainKey="tool" subKey="output" />
            <CitationLane title="Math/stat validators" rows={category7.validators} mainKey="check" subKey="result" />
            <CitationLane title="Chemistry and DNA" rows={category7.chemistryBio} mainKey="tool" subKey="output" />
            <CitationLane title="Vector exports" rows={category7.exports} mainKey="format" subKey="artifact" />
          </section>

          <section id="reference-library" className="writing-library-card">
            <div className="writing-draft-head">
              <div>
                <p className="resora-label">Reference management</p>
                <h2>Zotero-style team library</h2>
              </div>
              <span className="status-pill status-pill-gold">{library?.saved_items.length || 0} saved papers</span>
            </div>
            <div className="writing-library-grid">
              {(library?.saved_items || []).map((item) => (
                <article key={item.paper_id} className="writing-reference-card">
                  <p className="resora-label">{item.folder || "Library"}</p>
                  <h3>{item.title}</h3>
                  <span>{item.open_access_resolution}</span>
                  <div>{item.tags.map((tag) => <em key={tag}>{tag}</em>)}</div>
                </article>
              ))}
            </div>
          </section>

          <section className="category-four-board">
            <div className="category-four-head">
              <div>
                <p className="resora-label">Category 4 - Reference and citation management</p>
                <h2>Automatic, contextual citations.</h2>
                <p>Manage references, clean metadata, recommend citations while writing, verify cited claims, export thesis bibliographies, and sync team libraries.</p>
              </div>
              <div className="category-four-score">
                <strong>{category4.completion.length}/25</strong>
                <span>features active</span>
              </div>
            </div>

            <div className="category-four-metrics">
              <Metric label="styles" value="10000+" />
              <Metric label="deduped" value={String(category4.dedupedReferences.length)} />
              <Metric label="recommend" value={String(category4.recommendations.length)} />
              <Metric label="exports" value={String(category4.masterExports.length)} />
            </div>

            <div className="category-four-feature-grid">
              {category4.completion.map((feature) => (
                <article key={feature.feature} className="category-four-feature">
                  <span>{feature.status}</span>
                  <strong>{feature.feature}</strong>
                  <p>{feature.evidence}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="category-four-workbench">
            <CitationTable title="Auto-deduped references" rows={category4.dedupedReferences} columns={["id", "title", "rule", "merged_fields"]} />
            <CitationTable title="Citation recommendations" rows={category4.recommendations} columns={["sentence", "recommendation", "formatted"]} />
            <CitationTable title="Reference cleanup" rows={category4.cleanupQueue} columns={["paper", "doi", "pages", "journal"]} />
            <CitationTable title="Priority and projection" rows={[...category4.prioritySort, ...category4.citationProjection]} columns={["rank", "paper", "score", "reason", "current", "projected_12m", "trend"]} />
          </section>

          <section className="category-four-lanes">
            <CitationGraphPanel graph={category4.citationGraph} />
            <CitationLane title="Styles and import" rows={[...category4.styleCoverage, ...category4.imports]} mainKey="pack" subKey="active" />
            <CitationLane title="Cloud, team, folders" rows={[...category4.cloudAndTeam, ...category4.folders, ...category4.teamDedup]} mainKey="feature" subKey="sync" />
            <CitationLane title="Verification and safety" rows={[...category4.missingReferences, ...category4.fatigue, ...category4.verification, ...category4.selfCitation, ...category4.retractions]} mainKey="suggestion" subKey="result" />
          </section>

          <section className="category-four-workbench category-four-workbench-compact">
            <CitationTable title="Archive restore and PDF naming" rows={[...category4.restoration, ...category4.pdfRenames]} columns={["paper", "archive", "filename", "status"]} />
            <CitationTable title="Citation memory and uncited alerts" rows={[...category4.contextMemory, ...category4.uncited]} columns={["citation", "why", "revisit", "paper", "title", "action"]} />
            <CitationTable title="Journal suggestions" rows={category4.journalSuggestions} columns={["journal", "fit", "reason"]} />
            <CitationTable title="Master exports and integrations" rows={[...category4.masterExports, ...category4.integrations]} columns={["format", "file", "app", "status", "action"]} />
          </section>

          <section id="category-10" className="category-ten-board">
            <div className="category-ten-head">
              <div>
                <p className="resora-label">Category 10 - Journal targeting and submission</p>
                <h2>Find the right journal and submit cleanly.</h2>
                <p>Match journals, rank venue quality, estimate acceptance and review time, build submission assets, check ethics risks, suggest editors/reviewers, and track post-submission status.</p>
              </div>
              <div className="category-ten-score">
                <strong>{category10.completion.length}/25</strong>
                <span>features active</span>
              </div>
            </div>

            <div className="category-ten-metrics">
              <Metric label="matches" value={String(category10.journalMatches.length * 10)} />
              <Metric label="ranked" value={String(category10.journalMetrics.length)} />
              <Metric label="preflight" value={String(category10.checklistReview.length)} />
              <Metric label="trackers" value={String(category10.tracking.length)} />
            </div>

            <div className="category-ten-feature-grid">
              {category10.completion.map((feature) => (
                <article key={feature.feature} className="category-ten-feature">
                  <span>{feature.status}</span>
                  <strong>{feature.feature}</strong>
                  <p>{feature.evidence}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="category-ten-workbench">
            <CitationTable title="Journal suggestor - top matches" rows={category10.journalMatches} columns={["journal", "fit", "audience", "match_basis"]} />
            <CitationTable title="Journal ranking display" rows={category10.journalMetrics} columns={["journal", "impact_factor", "citescore", "sjr", "h_index"]} />
            <CitationTable title="Acceptance and turnaround predictors" rows={category10.submissionRisk} columns={["feature", "journal", "probability", "rationale"]} />
            <CitationTable title="Special issues, fees, waivers, trends" rows={category10.issueFees} columns={["feature", "journal", "value", "action"]} />
          </section>

          <section className="category-ten-lanes">
            <CitationLane title="Formatting and visual assets" rows={category10.formattingAssets} mainKey="feature" subKey="status" />
            <CitationLane title="Pre-submission QA" rows={[...category10.checklistReview, ...category10.ethicsSafety]} mainKey="feature" subKey="score" />
            <CitationLane title="Portals and author forms" rows={category10.integrationsForms} mainKey="feature" subKey="status" />
            <CitationLane title="Editors, reviewers, tracker" rows={[...category10.peopleTargets, ...category10.tracking]} mainKey="feature" subKey="reason" />
          </section>

          <section id="category-11" className="category-eleven-board">
            <div className="category-eleven-head">
              <div>
                <p className="resora-label">Category 11 - Grant writing and funding discovery</p>
                <h2>Secure funding faster.</h2>
                <p>Discover global calls, filter eligibility, score grant fit, draft proposal sections, build agency templates, justify budgets, manage endorsements, and prepare progress reports.</p>
              </div>
              <div className="category-eleven-score">
                <strong>{category11.completion.length}/25</strong>
                <span>features active</span>
              </div>
            </div>

            <div className="category-eleven-metrics">
              <Metric label="databases" value="50+" />
              <Metric label="calls" value={String(category11.opportunities.length)} />
              <Metric label="templates" value={String(category11.agencyTemplates.length)} />
              <Metric label="budget lines" value={String(category11.budget.length)} />
            </div>

            <div className="category-eleven-feature-grid">
              {category11.completion.map((feature) => (
                <article key={feature.feature} className="category-eleven-feature">
                  <span>{feature.status}</span>
                  <strong>{feature.feature}</strong>
                  <p>{feature.evidence}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="category-eleven-workbench">
            <CitationTable title="Funding opportunity aggregator" rows={category11.opportunities} columns={["funder", "scheme", "amount", "deadline", "country"]} />
            <CitationTable title="Grant fit score and filters" rows={category11.fitScoring} columns={["call", "fit", "reason", "filter"]} />
            <CitationTable title="Grant proposal outliner" rows={category11.proposalPackage} columns={["section", "output", "words"]} />
            <CitationTable title="Agency template engine" rows={category11.agencyTemplates} columns={["agency", "template", "status"]} />
          </section>

          <section className="category-eleven-lanes">
            <CitationLane title="Budget and F&A" rows={category11.budget} mainKey="item" subKey="justification" />
            <CitationLane title="People and support" rows={category11.peopleSupport} mainKey="feature" subKey="status" />
            <CitationLane title="Impact, DMP, abstract" rows={category11.impactData} mainKey="feature" subKey="audience" />
            <CitationLane title="Calendar, rebuttal, reports" rows={[...category11.compliance, ...category11.integrationsReports]} mainKey="feature" subKey="score" />
          </section>

          <section id="category-17" className="category-seventeen-board">
            <div className="category-seventeen-head">
              <div>
                <p className="resora-label">Category 17 - Presentation and slide generation</p>
                <h2>Turn your paper into a presentation in minutes.</h2>
                <p>Create PPT decks, talk scripts, posters, 3-minute thesis pitches, carousels, narration, video intros, Q&A prep, rehearsal feedback, flashcards, and export-ready design assets.</p>
              </div>
              <div className="category-seventeen-score">
                <strong>{category17.completion.length}/25</strong>
                <span>features active</span>
              </div>
            </div>

            <div className="category-seventeen-metrics">
              <Metric label="slides" value={String(category17.slideDeck.length)} />
              <Metric label="timing" value="7:30" />
              <Metric label="Q&A" value={String(category17.qaPrep.length)} />
              <Metric label="exports" value={String(category17.designExport.length)} />
            </div>

            <div className="category-seventeen-feature-grid">
              {category17.completion.map((feature) => (
                <article key={feature.feature} className="category-seventeen-feature">
                  <span>{feature.status}</span>
                  <strong>{feature.feature}</strong>
                  <p>{feature.evidence}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="category-seventeen-deck">
            {category17.slideDeck.slice(0, 6).map((slide) => (
              <article key={String(slide.slide)} className="category-seventeen-slide">
                <span>Slide {String(slide.slide).padStart(2, "0")}</span>
                <h3>{String(slide.title)}</h3>
                <p>{String(slide.content)}</p>
                <em>{String(slide.asset)}</em>
              </article>
            ))}
          </section>

          <section className="category-seventeen-workbench">
            <CitationTable title="Auto-PPT generation deck plan" rows={category17.slideDeck} columns={["slide", "title", "content", "asset", "export"]} />
            <CitationTable title="Talk script, notes, timing, narration, rehearsal" rows={category17.scriptsTiming} columns={["feature", "slide", "output", "timing"]} />
            <CitationTable title="Q&A, interview prep and flashcards" rows={category17.qaPrep} columns={["feature", "question", "answer", "priority"]} />
            <CitationTable title="Audience, 3MT, elevator and conference formats" rows={category17.audienceFormats} columns={["feature", "format", "output", "length"]} />
          </section>

          <section className="category-seventeen-lanes">
            <CitationLane title="Poster, carousel, video, press" rows={category17.mediaAssets} mainKey="feature" subKey="output" />
            <CitationLane title="Design, animation and exports" rows={category17.designExport} mainKey="feature" subKey="output" />
            <CitationLane title="Rehearsal flashcards" rows={category17.rehearsalCards} mainKey="card" subKey="prompt" />
          </section>
        </main>

        <aside className="writing-side">
          <SidePanel title="Export package">
            {(writing?.export_artifacts || []).map((artifact) => (
              <button key={artifact.file_name} type="button" onClick={() => exportArtifact(artifact.format)} className="writing-export-button">
                <strong>{artifact.format}</strong>
                <span>{artifact.file_name} · {Math.round(artifact.byte_size / 1000)} KB</span>
              </button>
            ))}
            <button type="button" onClick={() => setStatus("Overleaf export link prepared")} className="resora-button-primary">Open Overleaf export</button>
          </SidePanel>

          <SidePanel title="Co-author review">
            {(writing?.coauthor_comments || []).map((comment) => <p key={comment}>{comment}</p>)}
            {(writing?.transition_suggestions || []).map((item) => <span key={item}>{item}</span>)}
          </SidePanel>

          <SidePanel title="Library graph">
            <p>Unread queue: {(library?.unread_queue || []).join(", ") || "clear"}</p>
            <p>Graph nodes: {library?.personal_citation_graph.nodes.length || 0}</p>
            <p>Duplicate groups: {Object.keys(library?.duplicate_groups || {}).length}</p>
            <p>Exports: {Object.keys(library?.full_library_bibliography_exports || {}).join(", ")}</p>
          </SidePanel>
        </aside>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="writing-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function QualityPanel({ title, tone = "default", children }: { title: string; tone?: "default" | "danger" | "blue"; children: ReactNode }) {
  return (
    <section className={`writing-quality writing-quality-${tone}`}>
      <p className="resora-label">{title}</p>
      <div>{children}</div>
    </section>
  );
}

function CitationTable({ title, rows, columns }: { title: string; rows: Array<Record<string, string | number>>; columns: string[] }) {
  return (
    <section className="category-four-table-card">
      <div className="writing-draft-head">
        <div>
          <p className="resora-label">{title}</p>
          <h2>{rows.length} records</h2>
        </div>
        <span className="status-pill status-pill-green">checked</span>
      </div>
      <div className="category-four-table-wrap">
        <table className="category-four-table">
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column.split("_").join(" ")}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, 6).map((row, index) => (
              <tr key={`${title}-${index}`}>
                {columns.map((column) => <td key={`${title}-${index}-${column}`}>{String(row[column] ?? "-")}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CitationGraphPanel({ graph }: { graph: Category4ReferenceSuite["citationGraph"] }) {
  const points = [
    { x: 18, y: 42 },
    { x: 54, y: 18 },
    { x: 78, y: 58 },
    { x: 42, y: 72 },
  ];
  return (
    <section className="category-four-lane category-four-graph">
      <p className="resora-label">Cited By personal graph</p>
      <svg viewBox="0 0 100 86" role="img" aria-label="Personal citation graph">
        {graph.edges.map((edge, index) => {
          const sourceIndex = Math.max(0, graph.nodes.findIndex((node) => node.id === edge.source));
          const targetIndex = Math.max(0, graph.nodes.findIndex((node) => node.id === edge.target));
          const source = points[sourceIndex % points.length];
          const target = points[targetIndex % points.length];
          return <line key={`${edge.source}-${edge.target}-${index}`} x1={source.x} y1={source.y} x2={target.x} y2={target.y} />;
        })}
        {graph.nodes.map((node, index) => {
          const point = points[index % points.length];
          return (
            <g key={String(node.id)}>
              <circle cx={point.x} cy={point.y} r="8" />
              <text x={point.x} y={point.y + 18} textAnchor="middle">{String(node.id).toUpperCase()}</text>
            </g>
          );
        })}
      </svg>
      <div>
        {graph.edges.map((edge, index) => (
          <p key={`${edge.source}-${edge.target}-${index}`}>
            <strong>{`${edge.source} -> ${edge.target}`}</strong>
            <span>{edge.label || "citation context"}</span>
          </p>
        ))}
      </div>
    </section>
  );
}

function CitationLane({ title, rows, mainKey, subKey }: { title: string; rows: Array<Record<string, string | number>>; mainKey: string; subKey: string }) {
  return (
    <section className="category-four-lane">
      <p className="resora-label">{title}</p>
      <div>
        {rows.slice(0, 7).map((row, index) => {
          const main = row[mainKey] ?? row.paper ?? row.author ?? row.format ?? row.folder ?? row.rule ?? row.claim ?? row.app ?? "record";
          const sub = row[subKey] ?? row.status ?? row.action ?? row.alert ?? row.reason ?? row.sync ?? "ready";
          return (
            <p key={`${title}-${index}`}>
              <strong>{String(main)}</strong>
              <span>{String(sub)}</span>
            </p>
          );
        })}
      </div>
    </section>
  );
}

function SidePanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="writing-side-panel">
      <p className="resora-label">{title}</p>
      <div>{children}</div>
    </section>
  );
}
