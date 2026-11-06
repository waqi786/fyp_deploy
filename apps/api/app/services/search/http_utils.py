import asyncio
import os
import random
import time
from urllib.parse import urlparse

import httpx


_RATE_LOCKS: dict[str, asyncio.Lock] = {}
_LAST_REQUEST: dict[str, float] = {}


async def _respect_api_rate_limit(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    minimum_gap = {
        "api.crossref.org": 0.34,
        "export.arxiv.org": 3.0,
        "api.openalex.org": 0.1,
        "www.ebi.ac.uk": 0.1,
        "api.archives-ouvertes.fr": 0.1,
        "zenodo.org": 0.1,
        "dblp.org": 0.1,
        "doaj.org": 0.1,
    }.get(host, 0.1)
    lock = _RATE_LOCKS.setdefault(host, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        delay = max(0.0, _LAST_REQUEST.get(host, 0.0) + minimum_gap - now)
        if delay:
            await asyncio.sleep(delay)
        _LAST_REQUEST[host] = time.monotonic()


async def get_json_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    attempts: int = 3,
    base_delay: float = 0.4,
) -> dict:
    return await _request_with_backoff(
        client,
        url,
        params=params,
        headers=headers,
        attempts=attempts,
        base_delay=base_delay,
        response_parser=lambda response: response.json(),
    )


async def get_text_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    attempts: int = 3,
    base_delay: float = 0.4,
) -> str:
    return await _request_with_backoff(
        client,
        url,
        params=params,
        headers=headers,
        attempts=attempts,
        base_delay=base_delay,
        response_parser=lambda response: response.text,
    )


async def _request_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None,
    headers: dict | None,
    attempts: int,
    base_delay: float,
    response_parser,
):
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            await _respect_api_rate_limit(url)
            email = os.getenv("API_CONTACT_EMAIL", "support@resora.local")
            request_headers = {"User-Agent": f"Resora/0.1 (+mailto:{email})"}
            request_headers.update(headers or {})
            response = await client.get(url, params=params, headers=request_headers)
            response.raise_for_status()
            return response_parser(response)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == attempts - 1:
                break
            await asyncio.sleep(base_delay * (2**attempt) + random.uniform(0.05, 0.2))
    raise RuntimeError(f"Request failed for {url}") from last_error
