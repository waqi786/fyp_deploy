import re
from collections import Counter
import json
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from app.schemas.comparison import ComparisonRequest, ComparisonResponse, ComparisonRow, InsightEvidenceRef, InsightKeyNumber, InsightsModel, PaperProfile
from app.schemas.paper import PaperRecord
from app.services.comparison.profiles import build_paper_profile


TOKEN_PATTERN = re.compile(r"\b[a-zA-Z][a-zA-Z-]+\b")
STOPWORDS = {"the", "and", "for", "with", "this", "that", "from", "into", "using", "study", "paper"}


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text or "")
        if token.lower() not in STOPWORDS
    }


class ComparisonEngine:
    def compare(self, payload: ComparisonRequest, cached_profiles: list[PaperProfile] | None = None) -> ComparisonResponse:
        rows: list[ComparisonRow] = []
        auto_columns = self._auto_suggest_columns(payload.papers, payload.focus)
        resolved_columns = self._resolve_custom_columns(payload.custom_columns)
        extraction_columns = self._resolve_custom_columns([*auto_columns, *resolved_columns])
        token_sets = {paper.paper_id: _tokens(f"{paper.title} {paper.abstract or ''} {paper.full_text or ''}") for paper in payload.papers}
        aggregate_terms = Counter(term for tokens in token_sets.values() for term in tokens)

        for paper in payload.papers:
            strengths = []
            weaknesses = []
            if paper.citation_count >= 100:
                strengths.append("High citation traction")
            elif paper.citation_count == 0:
                weaknesses.append("No citation traction yet")
            if paper.is_open_access:
                strengths.append("Open access available")
            else:
                weaknesses.append("Closed access may limit reproducibility")
            if paper.abstract and len(paper.abstract) > 180:
                strengths.append("Rich abstract coverage")
            else:
                weaknesses.append("Limited abstract detail")
            if paper.year and paper.year >= 2023:
                strengths.append("Recent publication")

            similarity = self._similarity_to_group(paper, payload.papers, token_sets)
            extracted_columns = {
                column: self._extract_column_value(column, paper)
                for column in extraction_columns
            }
            evidence, evidence_source, confidence_by_column = {}, {}, {}
            for column, value in extracted_columns.items():
                quote, source, confidence = self._evidence_for_column(column, value, paper)
                analysis_note = value.startswith(("Not applicable:", "Conceptual overview", "Narrative review", "Review of prior studies", "Synthesizes prior findings", "No named ", "No single ", "No empirical ", "No explicit ", "No clear ", "Method details not identified"))
                if value != "Not found" and not analysis_note and not quote:
                    extracted_columns[column] = "Not found"
                    value = "Not found"
                if quote:
                    evidence[column] = quote
                    evidence_source[column] = source
                confidence_by_column[column] = confidence
            analysis_text = paper.full_text or paper.abstract or ""
            conceptual_article = self._is_conceptual_article(paper)
            document_type = self._classify_document(paper)
            sections = self._split_sections(analysis_text)
            section_text = "\n".join(body for role in ("abstract", "method", "experimental_setup", "results", "conclusion") for body in sections.get(role, []))
            methods_text = "\n".join(part for part in (paper.title, section_text or analysis_text) if part)
            methods = ["Conceptual synthesis"] if conceptual_article else ["Narrative review"] if document_type == "survey" else self._trusted_facets(paper.methodologies) or self._extract_methods(paper.title, methods_text)
            datasets = [] if conceptual_article else self._trusted_facets(paper.datasets) or self._extract_datasets(analysis_text)
            result_metrics = {} if conceptual_article else self._extract_result_metrics(analysis_text)
            rows.append(
                ComparisonRow(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    source_url=self._source_link(paper),
                    full_text_source_url=paper.full_text_source_url,
                    discovery_source=paper.source,
                    year=paper.year,
                    venue=paper.venue,
                    citation=self._citation(paper),
                    citation_count=paper.citation_count,
                    open_access=paper.is_open_access,
                    abstract_available=bool(paper.abstract and paper.abstract.strip()),
                    full_text_available=bool(paper.full_text and paper.full_text.strip()),
                    full_text_status=paper.full_text_status,
                    full_text_source=paper.full_text_source,
                    document_type=self._classify_document(paper),
                    strengths=strengths,
                    weaknesses=weaknesses,
                    extracted_columns=extracted_columns,
                    evidence=evidence,
                    evidence_source=evidence_source,
                    confidence_by_column=confidence_by_column,
                    similarity_score=round(similarity, 3),
                    method_similarity_score=0.0,
                    dataset_similarity_score=0.0,
                    result_similarity_score=0.0,
                    methods=methods,
                    datasets=datasets,
                    result_metrics=result_metrics,
                    significance_note="Not applicable: conceptual article" if conceptual_article else self._significance_note(analysis_text),
                    pinned=paper.paper_id in payload.pinned_paper_ids,
                )
            )

        rows = self._enrich_similarity_channels(rows)
        rows = self._apply_pinning(rows, payload.pinned_paper_ids)

        leaderboard = [
            row.title
            for row in sorted(rows, key=lambda item: (item.citation_count, item.similarity_score), reverse=True)
        ]
        contradiction_highlights = self._find_contradictions(payload.papers, aggregate_terms)
        narrative = self._build_narrative(payload.papers, rows, payload.focus)
        markdown = self._to_markdown(rows)
        csv_export = self._to_csv(rows)
        latex_export = self._to_latex(rows)
        json_export = self._to_json(rows)
        grouped_methods = self._group_by_method(rows)
        heatmap = self._similarity_heatmap(rows, token_sets)
        method_heatmap = self._channel_heatmap(rows, "methods")
        dataset_heatmap = self._channel_heatmap(rows, "datasets")
        result_heatmap = self._result_heatmap(rows)
        dendrogram = self._methodology_dendrogram(grouped_methods)
        dendrogram_edges = self._dendrogram_edges(rows)
        timeline = self._timeline(rows)
        best = self._best_paper_for_focus(rows, payload.criterion or payload.focus)
        dataset_overlap = self._dataset_overlap(rows)
        dataset_overlap_matrix = self._dataset_overlap_matrix(rows)
        venn = self._citation_overlap_venn(rows)
        citation_sets = self._citation_overlap_sets(rows)
        dataset_leaderboard = self._performance_leaderboard_by_dataset(rows)
        review_section = self._comparison_to_review(rows, payload.focus)
        snapshot_id = f"snap-{uuid4().hex[:10]}"
        share_token = f"cmp-{uuid4().hex[:12]}"
        shareable_url = f"/comparison/share/{share_token}"

        profiles = cached_profiles if cached_profiles is not None else [build_paper_profile(paper) for paper in payload.papers]
        insights_model = self._build_insights_model(rows, profiles)

        return ComparisonResponse(
            focus=payload.focus,
            rows=rows,
            comparison_count=len(rows),
            max_supported_papers=15,
            auto_suggested_columns=auto_columns,
            custom_columns_resolved=resolved_columns,
            contradiction_highlights=contradiction_highlights,
            leaderboard=leaderboard,
            grouped_methods=grouped_methods,
            similarity_heatmap=heatmap,
            method_similarity_heatmap=method_heatmap,
            dataset_similarity_heatmap=dataset_heatmap,
            result_similarity_heatmap=result_heatmap,
            heatmap_labels=[row.title for row in rows],
            methodology_dendrogram=dendrogram,
            dendrogram_edges=dendrogram_edges,
            timeline=timeline,
            performance_leaderboard_by_dataset=dataset_leaderboard,
            best_paper_recommendation=best,
            dataset_overlap=dataset_overlap,
            dataset_overlap_matrix=dataset_overlap_matrix,
            citation_overlap_venn=venn,
            citation_overlap_sets=citation_sets,
            narrative_summary=narrative,
            export_markdown=markdown,
            export_csv=csv_export,
            export_latex=latex_export,
            export_json=json_export,
            comparison_snapshot_id=snapshot_id,
            shareable_link_token=share_token,
            shareable_url=shareable_url,
            snapshot_metadata={
                "snapshot_id": snapshot_id,
                "share_token": share_token,
                "generated_at": datetime.now(UTC).isoformat(),
                "paper_ids": [row.paper_id for row in rows],
                "focus": payload.focus,
                "comparison_count": len(rows),
            },
            literature_review_section=review_section,
            literature_review_export_job={
                "job_id": f"review-{uuid4().hex[:10]}",
                "status": "ready",
                "target": "literature-review-draft",
            },
            pinned_row_order=[row.paper_id for row in rows if row.pinned],
            paper_profiles=profiles,
            insights_model=insights_model,
        )

    def _build_insights_model(self, rows: list[ComparisonRow], profiles: list[PaperProfile]) -> InsightsModel:
        """Build short, deterministic overview facts with source excerpts attached."""
        profile_by_id = {profile.paper_id: profile for profile in profiles}

        def reference(paper_id: str, field: str, quote: str, page: int | None = None) -> InsightEvidenceRef | None:
            quote = " ".join(quote.split())
            if not quote:
                return None
            return InsightEvidenceRef(paper_id=paper_id, field=field, quote=quote[:1200], page=page if page and page > 0 else None)

        all_refs: list[InsightEvidenceRef] = []
        code_refs: list[InsightEvidenceRef] = []
        dataset_refs: list[InsightEvidenceRef] = []
        dataset_names: dict[str, str] = {}
        for row in rows:
            profile = profile_by_id.get(row.paper_id)
            if not profile:
                continue
            page_refs = profile.evidence_pages or profile.experiments or profile.contributions
            if page_refs:
                first = page_refs[0]
                ref = reference(row.paper_id, "full_text", str(first.get("quote") or ""), first.get("page"))
                if ref:
                    all_refs.append(ref)
            code = profile.reproducibility.get("code", {})
            if code.get("status") == "reported":
                ref = reference(row.paper_id, "code", str(code.get("quote") or profile.repo_url or ""), code.get("page"))
                if ref:
                    code_refs.append(ref)
            for dataset in profile.datasets_detail:
                name = " ".join(str(dataset.get("name") or "").split())
                quote = str(dataset.get("quote") or "")
                if not name or not quote:
                    continue
                key = name.casefold()
                dataset_names.setdefault(key, name)
                ref = reference(row.paper_id, "dataset", quote, dataset.get("page"))
                if ref:
                    dataset_refs.append(ref)

        named_datasets = len(dataset_names)
        takeaway = (
            f"{named_datasets} named datasets appear in these PDFs; verify matching metrics and splits before ranking results."
            if named_datasets
            else "These papers do not share a verified dataset, so performance scores should not be ranked across them."
        )
        full_text_refs = [
            ref for row in rows if row.full_text_available
            if (profile := profile_by_id.get(row.paper_id))
            for item in (profile.evidence_pages or profile.experiments or profile.contributions)[:1]
            if (ref := reference(row.paper_id, "full_text", str(item.get("quote") or ""), item.get("page")))
        ]
        key_numbers: list[InsightKeyNumber] = []
        if full_text_refs:
            key_numbers.append(InsightKeyNumber(value=f"{len(full_text_refs)}/{len(rows)}", label="PDFs with readable full text", source="Uploaded PDF text", evidence=full_text_refs[:15]))
        if dataset_refs:
            key_numbers.append(InsightKeyNumber(value=str(named_datasets), label="Named datasets found", source="Dataset passages in uploaded PDFs", evidence=dataset_refs[:15]))
        if code_refs:
            key_numbers.append(InsightKeyNumber(value=f"{len(code_refs)}/{len(rows)}", label="Papers with a code signal", source="Code availability passages", evidence=code_refs[:15]))
        return InsightsModel(
            takeaway=takeaway,
            takeaway_evidence=(dataset_refs or full_text_refs)[:15],
            key_numbers=key_numbers[:3],
            # Deliberately omitted until the extractor can establish the same split and protocol,
            # not merely the same dataset and metric label.
            head_to_head=None,
            generated_from_full_text=all(row.full_text_available for row in rows),
        )

    def _auto_suggest_columns(self, papers: list[PaperRecord], focus: str) -> list[str]:
        text = " ".join(f"{paper.title} {paper.abstract or ''} {paper.full_text or ''}" for paper in papers).lower()
        columns = ["method", "dataset", "result", "sample size", "limitation"]
        if any(token in text for token in ("p < 0.05", "confidence interval", "auc", "f1")):
            columns.append("statistical significance")
        if "github" in text or "code" in text:
            columns.append("reproducibility")
        if "open access" in text or focus.lower() in {"access", "reproducibility"}:
            columns.append("access")
        return columns[:8]

    def _similarity_to_group(self, paper: PaperRecord, papers: list[PaperRecord], token_sets: dict[str, set[str]]) -> float:
        current = token_sets.get(paper.paper_id, set())
        if not current:
            return 0.0
        scores = []
        for other in papers:
            if other.paper_id == paper.paper_id:
                continue
            comparison = token_sets.get(other.paper_id, set())
            union = current | comparison
            if not union:
                continue
            scores.append(len(current & comparison) / len(union))
        return sum(scores) / len(scores) if scores else 0.0

    def _extract_column_value(self, column: str, paper: PaperRecord) -> str:
        column_key = column.lower().strip()
        text = paper.full_text or paper.abstract or ""
        if self._is_book(paper) and any(term in column_key for term in ("method", "dataset", "model", "metric", "result", "limitation", "sample", "reproducibility")):
            return "Not applicable: book"
        if self._is_conceptual_article(paper):
            if "method" in column_key:
                return "Conceptual synthesis"
            if "result" in column_key or "performance" in column_key:
                return "Conceptual overview; no original experiment reported"
            if "study design" in column_key or "study type" in column_key:
                return "Conceptual article"
            if any(term in column_key for term in ("dataset", "model", "metric", "sample", "significance", "reproducibility", "code", "limitation", "weakness")):
                return "Not applicable: conceptual article"
        if "problem" in column_key or "research question" in column_key:
            return self._extract_sentence(text, ("aim", "address", "problem", "challenge", "we study", "we investigate"))
        if "model" in column_key:
            sections = self._split_sections(text)
            model_text = "\n".join(body for role in ("abstract", "method", "experimental_setup", "results", "discussion", "conclusion") for body in sections.get(role, [])) or text
            if self._classify_document(paper) == "survey":
                model_text = f"{paper.title} {sections.get('abstract', [''])[0]}"
            return self._extract_model_signal(paper.title, model_text)
        if "metric" in column_key:
            if self._classify_document(paper) == "survey":
                return "No single evaluation metric; prior studies are summarized"
            metric_text = self._text_with_preferred_sections(text, ("results", "experimental_setup", "datasets", "ablation", "discussion", "conclusion"))
            metric = self._extract_metric_signal(metric_text)
            return metric if metric != "Not found" else "No named evaluation metric identified in extracted full text"
        if "training dataset size" in column_key:
            match = re.search(r"\b(?:training set|training dataset|training data)\s+(?:of|with|containing)\s+(\d[\d,]*)\s+(?:examples|samples|records|instances)\b", text, re.IGNORECASE)
            return match.group(1) if match else "Not found"
        if ("dataset size" in column_key and "training" not in column_key) or "sample" in column_key:
            if self._classify_document(paper) == "survey":
                return "No empirical sample; narrative review"
            return str(paper.sample_size) if paper.sample_size is not None else self._extract_sample_size(text)
        if "dataset" in column_key:
            dataset_text = self._text_with_preferred_sections(text, ("datasets", "experimental_setup", "results", "introduction"))
            values = self._trusted_facets(paper.datasets) or self._extract_datasets(dataset_text)
            if values:
                return ", ".join(values[:4])
            detected = self._extract_dataset(text)
            if detected != "Not found":
                return detected
            if self._classify_document(paper) in {"survey", "conceptual_article"}:
                return "Review of prior studies; no single benchmark evaluated"
            return "No named dataset identified in extracted full text"
        if "method" in column_key:
            sections = self._split_sections(text)
            method_text = "\n".join(body for role in ("abstract", "method", "experimental_setup", "results", "conclusion") for body in sections.get(role, [])) or text
            if self._classify_document(paper) == "survey":
                method_text = f"{paper.title} {sections.get('abstract', [''])[0]}"
            values = self._trusted_facets(paper.methodologies) or self._extract_methods("", method_text)
            if values:
                return ", ".join(values[:4])
            if self._classify_document(paper) in {"survey", "conceptual_article"}:
                return "Narrative review and synthesis"
            return "Method details not identified in extracted full text"
        if "sample" in column_key:
            return str(paper.sample_size) if paper.sample_size is not None else self._extract_sample_size(text)
        if "study type" in column_key or "study design" in column_key:
            return paper.study_type or self._extract_study_design(text)
        if "venue" in column_key or "journal" in column_key:
            return paper.venue or "Not found"
        if "year" in column_key or "publication date" in column_key:
            return str(paper.year) if paper.year else "Not found"
        if "citation" in column_key:
            return str(paper.citation_count)
        if "open access" in column_key or "access" in column_key:
            if paper.full_text:
                return "Full text available from linked source"
            return "Open access copy listed" if paper.is_open_access else "Access not confirmed"
        if "code" in column_key or "reproducibility" in column_key:
            if paper.code_repositories:
                return ", ".join(paper.code_repositories[:3])
            repositories = re.findall(
                r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|huggingface\.co|zenodo\.org|osf\.io)/[^\s<>()\]\[\"']+",
                text,
                re.IGNORECASE,
            )
            if repositories:
                return ", ".join(dict.fromkeys(url.rstrip(".,;:" ) for url in repositories))[:500]
            return "Not found"
        if "author" in column_key:
            authors = [author.get("name", "").strip() for author in paper.authors if author.get("name", "").strip()]
            return ", ".join(authors[:5]) if authors else "Not found"
        if "doi" in column_key:
            return paper.doi or "Not found"
        if "result" in column_key or "performance" in column_key:
            result_text = self._text_with_preferred_sections(text, ("results", "ablation", "discussion", "conclusion", "experimental_setup"))
            result = self._extract_result_signal(result_text)
            if result != "Not found":
                return result
            if self._classify_document(paper) in {"survey", "conceptual_article"}:
                return "Synthesizes prior findings; no single experiment reported"
            return "No clear outcome sentence identified in extracted full text"
        if "limitation" in column_key or "weakness" in column_key:
            limitation_text = self._text_with_preferred_sections(text, ("limitations", "discussion", "conclusion", "threats", "future_work"))
            limitation = self._extract_limitation_signal(limitation_text)
            return limitation if limitation != "Not found" else "No explicit limitation statement identified in extracted full text"
        if "significance" in column_key:
            return self._extract_sentence(text, ("p < 0.05", "confidence interval", "statistically significant"))
        if "reproducibility" in column_key:
            return "Code/data signal present" if "github" in (paper.abstract or "").lower() or paper.code_repositories else "Not found"
        return "Not found"

    def _extract_study_design(self, text: str) -> str:
        patterns = (
            r"\b(randomized controlled trial|systematic review|meta-analysis|cohort study|case-control study|cross-sectional study|longitudinal study|survey|benchmark study|ablation study)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return "Not found"

    def _extract_sentence(self, text: str, cues: tuple[str, ...]) -> str:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if any(cue in sentence.lower() for cue in cues):
                return sentence.strip()
        return "Not found"

    def _evidence_for_column(self, column: str, value: str, paper: PaperRecord) -> tuple[str, str, str]:
        source_text = paper.full_text or paper.abstract or ""
        def source_for(quote: str, fallback: str) -> str:
            if paper.source == "uploaded_pdf" and quote:
                position = source_text.casefold().find(quote.casefold())
                if position >= 0:
                    pages = re.findall(r"\[PDF page (\d+)\]", source_text[:position], re.IGNORECASE)
                    if pages:
                        return f"Uploaded PDF · page {pages[-1]}"
                return "Uploaded PDF text"
            return fallback

        if value == "Not found":
            return "", "", "not_found"
        if value == "Not applicable: book":
            return paper.publication_type or paper.venue or "Book publication metadata", "metadata", "medium"
        if value == "Not applicable: conceptual article":
            return "No original empirical study was identified in the retrieved full text.", "full-text structure", "medium"
        if value in {"Conceptual synthesis", "Conceptual article"} or value.startswith("Conceptual overview;"):
            source_text = paper.full_text or paper.abstract or ""
            quote = self._extract_sentence(source_text, ("we summarize the fundamentals", "conceptual distinction", "fundamental understanding", "we synthesize"))
            return quote, source_for(quote, "full paper text" if paper.full_text else "abstract"), "medium"
        if value in (paper.title or ""):
            return paper.title, "title", "medium"
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", source_text) if sentence.strip()]
        quote = next((sentence for sentence in sentences if value.casefold() in sentence.casefold()), "")
        if quote:
            return quote, source_for(quote, "full paper text" if paper.full_text else "abstract"), "medium"
        if " | " in value:
            normalized_sentences = [" ".join(sentence.split()) for sentence in sentences]
            quotes = []
            for claim in value.split(" | ")[:3]:
                normalized_claim = " ".join(claim.split()).casefold()
                match = next((sentence for sentence in normalized_sentences if normalized_claim and normalized_claim in sentence.casefold()), None)
                if match and match not in quotes:
                    quotes.append(match)
            if quotes:
                return " ... ".join(quotes)[:900], source_for(quotes[0], "full paper text" if paper.full_text else "abstract"), "medium"
        # Multi-method/model values need more than one source sentence. Keep the
        # extracted value only when at least one of its specific terms is evidenced.
        parts = [part.strip() for part in value.split(",") if part.strip()]
        evidence_quotes = []
        for part in parts[:4]:
            terms = [term for term in re.findall(r"[A-Za-z0-9-]+", part.casefold()) if len(term) > 2 and term not in {"model", "method", "network", "algorithm", "based", "using"}]
            match = next((sentence for sentence in sentences if terms and any(re.search(rf"\b{re.escape(term)}\b", sentence, re.IGNORECASE) for term in terms)), None)
            if match and match not in evidence_quotes:
                evidence_quotes.append(match)
        if evidence_quotes:
            quote = " … ".join(evidence_quotes[:3])
            return quote[:900], source_for(evidence_quotes[0], "full paper text" if paper.full_text else "abstract"), "medium"
        key = column.lower()
        if "venue" in key and paper.venue:
            return paper.venue, "metadata", "medium"
        if "year" in key and paper.year:
            return str(paper.year), "metadata", "medium"
        if "citation" in key:
            return str(paper.citation_count), "metadata", "medium"
        if "doi" in key and paper.doi:
            return paper.doi, "metadata", "medium"
        if "author" in key and paper.authors:
            names = [author.get("name", "").strip() for author in paper.authors if author.get("name", "").strip()]
            if names:
                return ", ".join(names[:5]), "metadata", "medium"
        if "sample" in key and paper.sample_size is not None:
            return str(paper.sample_size), "metadata", "medium"
        if "study type" in key or "study design" in key:
            if paper.study_type:
                return paper.study_type, "metadata", "medium"
        if "dataset" in key and paper.datasets:
            return ", ".join(paper.datasets[:4]), "metadata", "medium"
        if "method" in key and paper.methodologies:
            return ", ".join(paper.methodologies[:4]), "metadata", "medium"
        if "access" in key:
            if paper.full_text:
                return f"Full text extracted from {paper.full_text_source or 'linked source'}", "source retrieval", "high"
            return ("Open access location listed" if paper.is_open_access else "Access not confirmed"), "metadata", "medium"
        if "reproducibility" in key or "code" in key:
            if paper.code_repositories:
                return ", ".join(paper.code_repositories[:3]), "metadata", "medium"
            quote = next((sentence for sentence in sentences if "github" in sentence.lower() or "code" in sentence.lower()), "")
            if quote:
                return quote, "abstract", "medium"
        return "", "", "low"

    def _resolve_custom_columns(self, columns: list[str]) -> list[str]:
        resolved: list[str] = []
        seen: set[str] = set()
        for column in columns:
            normalized = re.sub(r"\s+", " ", column.strip())
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            resolved.append(normalized)
        return resolved

    def _extract_dataset(self, text: str) -> str:
        match = re.search(r"\b([A-Z][A-Za-z0-9-]{2,}\s?(dataset|corpus|benchmark))\b", text)
        return match.group(1) if match else "Not found"

    def _extract_method(self, title: str, text: str) -> str:
        combined = f"{title}. {text}"
        patterns = ["transformer", "bert", "cnn", "bm25", "rag", "graph neural network", "svm", "random forest", "reinforcement learning", "support vector machine", "logistic regression", "decision tree", "xgboost", "contrastive learning", "retrieval augmented generation"]
        for pattern in patterns:
            if pattern in combined.lower():
                return pattern.upper() if len(pattern) <= 4 else pattern.title()
        return "Not found"

    def _extract_methods(self, title: str, text: str) -> list[str]:
        combined = f"{title}. {text}".replace("_", " ")
        patterns = (
            (r"\b(?:advanced|a)[-\s]?knn\b", "Advanced KNN (A-KNN)"),
            (r"\bmk[-\s]?nn\b", "Modified KNN (MkNN)"),
            (r"\b(?:adaptive|advanced|weighted|improved|enhanced)?\s*k[-\s]?nearest\s+neighbou?r(?:\s+algorithm)?\b", "K-nearest neighbors"),
            (r"\bk[-\s]?nn\b", "K-nearest neighbors"),
            (r"\bconvolutional neural networks?\b", "Convolutional neural network"),
            (r"\bcondensed nearest neighbou?r\b", "Condensed nearest neighbor"),
            (r"\btransformers?\b", "Transformer"),
            (r"\bbert\b", "BERT"),
            (r"\bbm25\b", "BM25"),
            (r"\brag\b|\bretrieval[- ]augmented generation\b", "Retrieval-augmented generation"),
            (r"\bgraph neural networks?\b", "Graph neural network"),
            (r"\bsvm\b|\bsupport vector machines?\b", "Support vector machine"),
            (r"\brandom forests?\b", "Random forest"),
            (r"\breinforcement learning\b", "Reinforcement learning"),
            (r"\blogistic regression\b", "Logistic regression"),
            (r"\bdecision trees?\b", "Decision tree"),
            (r"\bxgboost\b", "XGBoost"),
            (r"\bcontrastive learning\b", "Contrastive learning"),
        )
        methods = list(dict.fromkeys(label for pattern, label in patterns if re.search(pattern, combined, re.IGNORECASE)))
        return methods[:6]

    def _extract_model_signal(self, title: str, text: str) -> str:
        combined = f"{title}. {text}".replace("_", " ")
        patterns = (
            (r"\b(?:advanced|a)[-\s]?knn\b", "Advanced KNN (A-KNN)"),
            (r"\bmk[-\s]?nn\b", "Modified KNN (MkNN)"),
            (r"\b(?:adaptive|advanced|weighted|improved|enhanced)?\s*k[-\s]?nearest\s+neighbou?r(?:\s+algorithm)?\b|\bk[-\s]?nn\b", "K-nearest neighbor model"),
            (r"\bconvolutional neural networks?\b", "Convolutional neural network (CNN)"),
            (r"\bcondensed nearest neighbou?r\b", "Condensed nearest neighbor (CNN)"),
            (r"\btransformers?\b", "Transformer model"),
            (r"\bbert\b", "BERT"),
            (r"\brandom forest\b", "Random forest"),
            (r"\bsupport vector machine\b|\bsvm\b", "Support vector machine"),
            (r"\blogistic regression\b", "Logistic regression"),
            (r"\bdecision tree\b", "Decision tree"),
            (r"\bneural network\b", "Neural network"),
        )
        found = [label for pattern, label in patterns if re.search(pattern, combined, re.IGNORECASE)]
        return ", ".join(found[:4]) if found else "Not found"

    def _extract_sample_size(self, text: str) -> str:
        statements = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            clean = " ".join(sentence.split())
            if not re.search(r"\b(?:instances|samples|participants|patients|subjects|records)\b", clean, re.IGNORECASE):
                continue
            train_count = re.search(r"training set.{0,45}?\b(\d[\d,]*)\b", clean, re.IGNORECASE)
            test_count = re.search(r"\b(\d[\d,]*)\s+(?:are\s+)?(?:in\s+)?(?:the\s+)?(?:original\s+)?test(?:ing)? set\b|\btest(?:ing)? set.{0,20}?\b(\d[\d,]*)\b", clean, re.IGNORECASE)
            total = re.search(r"\b(?:total (?:number of )?(?:instances|samples|records)|contains? a total of|comprises?)\b.{0,35}?(\d[\d,]*)", clean, re.IGNORECASE)
            if train_count and test_count:
                test_size = test_count.group(1) or test_count.group(2)
                item = f"Train {train_count.group(1)} / test {test_size}"
            elif total:
                item = f"{total.group(1)} instances"
            else:
                match = re.search(r"\b(n\s*=\s*\d+|\d+\s+(?:participants|samples|patients|subjects|instances|records))\b", clean, re.IGNORECASE)
                item = match.group(1) if match else ""
            if item and item not in statements:
                statements.append(item)
        return "; ".join(statements[:6]) if statements else "Not found"

    def _extract_result_signal(self, text: str) -> str:
        candidates = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            clean = " ".join(sentence.split())
            lowered = clean.lower()
            if not clean or len(clean) > 700:
                continue
            if re.search(r"\b(aims? to|we propose|we introduce|objective is|we present)\b", lowered):
                continue
            clean_without_citations = re.sub(r"\[\s*\d+(?:\s*[,;-]\s*\d+)*\s*\]", "", clean)
            has_number = bool(re.search(r"\b\d+(?:\.\d+)?\s*%?\b", clean_without_citations))
            has_metric = bool(re.search(r"\b(accuracy|auc|f1(?:-score)?|precision|recall|bleu|rouge|rmse|mae|mAP|error rate|classification rate)\b", lowered))
            has_outcome = bool(re.search(r"\b(achiev(?:e|es|ed)|obtain(?:s|ed)?|reach(?:es|ed)?|outperform(?:s|ed)?|improv(?:e|es|ed)|increas(?:e|es|ed)|decreas(?:e|es|ed)|yield(?:s|ed)?|report(?:s|ed)?|correctly classified|drops?|dips?|misclassif(?:y|ies|ied|ication))\b", lowered))
            has_comparison = bool(re.search(r"\b(baseline|compared (?:with|to)|higher|lower|reduced|improved|outperform(?:s|ed)?|error rate|accuracy|precision|recall|f1)\b", lowered))
            # General background prose such as "learning improves itself" is not a
            # research result. Require a measured value or an explicit comparison.
            if (has_number and (has_metric or has_outcome)) or (has_outcome and has_comparison):
                score = int(has_metric) * 4 + int(has_number) * 3 + int(has_outcome) * 2
                concise = " ".join(clean.split()[:24]).rstrip(" ,;:")
                candidates.append((score, concise))
        if candidates:
            selected = []
            for _, sentence in sorted(candidates, key=lambda item: item[0], reverse=True):
                if any(sentence.casefold() in existing.casefold() or existing.casefold() in sentence.casefold() for existing in selected):
                    continue
                selected.append(sentence)
                if len(selected) == 3:
                    break
            return " | ".join(selected)
        return "Not found"

    def _extract_metric_signal(self, text: str) -> str:
        metric = re.compile(r"\b(AUC|F1(?:[- ]score)?|accuracy|precision|recall|sensitivity|specificity|error rate|classification rate|classification accuracy|BLEU|ROUGE|RMSE|MAE|mAP|mean squared error|mean absolute error)\b", re.IGNORECASE)
        candidates = []
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            clean = " ".join(sentence.split())
            if not clean or len(clean) > 900:
                continue
            match = metric.search(clean)
            if match:
                # Prefer an actual reported score over a sentence that only defines
                # the metric in background or methods text.
                clean_without_citations = re.sub(r"\[\s*\d+(?:\s*[,;-]\s*\d+)*\s*\]", "", clean)
                has_number = bool(re.search(r"\d+(?:\.\d+)?\s*%?", clean_without_citations))
                has_reported_score = bool(re.search(r"\b(?:accuracy|auc|f1(?:[- ]score)?|precision|recall|sensitivity|specificity|error rate|classification rate|bleu|rouge|rmse|mae|map)\b.{0,18}?\b\d+(?:\.\d+)?\s*%?|\b\d+(?:\.\d+)?\s*%?\s*(?:accuracy|auc|f1(?:[- ]score)?|precision|recall|sensitivity|specificity|error rate|classification rate|bleu|rouge|rmse|mae|map)\b", clean_without_citations, re.IGNORECASE))
                result_cue = bool(re.search(r"\b(results?|achieved|obtained|reported|reached|accuracy of|error rate of)\b", clean, re.IGNORECASE))
                if not has_reported_score or (re.search(r"\b(define[sd]?|definition|basis of|calculated as|is computed)\b", clean, re.IGNORECASE) and not result_cue):
                    continue
                score = int(has_number) * 3 + int(result_cue)
                candidates.append((score, clean))
        if candidates:
            return max(candidates, key=lambda item: item[0])[1]
        return "Not found"

    def _extract_limitation_signal(self, text: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        candidates = []
        for sentence in sentences:
            lowered = sentence.lower()
            future_only = re.search(r"\b(future work|future research|we plan to|will investigate)\b", lowered) and not re.search(r"\b(limited|limitation|cannot|fails?|underperform|small sample|lack of|not evaluated|not assess|constrained)\b", lowered)
            if re.search(r"\b(?:student|pass(?:ed)?|fail(?:ed)?|fruit|mango|example|toy)\b", lowered):
                continue
            cues = ("limitation", "underperforms", "fails to", "failure", "not evaluated", "not assess", "remains challenging", "challenges remain", "constraint", "cannot predict", "cannot classify", "cannot be classified", "limited prediction ability", "limited prediction capacity", "limited capacity", "limited ability", "limited by", "lack of")
            if not future_only and any(token in lowered for token in cues):
                score = int("limitation" in lowered) * 4 + int("limited prediction" in lowered) * 3 + int("cannot predict" in lowered) * 2
                candidates.append((score, sentence))
        if candidates:
            sentence = max(candidates, key=lambda item: item[0])[1]
            return " ".join(sentence.split()[:26]).rstrip(" ,;:").strip()
        return "Not found"

    def _is_book(self, paper: PaperRecord) -> bool:
        return self._classify_document(paper) == "book"

    def _is_conceptual_article(self, paper: PaperRecord) -> bool:
        text = f"{paper.abstract or ''}\n{paper.full_text or ''}"
        conceptual_cues = (
            "we summarize the fundamentals", "conceptual distinction", "fundamental understanding",
            "conceptual overview", "conceptual framework",
        )
        if not any(cue in text.casefold() for cue in conceptual_cues):
            return False
        sections = self._split_sections(paper.full_text or "")
        empirical_sections = any(sections.get(role) for role in ("method", "experimental_setup", "results", "datasets"))
        reports_sample = paper.sample_size is not None or bool(re.search(r"\b(?:n\s*=\s*\d+|\d+\s+(?:participants|patients|subjects))\b", text, re.IGNORECASE))
        return not empirical_sections and not reports_sample

    def _classify_document(self, paper: PaperRecord) -> str:
        publication_type = (paper.publication_type or "").casefold().replace("_", "-")
        venue = (paper.venue or "").casefold()
        title = re.sub(r"[_-]+", " ", (paper.title or "").casefold())
        metadata = f"{publication_type} {venue} {title}"
        if "chapter" in publication_type or "book chapter" in metadata:
            return "book_chapter"
        if any(term in metadata for term in ("ebook", "e-book", "edited volume", "monograph", "book")):
            return "book"
        if any(term in publication_type for term in ("review", "survey")) or re.search(r"\b(?:a\s+)?(?:systematic\s+)?review\b|\bmeta-analysis\b|\bsurvey paper\b", title):
            return "survey"
        if "preprint" in publication_type:
            return "preprint"
        if "thesis" in publication_type or "dissertation" in publication_type:
            return "thesis"
        if self._is_conceptual_article(paper):
            return "conceptual_article"
        return "research_article"

    def _text_with_preferred_sections(self, text: str, preferred_roles: tuple[str, ...]) -> str:
        sections = self._split_sections(text)
        if not sections:
            return text
        preferred = [body for role in preferred_roles for body in sections.get(role, [])]
        remainder = [
            body for role, bodies in sections.items()
            if role not in {*preferred_roles, "abstract", "references"}
            for body in bodies
        ]
        abstract = sections.get("abstract", [])
        return "\n\n".join([*preferred, *remainder, *abstract]) or text

    def _split_sections(self, text: str) -> dict[str, list[str]]:
        role_cues = (
            ("abstract", r"\babstract\b"),
            ("introduction", r"\b(introduction|background)\b"),
            ("related_work", r"\b(related work|literature review)\b"),
            ("method", r"(?:methods?|methodology|approach|proposed method|model architecture|algorithm description|proposed algorithm)"),
            ("experimental_setup", r"(?:experiments?.*|experimental setup.*|evaluation.*|implementation details.*)"),
            ("datasets", r"(?:data sets?|datasets?|benchmarks?.*)"),
            ("results", r"(?:(?:experimental )?results?.*|findings.*)"),
            ("ablation", r"\b(ablation|component analysis)\b"),
            ("discussion", r"\bdiscussion\b"),
            ("limitations", r"\b(limitations?|threats to validity|study weaknesses)\b"),
            ("conclusion", r"(?:conclusions?.*|concluding remarks.*)"),
            ("future_work", r"\b(future work|future directions)\b"),
            ("code_data_availability", r"\b(code availability|data availability|software availability|reproducibility)\b"),
            ("appendix", r"\b(appendix|supplementary material)\b"),
            ("references", r"\b(references|bibliography)\b"),
        )
        heading = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?P<title>[A-Za-z][A-Za-z &/,-]{1,90})\s*$")
        lines = text.splitlines()
        sections: dict[str, list[str]] = {}
        current_role = "body"
        chunks: dict[str, list[str]] = {current_role: []}
        for line in lines:
            match = heading.match(line)
            next_role = None
            table_heading = re.match(r"^\s*Table\s+\d+\s*:\s*(?P<title>.+)$", line, re.IGNORECASE)
            if table_heading and re.search(r"\b(results?|accuracy|performance)\b", table_heading.group("title"), re.IGNORECASE):
                next_role = "results"
            if match:
                title = match.group("title").casefold().strip()
                for role, pattern in role_cues:
                    if re.fullmatch(pattern, title, re.IGNORECASE):
                        next_role = role
                        break
            if next_role:
                current_role = next_role
                chunks.setdefault(current_role, [])
            else:
                chunks.setdefault(current_role, []).append(line)
        for role, body_lines in chunks.items():
            body = "\n".join(body_lines).strip()
            if body:
                sections.setdefault(role, []).append(body)
        return sections

    def _trusted_facets(self, values: list[str]) -> list[str]:
        banned = {"general research", "unspecified dataset", "unknown", "n/a", "not reported"}
        return [value for value in values if value.strip().casefold() not in banned]

    def _extract_datasets(self, text: str) -> list[str]:
        # Require a dataset/benchmark cue. Generic title-case phrases after "on"
        # were producing people, headings, and method names as false datasets.
        text = re.sub(r"\s+", " ", text)
        patterns = (
            r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,4})\s+(?:dataset|benchmark|corpus)\b",
            r"\b(?:dataset|data set|benchmark|corpus)\s+(?:named|called|used|is|was|includes|included|contains|:)?\s*(?:the\s+)?([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,3})\b",
            r"\b(?:experiment\s+on|experiments\s+on|results?\s+of|evaluation\s+on|tested\s+on)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,4}?)\s+data\s+sets?\b",
        )
        ignored = {"the", "this", "our", "their", "proposed", "training", "testing", "validation", "benchmark dataset", "data set", "dataset", "data"}
        normalized = []
        named_lists = re.findall(r"\bdata\s+sets?\s+namely\s+(.+?)(?=[.;\n]|$)", text, re.IGNORECASE)
        for named_list in named_lists:
            pieces = re.split(r",\s*(?:and\s+)?|\s+and\s+", named_list, flags=re.IGNORECASE)
            for piece in pieces:
                candidate = re.sub(r"\s+", " ", re.sub(r"\s+data\s+set$", "", piece.strip(" .,:;()[]"), flags=re.IGNORECASE)).strip()
                candidate = re.sub(r"^(?:the\s+)?", "", candidate, flags=re.IGNORECASE)
                if candidate and candidate.casefold() not in {"data", "dataset", "the data"} and candidate not in normalized:
                    normalized.append(candidate)
        for pattern in patterns:
            for match in re.findall(pattern, text):
                candidate = re.sub(r"\s+", " ", match.strip(" .,:;()[]"))
                candidate = re.sub(r"\s+(?:data\s+set|dataset)$", "", candidate, flags=re.IGNORECASE).strip()
                words = candidate.split()
                while words and words[0].casefold() in {"the", "a", "an", "in", "on", "of", "and", "namely", "using", "this", "particular", "been", "performed", "training", "testing", "existing", "classification", "algorithms", "algorithm", "divide", "details", "instances"}:
                    words.pop(0)
                candidate = " ".join(words)
                if candidate.casefold() not in ignored and len(candidate) > 1 and candidate not in normalized:
                    normalized.append(candidate)
        return normalized[:6]

    def _extract_result_metrics(self, text: str) -> dict[str, float]:
        metrics: dict[str, float] = {}
        result_text = self._text_with_preferred_sections(text, ("results", "ablation", "discussion"))
        labels = {
            "AUC": r"auc|area under (?:the )?(?:roc )?curve",
            "F1": r"f1(?:[- ]score)?",
            "ACCURACY": r"accuracy",
            "PRECISION": r"precision",
            "RECALL": r"recall",
            "BLEU": r"bleu",
            "ROUGE": r"rouge(?:-\w+)?",
            "RMSE": r"rmse|root mean squared error",
            "MAE": r"(?<![a-z])mae(?![a-z])|mean absolute error",
        }
        for canonical, pattern in labels.items():
            match = re.search(rf"\b(?:{pattern})\b\s*(?:was|of|=|:)?\s*(\d+(?:\.\d+)?)\s*(%)?", result_text, re.IGNORECASE)
            if not match:
                match = re.search(rf"(\d+(?:\.\d+)?)\s*(%)?\s*(?:{pattern})\b", result_text, re.IGNORECASE)
            if match:
                raw_value = float(match.group(1))
                is_percent = bool(match.group(2))
                metrics[canonical] = raw_value / 100 if raw_value > 1 and (is_percent or canonical not in {"RMSE", "MAE"}) else raw_value
        return metrics

    def _enrich_similarity_channels(self, rows: list[ComparisonRow]) -> list[ComparisonRow]:
        enriched = []
        for row in rows:
            method_scores = []
            dataset_scores = []
            result_scores = []
            for other in rows:
                if row.paper_id == other.paper_id:
                    continue
                method_scores.append(self._list_similarity(row.methods, other.methods))
                dataset_scores.append(self._list_similarity(row.datasets, other.datasets))
                result_scores.append(self._metric_similarity(row.result_metrics, other.result_metrics))
            enriched.append(
                row.model_copy(
                    update={
                        "method_similarity_score": round(sum(method_scores) / len(method_scores), 3) if method_scores else 0.0,
                        "dataset_similarity_score": round(sum(dataset_scores) / len(dataset_scores), 3) if dataset_scores else 0.0,
                        "result_similarity_score": round(sum(result_scores) / len(result_scores), 3) if result_scores else 0.0,
                    }
                )
            )
        return enriched

    def _apply_pinning(self, rows: list[ComparisonRow], pinned_paper_ids: list[str]) -> list[ComparisonRow]:
        pin_index = {paper_id: index for index, paper_id in enumerate(pinned_paper_ids)}
        return sorted(rows, key=lambda row: (0 if row.paper_id in pin_index else 1, pin_index.get(row.paper_id, 999), -row.citation_count))

    def _list_similarity(self, left: list[str], right: list[str]) -> float:
        left_set = {item.lower() for item in left}
        right_set = {item.lower() for item in right}
        union = left_set | right_set
        return len(left_set & right_set) / len(union) if union else 0.0

    def _metric_similarity(self, left: dict[str, float], right: dict[str, float]) -> float:
        shared = set(left) & set(right)
        if not shared:
            return 0.0
        distances = [1 - min(abs(left[key] - right[key]), 1) for key in shared]
        return sum(distances) / len(distances)

    def _find_contradictions(self, papers: list[PaperRecord], aggregate_terms: Counter[str]) -> list[str]:
        # A positive claim in one paper and a limitation in another is not, by itself,
        # a contradiction. Only emit this section when the evidence supports a true
        # same-claim conflict; the current extracted schema does not establish that.
        return []

    def _significance_note(self, text: str) -> str:
        lowered = text.lower()
        if "p < 0.05" in lowered or "confidence interval" in lowered:
            return "Statistical significance reported"
        return "No explicit significance signal"

    def _build_narrative(self, papers: list[PaperRecord], rows: list[ComparisonRow], focus: str) -> str:
        paper_count = len(rows)
        full_text_count = sum(bool(paper.full_text and paper.full_text.strip()) for paper in papers)
        abstract_count = sum(bool(paper.abstract and paper.abstract.strip()) for paper in papers)
        metadata_fields = ("method", "dataset", "model", "metric", "result", "limitation")
        coverage = {
            field: sum(bool(row.result_metrics) for row in rows)
            if field == "metric"
            else sum(
                bool((value := row.extracted_columns.get(field, "")).strip())
                and value != "Not found"
                and not value.startswith(("Not applicable:", "No named ", "No single ", "No empirical ", "No explicit ", "No clear ", "Review of prior studies", "Synthesizes prior findings", "Method details not identified"))
                for row in rows
            )
            for field in metadata_fields
        }
        top = max(rows, key=lambda row: (row.similarity_score, row.citation_count))
        recent = [row for row in rows if row.year and row.year >= max((item.year or 0 for item in rows), default=0) - 4]
        shared_methods = self._shared_items([row.methods for row in rows])
        shared_datasets = self._shared_items([row.datasets for row in rows])
        metric_values: dict[str, list[tuple[str, float]]] = {}
        for row in rows:
            for metric, value in row.result_metrics.items():
                metric_values.setdefault(metric, []).append((row.title, value))
        comparable_metrics = []
        incomparable_metrics = []
        for metric, items in metric_values.items():
            item_rows = [row for row in rows if metric in row.result_metrics]
            comparable_pairs = []
            for index, left in enumerate(item_rows):
                left_quote = left.evidence.get("result", "")
                left_quote_metrics = self._extract_result_metrics(left_quote)
                for right in item_rows[index + 1:]:
                    right_quote = right.evidence.get("result", "")
                    shared = [dataset for dataset in left.datasets if dataset.casefold() in {item.casefold() for item in right.datasets}]
                    shared_in_both_quotes = next((dataset for dataset in shared if dataset.casefold() in left_quote.casefold() and dataset.casefold() in right_quote.casefold()), None)
                    right_quote_metrics = self._extract_result_metrics(right_quote)
                    if shared_in_both_quotes and metric in left_quote_metrics and metric in right_quote_metrics:
                        comparable_pairs.append((left, right, shared_in_both_quotes, left_quote_metrics[metric], right_quote_metrics[metric]))
            if comparable_pairs:
                lower_is_better = metric in {"RMSE", "MAE"}
                for left, right, shared_dataset, left_value, right_value in comparable_pairs[:3]:
                    winner = left if (left_value <= right_value if lower_is_better else left_value >= right_value) else right
                    comparable_metrics.append(f"{metric} on {shared_dataset}: {left.title} reported {left_value:g}; {right.title} reported {right_value:g}. The larger value is in {winner.title}{' (lower is better for this metric)' if lower_is_better else ''}; check split and protocol details before treating this as a definitive ranking.")
            elif len(items) > 1:
                incomparable_metrics.append(metric)
        coverage_summary = ", ".join(f"{name} {count}/{paper_count}" for name, count in coverage.items())
        parts = [f"Full-text coverage for {focus}: {full_text_count} of {paper_count} selected papers were analyzed from extracted PDF text; {abstract_count} include abstracts. Extracted coverage across the set is {coverage_summary}."]
        parts.append(f"{top.title} has the highest average text overlap with the rest of this set (Jaccard {top.similarity_score:.2f}); this is textual overlap, not proof of methodological equivalence.")
        if shared_methods:
            parts.append(f"Methods appearing in multiple papers: {', '.join(shared_methods[:6])}.")
        if shared_datasets:
            parts.append(f"Datasets reported by multiple papers: {', '.join(shared_datasets[:6])}.")
        if comparable_metrics:
            parts.extend(f"{insight}." for insight in comparable_metrics[:4])
        if incomparable_metrics:
            parts.append(f"Results are not directly comparable for {', '.join(incomparable_metrics)}: the papers do not share a named dataset.")
        if not comparable_metrics and not incomparable_metrics:
            parts.append("No numeric result metric is reported by multiple papers; a performance ranking would not be evidence-based.")
        if recent:
            parts.append(f"The most recent publication year represented is {max(row.year for row in recent if row.year)} ({len(recent)} papers in the latest four-year window).")
        if full_text_count < paper_count:
            parts.append("Papers without accessible PDF text use only their available abstract and metadata; missing details in those rows do not establish that the full paper omits them.")
        else:
            parts.append("All selected papers had extractable PDF text. Automated extraction can still miss details in tables, images, or complex layouts; verify source passages before citation.")
        return " ".join(parts)

    def _shared_items(self, groups: list[list[str]]) -> list[str]:
        counts = Counter(item.strip() for group in groups for item in group if item.strip())
        return [item for item, count in counts.most_common() if count > 1]

    def _to_markdown(self, rows: list[ComparisonRow]) -> str:
        lines = [
            "| Title | Year | Citations | OA | Similarity | Citation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            title = row.title.replace("|", "&#124;")
            citation = row.citation.replace("|", "&#124;")
            lines.append(
                f"| {title} | {row.year or '-'} | {row.citation_count} | {'Yes' if row.open_access else 'No'} | {row.similarity_score:.2f} | {citation} |"
            )
        return "\n".join(lines)

    def _to_csv(self, rows: list[ComparisonRow]) -> str:
        lines = ["Title,Year,Citations,OpenAccess,Similarity,Methods,Datasets,Significance,Citation"]
        for row in rows:
            lines.append(
                ",".join(f'"{value.replace(chr(34), chr(34) * 2)}"' for value in [row.title, str(row.year or ''), str(row.citation_count), str(row.open_access), str(row.similarity_score), '|'.join(row.methods), '|'.join(row.datasets), row.significance_note, row.citation])
            )
        return "\n".join(lines)

    def _citation(self, paper: PaperRecord) -> str:
        authors = ", ".join(author.get("name", "") for author in paper.authors if author.get("name"))
        parts = [authors, str(paper.year or "n.d."), paper.title, paper.venue or "", paper.doi or paper.url or ""]
        return ". ".join(part.strip().rstrip(".") for part in parts if part and part.strip()) + "."

    def _source_link(self, paper: PaperRecord) -> str | None:
        doi = paper.doi or next((item for key, item in paper.external_ids.items() if key.casefold() == "doi"), None)
        value = paper.url
        try:
            host = (urlsplit(value).hostname or "").casefold() if value else ""
        except ValueError:
            host = ""
        if not value or any(host == domain or host.endswith(f".{domain}") for domain in ("openalex.org", "semanticscholar.org", "scholar.google.com", "doi.org")):
            value = doi or value
        if not value:
            return None
        if not value.startswith(("https://", "http://")):
            value = f"https://doi.org/{value.removeprefix('doi:')}"
        try:
            parsed = urlsplit(value)
            return value if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password else None
        except ValueError:
            return None

    def _to_latex(self, rows: list[ComparisonRow]) -> str:
        lines = [
            "\\begin{tabular}{lrrrr}",
            "Title & Year & Citations & OA & Similarity \\\\",
            "\\hline",
        ]
        for row in rows:
            oa = "Yes" if row.open_access else "No"
            lines.append(f"{row.title} & {row.year or '-'} & {row.citation_count} & {oa} & {row.similarity_score:.2f} \\\\")
        lines.append("\\end{tabular}")
        return "\n".join(lines)

    def _to_json(self, rows: list[ComparisonRow]) -> str:
        return json.dumps([row.model_dump() for row in rows], indent=2)

    def _group_by_method(self, rows: list[ComparisonRow]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for row in rows:
            for key in row.methods:
                groups.setdefault(key, []).append(row.title)
        return groups

    def _similarity_heatmap(self, rows: list[ComparisonRow], token_sets: dict[str, set[str]]) -> list[list[float]]:
        heatmap = []
        for row in rows:
            current = token_sets.get(row.paper_id, set())
            matrix_row = []
            for other in rows:
                comparison = token_sets.get(other.paper_id, set())
                union = current | comparison
                score = len(current & comparison) / len(union) if union else 0.0
                matrix_row.append(round(score, 3))
            heatmap.append(matrix_row)
        return heatmap

    def _methodology_dendrogram(self, groups: dict[str, list[str]]) -> dict[str, list[str]]:
        return groups

    def _channel_heatmap(self, rows: list[ComparisonRow], attribute: str) -> list[list[float]]:
        heatmap = []
        for row in rows:
            left = getattr(row, attribute)
            heatmap.append([round(self._list_similarity(left, getattr(other, attribute)), 3) for other in rows])
        return heatmap

    def _result_heatmap(self, rows: list[ComparisonRow]) -> list[list[float]]:
        return [
            [round(self._metric_similarity(row.result_metrics, other.result_metrics), 3) for other in rows]
            for row in rows
        ]

    def _dendrogram_edges(self, rows: list[ComparisonRow]) -> list[dict[str, str | float]]:
        edges = []
        for left_index, left in enumerate(rows):
            for right in rows[left_index + 1:]:
                score = max(
                    self._list_similarity(left.methods, right.methods),
                    self._list_similarity(left.datasets, right.datasets),
                    self._metric_similarity(left.result_metrics, right.result_metrics),
                )
                if score > 0:
                    edges.append({"source": left.paper_id, "target": right.paper_id, "similarity": round(score, 3)})
        return edges[:20]

    def _timeline(self, rows: list[ComparisonRow]) -> list[dict[str, str | int]]:
        return [
            {"title": row.title, "year": row.year or 0, "methods": ", ".join(row.methods)}
            for row in sorted(rows, key=lambda item: item.year or 0)
        ]

    def _best_paper_for_focus(self, rows: list[ComparisonRow], focus: str) -> str:
        focus_terms = _tokens(focus)

        def score(row: ComparisonRow) -> tuple[int, int, float, int]:
            row_text = " ".join([row.title, *row.methods, *row.datasets, *row.extracted_columns.values()])
            overlap = len(focus_terms & _tokens(row_text))
            available = sum(value != "Not found" for value in row.extracted_columns.values())
            return overlap, available, row.similarity_score, row.citation_count

        best = max(rows, key=score)
        overlap, available, _, _ = score(best)
        reason = f"matches {overlap} focus terms and has {available} extractable comparison fields" if focus_terms else f"has {available} extractable comparison fields"
        return f"Best evidence coverage for {focus}: {best.title} ({reason}). This ranks the supplied metadata and abstracts, not paper quality."

    def _dataset_overlap(self, rows: list[ComparisonRow]) -> dict[str, list[str]]:
        overlap: dict[str, list[str]] = {}
        for row in rows:
            for dataset in row.datasets:
                overlap.setdefault(dataset, []).append(row.title)
        return overlap

    def _dataset_overlap_matrix(self, rows: list[ComparisonRow]) -> list[list[int]]:
        matrix = []
        for row in rows:
            row_datasets = {dataset.lower() for dataset in row.datasets}
            matrix.append([
                len(row_datasets & {dataset.lower() for dataset in other.datasets})
                for other in rows
            ])
        return matrix

    def _citation_overlap_venn(self, rows: list[ComparisonRow]) -> dict[str, int]:
        highly_cited = sum(1 for row in rows if row.citation_count >= 100)
        recent = sum(1 for row in rows if row.year and row.year >= 2023)
        intersection = sum(1 for row in rows if row.citation_count >= 100 and row.year and row.year >= 2023)
        return {"highly_cited": highly_cited, "recent": recent, "intersection_estimate": intersection}

    def _citation_overlap_sets(self, rows: list[ComparisonRow]) -> dict[str, list[str]]:
        return {
            "highly_cited": [row.title for row in rows if row.citation_count >= 100],
            "recent": [row.title for row in rows if row.year and row.year >= 2023],
            "open_access": [row.title for row in rows if row.open_access],
        }

    def _performance_leaderboard_by_dataset(self, rows: list[ComparisonRow]) -> dict[str, list[str]]:
        leaderboard: dict[str, list[str]] = {}
        for dataset, titles in self._dataset_overlap(rows).items():
            dataset_rows = [row for row in rows if row.title in titles]
            if len(dataset_rows) < 2:
                continue
            shared_metrics = set.intersection(*(set(row.result_metrics) for row in dataset_rows))
            if not shared_metrics:
                continue
            metric = sorted(shared_metrics)[0]
            lower_is_better = metric in {"MAE", "RMSE", "LOSS", "ERROR"}
            ranked = sorted(dataset_rows, key=lambda row: row.result_metrics[metric], reverse=not lower_is_better)
            leaderboard[dataset] = [row.title for row in ranked]
        return leaderboard

    def _comparison_to_review(self, rows: list[ComparisonRow], focus: str) -> str:
        top_rows = sorted(rows, key=lambda row: (row.citation_count, row.similarity_score), reverse=True)[:3]
        sentences = [
            f"In the {focus} literature, {row.title} stands out through {', '.join(row.strengths[:2]) or 'its comparative presence'}."
            for row in top_rows
        ]
        return " ".join(sentences)
