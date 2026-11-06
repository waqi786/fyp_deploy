# RESORA Product Specification

Traceability checklist derived from `docs/source/Resora_Product_Vision.pdf` (Vision sections 1-34) and `docs/source/RESORA-Proposal-Final.pdf` (objectives, scope, components, use cases, risks and future work). The source documents describe a mix of committed project goals and future/optional vision; each item retains that distinction in its text. Status is tracked separately in root `STATUS.md`.

## Product objective

Provide one accessible research workflow for discovery, understanding, verification, comparison, organization, analysis and research-grounded writing. The system supports researchers; it does not replace expert judgment.

## Home & research workspace

- [ ] **HOME-01** - Unified research workflow and central research home; project overview, tasks, milestones, deadlines, notes, ideas and reading lists (Vision 20, 33-34).

## Search & discovery

- [ ] **SRCH-01** - Multi-source academic search with normalized paper records and metadata (Vision 3-5; Proposal goals/scope).
- [ ] **SRCH-02** - Keyword, DOI, natural-language, title, semantic, topic, hybrid, citation, author, reference, exact-phrase, similar-paper and citing-paper search (Vision 4).
- [ ] **SRCH-03** - Research-question understanding, query generation, multi-source retrieval, deduplication, ranking, grouping, findings, conflicts, emerging approaches, evidence, gap signals and selection rationale (Vision 5).
- [ ] **SRCH-04** - Filters for date, method, author, model, institution, dataset, journal, task, conference, access, citations, review status, topic and publication type (Vision 4).
- [ ] **SRCH-05** - Merge duplicate records across sources; preserve trustworthy metadata and source transparency (Vision 4, 29).
- [ ] **SRCH-06** - Search/research outputs include authorship, publication, citation details and quick summaries (Proposal goals and web application).

## Library & workspace

- [ ] **LIB-01** - Normalized research database for papers, authors, citations, institutions, references, topics, venues, methods, projects, datasets, code, tasks, relationships and metrics (Vision 6-7).
- [ ] **LIB-02** - User-owned workspace and research memory for saved papers, notes, highlights, searches, interests, projects, AI conversations, comparisons, gaps, datasets, code and tasks (Vision 20-21, 33).
- [ ] **LIB-03** - Citation management: folders, collections, tags, DOI, styles and BibTeX/RIS/EndNote/CSL-JSON/Markdown export; Zotero/LaTeX/Word/Overleaf are future integrations (Vision 26).

## Reader & document intelligence

- [ ] **READ-01** - Paper detail and structured summary covering problem, motivation, contributions, methods, experiments, results, limitations, future work, references and key metadata (Vision 8; Proposal).
- [ ] **READ-02** - Grounded paper Q&A with verifiable source passage, paper, page/section, citation and confidence/evidence strength (Vision 8, 10).
- [ ] **READ-03** - PDF extraction and OCR for normal and scanned PDFs; preserve layout/text and support figures, tables, equations, footnotes, references, captions and supplementary content (Vision 9; Proposal).
- [ ] **READ-04** - Explain or answer questions about specific figures, tables, equations, datasets, metrics, sample size, baselines and code availability (Vision 8-9; Proposal).
- [ ] **READ-05** - Short, structured and detailed summaries; simpler English and Urdu explanations; keyword extraction (Proposal goals/use cases).

## Compare & evidence

- [ ] **COMP-01** - Compare 2-15 papers (and larger sets as scale allows) across problem, method, dataset, model, metrics, results, limitation and user-requested columns (Vision 11).
- [ ] **COMP-02** - Multi-paper literature analysis: evidence extraction, topic/method grouping, comparison, contradiction analysis and supported conclusions (Vision 11, 22).
- [ ] **COMP-03** - Detect supporting, opposing and mixed evidence; explain possible methodological differences with sources (Vision 13-14).

## Gaps, trends & intelligence

- [ ] **GAPS-01** - Evidence-based potential gap signals with corpus counts, supporting papers and explicit strong/moderate/limited/hypothesis confidence distinctions (Vision 12).
- [ ] **GAPS-02** - Research trends: publication/citation growth, clusters, keywords, topics, methods, researchers, institutions, models and datasets across time (Vision 17).
- [ ] **GAPS-03** - Researcher and institution/lab discovery: publications, topics, collaborators, timelines, labs and recent work (Vision 18-19).
- [ ] **GAPS-04** - Personalized recommendations with explanations tied to saved work, datasets, methods, interests and identified limitations (Vision 15).
- [ ] **GAPS-05** - Research alerts for topics, journals, people, conferences, methods, projects and datasets; daily/weekly/monthly briefs (Vision 16).
- [ ] **GAPS-06** - Dataset intelligence: datasets, papers, metrics, sample size, tasks, models, access and license metadata (Vision 30).
- [ ] **GAPS-07** - Code/reproducibility intelligence and transparent checklist for code, data, hyperparameters, experimental details, models and licenses (Vision 31-32).

