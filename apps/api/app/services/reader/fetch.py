"""Legal full-text acquisition for the Reader: the paper's own open-access PDF link, then Unpaywall, then arXiv.

Every hop is checked against the same SSRF rules as document extraction (https only, public addresses,
no login/captcha walls, blocked sites), the body must be a real PDF, and size is capped.
"""

from __future__ import annotations

import os
import re
from urllib.parse import quote, urljoin

import httpx

from app.core.config import settings

MAX_PDF_BYTES = int(os.getenv("READER_MAX_PDF_MB", "40")) * 1024 * 1024
ARXIV_ID = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
DOI = re.compile(r"(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)
USER_AGENT = "Resora/1.0 (research reader; open-access full text only)"


class FetchFailed(RuntimeError):
    pass


def _guard():
    from app.services.documents.pdf_extraction import DocumentExtractionService

    return DocumentExtractionService()


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    match = DOI.search(value)
    return match.group(1).rstrip(".,;)").lower() if match else None


def arxiv_id(*values: str | None) -> str | None:
    for value in values:
        if value:
            match = ARXIV_ID.search(value)
            if match:
                return match.group(1)
    return None


async def download_pdf(url: str, *, client: httpx.AsyncClient | None = None) -> bytes:
    guard = _guard()
    if guard._preflight_source_url(url):
        raise FetchFailed("blocked")
    current = guard._normalize_source_url(url)
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=False)
    try:
        for _ in range(6):
            async with client.stream("GET", current, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf"}) as response:
                if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
                    nxt = urljoin(current, response.headers["location"])
                    if guard._preflight_source_url(nxt):
                        raise FetchFailed("blocked redirect")
                    current = guard._normalize_source_url(nxt)
                    continue
                if response.status_code != 200:
                    raise FetchFailed(f"status {response.status_code}")
                declared = int(response.headers.get("content-length") or 0)
                if declared > MAX_PDF_BYTES:
                    raise FetchFailed("too large")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_PDF_BYTES:
                        raise FetchFailed("too large")
                data = bytes(body)
                if not data.startswith(b"%PDF"):
                    raise FetchFailed("not a pdf")
                return data
        raise FetchFailed("too many redirects")
    except httpx.HTTPError as error:
        raise FetchFailed(error.__class__.__name__) from error
    finally:
        if own_client:
            await client.aclose()


async def unpaywall_pdf_url(doi: str, *, client: httpx.AsyncClient | None = None) -> str | None:
    email = os.getenv("UNPAYWALL_EMAIL") or getattr(settings, "unpaywall_email", "")
    if not email or email.endswith(("example.com", ".local")):
        return None  # Unpaywall requires a real contact address
    base = getattr(settings, "unpaywall_base_url", "https://api.unpaywall.org/v2").rstrip("/")
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=15)
    try:
        response = await client.get(f"{base}/{quote(doi)}", params={"email": email})
        if response.status_code != 200:
            return None
        payload = response.json()
        locations = [payload.get("best_oa_location") or {}, *(payload.get("oa_locations") or [])]
        for location in locations:
            link = (location or {}).get("url_for_pdf")
            if link and link.startswith("https://"):
                return link
        return None
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if own_client:
            await client.aclose()


async def find_open_pdf(*, pdf_url: str | None, doi: str | None, url: str | None, link: str | None = None) -> bytes | None:
    """Try every legal source in order; None when no open-access PDF can be found."""
    candidates: list[str] = []
    for value in (pdf_url, link):
        if value and value.startswith("https://"):
            candidates.append(value)
    identifier = arxiv_id(pdf_url, url, link, doi)
    if identifier:
        candidates.append(f"https://export.arxiv.org/pdf/{identifier}")
    clean_doi = normalize_doi(doi) or normalize_doi(link)
    if clean_doi:
        found = await unpaywall_pdf_url(clean_doi)
        if found:
            candidates.append(found)
    for candidate in dict.fromkeys(candidates):
        try:
            return await download_pdf(candidate)
        except FetchFailed:
            continue
    return None
