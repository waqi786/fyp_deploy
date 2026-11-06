"""Federated research search.

Pipeline: understand query → (translate query) → fan out to scholarly sources + web → clean → filter junk →
deduplicate → apply user filters → rank → keep relevant → page → translate visible page.

Paging uses a per-search *result pool*: page 1 builds a ranked pool from every source's first page; "show more"
serves the next slice of that pool and, when it runs low, fetches the sources' next page and appends newly found
papers. Users therefore never see the same paper twice or skip papers between pages.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from math import ceil
from typing import Any, Callable
from urllib.parse import urlencode

from app.schemas.paper import (
    PaperSearchResponse,
    RankingExplanation,
    SearchCacheStatus,
    SearchPagination,
)
from app.schemas.search import SearchFilters, SourceSearchRequest
from app.services.language.config import canonical_language_code, detect_language
from app.services.plugins.registry import PluginRegistryService
from app.services.search.base import SearchProvider
from app.services.search.deduplication import deduplicate_papers
from app.services.search.discovery import (
    apply_filters,
    build_discovery_facets,
    enrich_search_results,
    infer_metadata_fields,
    interpret_search_query,
    search_relevance_score,
    semantic_vector_scores,
)
from app.services.search.query_parser import understand_research_query
from app.services.search.source_ids import DEFAULT_SCHOLARLY_SOURCES
from app.services.search.translation import (
    TranslationUnavailable,
    schedule_translation_retry,
    translate_batch,
    translate_text,
)
from app.services.search.web_search import WebSearchService
from app.services.search.workspace import SearchWorkspaceService
from app.services.storage.background_cache import BackgroundPaperCache

logger = logging.getLogger(__name__)

SourceEventCallback = Callable[[str, dict[str, object]], None]

POOL_TTL_SECONDS = 15 * 60
POOL_MAX_ENTRIES = 256
MAX_PROVIDER_PAGES = 5
MAX_EXTENSIONS_PER_REQUEST = 3
SNIPPET_TRANSLATION_CHARS = 900

# Sources whose indexes contain substantial non-English content. Only these receive the extra
# original-language query, which keeps free API quotas for the rest.
MULTILINGUAL_SOURCES = {"openalex", "crossref", "core", "doaj", "hal", "zenodo", "europe_pmc"}

JUNK_TITLE = re.compile(
    r"(?i)^\s*(?:front\s+matter|back\s+matter|table\s+of\s+contents|contents|cover(?:\s+image)?|editorial\s+board|"
    r"masthead|issue\s+information|title\s+page|author\s+index|subject\s+index|index|"
    r"(?:acknowledg(?:e)?ments?\s+to\s+)?reviewers?(?:\s+(?:list|acknowledg\w*))?|untitled|unknown|no\s+title)\s*\.?\s*$"
)
COMPONENT_TITLE = re.compile(r"(?i)^\s*(?:figure\s+\d+|fig\.\s*\d+|table\s+\d+|supplementary(?:\s+\w+)?)\s*[:.]")
IGNORED_PUBLICATION_TYPES = {"component", "figure", "table", "peer-review", "dataset-component"}
TAG = re.compile(r"<[^>]{0,200}>")
LEADING_LABEL = re.compile(r"(?i)^\s*(?:abstract|summary|background|graphical\s+abstract)\s*[:.\-–—]?\s+")
LEADING_PUNCT = re.compile(r"^[\s:.;,|\-–—]+")
WORD = re.compile(r"\S+")
NON_ALNUM = re.compile(r"[^\w]+", re.UNICODE)


# --------------------------------------------------------------------------- text cleaning


def _current_year() -> int:
    return datetime.now(timezone.utc).year


def clean_text(value: str | None) -> str:
    """Remove markup (HTML/JATS), decode entities and normalise whitespace."""
    if not value:
        return ""
    text = html.unescape(TAG.sub(" ", str(value)))
    text = text.replace("​", "").replace("﻿", "")
    return " ".join(text.split())


def _comparable(word: str) -> str:
    return NON_ALNUM.sub("", word.casefold())


def strip_leading_title(title: str, text: str) -> str:
    """Drop an "Abstract:" label and a repeated title at the start of a snippet."""
    if not text:
        return ""
    text = LEADING_LABEL.sub("", text)
    title_words = [word for word in (_comparable(part) for part in title.split()) if word]
    if len(title_words) < 2:
        return text
    matched = 0
    cut_at = 0
    for token in WORD.finditer(text):
        word = _comparable(token.group())
        if not word:
            cut_at = token.end()
            continue
        if matched < len(title_words) and word == title_words[matched]:
            matched += 1
            cut_at = token.end()
            if matched == len(title_words):
                break
        else:
            break
    if matched >= max(2, ceil(len(title_words) * 0.85)):
        text = LEADING_LABEL.sub("", LEADING_PUNCT.sub("", text[cut_at:]))
    return text


MATCH_STOPWORDS = {
    "about", "after", "against", "analysis", "and", "are", "based", "between", "does", "for", "from", "how", "into",
    "latest", "new", "of", "on", "paper", "papers", "recent", "research", "review", "study", "studies", "the", "this",
    "using", "what", "when", "which", "why", "with",
}


def matched_query_terms(query: str, paper: Any, limit: int = 4) -> list[str]:
    """Query words (or the whole short query) that appear in the paper's title or abstract, title matches first."""
    title = (paper.title or "").casefold()
    text = f"{title} {(paper.abstract or paper.micro_summary or '').casefold()}"
    query_clean = " ".join(query.casefold().split())
    words = [word for word in re.findall(r"[\w-]{3,}", query_clean) if word not in MATCH_STOPWORDS and not word.isdigit()]
    if 2 <= len(words) <= 4 and query_clean in title:
        return [query_clean]
    in_title = [word for word in words if re.search(rf"\b{re.escape(word)}\b", title)]
    in_text = [word for word in words if word not in in_title and re.search(rf"\b{re.escape(word)}\b", text)]
    return list(dict.fromkeys(in_title + in_text))[:limit]


