import asyncio
import html
import os
import ipaddress
import re
import socket
import hashlib
from collections import OrderedDict
from difflib import SequenceMatcher
from urllib.parse import quote, urljoin, urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.deps import AuthContext, get_auth_context
from app.core.config import settings
from app.schemas.comparison import ComparisonRequest, ComparisonResponse, PaperProfile
from app.schemas.paper import PaperRecord
from app.services.comparison.engine import ComparisonEngine
from app.services.documents.pdf_extraction import DocumentExtractionService
from app.services.comparison.uploads.repository import ComparisonPdfRepository
from app.services.comparison.insights_repository import ComparisonInsightsRepository
from app.services.comparison.saved_repository import ComparisonSavedRepository


router = APIRouter()
engine = ComparisonEngine()
document_extractor = DocumentExtractionService()
pdf_fetch_slots = asyncio.Semaphore(6)


async def _unpaywall_locations(paper: PaperRecord) -> list[str]:
    doi_value = paper.doi or next((value for key, value in paper.external_ids.items() if key.casefold() == "doi"), None)
    if not doi_value:
        return []
    doi = doi_value.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    try:
        async with httpx.AsyncClient(
            timeout=5,
            follow_redirects=False,
            headers={"User-Agent": f"Resora/0.1 (mailto:{settings.unpaywall_email})"},
        ) as client:
            response = await client.get(f"{settings.unpaywall_base_url}/{doi}", params={"email": settings.unpaywall_email})
            if response.status_code != 200:
                return []
            record = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    if not isinstance(record, dict) or record.get("is_oa") is not True:
        return []
    locations = [record.get("best_oa_location"), *(record.get("oa_locations") or [])]
    return list(dict.fromkeys(
        url
        for location in locations
        if isinstance(location, dict)
        for url in (location.get("url_for_pdf"), location.get("url_for_landing_page"))
        if isinstance(url, str) and url.startswith("https://")
    ))


async def _openalex_oa_locations(paper: PaperRecord) -> list[str]:
    doi_value = paper.doi or next((value for key, value in paper.external_ids.items() if key.casefold() == "doi"), None)
    if not doi_value:
        return []
    doi = doi_value.removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip()
    if not doi:
        return []
    work_url = f"{settings.openalex_base_url}/works/https://doi.org/{quote(doi, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=False, headers={"User-Agent": "Resora/0.1 (scholarly full-text discovery)"}) as client:
            response = await client.get(work_url)
            if response.status_code != 200:
                return []
            record = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    if not isinstance(record, dict):
        return []
    locations = record.get("locations") or []
    primary = record.get("primary_location")
    if isinstance(primary, dict):
        locations = [primary, *locations]
    return list(dict.fromkeys(
        url
        for location in locations
        if isinstance(location, dict) and location.get("is_oa") is True
        for url in (location.get("pdf_url"), location.get("landing_page_url"))
        if isinstance(url, str) and url.startswith("https://")
    ))


def _doi_url(paper: PaperRecord) -> str | None:
    doi = paper.doi or next((value for key, value in paper.external_ids.items() if key.casefold() == "doi"), None)
    if not doi:
        return None
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").strip()
    return f"https://doi.org/{doi}" if doi else None


