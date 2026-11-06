"""Researcher and institution data (provider module).

All calls to the open scholarly-graph API live here, behind EntityService. Public responses never name the
provider; ids are shortened to their key (e.g. "A5023888391"). Results are cached in memory for an hour.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from app.core.config import settings
from app.schemas.entities import (
    EntityMatches,
    EntitySummary,
    InstitutionProfile,
    PersonLink,
    ResearcherProfile,
    Topic,
    WorkItem,
    YearCount,
)

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60 * 60
CACHE_MAX_ENTRIES = 512
TIMEOUT_SECONDS = 8.0
RESEARCHER_ID = re.compile(r"^A\d{4,12}$")
INSTITUTION_ID = re.compile(r"^I\d{3,12}$")
WORK_FIELDS = "id,display_name,publication_year,primary_location,cited_by_count,doi,open_access,authorships"


class EntityNotFound(LookupError):
    pass


class EntityUnavailable(RuntimeError):
    pass


def _short_id(value: str | None) -> str | None:
    if not value:
        return None
    return value.rstrip("/").rsplit("/", 1)[-1]


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[\w]+", (value or "").casefold()) if len(token) > 1]


def _name_matches_query(name: str, query: str) -> bool:
    """Show an entity only when the query is clearly about it (avoids noise for topic searches)."""
    name_tokens, query_tokens = set(_tokens(name)), set(_tokens(query))
    if not name_tokens or not query_tokens:
        return False
    if name_tokens <= query_tokens:
        return True
    return len(query_tokens) >= 2 and query_tokens <= name_tokens


class EntityService:
    def __init__(self, client_factory: Callable[[], httpx.AsyncClient] | None = None) -> None:
        self._base = (os.getenv("SCHOLARLY_GRAPH_BASE_URL") or getattr(settings, "openalex_base_url", None) or "https://api.openalex.org").rstrip("/")
        contact = os.getenv("OPENALEX_MAILTO") or getattr(settings, "api_contact_email", None) or ""
        # The polite pool needs a real address; placeholder addresses are not sent.
        self._mailto = contact if contact and "@" in contact and not contact.endswith((".local", "example.com")) else None
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers={"User-Agent": "Resora/1.0"}))
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    # ------------------------------------------------------------------ http

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        if self._mailto:
            query["mailto"] = self._mailto
        key = f"{path}?{sorted(query.items())}"
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        for attempt in range(2):
            try:
                response = await client.get(f"{self._base}{path}", params=query)
                if response.status_code == 404:
                    raise EntityNotFound(path)
                if response.status_code == 429 and attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
                response.raise_for_status()
                data = response.json()
                self._cache[key] = (time.monotonic(), data)
                while len(self._cache) > CACHE_MAX_ENTRIES:
                    self._cache.popitem(last=False)
                return data
            except EntityNotFound:
                raise
            except (httpx.HTTPError, ValueError) as error:
                if attempt == 1:
                    raise EntityUnavailable(str(error)) from error
        raise EntityUnavailable(path)

    # ------------------------------------------------------------------ search

    async def find(self, query: str) -> EntityMatches:
        query = " ".join((query or "").split())
        if len(query) < 3 or len(query) > 120:
            return EntityMatches()
        async with self._client_factory() as client:
            authors, institutions = await asyncio.gather(
                self._get(client, "/autocomplete/authors", {"q": query}),
                self._get(client, "/autocomplete/institutions", {"q": query}),
                return_exceptions=True,
            )
        matches = EntityMatches()
        if isinstance(authors, dict):
            for item in authors.get("results", [])[:8]:
                if _name_matches_query(item.get("display_name", ""), query):
                    matches.researchers.append(
                        EntitySummary(
                            id=_short_id(item.get("id")) or "",
                            kind="researcher",
                            name=item.get("display_name", ""),
                            subtitle=item.get("hint") or None,
                            works_count=int(item.get("works_count") or 0),
                            cited_by_count=int(item.get("cited_by_count") or 0),
                        )
                    )
        if isinstance(institutions, dict):
            for item in institutions.get("results", [])[:8]:
                if _name_matches_query(item.get("display_name", ""), query):
                    matches.institutions.append(
                        EntitySummary(
                            id=_short_id(item.get("id")) or "",
                            kind="institution",
                            name=item.get("display_name", ""),
                            subtitle=item.get("hint") or None,
                            works_count=int(item.get("works_count") or 0),
                            cited_by_count=int(item.get("cited_by_count") or 0),
                        )
                    )
        matches.researchers = [item for item in matches.researchers if item.id][:3]
        matches.institutions = [item for item in matches.institutions if item.id][:2]
        return matches

    # ------------------------------------------------------------------ profiles

    @staticmethod
    def _work(item: dict[str, Any]) -> WorkItem:
        location = item.get("primary_location") or {}
        source = location.get("source") or {}
        open_access = item.get("open_access") or {}
        return WorkItem(
            title=item.get("display_name") or "",
            year=item.get("publication_year"),
            venue=source.get("display_name"),
            citation_count=int(item.get("cited_by_count") or 0),
            doi=(item.get("doi") or "").removeprefix("https://doi.org/") or None,
            url=open_access.get("oa_url") or location.get("landing_page_url") or item.get("doi"),
            is_open_access=bool(open_access.get("is_oa")),
        )

    @staticmethod
    def _timeline(counts: list[dict[str, Any]]) -> list[YearCount]:
        current_year = datetime.now(timezone.utc).year
        rows = [
            YearCount(year=int(row["year"]), works=int(row.get("works_count") or 0), citations=int(row.get("cited_by_count") or 0))
            for row in counts or []
            if row.get("year") and current_year - 10 < int(row["year"]) <= current_year
        ]
        return sorted(rows, key=lambda row: row.year)

    @staticmethod
    def _topics(entity: dict[str, Any]) -> list[Topic]:
        topics = entity.get("topics") or []
        if topics:
            return [Topic(name=item.get("display_name", ""), count=int(item.get("count") or 0)) for item in topics[:10] if item.get("display_name")]
        concepts = entity.get("x_concepts") or []
        return [Topic(name=item.get("display_name", ""), count=0) for item in concepts[:10] if item.get("display_name")]

    async def researcher(self, entity_id: str) -> ResearcherProfile:
        if not RESEARCHER_ID.match(entity_id or ""):
            raise EntityNotFound(entity_id)
        async with self._client_factory() as client:
            author, top, recent = await asyncio.gather(
                self._get(client, f"/authors/{entity_id}"),
                self._get(client, "/works", {"filter": f"author.id:{entity_id}", "sort": "cited_by_count:desc", "per-page": 8, "select": WORK_FIELDS}),
                self._get(client, "/works", {"filter": f"author.id:{entity_id}", "sort": "publication_date:desc", "per-page": 8, "select": WORK_FIELDS}),
            )
        collaborators: Counter[tuple[str | None, str]] = Counter()
        for work in [*top.get("results", []), *recent.get("results", [])]:
            for authorship in work.get("authorships") or []:
                person = authorship.get("author") or {}
                person_id = _short_id(person.get("id"))
                if person_id and person_id != entity_id and person.get("display_name"):
                    collaborators[(person_id, person["display_name"])] += 1
        institutions = author.get("last_known_institutions") or ([author["last_known_institution"]] if author.get("last_known_institution") else [])
        orcid = (author.get("orcid") or "").removeprefix("https://orcid.org/") or None
        return ResearcherProfile(
            id=entity_id,
            name=author.get("display_name") or "",
            affiliations=[item.get("display_name") for item in institutions if item and item.get("display_name")][:3],
            orcid=orcid,
            works_count=int(author.get("works_count") or 0),
            cited_by_count=int(author.get("cited_by_count") or 0),
            h_index=(author.get("summary_stats") or {}).get("h_index"),
            topics=self._topics(author),
            timeline=self._timeline(author.get("counts_by_year") or []),
            top_works=[self._work(item) for item in top.get("results", []) if item.get("display_name")],
            recent_works=[self._work(item) for item in recent.get("results", []) if item.get("display_name")],
            collaborators=[PersonLink(id=pid, name=name, count=count) for (pid, name), count in collaborators.most_common(8)],
        )

    async def institution(self, entity_id: str) -> InstitutionProfile:
        if not INSTITUTION_ID.match(entity_id or ""):
            raise EntityNotFound(entity_id)
        async with self._client_factory() as client:
            institution, authors, works = await asyncio.gather(
                self._get(client, f"/institutions/{entity_id}"),
                self._get(client, "/authors", {"filter": f"last_known_institutions.id:{entity_id}", "sort": "cited_by_count:desc", "per-page": 8}),
                self._get(client, "/works", {"filter": f"institutions.id:{entity_id}", "sort": "cited_by_count:desc", "per-page": 8, "select": WORK_FIELDS}),
            )
        geo = institution.get("geo") or {}
        return InstitutionProfile(
            id=entity_id,
            name=institution.get("display_name") or "",
            country=geo.get("country") or institution.get("country_code"),
            type=institution.get("type"),
            homepage=institution.get("homepage_url"),
            works_count=int(institution.get("works_count") or 0),
            cited_by_count=int(institution.get("cited_by_count") or 0),
            topics=self._topics(institution),
            timeline=self._timeline(institution.get("counts_by_year") or []),
            top_researchers=[
                PersonLink(
                    id=_short_id(item.get("id")),
                    name=item.get("display_name") or "",
                    count=int(item.get("cited_by_count") or 0),
                )
                for item in authors.get("results", [])
                if item.get("display_name")
            ],
            top_works=[self._work(item) for item in works.get("results", []) if item.get("display_name")],
        )


_default: EntityService | None = None


def get_entity_service() -> EntityService:
    global _default
    if _default is None:
        _default = EntityService()
    return _default