## Writing & review

- [ ] **WRITE-01** - Research-grounded drafts for literature review, questions, introduction, abstract, related work, conclusion, proposal and outline, with inspectable citations (Vision 25; Proposal).
- [ ] **WRITE-02** - Literature review pipeline: collection, screening, eligibility, extraction, clustering, evidence, comparison, contradictions, gaps, outline and cited draft for 30-50 papers (Vision 22).
- [ ] **WRITE-03** - Screening decisions, duplicate detection, exclusion reasons, eligibility criteria, full-text status, notes, tags and reviewer assignments (Vision 23).
- [ ] **WRITE-04** - PRISMA-oriented record counts from identification through deduplication, screening, full-text assessment and inclusion (Vision 24).
- [ ] **WRITE-05** - Citation intelligence and claim verification: identify claims, search selected research, check support, suggest stronger sources and show evidence strength (Vision 27-28).

## Account, plans & trust

- [ ] **ACCOUNT-01** - Accounts and settings; persist user workspace, search and chat history (Proposal architecture).
- [ ] **ACCOUNT-02** - Transparent trust metadata: review/preprint, date, venue, citations, DOI verification, retractions/corrections and OA/full-text availability (Vision 29).
- [ ] **ACCOUNT-03** - Confidence/evidence indicators, retrieval-grounded generation and clear human-review expectations (Proposal risks; Vision 10, 12-14, 32).

## Teams & collaboration

- [ ] **TEAMS-01** - Optional shared reading lists, collaborative literature-review editing, independent screening and decision comparison, supervisor feedback (Vision 23; Proposal optional/future).

## Platform & architecture

- [ ] **PLAT-01** - Responsive modular React/Tailwind frontend, FastAPI backend, academic API connectors, PDF/OCR processing, AI, vector retrieval and persistent data (Proposal architecture/tools).
- [ ] **PLAT-02** - Use free/open academic sources and cache around API limits; prioritize OA/metadata when full text is inaccessible (Proposal scope/risks).
- [ ] **PLAT-03** - Reliability controls for AI inaccuracy, OCR variability, API limits, large comparisons and project time; retain human judgment (Proposal risks/constraints).
- [ ] **PLAT-04** - Optional future voice chat, offline/mobile reading, reference-manager integrations, journal recommendations, plagiarism support, trend prediction and richer citation graph (Proposal optional/future; Vision future enhancements).

## Proposal constraints and context

- Target users: undergraduate/Master-s/FYP/thesis students, PhD researchers, academics, supervisors, research assistants, study groups and industry R&D. (Proposal, -4)
- Initial domain focus: Data Science, Computer Science, AI, Machine Learning and related research. (Proposal, -1.4)
- Explicit exclusions from current scope: paid academic databases, plagiarism checking, journal submission, and replacing expert supervision. (Proposal, -1.4)
- Risks to manage: restricted full text, upstream API limits, inaccurate generated content, OCR quality, large comparison workloads and FYP schedule. (Proposal, -5)
- Proposed stack in the source proposal: React/Tailwind, FastAPI, free academic APIs, PyMuPDF/Tesseract, Groq/Llama/Mistral options, Sentence-Transformers/FAISS, PostgreSQL/SQLite and Docker. This is source-document context, not a guarantee that every technology is currently active or license-cleared. (Proposal, --1.7-1.9)

## Source mapping

- Vision section 1 frames production readiness and the overall product direction; sections 2-34 map to the feature IDs above by their named product area.
- Proposal objectives map to `SRCH-01`, `SRCH-06`, `READ-01`-`READ-05`, `COMP-01`-`COMP-03`, `GAPS-01`, `WRITE-01` and `PLAT-01`. Proposal scope, components, use cases and risks map to `ACCOUNT-*`, `TEAMS-*` and `PLAT-*` as noted in each item.
- Vision sections 1-2 and the proposal executive summary establish the product objective; they are not independent screen-level acceptance criteria.