def _paper_key(paper: Any) -> str:
    doi = (getattr(paper, "doi", None) or "").strip().casefold()
    if doi:
        return f"doi:{doi.removeprefix('https://doi.org/').removeprefix('http://dx.doi.org/')}"
    return "title:" + NON_ALNUM.sub("", (paper.title or "").casefold())


# --------------------------------------------------------------------------- internal state


@dataclass
class _SearchContext:
    original_query: str
    query: str
    normalized_query: str
    provider_query: str
    original_language_query: str | None
    limit: int
    filters: SearchFilters
    filter_kwargs: dict[str, Any]
    providers: list[tuple[str, SearchProvider]]
    author_hint: str | None
    author: str | None
    search_mode: str
    sort_by: str
    query_type: str
    image_caption: str | None


@dataclass
class _ResultPool:
    ranked: list[Any]
    seen: set[str]
    provider_page: int
    exhausted: bool
    raw_count: int
    filtered_count: int
    clusters: dict[str, Any]
    suggestions: list[str]
    trending_topics: list[str]
    discovery_facets: dict[str, Any]
    source_failures: list[str]
    author_exact_match_available: bool | None
    created_at: float = field(default_factory=time.monotonic)

    def expired(self) -> bool:
        return time.monotonic() - self.created_at > POOL_TTL_SECONDS


# --------------------------------------------------------------------------- service


