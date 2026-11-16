"""Search provider over Resora's own deduplicated catalog (built by apps/pipeline): hybrid FAISS + BM25 search.

Opt-in source "resora_catalog"; it is registered only when a pipeline index exists, so nothing changes for
installations that do not run the pipeline.
"""

from __future__ import annotations

import asyncio

from app.schemas.paper import PaperRecord
from app.schemas.search import SourceSearchRequest
from app.services.catalog.service import get_catalog_service


class ResoraCatalogProvider:
    source_name = "resora_catalog"

    async def search(self, request: SourceSearchRequest) -> list[PaperRecord]:
        result = await asyncio.to_thread(get_catalog_service().search, request.query, limit=request.limit * request.page)
        rows = result["results"][(request.page - 1) * request.limit:]
        papers = []
        for paper in rows:
            papers.append(PaperRecord(
                paper_id=paper["paper_id"], title=paper.get("title") or "Untitled", abstract=paper.get("abstract") or None,
                year=paper.get("year"), venue=paper.get("venue"), publication_type=paper.get("type"), doi=paper.get("doi"),
                url=paper.get("oa_url"), pdf_url=paper.get("pdf_url"), citation_count=paper.get("citation_count") or 0,
                reference_count=paper.get("reference_count") or 0, is_open_access=bool(paper.get("is_open_access")),
                authors=[{"name": author.get("name")} for author in paper.get("authors") or [] if author.get("name")],
                source=self.source_name, all_sources=paper.get("sources") or [],
                external_ids={key: value for key, value in (("doi", paper.get("doi")), ("arxiv", paper.get("arxiv_id"))) if value},
                ranking_score=float(paper.get("match", {}).get("score") or 0.0),
            ))
        return papers
