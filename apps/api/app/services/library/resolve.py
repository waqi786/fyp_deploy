"""Metadata for DOIs and arXiv ids pasted into the Library importer.

Only public scholarly metadata endpoints are called, with short timeouts and bounded concurrency. Which service answered
is never returned to the client (users see a paper or "could not be found").
"""

from __future__ import annotations

import asyncio
import os
import re
import xml.etree.ElementTree as ElementTree
from typing import Any

import httpx

from app.core.config import settings

TIMEOUT = float(os.getenv("LIBRARY_RESOLVE_TIMEOUT", "8"))
_slots = asyncio.Semaphore(6)
ATOM = "{http://www.w3.org/2005/Atom}"


def _agent() -> str:
    contact = os.getenv("CROSSREF_MAILTO") or getattr(settings, "unpaywall_email", "") or ""
    return f"Resora/1.0 (mailto:{contact})" if "@" in contact and "example" not in contact else "Resora/1.0"


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    value = re.sub(r"<[^>]+>", " ", text)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


async def resolve_doi(client: httpx.AsyncClient, doi: str) -> dict[str, Any] | None:
    async with _slots:
        try:
            response = await client.get(f"https://api.crossref.org/works/{doi}", headers={"User-Agent": _agent()})
        except httpx.HTTPError:
            return None
    if response.status_code != 200:
        return None
    try:
        message = response.json().get("message") or {}
    except ValueError:
        return None
    title = _clean((message.get("title") or [None])[0])
    if not title:
        return None
    authors = []
    for author in message.get("author") or []:
        name = ", ".join(part for part in (author.get("family"), author.get("given")) if part) or author.get("name")
        if name:
            authors.append(name)
    date_parts = ((message.get("issued") or message.get("published") or {}).get("date-parts") or [[None]])[0]
    return {
        "title": title,
        "authors": authors,
        "year": date_parts[0] if date_parts and isinstance(date_parts[0], int) else None,
        "venue": _clean((message.get("container-title") or [None])[0]),
        "doi": doi,
        "url": message.get("URL"),
        "abstract": _clean(message.get("abstract")),
    }


async def resolve_arxiv(client: httpx.AsyncClient, arxiv_id: str) -> dict[str, Any] | None:
    async with _slots:
        try:
            response = await client.get("https://export.arxiv.org/api/query", params={"id_list": arxiv_id, "max_results": 1}, headers={"User-Agent": _agent()})
        except httpx.HTTPError:
            return None
    if response.status_code != 200 or len(response.content) > 2_000_000:
        return None
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return None
    entry = root.find(f"{ATOM}entry")
    title = _clean(entry.findtext(f"{ATOM}title")) if entry is not None else None
    if entry is None or not title or title.lower() == "error":
        return None
    published = entry.findtext(f"{ATOM}published") or ""
    doi = entry.findtext("{http://arxiv.org/schemas/atom}doi")
    return {
        "title": title,
        "authors": [_clean(author.findtext(f"{ATOM}name")) for author in entry.findall(f"{ATOM}author") if _clean(author.findtext(f"{ATOM}name"))],
        "year": int(published[:4]) if published[:4].isdigit() else None,
        "venue": "arXiv preprint",
        "doi": doi,
        "arxiv_id": arxiv_id,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "abstract": _clean(entry.findtext(f"{ATOM}summary")),
    }


async def resolve_identifiers(identifiers: list[tuple[str, str]]) -> list[tuple[str, dict[str, Any] | None]]:
    """[(identifier, paper or None)] in the same order as given."""
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        results = await asyncio.gather(*[
            resolve_doi(client, value) if kind == "doi" else resolve_arxiv(client, value)
            for kind, value in identifiers
        ])
    return [(value, result) for (_, value), result in zip(identifiers, results)]