class FederatedSearchService:
    def __init__(
        self,
        *,
        providers: dict[str, SearchProvider] | None = None,
        cache: BackgroundPaperCache | None = None,
        workspace: SearchWorkspaceService | None = None,
        web_search: WebSearchService | None = None,
    ) -> None:
        self.providers: dict[str, SearchProvider] = providers or PluginRegistryService().source_plugins()
        self.cache = cache or BackgroundPaperCache()
        self.workspace = workspace or SearchWorkspaceService()
        self.web_search = web_search or WebSearchService()
        self.source_timeout_seconds = 12.0
        # Per-process pool cache. With several API workers, a "show more" request that lands on another
        # worker simply rebuilds the pool (correct, slightly slower). Move to Redis when scaling out.
        self._pools: OrderedDict[str, _ResultPool] = OrderedDict()
        self._background_tasks: set[asyncio.Task] = set()

    async def search(
        self,
        query: str,
        limit: int,
        sources: list[str],
        *,
        page: int = 1,
        language: str = "en",
        query_language: str | None = None,
        paper_language: str | None = None,
        target_language: str = "en",
        translate_results: bool = False,
        min_citations: int = 0,
        open_access_only: bool = False,
        study_type: str | None = None,
        quartile: str | None = None,
        sample_size_min: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        methodology: str | None = None,
        author: str | None = None,
        venue: str | None = None,
        institution: str | None = None,
        dataset: str | None = None,
        peer_reviewed_only: bool = False,
        preprint_only: bool = False,
        include_retracted: bool = False,
        citation_context: str | None = None,
        region: str | None = None,
        chemical_formula: str | None = None,
        gene_or_protein: str | None = None,
        equipment_or_software: str | None = None,
        negative_results_only: bool = False,
        temporal_aware: bool = False,
        patent_overlap: bool = False,
        grey_literature: bool = False,
        conference_priority: bool = False,
        cited_by_quality_only: bool = False,
        private_search_vault: bool = True,
        collaborative_session: bool = False,
        search_mode: str = "hybrid",
        query_type: str = "natural_language",
        voice_transcript: str | None = None,
        image_caption: str | None = None,
        sort_by: str = "relevance",
        session_id: str | None = None,
        save_history: bool = True,
        user_id: str | None = None,
        source_event_callback: SourceEventCallback | None = None,
    ) -> PaperSearchResponse:
        # Everything that defines "the same search" (all arguments except paging/session/callback).
        pool_key = self._pool_key(
            {
                name: value
                for name, value in locals().items()
                if name not in {"self", "page", "session_id", "save_history", "source_event_callback"}
            }
        )
        limit = max(1, int(limit or 20))
        page = max(1, int(page or 1))

        # ---- understand the query -------------------------------------------------------------
        original_query = query
        understood = understand_research_query(query)
        query = understood.query
        requested_query_language = query_language or language
        if requested_query_language == "auto":
            resolved_query_language, _ = detect_language(query)
        else:
            resolved_query_language = canonical_language_code(requested_query_language)
        resolved_target_language = canonical_language_code(target_language)
        query_intelligence = interpret_search_query(
            understood.query,
            language=resolved_query_language,
            query_type=query_type,
            voice_transcript=voice_transcript,
            image_caption=image_caption,
        )
        normalized_query = query_intelligence["normalized_query"] or query
        source_query = voice_transcript if query_type == "voice" and voice_transcript else query
        source_query = image_caption if query_type == "image" and image_caption else source_query

        # Rule-based phrase mappings stay fast; use the cached translation chain when a non-English
        # query contains terms the dictionary does not know.
        residual_language, residual_confidence = detect_language(normalized_query)
        needs_query_translation = resolved_query_language != "en" and (
            not query_intelligence.get("translated_query") or (residual_language != "en" and residual_confidence >= 0.72)
        )
        if needs_query_translation:
            try:
                translated = await asyncio.to_thread(
                    translate_text, source_query, "en", source_language=resolved_query_language, user_id=user_id
                )
                if translated and translated.strip() and translated.strip() != source_query.strip():
                    query_intelligence["translated_query"] = translated.strip()
                    normalized_query = translated.strip()
            except (TranslationUnavailable, ValueError):
                logger.info("Query translation unavailable; searching with the original-language query")

        author_hint, cleaned_query = self._extract_author_intent(normalized_query)
        if author_hint and not author:
            normalized_query = cleaned_query or normalized_query
        provider_query = f"{normalized_query} {author_hint}".strip() if author_hint and not author else normalized_query
        advanced_discovery = self._advanced_discovery_terms(
            citation_context=citation_context,
            region=region,
            chemical_formula=chemical_formula,
            gene_or_protein=gene_or_protein,
            equipment_or_software=equipment_or_software,
            negative_results_only=negative_results_only,
            patent_overlap=patent_overlap,
            grey_literature=grey_literature,
            conference_priority=conference_priority,
            cited_by_quality_only=cited_by_quality_only,
        )
        if advanced_discovery["query_terms"]:
            provider_query = f"{provider_query} {' '.join(advanced_discovery['query_terms'])}".strip()
        translated_query = query_intelligence["translated_query"]
        year_from = year_from if year_from is not None else understood.year_from
        open_access_only = open_access_only or understood.open_access_only
        author = author or understood.author
        if understood.reviews_only and not study_type:
            study_type = "review"

        filters = SearchFilters(
            language=paper_language or resolved_query_language,
            min_citations=min_citations,
            open_access_only=open_access_only,
            study_type=study_type,
            quartile=quartile,
            sample_size_min=sample_size_min,
            year_from=year_from,
            year_to=year_to,
            methodology=methodology,
            author=author,
            venue=venue,
            institution=institution,
            dataset=dataset,
            peer_reviewed_only=peer_reviewed_only,
            preprint_only=preprint_only,
            include_retracted=include_retracted,
            citation_context=citation_context,
            region=region,
            chemical_formula=chemical_formula,
            gene_or_protein=gene_or_protein,
            equipment_or_software=equipment_or_software,
            negative_results_only=negative_results_only,
            temporal_aware=temporal_aware,
            patent_overlap=patent_overlap,
            grey_literature=grey_literature,
            conference_priority=conference_priority,
            cited_by_quality_only=cited_by_quality_only,
            private_search_vault=private_search_vault,
            collaborative_session=collaborative_session,
        )
        filter_kwargs: dict[str, Any] = {
            "min_citations": min_citations,
            "open_access_only": open_access_only,
            "study_type": study_type,
            "quartile": quartile,
            "sample_size_min": sample_size_min,
            "year_from": year_from,
            "year_to": year_to,
            "methodology": methodology,
            "author": author,
            "venue": venue,
            "institution": institution,
            "dataset": dataset,
            "peer_reviewed_only": peer_reviewed_only,
            "preprint_only": preprint_only,
            "include_retracted": include_retracted,
            "paper_language": paper_language,
        }

        selected_names = [name for name in sources if name in self.providers] if sources else [
            name for name in DEFAULT_SCHOLARLY_SOURCES if name in self.providers
        ]
        original_language_query = None
        if (
            resolved_query_language != "en"
            and source_query.strip()
            and source_query.strip().casefold() != provider_query.strip().casefold()
        ):
            original_language_query = source_query.strip()

        ctx = _SearchContext(
            original_query=original_query,
            query=query,
            normalized_query=normalized_query,
            provider_query=provider_query,
            original_language_query=original_language_query,
            limit=limit,
            filters=filters,
            filter_kwargs=filter_kwargs,
            providers=[(name, self.providers[name]) for name in selected_names],
            author_hint=author_hint if not author else None,
            author=author,
            search_mode=search_mode,
            sort_by=sort_by,
            query_type=query_type,
            image_caption=image_caption,
        )

        # ---- build or reuse the result pool --------------------------------------------------
        pool = self._get_pool(pool_key) if page > 1 else None
        built_now = pool is None
        if pool is None:
            pool = await self._build_pool(ctx, emit=self._safe_emitter(source_event_callback) if page == 1 else None)
            self._store_pool(pool_key, pool)
            self.workspace_update_trending(pool, user_id)
            self._cache_in_background(pool.ranked)

        needed = page * limit
        extensions = 0
        while len(pool.ranked) < needed and not pool.exhausted and extensions < MAX_EXTENSIONS_PER_REQUEST:
            await self._extend_pool(ctx, pool)
            extensions += 1

        page_start = (page - 1) * limit
        page_papers = [paper.model_copy(deep=True) for paper in pool.ranked[page_start : page_start + limit]]
        for paper in page_papers:
            paper.matched_terms = matched_query_terms(normalized_query, paper)
        has_next_page = len(pool.ranked) > page_start + limit or not pool.exhausted

        # ---- translate the visible page -------------------------------------------------------
        translation_retry_ids: list[str] = []
        if translate_results and resolved_target_language != "en" and page_papers:
            translation_retry_ids = await self._translate_page(page_papers, resolved_target_language, user_id)

        # ---- history --------------------------------------------------------------------------
        resolved_session_id = session_id
        if save_history and page == 1:
            try:
                resolved_session_id = self.workspace.record_history(
                    query=query,
                    normalized_query=normalized_query,
                    sources=sources,
                    result_count=len(pool.ranked),
                    session_id=session_id,
                    user_id=user_id,
                )
            except Exception:  # noqa: BLE001 — history must never break search
                logger.exception("Could not record search history")

        total_pages = ceil(len(pool.ranked) / limit) if pool.ranked else 0
        if has_next_page and total_pages <= page:
            total_pages = page + 1
        facets = pool.discovery_facets
        next_query = urlencode({"page": page + 1, "limit": limit, "query": normalized_query})

        return PaperSearchResponse(
            query=original_query,
            normalized_query=normalized_query,
            query_understanding={**understood.__dict__, "query": normalized_query},
            translated_query=translated_query,
            total_results=len(pool.ranked),
            deduplicated_results=len(pool.ranked),
            papers=page_papers,
            translation_retry_ids=translation_retry_ids,
            pagination=SearchPagination(
                page=page,
                page_size=limit,
                returned_results=len(page_papers),
                total_pages=total_pages,
                has_next_page=has_next_page,
            ),
            cache_status=SearchCacheStatus(),
            likely_duplicate_pairs=[],
            source_failures=pool.source_failures if built_now else [],
            suggestions=pool.suggestions,
            trending_topics=pool.trending_topics,
            clusters=pool.clusters,
            search_mode=search_mode,
            query_type=query_type,
            interpreted_query=query_intelligence["interpreted_query"],
            corrected_query=query_intelligence["corrected_query"],
            boolean_query=query_intelligence["boolean_query"],
            resumable_session_id=resolved_session_id,
            author_network=facets["author_network"],
            author_disambiguation=facets["author_disambiguation"],
            venue_matches=facets["venue_matches"],
            institution_matches=facets["institution_matches"],
            dataset_matches=facets["dataset_matches"],
            code_repository_matches=facets["code_repository_matches"],
            recommended_papers=facets["recommended_papers"],
            citation_expansion_titles=facets["citation_expansion_titles"],
            co_citation_pairs=facets["co_citation_pairs"],
            bibliographic_coupling_pairs=facets["bibliographic_coupling_pairs"],
            figure_search_matches=facets["figure_search_matches"],
            source_coverage=facets["source_coverage"],
            search_insights={
                **facets["search_insights"],
                "dedup_reduction_ratio": round(max(0.0, (pool.raw_count - pool.filtered_count) / max(pool.raw_count, 1)), 2),
                "query_type": query_type,
                "saved_history": save_history,
                "semantic_vector_indexed_results": len(pool.ranked),
                "advanced_query_blocks": query_intelligence["boolean_query"].split(" AND ") if query_intelligence["boolean_query"] else [],
                "author_intent": author_hint,
                "author_exact_match_available": pool.author_exact_match_available,
                "advanced_discovery_modes": advanced_discovery["modes"],
                "advanced_discovery_filters": advanced_discovery["filters"],
                "temporal_aware": temporal_aware,
                "private_search_vault": private_search_vault,
                "collaborative_session": collaborative_session,
            },
            ranking_explanations=self._ranking_explanations(normalized_query, page_papers),
            prefetch_next_page=f"/api/v1/search?{next_query}" if has_next_page else None,
            lazy_prefetch_window=[f"/api/v1/search?{next_query}"] if has_next_page else [],
            alert_preview_available=True,
        )

    # ------------------------------------------------------------------ pool management

    @staticmethod
    def _pool_key(arguments: dict[str, Any]) -> str:
        normalized = {
            key: (sorted(value) if isinstance(value, (list, tuple, set)) else value)
            for key, value in arguments.items()
        }
        if isinstance(normalized.get("query"), str):
            normalized["query"] = " ".join(normalized["query"].casefold().split())
        raw = json.dumps(normalized, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _get_pool(self, key: str) -> _ResultPool | None:
        pool = self._pools.get(key)
        if pool is None:
            return None
        if pool.expired():
            self._pools.pop(key, None)
            return None
        self._pools.move_to_end(key)
        return pool

    def _store_pool(self, key: str, pool: _ResultPool) -> None:
        self._pools[key] = pool
        self._pools.move_to_end(key)
        while len(self._pools) > POOL_MAX_ENTRIES:
            self._pools.popitem(last=False)

    async def _build_pool(self, ctx: _SearchContext, emit: SourceEventCallback | None) -> _ResultPool:
        raw, failures, has_more = await self._gather(ctx, provider_page=1, emit=emit, include_web=True)

        # An author name glued to the topic can return nothing; retry once with the topic only.
        if ctx.author_hint and ctx.provider_query != ctx.normalized_query and not raw:
            retry_ctx = replace(ctx, provider_query=ctx.normalized_query, original_language_query=None)
            raw, _, has_more = await self._gather(retry_ctx, provider_page=1, emit=None, include_web=False)

        ranked, filtered_count, clusters, suggestions, trending, author_exact = self._rank(ctx, raw)
        facets = build_discovery_facets(ranked, query=ctx.normalized_query, query_type=ctx.query_type, image_caption=ctx.image_caption)
        facets["search_insights"] = {
            key: value for key, value in (facets.get("search_insights") or {}).items() if key != "category_1_coverage"
        }
        return _ResultPool(
            ranked=ranked,
            seen={_paper_key(paper) for paper in ranked},
            provider_page=1,
            exhausted=not raw or not has_more,
            raw_count=len(raw),
            filtered_count=filtered_count,
            clusters=clusters,
            suggestions=suggestions,
            trending_topics=trending,
            discovery_facets=facets,
            source_failures=failures,
            author_exact_match_available=author_exact,
        )

    async def _extend_pool(self, ctx: _SearchContext, pool: _ResultPool) -> None:
        """Fetch the sources' next page and append papers the user has not seen yet."""
        if pool.provider_page >= MAX_PROVIDER_PAGES:
            pool.exhausted = True
            return
        next_page = pool.provider_page + 1
        raw, _, has_more = await self._gather(ctx, provider_page=next_page, emit=None, include_web=False)
        pool.provider_page = next_page
        fresh = [paper for paper in raw if _paper_key(paper) not in pool.seen]
        if not fresh:
            pool.exhausted = True
            return
        ranked, filtered_count, *_ = self._rank(ctx, fresh)
        added = 0
        for paper in ranked:
            key = _paper_key(paper)
            if key in pool.seen:
                continue
            pool.seen.add(key)
            pool.ranked.append(paper)
            added += 1
        pool.raw_count += len(raw)
        pool.filtered_count += filtered_count
        if not added or not has_more:
            pool.exhausted = True

    # ------------------------------------------------------------------ fetching

    async def _gather(
        self,
        ctx: _SearchContext,
        *,
        provider_page: int,
        emit: SourceEventCallback | None,
        include_web: bool,
    ) -> tuple[list[Any], list[str], bool]:
        """Returns (records, failure messages, whether any source returned a full page and may have more)."""
        main_request = SourceSearchRequest(query=ctx.provider_query, limit=ctx.limit, page=provider_page, filters=ctx.filters)
        calls: list[tuple[str, SearchProvider, SourceSearchRequest]] = [(name, provider, main_request) for name, provider in ctx.providers]
        if ctx.original_language_query:
            original_request = SourceSearchRequest(
                query=ctx.original_language_query, limit=ctx.limit, page=provider_page, filters=ctx.filters
            )
            calls.extend((name, provider, original_request) for name, provider in ctx.providers if name in MULTILINGUAL_SOURCES)

        async def collect(name: str, provider: SearchProvider, request: SourceSearchRequest) -> tuple[list[Any], bool]:
            if emit is not None:
                emit("source_started", {})
            try:
                papers = await self._search_provider_with_timeout(provider, request)
            except Exception as error:
                logger.warning("Search source %s failed (page %s): %s", name, provider_page, error)
                raise
            records = self._prepare_records(papers)
            if emit is not None and records:
                visible = self._filter_for_stream(ctx, records)
                if visible:
                    emit("source_results", {"papers": [paper.model_dump(mode="json") for paper in visible]})
            return records, len(papers or []) >= max(1, int(request.limit * 0.8))

        async def collect_web() -> list[Any]:
            try:
                papers = await self.web_search.search(ctx.provider_query, ctx.limit)
            except Exception as error:  # noqa: BLE001
                logger.warning("Web search failed: %s", error)
                return []
            records = self._prepare_records(papers)
            if emit is not None and records:
                visible = self._filter_for_stream(ctx, records)
                if visible:
                    emit("source_results", {"papers": [paper.model_dump(mode="json") for paper in visible]})
            return records

        web_task = asyncio.create_task(collect_web()) if include_web else None
        batches = await asyncio.gather(*(collect(name, provider, request) for name, provider, request in calls), return_exceptions=True)
        web_papers = await web_task if web_task is not None else []

        raw: list[Any] = []
        failures: list[str] = []
        has_more = False
        for batch in batches:
            if isinstance(batch, BaseException):
                failures.append("A research source is temporarily unavailable.")
                continue
            records, full_page = batch
            raw.extend(records)
            has_more = has_more or full_page
        raw.extend(web_papers)
        return raw, failures, has_more

    async def _search_provider_with_timeout(self, provider: SearchProvider, request: SourceSearchRequest):
        try:
            return await asyncio.wait_for(provider.search(request), timeout=self.source_timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"source exceeded {self.source_timeout_seconds:.0f}s soft timeout") from exc

    @staticmethod
    def _safe_emitter(callback: SourceEventCallback | None) -> SourceEventCallback | None:
        if callback is None:
            return None

        def emit(event: str, payload: dict[str, object]) -> None:
            try:
                callback(event, payload)
            except Exception:  # noqa: BLE001 — a broken listener must not fail the search
                logger.debug("Search event listener failed", exc_info=True)

        return emit

    # ------------------------------------------------------------------ cleaning & ranking

    def _prepare_records(self, papers: list[Any]) -> list[Any]:
        """Clean every record once, then drop records that are not real, readable results."""
        prepared = []
        for paper in papers or []:
            try:
                cleaned = self._clean_record(paper)
            except Exception:  # noqa: BLE001
                logger.debug("Skipping record that could not be cleaned", exc_info=True)
                continue
            if self._is_usable_record(cleaned):
                prepared.append(cleaned)
        return prepared

    @staticmethod
    def _clean_record(paper: Any) -> Any:
        title = clean_text(paper.title).rstrip(" .") if paper.title else ""
        abstract = strip_leading_title(title, clean_text(getattr(paper, "abstract", None)))
        micro_summary = strip_leading_title(title, clean_text(getattr(paper, "micro_summary", None)))
        updates: dict[str, Any] = {"title": title, "abstract": abstract or None, "micro_summary": micro_summary or None}
        year = getattr(paper, "year", None)
        if year and (year > _current_year() or year < 1500):
            updates["year"] = None  # never show impossible or future years
        if not paper.authors and getattr(paper, "ranking_score", None):
            updates["ranking_score"] = paper.ranking_score * 0.8  # applied once, here
        return paper.model_copy(update=updates)

    @staticmethod
    def _is_usable_record(paper: Any) -> bool:
        title = paper.title or ""
        if len(title) < 4 or JUNK_TITLE.match(title) or COMPONENT_TITLE.match(title):
            return False
        if (paper.publication_type or "").casefold().replace("_", "-") in IGNORED_PUBLICATION_TYPES:
            return False
        if ((paper.source or "").startswith("web_") or paper.publication_type == "web") and not paper.url:
            return False
        return True

    def _filter_for_stream(self, ctx: _SearchContext, records: list[Any]) -> list[Any]:
        """Apply the user's filters to streamed papers so nothing appears that the final list will remove."""
        try:
            enriched = [infer_metadata_fields(paper.model_copy(deep=True)) for paper in records]
            return apply_filters(enriched, **ctx.filter_kwargs)
        except Exception:  # noqa: BLE001
            logger.debug("Stream filter failed; streaming unfiltered batch", exc_info=True)
            return records

    def _rank(self, ctx: _SearchContext, raw: list[Any]):
        """Deduplicate, enrich, filter and rank. Returns (ranked, filtered_count, clusters, suggestions, trending, author_exact)."""
        if not raw:
            return [], 0, {}, [], [], None
        deduped = deduplicate_papers(raw)
        enriched = [infer_metadata_fields(paper) for paper in deduped.papers]
        for paper in enriched:
            detected_language, confidence = detect_language(f"{paper.title} {paper.abstract or ''}")
            if confidence >= 0.72:
                paper.language = detected_language
        filtered = apply_filters(enriched, **ctx.filter_kwargs)

        author_exact: bool | None = None
        if ctx.author_hint:
            author_matches = apply_filters(enriched, **{**ctx.filter_kwargs, "author": ctx.author_hint})
            author_exact = bool(author_matches)
            if author_matches:
                filtered = author_matches
            else:
                text_matches = [paper for paper in filtered if self._author_hint_in_record(ctx.author_hint, paper)]
                if text_matches:
                    filtered = text_matches

        ranked, clusters, suggestions, trending_topics = enrich_search_results(
            ctx.normalized_query, filtered, search_mode=ctx.search_mode, sort_by=ctx.sort_by
        )
        if ctx.sort_by == "relevance":
            ranked = self._keep_relevant_results(ctx.normalized_query, ranked)
        return ranked, len(filtered), clusters, suggestions, trending_topics, author_exact

    def _keep_relevant_results(self, query: str, papers: list) -> list:
        """Promote clearly relevant papers; never turn a non-empty result set into "no results"."""
        if not papers:
            return papers
        intent_terms = {
            term
            for term in re.findall(r"\b[a-zA-Z][a-zA-Z-]+\b", query.lower())
            if len(term) > 2 and term not in {"and", "for", "from", "the", "with", "using", "paper", "papers", "research", "study"}
        }
        if len(intent_terms) < 3:
            return papers
        scored = [(search_relevance_score(query, paper), paper) for paper in papers]
        strong = [(score, paper) for score, paper in scored if score >= 0.34]
        moderate = [(score, paper) for score, paper in scored if score >= 0.22 and paper.ranking_score >= 0.12]
        kept = strong or moderate
        if not kept:
            # Nothing passed the lexical bar (often synonyms or translated queries): keep the ranker's order.
            return papers
        for score, paper in kept:
            paper.ranking_score = round(max(paper.ranking_score, score), 3)
        return [
            paper
            for _, paper in sorted(
                kept,
                key=lambda item: (item[0], self._title_intent_score(query, item[1]), item[1].ranking_score, item[1].citation_count),
                reverse=True,
            )
        ]

    # ------------------------------------------------------------------ translation

    async def _translate_page(self, page_papers: list[Any], target_language: str, user_id: str | None) -> list[str]:
        """Translate titles and snippets of the visible page in one batch. Mutates page_papers (copies)."""
        segments: list[str] = []
        segment_indexes: list[tuple[int, str]] = []
        for index, paper in enumerate(page_papers):
            if (getattr(paper, "language", None) or "").split("-")[0] == target_language.split("-")[0]:
                paper.translation_status = "original"  # already in the user's language
                continue
            segments.append(paper.title)
            segment_indexes.append((index, "title"))
            snippet = (paper.micro_summary or paper.abstract or "").strip()[:SNIPPET_TRANSLATION_CHARS]
            if snippet:
                segments.append(snippet)
                segment_indexes.append((index, "abstract"))
        if not segments:
            return []

        retry_ids: list[str] = []
        try:
            # Paper titles and abstracts are public metadata: user_content=False lets every user share cached translations.
            translated_segments = await asyncio.to_thread(translate_batch, segments, target_language, user_id=user_id, user_content=False)
        except (TranslationUnavailable, ValueError):
            translated_segments = None

        if translated_segments is not None:
            for (index, field_name), text in zip(segment_indexes, translated_segments):
                text = clean_text(text)
                if not text:
                    continue
                if field_name == "title":
                    page_papers[index].translated_title = text
                    page_papers[index].translation_status = "translated"
                else:
                    page_papers[index].translated_abstract = text
            # Anything the batch skipped is retried in the background.
            pending = {index for index, field_name in segment_indexes if field_name == "title" and not page_papers[index].translated_title}
        else:
            pending = {index for index, _ in segment_indexes}

        for index in sorted(pending):
            paper = page_papers[index]
            paper.translated_title = None
            paper.translated_abstract = None
            paper.translation_status = "unavailable"
            try:
                retry_id = schedule_translation_retry(
                    paper.title, paper.abstract or paper.micro_summary, target_language, user_id=user_id, paper_id=paper.paper_id
                )
            except Exception:  # noqa: BLE001
                logger.exception("Could not schedule translation retry")
                retry_id = None
            if retry_id:
                retry_ids.append(retry_id)
        return retry_ids

    # ------------------------------------------------------------------ background work

    def _cache_in_background(self, papers: list[Any]) -> None:
        """Persist results without making the user wait for it."""
        if not papers:
            return

        async def run() -> None:
            try:
                await self.cache.cache_search_results(papers)
            except Exception:  # noqa: BLE001
                logger.exception("Background paper cache failed")

        try:
            task = asyncio.get_running_loop().create_task(run())
        except RuntimeError:
            return
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def workspace_update_trending(self, pool: _ResultPool, user_id: str | None) -> None:
        try:
            self.workspace.update_trending(pool.ranked, pool.trending_topics, user_id=user_id)
        except Exception:  # noqa: BLE001 — trending is optional
            logger.exception("Could not update trending topics")

    # ------------------------------------------------------------------ query helpers (unchanged behaviour)

    def _advanced_discovery_terms(
        self,
        *,
        citation_context: str | None,
        region: str | None,
        chemical_formula: str | None,
        gene_or_protein: str | None,
        equipment_or_software: str | None,
        negative_results_only: bool,
        patent_overlap: bool,
        grey_literature: bool,
        conference_priority: bool,
        cited_by_quality_only: bool,
    ) -> dict[str, list[str] | dict[str, str | bool]]:
        query_terms: list[str] = []
        modes: list[str] = []
        filters: dict[str, str | bool] = {}
        if citation_context:
            query_terms.extend(["citation context", citation_context])
            modes.append("citation-context search")
            filters["citation_context"] = citation_context
        if region:
            query_terms.extend(["geography", region])
            modes.append("geospatial search")
            filters["region"] = region
        if chemical_formula:
            query_terms.extend(["chemical formula", chemical_formula])
            modes.append("chemical/formula search")
            filters["chemical_formula"] = chemical_formula
        if gene_or_protein:
            query_terms.extend(["gene protein sequence", gene_or_protein])
            modes.append("gene/protein search")
            filters["gene_or_protein"] = gene_or_protein
        if equipment_or_software:
            query_terms.extend(["equipment software method", equipment_or_software])
            modes.append("equipment/methodology search")
            filters["equipment_or_software"] = equipment_or_software
        if negative_results_only:
            query_terms.extend(["null result", "negative finding", "non-significant"])
            modes.append("negative-results discovery")
            filters["negative_results_only"] = True
        if patent_overlap:
            query_terms.extend(["patent", "intellectual property"])
            modes.append("patent/IP overlap")
            filters["patent_overlap"] = True
        if grey_literature:
            query_terms.extend(["thesis", "white paper", "government report"])
            modes.append("grey literature")
            filters["grey_literature"] = True
        if conference_priority:
            query_terms.extend(["conference proceedings", "proceedings"])
            modes.append("conference proceedings priority")
            filters["conference_priority"] = True
        if cited_by_quality_only:
            query_terms.extend(["high impact journal", "highly cited"])
            modes.append("cited-by quality filter")
            filters["cited_by_quality_only"] = True
        return {"query_terms": query_terms, "modes": modes, "filters": filters}

    def _extract_author_intent(self, query: str) -> tuple[str | None, str]:
        """Parse natural author queries without letting the word "author" pollute source search."""
        tokens = query.split()
        lowered = [token.strip(" ,.;:()[]{}").lower() for token in tokens]
        author_markers = {"author", "authors", "by"}
        topic_stop_words = {
            "about", "against", "analysis", "attention", "benchmark", "benchmarks", "biomarker", "biomarkers", "cancer",
            "classification", "dataset", "datasets", "deep", "deepfake", "detection", "evaluation", "folding", "for",
            "frequency", "graph", "hybrid", "immunotherapy", "learning", "method", "methods", "network", "networks",
            "neural", "paper", "papers", "protein", "rag", "retrieval", "review", "survey", "using", "with",
        }
        probable_name = self._probable_author_name(tokens, topic_stop_words)
        if probable_name:
            return probable_name, ""
        for index, token in enumerate(lowered):
            if token not in author_markers:
                continue
            name_tokens: list[str] = []
            consumed_indexes = {index}
            for candidate_index in range(index + 1, min(len(tokens), index + 5)):
                raw_candidate = tokens[candidate_index].strip(" ,.;:()[]{}")
                candidate = raw_candidate.lower()
                if not raw_candidate:
                    continue
                if name_tokens and candidate in topic_stop_words:
                    break
                if len(name_tokens) >= 3:
                    break
                name_tokens.append(raw_candidate)
                consumed_indexes.add(candidate_index)
            if name_tokens:
                cleaned = " ".join(token for idx, token in enumerate(tokens) if idx not in consumed_indexes)
                return " ".join(name_tokens), " ".join(cleaned.split())
        return None, query

    def _probable_author_name(self, tokens: list[str], topic_stop_words: set[str]) -> str | None:
        clean_tokens = [token.strip(" ,.;:()[]{}") for token in tokens if token.strip(" ,.;:()[]{}")]
        if not 2 <= len(clean_tokens) <= 4:
            return None
        lowered = [token.lower() for token in clean_tokens]
        if any(token in topic_stop_words for token in lowered):
            return None
        if any(token in {"and", "or", "near", "not", "vs", "versus"} for token in lowered):
            return None
        name_like = [
            bool(re.match(r"^[A-Z][A-Za-z'.-]{1,}$", token)) or bool(re.match(r"^[A-Z]\.?$", token)) for token in clean_tokens
        ]
        return " ".join(clean_tokens) if all(name_like) else None

    def _author_hint_in_record(self, author_hint: str, paper) -> bool:
        haystack = " ".join(str(author.get("name", "")) for author in paper.authors)
        author_tokens = [token.lower() for token in re.findall(r"[A-Za-z]+", author_hint)]
        lowered = haystack.lower()
        if not author_tokens:
            return False
        if all(re.search(rf"\b{re.escape(token)}\b", lowered) for token in author_tokens):
            return True
        if len(author_tokens) >= 2:
            first, last = author_tokens[0], author_tokens[-1]
            return bool(re.search(rf"\b{re.escape(last)}\b", lowered) and re.search(rf"\b{re.escape(first[0])}\.?\b", lowered))
        return False

    def _title_intent_score(self, query: str, paper) -> float:
        title = paper.title.lower()
        aliases = {
            "convolutional": {"convolutional", "cnn", "convnet"},
            "neural": {"neural", "cnn", "rnn", "transformer"},
            "networks": {"network", "networks", "cnn", "gcn", "rnn"},
            "deepfake": {"deepfake", "deepfakes", "forgery", "manipulation"},
            "urdu": {"urdu", "roman urdu"},
            "sentiment": {"sentiment", "opinion", "polarity"},
            "lung": {"lung", "pulmonary", "nsclc"},
            "cancer": {"cancer", "carcinoma", "adenocarcinoma", "oncology"},
            "immunotherapy": {"immunotherapy", "nivolumab", "pembrolizumab", "checkpoint"},
            "biomarkers": {"biomarker", "biomarkers", "pd-l1"},
            "graph": {"graph", "gcn"},
            "protein": {"protein", "proteins"},
            "folding": {"folding", "structure"},
        }
        terms = [
            term
            for term in re.findall(r"\b[a-zA-Z][a-zA-Z-]+\b", query.lower())
            if len(term) > 2
            and term not in {"and", "for", "from", "the", "with", "using", "paper", "papers", "research", "study", "methods", "method", "based"}
        ]
        if not terms:
            return 0.0
        hits = sum(
            1 for term in terms if any(re.search(rf"\b{re.escape(variant)}\b", title) for variant in aliases.get(term, {term}))
        )
        return round(hits / len(terms), 3)

    def _ranking_explanations(self, query: str, papers: list) -> list[RankingExplanation]:
        """Internal diagnostics (stripped by the public API presenter)."""
        query_terms = {part.lower() for part in query.split() if part}
        vector_scores = semantic_vector_scores(query, papers)
        explanations = []
        for paper in papers[:6]:
            title_tokens = {part.lower() for part in paper.title.split()}
            abstract_tokens = {part.lower() for part in (paper.abstract or "").split()}
            keyword_score = round(min(1.0, len(query_terms & title_tokens) / max(len(query_terms), 1)), 2)
            lexical_semantic_score = round(min(1.0, len(query_terms & (title_tokens | abstract_tokens)) / max(len(query_terms), 1)), 2)
            semantic_score = round(max(lexical_semantic_score, vector_scores.get(paper.paper_id, 0.0)), 2)
            citation_bonus = round(min(1.0, paper.citation_count / 250), 2)
            reasons = []
            if keyword_score:
                reasons.append("Title matches the query strongly.")
            if vector_scores.get(paper.paper_id, 0.0) > 0:
                reasons.append("Semantic similarity found in title and abstract.")
            elif semantic_score > keyword_score:
                reasons.append("Abstract contains additional concept overlap.")
            if paper.is_open_access:
                reasons.append("Open-access availability improves downstream reading.")
            if paper.datasets:
                reasons.append("Dataset signal detected for structured comparison.")
            explanations.append(
                RankingExplanation(
                    paper_id=paper.paper_id,
                    semantic_score=semantic_score,
                    keyword_score=keyword_score,
                    citation_bonus=citation_bonus,
                    reasons=reasons or ["General relevance score from hybrid reranking."],
                )
            )
        return explanations
