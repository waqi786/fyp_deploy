"""Optional, cached web search adapters. No model or translation work is performed here."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.schemas.paper import PaperRecord

logger = logging.getLogger(__name__)


class WebSearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[PaperRecord]: ...


def _result_paper(provider: str, item: dict, index: int) -> PaperRecord | None:
    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    if not title or not url:
        return None
    snippet = item.get("content") or item.get("text") or item.get("snippet") or item.get("highlights") or ""
    if isinstance(snippet, list):
        snippet = " ".join(str(part) for part in snippet)
    published = item.get("published_date") or item.get("publishedDate")
    year = None
    if published:
        try:
            year = parsedate_to_datetime(str(published)).year
        except (TypeError, ValueError, OverflowError):
            try:
                year = int(str(published)[:4])
            except (TypeError, ValueError):
                year = None
    return PaperRecord(
        paper_id=f"web:{hashlib.sha256(url.encode()).hexdigest()[:24]}",
        title=title,
        abstract=str(snippet).strip() or None,
        year=year,
        venue=urlparse(url).hostname or "Web page",
        publication_type="web",
        url=url,
        source="web",
        citation_count=0,
        authors=[],
        result_badges=["Web"],
        external_ids={"web_index": str(index)},
    )


class TavilyWebSearchProvider:
    name = "tavily"
    monthly_credit_limit = 1000
    credit_cost = 2  # advanced search

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, limit: int) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=float(getattr(settings, "web_search_timeout_seconds", 8))) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.api_key}", "User-Agent": _user_agent()},
                json={"query": query, "search_depth": "advanced", "max_results": min(limit, 20), "include_answer": False},
            )
            response.raise_for_status()
            items = response.json().get("results", [])
        return [paper for index, item in enumerate(items) if (paper := _result_paper(self.name, item, index))]


class ExaWebSearchProvider:
    name = "exa"
    monthly_credit_limit: int | None = None
    credit_cost = 1

    def __init__(self, api_key: str, monthly_limit: int | None = None) -> None:
        self.api_key = api_key
        self.monthly_credit_limit = monthly_limit

    async def search(self, query: str, limit: int) -> list[PaperRecord]:
        async with httpx.AsyncClient(timeout=float(getattr(settings, "web_search_timeout_seconds", 8))) as client:
            response = await client.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": self.api_key, "User-Agent": _user_agent()},
                json={"query": query, "type": "auto", "numResults": min(limit, 20), "contents": {"highlights": True}},
            )
            response.raise_for_status()
            items = response.json().get("results", [])
        return [paper for index, item in enumerate(items) if (paper := _result_paper(self.name, item, index))]


def _user_agent() -> str:
    contact = getattr(settings, "api_contact_email", None) or "support@resora.local"
    return f"Resora/0.1 (+mailto:{contact})"


class WebSearchService:
    """Tavily-first/Exa-fallback search with Redis-backed 24h cache and monthly usage caps."""

    def __init__(self, providers: list[WebSearchProvider] | None = None, redis_client=None) -> None:
        if providers is None:
            providers = []
            tavily_key = getattr(settings, "tavily_api_key", None) or os.getenv("TAVILY_API_KEY")
            exa_key = getattr(settings, "exa_api_key", None) or os.getenv("EXA_API_KEY")
            try:
                budgets = json.loads(getattr(settings, "web_search_monthly_budgets", "{}") or "{}")
            except (TypeError, ValueError):
                budgets = {}
            if tavily_key:
                tavily = TavilyWebSearchProvider(tavily_key)
                tavily.monthly_credit_limit = int(budgets["tavily"]) if budgets.get("tavily") is not None else None
                providers.append(tavily)
            if exa_key:
                providers.append(ExaWebSearchProvider(exa_key, int(budgets["exa"]) if budgets.get("exa") is not None else None))
            configured_order = getattr(settings, "web_search_provider_order", "") or getattr(settings, "web_search_provider", "tavily")
            provider_rank = {name.strip().lower(): index for index, name in enumerate(configured_order.split(","))}
            providers.sort(key=lambda provider: provider_rank.get(provider.name, len(provider_rank)))
        self.providers = providers
        self.redis_client = redis_client
        self.memory_cache: dict[str, tuple[datetime, list[PaperRecord]]] = {}
        self.memory_usage: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._last_call: dict[str, float] = {}

    async def search(self, query: str, limit: int = 10) -> list[PaperRecord]:
        if not self.providers:
            return []
        limit = min(max(1, limit), int(getattr(settings, "web_search_max_results", 10)))
        normalized = " ".join(query.casefold().split())
        cache_key = "resora:web-search:v1:" + hashlib.sha256(normalized.encode()).hexdigest()
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached[:limit]
        for provider in self.providers:
            if not await self._reserve_budget(provider):
                continue
            try:
                await self._polite_wait(provider.name)
                results = await asyncio.wait_for(
                    provider.search(query, limit),
                    timeout=float(getattr(settings, "web_search_timeout_seconds", 8)),
                )
            except Exception as exc:  # provider errors are intentionally isolated from paper search
                logger.warning("Web search provider %s failed (%s)", provider.name, type(exc).__name__)
                continue
            if results:
                await self._cache_set(cache_key, results)
                return results[:limit]
        return []

    async def _cache_get(self, key: str) -> list[PaperRecord] | None:
        client = self.redis_client or _redis_client()
        if client:
            try:
                encoded = await client.get(key)
                if encoded:
                    return [PaperRecord.model_validate(value) for value in json.loads(encoded)]
            except Exception:  # Redis is optional; local cache remains usable.
                pass
        entry = self.memory_cache.get(key)
        if entry and datetime.now(UTC) - entry[0] < timedelta(seconds=int(getattr(settings, "web_search_cache_ttl_seconds", 86400))):
            return entry[1]
        return None

    async def _cache_set(self, key: str, papers: list[PaperRecord]) -> None:
        self.memory_cache[key] = (datetime.now(UTC), papers)
        client = self.redis_client or _redis_client()
        if client:
            try:
                await client.set(key, json.dumps([paper.model_dump(mode="json") for paper in papers]), ex=int(getattr(settings, "web_search_cache_ttl_seconds", 86400)))
            except Exception:
                pass

    async def _reserve_budget(self, provider: WebSearchProvider) -> bool:
        limit = getattr(provider, "monthly_credit_limit", None)
        cost = int(getattr(provider, "credit_cost", 1))
        month = datetime.now(UTC).strftime("%Y-%m")
        key = f"resora:web-search:usage:{provider.name}:{month}"
        ttl = int((datetime.now(UTC).replace(day=28) + timedelta(days=4)).replace(day=1).timestamp() - datetime.now(UTC).timestamp())
        client = self.redis_client or _redis_client()
        if client:
            script = "local n=tonumber(redis.call('GET',KEYS[1]) or '0'); local c=tonumber(ARGV[1]); local m=tonumber(ARGV[2]); if n+c>m then return 0 end; redis.call('INCRBY',KEYS[1],c); redis.call('EXPIRE',KEYS[1],ARGV[3]); return 1"
            try:
                if limit is None:
                    await client.incrby(key, cost)
                    await client.expire(key, max(ttl, 60))
                    return True
                return bool(await client.eval(script, 1, key, cost, limit, max(ttl, 60)))
            except Exception:
                pass
        async with self._lock:
            used = self.memory_usage.get(key, 0)
            if limit is not None and used + cost > limit:
                return False
            self.memory_usage[key] = used + cost
            return True

    async def _polite_wait(self, provider: str) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            delay = max(0.0, self._last_call.get(provider, 0.0) + 0.15 - now)
            if delay:
                await asyncio.sleep(delay)
            self._last_call[provider] = asyncio.get_running_loop().time()


_redis = None


def _redis_client():
    global _redis
    if _redis is not None:
        return _redis
    try:
        from redis.asyncio import Redis

        redis_url = getattr(settings, "redis_url", None)
        if redis_url:
            _redis = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=0.25, socket_timeout=0.25)
    except Exception:
        return None
    return _redis