async def _publisher_pdf_links(source_url: str) -> list[str]:
    """Resolve explicit publisher PDF/full-text links from a paper landing page."""
    if not await asyncio.to_thread(_public_https_url, source_url):
        return []
    try:
        async with httpx.AsyncClient(timeout=7, follow_redirects=False, headers={"User-Agent": "Resora/0.1 (research paper text extraction)"}) as client:
            current_url = source_url
            response = None
            for _ in range(5):
                response = await client.get(current_url)
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("location")
                if not location:
                    return []
                current_url = urljoin(current_url, location)
                if not await asyncio.to_thread(_public_https_url, current_url):
                    return []
            if response is None or response.status_code != 200 or "html" not in response.headers.get("content-type", "").lower():
                return []
            if len(response.content) > 5_000_000:
                return []
            page = response.content.decode(response.encoding or "utf-8", errors="ignore")
    except (httpx.HTTPError, UnicodeError):
        return []

    links: list[str] = []
    for tag in re.findall(r"(?is)<(?:meta|link)\b[^>]*>", page):
        attrs = {key.lower(): html.unescape(value) for key, value in re.findall(r"([\w:-]+)\s*=\s*['\"]([^'\"]*)['\"]", tag)}
        hint = " ".join((attrs.get("name", ""), attrs.get("property", ""), attrs.get("rel", ""), attrs.get("type", ""))).casefold()
        target = attrs.get("content") or attrs.get("href")
        if target and ("citation_pdf_url" in hint or "application/pdf" in hint or "citation_fulltext_html_url" in hint):
            links.append(urljoin(current_url, target))
    for tag in re.findall(r"(?is)<a\b[^>]*>", page):
        attrs = {key.lower(): html.unescape(value) for key, value in re.findall(r"([\w:-]+)\s*=\s*['\"]([^'\"]*)['\"]", tag)}
        target = attrs.get("href")
        label = " ".join((attrs.get("title", ""), attrs.get("data-track", ""), re.sub(r"<[^>]+>", " ", tag))).casefold()
        if target and (re.search(r"\.pdf(?:$|[?#])", target, re.IGNORECASE) or ("full text" in label and "download" in label)):
            links.append(urljoin(current_url, target))
    return list(dict.fromkeys(link for link in links if link.startswith("https://")))[:8]


def _is_full_html_paper(text: str) -> bool:
    if len(text) < 3_000:
        return False
    section_count = sum(bool(re.search(pattern, text, re.IGNORECASE)) for pattern in (
        r"\bintroduction\b", r"\b(?:materials and methods|methodology|methods)\b", r"\bresults\b",
        r"\bdiscussion\b", r"\bconclusion\b",
    ))
    return section_count >= 2


def _title_matches_paper(title: str, text: str) -> bool:
    title_words = re.findall(r"[a-z0-9]+", title.casefold())
    if len(title_words) < 3:
        return True
    opening = " ".join(re.findall(r"[a-z0-9]+", text[:12_000].casefold()))
    exact_title = " ".join(title_words)
    if exact_title in opening:
        return True
    present = sum(word in opening for word in title_words)
    token_coverage = present / len(title_words)
    short_excerpt_score = SequenceMatcher(None, exact_title, opening[: len(exact_title) + 80]).ratio()
    return token_coverage >= 0.65 or short_excerpt_score >= 0.72


def _public_https_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        hostname = parsed.hostname.rstrip(".")
        try:
            addresses = [ipaddress.ip_address(hostname)]
        except ValueError:
            addresses = [ipaddress.ip_address(result[4][0]) for result in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)]
        return bool(addresses) and all(address.is_global for address in addresses)
    except (OSError, ValueError):
        return False


async def _load_full_text(
    paper: PaperRecord,
    *,
    resolve_unpaywall: bool = True,
    resolve_openalex: bool = True,
    source_urls: list[str] | None = None,
) -> PaperRecord:
    if paper.full_text and paper.full_text.strip():
        return paper.model_copy(update={"full_text_status": "provided"})
    urls = list(dict.fromkeys(source_urls if source_urls is not None else [url for url in [paper.pdf_url, *paper.pdf_urls, paper.url, _doi_url(paper)] if url]))
    saw_safe_url = False
    saw_metadata_mismatch = False
    async with pdf_fetch_slots:
        index = 0
        while index < min(len(urls), 12):
            url = urls[index]
            index += 1
            if not await asyncio.to_thread(_public_https_url, url):
                continue
            saw_safe_url = True
            try:
                extraction = await asyncio.wait_for(document_extractor.extract(source_url=url), timeout=9)
            except Exception:
                extraction = None
            is_document_text = bool(extraction and extraction.extraction_method in {"pymupdf", "pymupdf+tesseract-ocr", "html-page"})
            text = extraction.extracted_text.strip() if extraction else ""
            full_text_candidate = bool(
                extraction and extraction.status == "ok" and is_document_text and len(text) >= 800
                and (extraction.extraction_method != "html-page" or _is_full_html_paper(text))
            )
            if full_text_candidate:
                if not _title_matches_paper(paper.title, text):
                    saw_metadata_mismatch = True
                elif len(text) > 1_500_000:
                    return paper.model_copy(update={"full_text_status": "too_long"})
                else:
                    if text[:len(paper.title)].casefold() == paper.title.casefold():
                        text = text[len(paper.title):].lstrip(" \t\r\n:—–-.")
                    normalized_source_url = getattr(extraction, "normalized_source_url", None)
                    source = normalized_source_url or url
                    return paper.model_copy(update={"full_text": text, "full_text_status": "extracted", "full_text_source": urlsplit(source).hostname, "full_text_source_url": source})
            # Publisher landing pages often expose a canonical PDF URL in citation metadata.
            # Follow only links explicitly identified as full text/PDF by that source.
            if "pdf" not in urlsplit(url).path.casefold() and index < 12:
                discovered = await _publisher_pdf_links(url)
                urls.extend(candidate for candidate in discovered if candidate not in urls)
    doi = paper.doi or next((value for key, value in paper.external_ids.items() if key.casefold() == "doi"), None)
    if doi and resolve_openalex:
        repository_urls = [url for url in await _openalex_oa_locations(paper) if url not in urls]
        if repository_urls:
            repository_copy = await _load_full_text(paper, resolve_unpaywall=False, resolve_openalex=False, source_urls=repository_urls)
            if repository_copy.full_text:
                return repository_copy
    if doi and resolve_unpaywall:
        fallback_urls = [url for url in await _unpaywall_locations(paper) if url not in urls]
        if fallback_urls:
            return await _load_full_text(paper, resolve_unpaywall=False, resolve_openalex=False, source_urls=fallback_urls)
    if saw_metadata_mismatch:
        status = "metadata_mismatch"
    elif saw_safe_url:
        status = "unavailable"
    elif urls:
        status = "blocked"
    elif paper.pdf_url and not paper.is_open_access:
        status = "not_open_access"
    else:
        status = "no_pdf"
    return paper.model_copy(update={"full_text_status": status})


@router.post("/", response_model=ComparisonResponse)
async def compare_papers(payload: ComparisonRequest) -> ComparisonResponse:
    papers = await asyncio.gather(*(_load_full_text(paper) for paper in payload.papers))
    return engine.compare(payload.model_copy(update={"papers": papers}))


def _comparison_owner(auth: AuthContext) -> str:
    if (settings.deployment_stage.lower() == "production" and not auth.verified) or not auth.user_id or auth.user_id == "anonymous":
        raise HTTPException(status_code=401, detail="Sign in to save and compare private PDFs.")
    return auth.user_id


@router.get("/pdfs")
async def list_comparison_pdfs(comparison_id: str = Query(...), auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner_id = _comparison_owner(auth)
    try:
        normalized_id = str(UUID(comparison_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid comparison ID.") from exc
    return {"comparison_id": normalized_id, "files": ComparisonPdfRepository.list(owner_id=owner_id, comparison_id=normalized_id)}


@router.get("/pdfs/limits")
async def comparison_pdf_limits() -> dict[str, int]:
    return {"max_files": 15, "max_bytes": int(os.getenv("COMPARISON_MAX_PDF_BYTES", str(50 * 1024 * 1024))), "max_pages": int(os.getenv("COMPARISON_MAX_PDF_PAGES", "120"))}


@router.post("/pdfs/upload")
async def upload_comparison_pdfs(
    files: list[UploadFile] = File(...),
    comparison_id: str | None = Form(default=None),
    auth: AuthContext = Depends(get_auth_context),
) -> dict:
    owner_id = _comparison_owner(auth)
    if not 1 <= len(files) <= 15:
        raise HTTPException(status_code=400, detail="Upload between 1 and 15 PDFs.")
    try:
        normalized_id = str(UUID(comparison_id)) if comparison_id else str(UUID(int=0))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid comparison ID.") from exc

    max_bytes = int(os.getenv("COMPARISON_MAX_PDF_BYTES", str(50 * 1024 * 1024)))
    max_pages = int(os.getenv("COMPARISON_MAX_PDF_PAGES", "120"))
    current = ComparisonPdfRepository.list(owner_id=owner_id, comparison_id=normalized_id) if comparison_id else []
    if len(current) + len(files) > 15:
        raise HTTPException(status_code=400, detail="A comparison can contain up to 15 PDFs.")
    added = []
    seen_hashes = {item["sha256"] for item in current}
    for upload in files:
        supplied_name = re.split(r"[/\\]", upload.filename or "paper.pdf")[-1]
        filename = re.sub(r"[^\w. ()-]", "_", supplied_name, flags=re.UNICODE).strip(" .")[:180] or "paper.pdf"
        data = await upload.read(max_bytes + 1)
        if upload.content_type not in {"application/pdf", "application/octet-stream", None} and data.startswith(b"%PDF-") and len(data) <= max_bytes:
            raise HTTPException(status_code=415, detail=f"{filename}: upload a PDF file.")
        added.append(_validate_and_store_pdf(owner_id=owner_id, comparison_id=normalized_id, filename=filename, data=data, seen_hashes=seen_hashes, max_bytes=max_bytes, max_pages=max_pages))
    return {"comparison_id": normalized_id, "files": added, "stored_notice": "PDFs are stored privately for your comparisons. Remove them to delete the stored files."}


def _validate_and_store_pdf(*, owner_id: str, comparison_id: str, filename: str, data: bytes, seen_hashes: set[str], max_bytes: int, max_pages: int) -> dict:
    """Validate one PDF exactly like an upload (size, PDF header, password, pages, readable text) and store it.

    Shared by uploads and by papers added from Search/Reader, so both paths produce identical stored files.
    Raises HTTPException with the same messages as before.
    """
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"{filename}: file exceeds the configured {max_bytes // (1024 * 1024)} MB limit.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail=f"{filename}: this file is not a valid PDF.")
    try:
        import fitz
        document = fitz.open(stream=data, filetype="pdf")
        if document.is_encrypted:
            document.close()
            raise HTTPException(status_code=422, detail=f"{filename}: remove the PDF password, then upload it again.")
        pages = len(document)
        if pages < 1 or pages > max_pages:
            document.close()
            raise HTTPException(status_code=422, detail=f"{filename}: PDF must contain 1 to {max_pages} pages.")
        document.close()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"{filename}: this PDF is damaged or cannot be read.") from exc
    import hashlib
    digest = hashlib.sha256(data).hexdigest()
    if digest in seen_hashes:
        raise HTTPException(status_code=409, detail=f"{filename}: this PDF is already in the comparison.")
    extracted = document_extractor._extract_from_bytes(data)
    if not extracted or extracted.status != "ok" or len(extracted.extracted_text.strip()) < 300:
        raise HTTPException(status_code=422, detail=f"{filename}: no readable paper text was found. Scanned PDFs need OCR support.")
    text_with_pages = _pdf_text_with_page_markers(data) or extracted.extracted_text
    saved = ComparisonPdfRepository.save(
        owner_id=owner_id,
        comparison_id=comparison_id,
        name=filename,
        data=data,
        page_count=pages,
        text=text_with_pages[:1_500_000],
        method=extracted.extraction_method,
        parsed_tables=[table.model_dump(mode="json") for table in extracted.tables],
    )
    seen_hashes.add(digest)
    return saved


class _AddPaper(BaseModel):
    key: str = Field(min_length=1, max_length=300)
    paper_id: str | None = Field(default=None, max_length=300)
    title: str = Field(min_length=1, max_length=600)
    abstract: str | None = Field(default=None, max_length=12000)
    authors: list[str] = Field(default_factory=list, max_length=60)
    year: int | None = None
    venue: str | None = Field(default=None, max_length=300)
    doi: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=2000)
    pdf_url: str | None = Field(default=None, max_length=2000)
    is_open_access: bool = False
    citation_count: int = 0


class _AddPapersRequest(BaseModel):
    comparison_id: str | None = None
    papers: list[_AddPaper] = Field(min_length=1, max_length=15)


async def _open_pdf_for(paper: _AddPaper) -> tuple[bytes | None, str]:
    """Legal open-access PDF for a search result: its own PDF link, arXiv, OpenAlex and Unpaywall locations.

    Returns (pdf bytes or None, reason). Every download is SSRF-checked, size-capped and must be a real PDF.
    """
    from app.services.reader.fetch import FetchFailed, arxiv_id, download_pdf, normalize_doi

    record = PaperRecord(paper_id=paper.paper_id or paper.key, title=paper.title, doi=normalize_doi(paper.doi), url=paper.url, pdf_url=paper.pdf_url, source="search")
    candidates: list[str] = [url for url in (paper.pdf_url,) if url and url.startswith("https://")]
    identifier = arxiv_id(paper.pdf_url, paper.url, paper.doi)
    if identifier:
        candidates.append(f"https://export.arxiv.org/pdf/{identifier}")
    if record.doi:
        try:
            candidates.extend(await _openalex_oa_locations(record))
            candidates.extend(await _unpaywall_locations(record))
        except Exception:  # noqa: BLE001 - discovery is best effort
            pass
    mismatch = False
    async with pdf_fetch_slots:
        for url in list(dict.fromkeys(candidates))[:8]:
            try:
                data = await download_pdf(url)
            except FetchFailed:
                continue
            extracted = await asyncio.to_thread(document_extractor._extract_from_bytes, data)
            text = extracted.extracted_text if extracted else ""
            if text and not _title_matches_paper(paper.title, text):
                mismatch = True
                continue
            return data, "ok"
    return None, "mismatch" if mismatch else "no_open_pdf"


def _paper_page_url(paper: _AddPaper) -> str | None:
    candidate = (paper.url or "").strip()
    parsed = urlsplit(candidate) if candidate else None
    if parsed and parsed.scheme in {"https", "http"} and parsed.netloc:
        return candidate
    doi = (paper.doi or "").strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return f"https://doi.org/{quote(doi, safe='/')}" if doi else None


@router.post("/pdfs/add-papers")
async def add_papers_to_comparison(payload: _AddPapersRequest, auth: AuthContext = Depends(get_auth_context)) -> dict:
    """Add papers picked in Search or the Reader: fetch each legal open-access PDF and store it like an upload.

    Papers without a readable open-access PDF are returned in `unavailable` so the user can upload them.
    """
    owner_id = _comparison_owner(auth)
    try:
        normalized_id = str(UUID(payload.comparison_id)) if payload.comparison_id else str(uuid4())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid comparison ID.") from exc
    max_bytes = int(os.getenv("COMPARISON_MAX_PDF_BYTES", str(50 * 1024 * 1024)))
    max_pages = int(os.getenv("COMPARISON_MAX_PDF_PAGES", "120"))
    current = ComparisonPdfRepository.list(owner_id=owner_id, comparison_id=normalized_id)
    seen_hashes = {item["sha256"] for item in current}
    found = await asyncio.gather(*(_open_pdf_for(paper) for paper in payload.papers))
    added: list[dict] = []
    unavailable: list[dict[str, str]] = []
    for paper, (data, reason) in zip(payload.papers, found):
        if data is None:
            unavailable.append({"key": paper.key, "title": paper.title, "reason": reason, "publisher_url": _paper_page_url(paper)})
            continue
        if len(current) + len(added) >= 15:
            unavailable.append({"key": paper.key, "title": paper.title, "reason": "limit", "publisher_url": _paper_page_url(paper)})
            continue
        filename = (re.sub(r"[^\w. ()-]", "_", paper.title, flags=re.UNICODE).strip(" .")[:170] or "paper") + ".pdf"
        try:
            added.append(_validate_and_store_pdf(owner_id=owner_id, comparison_id=normalized_id, filename=filename, data=data, seen_hashes=seen_hashes, max_bytes=max_bytes, max_pages=max_pages))
        except HTTPException as error:
            unavailable.append({"key": paper.key, "title": paper.title, "reason": "duplicate" if error.status_code == 409 else "not_readable", "publisher_url": _paper_page_url(paper)})
    return {"comparison_id": normalized_id, "files": added, "unavailable": unavailable}


def _pdf_text_with_page_markers(data: bytes) -> str:
    """Preserve page coordinates for evidence when a PDF has a text layer."""
    try:
        import fitz
        document = fitz.open(stream=data, filetype="pdf")
        page_text = [page.get_text("text").strip() for page in document]
        document.close()
    except Exception:
        return ""
    if not page_text or sum(len(page) for page in page_text) < 300:
        return ""
    return "\n\n".join(f"[PDF page {index}]\n{text}" for index, text in enumerate(page_text, start=1) if text)


@router.post("/pdfs/run", response_model=ComparisonResponse)
async def compare_uploaded_pdfs(payload: dict, auth: AuthContext = Depends(get_auth_context)) -> ComparisonResponse:
    owner_id = _comparison_owner(auth)
    try:
        comparison_id = str(UUID(str(payload.get("comparison_id", ""))))
        file_ids = [str(UUID(str(value))) for value in payload.get("file_ids", [])]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid comparison or PDF ID.") from exc
    if not 2 <= len(file_ids) <= 15 or len(file_ids) != len(set(file_ids)):
        raise HTTPException(status_code=400, detail="Select between 2 and 15 unique PDFs to compare.")
    try:
        stored = ComparisonPdfRepository.load_papers(owner_id=owner_id, comparison_id=comparison_id, file_ids=file_ids)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    papers = [PaperRecord.model_validate(item) for item in stored]
    request = ComparisonRequest(
        papers=papers,
        focus=str(payload.get("focus") or "Compare uploaded research papers"),
        criterion=str(payload.get("focus") or "Compare uploaded research papers"),
        custom_columns=payload.get("custom_columns") or ["method", "dataset", "model", "metric", "result", "limitation", "reproducibility"],
    )
    # This endpoint intentionally never resolves publisher, DOI, search or abstract sources.
    stored_files = ComparisonPdfRepository.list(owner_id=owner_id, comparison_id=comparison_id)
    selected_hashes = [item["sha256"] for item in stored_files if item["id"] in set(file_ids)]
    cached = ComparisonInsightsRepository.load_cached_analysis(
        owner_id=owner_id,
        comparison_id=comparison_id,
        file_hashes=selected_hashes,
        columns=request.custom_columns,
        focus=request.focus,
    )
    cached_profiles = [PaperProfile.model_validate(item) for item in cached[1]] if cached else None
    response = engine.compare(request, cached_profiles=cached_profiles)
    if cached and cached[2]:
        response.insights_model = response.insights_model.model_validate(cached[2]) if response.insights_model else None
    response.insight_run_id, existed = ComparisonInsightsRepository.save_run(
        owner_id=owner_id,
        comparison_id=comparison_id,
        file_hashes=selected_hashes,
        columns=request.custom_columns,
        focus=request.focus,
        profiles=[item.model_dump(mode="json") for item in response.paper_profiles],
        insights_model=response.insights_model.model_dump(mode="json") if response.insights_model else None,
    )
    response.insights_cached = cached is not None or existed
    return response


@router.post("/pdfs/insights/{run_id}/feedback", status_code=204)
async def save_insight_feedback(run_id: str, payload: dict, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner_id = _comparison_owner(auth)
    if payload.get("value") not in {"useful", "not_useful"}:
        raise HTTPException(status_code=422, detail="Feedback must be useful or not_useful.")
    section_key = str(payload.get("section_key") or "")
    if not section_key or len(section_key) > 80:
        raise HTTPException(status_code=422, detail="A valid section key is required.")
    try:
        ComparisonInsightsRepository.save_feedback(owner_id=owner_id, run_id=run_id, section_key=section_key, value=payload["value"], note=str(payload.get("note") or "")[:1000])
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/pdfs/{comparison_id}/insights/{interaction_kind}")
async def save_insight_interaction(comparison_id: str, interaction_kind: str, payload: dict, auth: AuthContext = Depends(get_auth_context)) -> dict[str, str]:
    owner_id = _comparison_owner(auth)
    if interaction_kind not in {"consensus_questions", "claim_checks"}:
        raise HTTPException(status_code=404, detail="Insight action not found.")
    try:
        normalized_id = str(UUID(comparison_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid comparison ID.") from exc
    prompt_key = "question" if interaction_kind == "consensus_questions" else "claim"
    prompt = str(payload.get(prompt_key) or "").strip()
    result = payload.get("result")
    if not prompt or len(prompt) > 2000 or not isinstance(result, dict):
        raise HTTPException(status_code=422, detail=f"A {prompt_key} and structured result are required.")
    record_id = ComparisonInsightsRepository.save_interaction(kind=interaction_kind, owner_id=owner_id, comparison_id=normalized_id, prompt=prompt, result=result)
    return {"id": record_id}


# ---------- Saved comparisons (name, focus and columns; the PDFs stay in comparison_pdf_files) ----------

class _SaveComparisonRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    default_name: str | None = Field(default=None, max_length=400)
    focus: str | None = Field(default=None, max_length=300)
    columns: list[str] | None = Field(default=None, max_length=30)


def _comparison_uuid(comparison_id: str) -> str:
    try:
        return str(UUID(comparison_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid comparison ID.") from exc


@router.get("/pdfs/saved")
async def list_saved_comparisons(auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner_id = _comparison_owner(auth)
    return {"comparisons": await asyncio.to_thread(ComparisonSavedRepository.list, owner_id=owner_id)}


@router.put("/pdfs/saved/{comparison_id}")
async def save_comparison(comparison_id: str, payload: _SaveComparisonRequest, auth: AuthContext = Depends(get_auth_context)) -> dict:
    owner_id = _comparison_owner(auth)
    normalized_id = _comparison_uuid(comparison_id)
    if not await asyncio.to_thread(ComparisonSavedRepository.has_files, owner_id=owner_id, comparison_id=normalized_id):
        raise HTTPException(status_code=404, detail="Comparison not found.")
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(status_code=422, detail="A comparison name cannot be empty.")
    return await asyncio.to_thread(
        ComparisonSavedRepository.upsert,
        owner_id=owner_id, comparison_id=normalized_id, name=payload.name, default_name=payload.default_name, focus=payload.focus, columns=payload.columns,
    )


@router.delete("/pdfs/saved/{comparison_id}", status_code=204)
async def delete_saved_comparison(comparison_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner_id = _comparison_owner(auth)
    normalized_id = _comparison_uuid(comparison_id)
    await asyncio.to_thread(ComparisonSavedRepository.delete, owner_id=owner_id, comparison_id=normalized_id)
    return Response(status_code=204)


# ---------- Translating table content into the reader's language ----------

class _TranslateRequest(BaseModel):
    language: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    texts: list[str] = Field(min_length=1, max_length=300)


_TRANSLATION_CACHE: "OrderedDict[str, str]" = OrderedDict()
_TRANSLATION_CACHE_SIZE = 5000
MAX_TRANSLATE_CHARS = 2000
MAX_TRANSLATE_TOTAL = 60_000


def _cache_key(owner_id: str, language: str, text: str) -> str:
    return hashlib.sha256(f"{owner_id}\x00{language}\x00{text}".encode("utf-8")).hexdigest()


@router.post("/pdfs/{comparison_id}/translate")
async def translate_comparison_text(comparison_id: str, payload: _TranslateRequest, request: Request, auth: AuthContext = Depends(get_auth_context)) -> dict:
    """Machine-translate comparison values (from the owner's own PDFs). Private content: user_content=True, never logged."""
    owner_id = _comparison_owner(auth)
    normalized_id = _comparison_uuid(comparison_id)
    if not await asyncio.to_thread(ComparisonSavedRepository.has_files, owner_id=owner_id, comparison_id=normalized_id):
        raise HTTPException(status_code=404, detail="Comparison not found.")
    texts = [str(item) for item in payload.texts]
    if any(len(item) > MAX_TRANSLATE_CHARS for item in texts) or sum(len(item) for item in texts) > MAX_TRANSLATE_TOTAL:
        raise HTTPException(status_code=413, detail={"code": "too_long"})
    keys = [_cache_key(owner_id, payload.language, item) for item in texts]
    missing = list(dict.fromkeys(text for text, key in zip(texts, keys) if text.strip() and key not in _TRANSLATION_CACHE))
    used = 0
    if missing:
        from app.api.v1.endpoints.reader import _limit, _plan, _viewer_key
        from app.services.credits.service import CreditLimitReached, get_credit_service
        from app.services.search.translation import translate_batch

        credits = get_credit_service()
        try:
            reservation = credits.reserve(_viewer_key(auth, request), "translate_pages", amount=max(1, credits.cost("translate_pages")), plan=_plan(auth))
        except CreditLimitReached as error:
            raise _limit(error) from error
        try:
            results = await asyncio.to_thread(translate_batch, missing, payload.language, source_language="auto", user_content=True)
            if len(results) != len(missing) or any(not isinstance(item, str) or not item.strip() for item in results):
                raise ValueError("incomplete translation")
        except Exception as error:  # noqa: BLE001 - provider failures become one stable code
            credits.refund(reservation)
            raise HTTPException(status_code=503, detail={"code": "translation_unavailable"}) from error
        used = max(1, credits.cost("translate_pages"))
        credits.commit(reservation, used)
        for text, translated in zip(missing, results):
            _TRANSLATION_CACHE[_cache_key(owner_id, payload.language, text)] = translated
            _TRANSLATION_CACHE.move_to_end(_cache_key(owner_id, payload.language, text))
        while len(_TRANSLATION_CACHE) > _TRANSLATION_CACHE_SIZE:
            _TRANSLATION_CACHE.popitem(last=False)
    return {"translations": [_TRANSLATION_CACHE.get(key, text) if text.strip() else text for text, key in zip(texts, keys)], "credits_used": used}


@router.get("/pdfs/{file_id}")
async def read_comparison_pdf(file_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner_id = _comparison_owner(auth)
    try:
        normalized_id = str(UUID(file_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="PDF not found.") from exc
    stored = ComparisonPdfRepository.read_pdf(owner_id=owner_id, file_id=normalized_id)
    if not stored:
        raise HTTPException(status_code=404, detail="PDF not found.")
    safe_filename = re.sub(r"[^\w. ()-]", "_", stored[0], flags=re.UNICODE).strip(" .")[:180] or "paper.pdf"
    return Response(content=stored[1], media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{safe_filename}"', "Cache-Control": "private, no-store"})


@router.delete("/pdfs/{file_id}", status_code=204)
async def delete_comparison_pdf(file_id: str, auth: AuthContext = Depends(get_auth_context)) -> Response:
    owner_id = _comparison_owner(auth)
    try:
        normalized_id = str(UUID(file_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="PDF not found.") from exc
    if not ComparisonPdfRepository.delete(owner_id=owner_id, file_id=normalized_id):
        raise HTTPException(status_code=404, detail="PDF not found.")
    return Response(status_code=204)
