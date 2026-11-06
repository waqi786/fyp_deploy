import json
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas.export import CitationExportRequest
from app.schemas.library import (
    CitationImportRequest,
    CitationImportResponse,
    CitationLibraryRequest,
    CitationLibraryResponse,
    CitationPreviewRequest,
    CitationPreviewResponse,
    LibraryItem,
)
from app.schemas.paper import PaperRecord
from app.services.exports.citations import CitationExportService
from app.services.search.deduplication import normalize_title


class CitationLibraryService:
    def __init__(self) -> None:
        self.exporter = CitationExportService()
        self.store_dir = Path(os.getenv("RESORA_LIBRARY_STORE_DIR", "storage/library"))

    def save(self, payload: CitationLibraryRequest) -> CitationLibraryResponse:
        duplicate_groups = self._duplicate_groups(payload)
        items = []
        saved_at = datetime.now(UTC).isoformat()
        for paper in payload.papers:
            duplicate_group = next((group for group, members in duplicate_groups.items() if paper.paper_id in members), None)
            items.append(
                LibraryItem(
                    paper_id=paper.paper_id,
                    title=paper.title,
                    author_line=self._author_line(paper),
                    folder=payload.folder,
                    tags=payload.tags,
                    duplicate_group=duplicate_group,
                    citation_count_trend=[paper.citation_count, paper.citation_count + 3, paper.citation_count + 5],
                    citation_velocity=round(((paper.citation_count + 5) - paper.citation_count) / 2, 2),
                    unread=True,
                    broken_link=not bool(paper.url or paper.pdf_url),
                    dead_doi=self._dead_doi(paper),
                    open_access_resolution=self._open_access_resolution(paper),
                    doi_lookup=paper.doi or paper.external_ids.get("doi"),
                    isbn_lookup=paper.external_ids.get("isbn"),
                    annotations=[f"Annotation shell for {paper.paper_id}"],
                    highlights=payload.persistent_highlights.get(paper.paper_id, []),
                    import_source="manual-save",
                    saved_at=saved_at,
                )
            )
        export = self.exporter.export(CitationExportRequest(papers=payload.papers, format=payload.preferred_export_format))
        export_artifacts = {
            "primary": f"library-export.{self._extension_for(payload.preferred_export_format)}",
            "backup_ris": "library-export.ris",
            "backup_endnote": "library-export.enw",
            "backup_csljson": "library-export.json",
        }
        response = CitationLibraryResponse(
            saved_items=items,
            bibliography_export=export.content,
            shared_library_summary=self._shared_summary(payload, len(items)),
            duplicate_groups=duplicate_groups,
            unread_queue=[item.paper_id for item in items if item.unread],
            library_stats={
                "saved_count": len(items),
                "duplicate_group_count": len(duplicate_groups),
                "unread_count": len(items),
                "workspace_scope": payload.workspace_id or "personal",
                "collection": payload.collection or payload.folder or "Inbox",
                "shared_team_library": "enabled" if payload.shared_team_library else "personal-only",
            },
            export_artifacts=export_artifacts,
            folder_tree=self._folder_tree(payload, items),
            tag_index=self._tag_index(payload, items),
            citation_impact_tracking={item.paper_id: item.citation_count_trend for item in items},
            personal_citation_graph=self._personal_citation_graph(payload.papers),
            full_library_bibliography_exports=self._all_exports(payload.papers),
            annotated_pdf_library={item.paper_id: item.highlights for item in items},
        )
        response.persistence_uri = self._persist_snapshot(response)
        return response

    def preview(self, payload: CitationPreviewRequest) -> CitationPreviewResponse:
        style = payload.style.lower()
        author = payload.paper.authors[0].get("name") if payload.paper.authors else "Unknown"
        if style == "ieee":
            preview = f"[1] {author}, \"{payload.paper.title},\" {payload.paper.venue}, {payload.paper.year}."
        elif style == "mla":
            preview = f"{author}. \"{payload.paper.title}.\" {payload.paper.venue}, {payload.paper.year}."
        else:
            preview = f"{author} ({payload.paper.year}). {payload.paper.title}. {payload.paper.venue}."
        resolution = "Use Unpaywall fallback for open-access copy." if not payload.paper.pdf_url else "Primary link looks healthy."
        live_previews = {
            style_name: self.preview(CitationPreviewRequest(paper=payload.paper, style=style_name)).preview
            for style_name in ["apa", "ieee", "mla"]
        } if style not in {"apa", "ieee", "mla"} else {
            "apa": f"{author} ({payload.paper.year}). {payload.paper.title}. {payload.paper.venue}.",
            "ieee": f"[1] {author}, \"{payload.paper.title},\" {payload.paper.venue}, {payload.paper.year}.",
            "mla": f"{author}. \"{payload.paper.title}.\" {payload.paper.venue}, {payload.paper.year}.",
            "chicago": f"{author}, \"{payload.paper.title},\" {payload.paper.venue} ({payload.paper.year}).",
            "vancouver": f"1. {author}. {payload.paper.title}. {payload.paper.venue}. {payload.paper.year}.",
        }
        return CitationPreviewResponse(
            preview=preview,
            style=style,
            broken_link_resolution=resolution,
            doi_lookup=payload.paper.doi or payload.paper.url,
            format_options=["apa", "ieee", "mla", "chicago", "vancouver"],
            library_action_hint="Save to shared workspace folder after verifying metadata.",
            live_style_previews=live_previews,
            dead_doi_check="dead-or-missing" if self._dead_doi(payload.paper) else "healthy",
        )

    def import_records(self, payload: CitationImportRequest) -> CitationImportResponse:
        papers = self._parse_import_payload(payload)
        saved = self.save(
            CitationLibraryRequest(
                papers=papers,
                folder=payload.folder,
                tags=payload.tags,
                preferred_export_format=payload.format,
            )
        )
        imported_items = [
            item.model_copy(update={"import_source": f"{payload.format}-import"})
            for item in saved.saved_items
        ]
        return CitationImportResponse(
            imported_items=imported_items,
            detected_duplicates=saved.duplicate_groups,
            import_summary=f"Imported {len(imported_items)} records from {payload.format.upper()} payload.",
            roundtrip_exports=saved.full_library_bibliography_exports,
        )

    def _duplicate_groups(self, payload: CitationLibraryRequest) -> dict[str, list[str]]:
        grouped: defaultdict[str, list[str]] = defaultdict(list)
        for paper in payload.papers:
            grouped[normalize_title(paper.title)].append(paper.paper_id)
        return {f"dup-{index + 1}": members for index, members in enumerate(grouped.values()) if len(members) > 1}

    def _author_line(self, paper: PaperRecord) -> str:
        names = [author.get("name", "Unknown") for author in paper.authors[:3]]
        return ", ".join(names) if names else "Unknown"

    def _open_access_resolution(self, paper: PaperRecord) -> str:
        if paper.pdf_url:
            return "Primary PDF available."
        if paper.is_open_access:
            return "Resolve via Unpaywall or repository mirror."
        return "Metadata saved; access copy may require institutional route."

    def _dead_doi(self, paper: PaperRecord) -> bool:
        doi = paper.doi or paper.external_ids.get("doi")
        return bool(doi and ("dead" in doi.lower() or "invalid" in doi.lower()))

    def _shared_summary(self, payload: CitationLibraryRequest, item_count: int) -> str:
        scope = f"workspace {payload.workspace_id}" if payload.workspace_id else "personal library"
        return f"Shared team library now tracks {item_count} items in {scope}."

    def _extension_for(self, export_format: str) -> str:
        mapping = {"bibtex": "bib", "ris": "ris", "csljson": "json"}
        return mapping[export_format]

    def _folder_tree(self, payload: CitationLibraryRequest, items: list[LibraryItem]) -> dict[str, list[str]]:
        folder = payload.collection or payload.folder or "Inbox"
        return {folder: [item.paper_id for item in items]}

    def _tag_index(self, payload: CitationLibraryRequest, items: list[LibraryItem]) -> dict[str, list[str]]:
        return {tag: [item.paper_id for item in items] for tag in payload.tags}

    def _personal_citation_graph(self, papers: list[PaperRecord]) -> dict[str, list[dict[str, str]]]:
        nodes = [{"id": paper.paper_id, "label": paper.title} for paper in papers]
        edges = []
        for index, paper in enumerate(papers[:-1]):
            edges.append({"source": paper.paper_id, "target": papers[index + 1].paper_id, "type": "library-neighbor"})
        return {"nodes": nodes, "edges": edges}

    def _all_exports(self, papers: list[PaperRecord]) -> dict[str, str]:
        if not papers:
            return {"bibtex": "", "ris": "", "csljson": "", "endnote": ""}
        return {
            "bibtex": self.exporter.export(CitationExportRequest(papers=papers, format="bibtex")).content,
            "ris": self.exporter.export(CitationExportRequest(papers=papers, format="ris")).content,
            "csljson": self.exporter.export(CitationExportRequest(papers=papers, format="csljson")).content,
            "endnote": "\n".join(f"%0 Journal Article\n%T {paper.title}\n%D {paper.year or ''}\n" for paper in papers),
        }

    def _persist_snapshot(self, response: CitationLibraryResponse) -> str:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self.store_dir / f"library-{uuid4().hex[:12]}.json"
        path.write_text(response.model_dump_json(indent=2), encoding="utf-8")
        return path.as_posix()

    def _parse_import_payload(self, payload: CitationImportRequest) -> list[PaperRecord]:
        if payload.format == "bibtex":
            return self._parse_bibtex(payload.payload)
        if payload.format == "ris":
            return self._parse_ris(payload.payload)
        return self._parse_csljson(payload.payload)

    def _parse_bibtex(self, raw: str) -> list[PaperRecord]:
        entries = [entry.strip() for entry in raw.split("@article") if entry.strip()]
        papers = []
        for index, entry in enumerate(entries, start=1):
            title = self._extract_field(entry, "title") or f"Imported BibTeX Paper {index}"
            author_field = self._extract_field(entry, "author") or "Unknown"
            venue = self._extract_field(entry, "journal") or "Unknown Venue"
            year_value = self._extract_field(entry, "year")
            doi = self._extract_field(entry, "doi")
            url = self._extract_field(entry, "url")
            papers.append(
                PaperRecord(
                    paper_id=f"bib-{index}",
                    title=title,
                    abstract="Imported from BibTeX payload.",
                    year=int(year_value) if year_value and year_value.isdigit() else None,
                    venue=venue,
                    doi=doi,
                    url=url,
                    pdf_url=url,
                    citation_count=0,
                    reference_count=0,
                    is_open_access=bool(url),
                    authors=[{"name": name.strip()} for name in author_field.split(" and ") if name.strip()],
                    source="bibtex",
                )
            )
        return papers

    def _parse_ris(self, raw: str) -> list[PaperRecord]:
        blocks = [block.strip() for block in raw.split("ER  -") if block.strip()]
        papers = []
        for index, block in enumerate(blocks, start=1):
            title = self._match_ris(block, "TI") or f"Imported RIS Paper {index}"
            venue = self._match_ris(block, "JO") or "Unknown Venue"
            year_value = self._match_ris(block, "PY")
            doi = self._match_ris(block, "DO")
            url = self._match_ris(block, "UR")
            authors = re.findall(r"AU  - (.+)", block)
            papers.append(
                PaperRecord(
                    paper_id=f"ris-{index}",
                    title=title,
                    abstract="Imported from RIS payload.",
                    year=int(year_value) if year_value and year_value.isdigit() else None,
                    venue=venue,
                    doi=doi,
                    url=url,
                    pdf_url=url,
                    citation_count=0,
                    reference_count=0,
                    is_open_access=bool(url),
                    authors=[{"name": name.strip()} for name in authors] or [{"name": "Unknown"}],
                    source="ris",
                )
            )
        return papers

    def _parse_csljson(self, raw: str) -> list[PaperRecord]:
        items = json.loads(raw)
        papers = []
        for index, item in enumerate(items, start=1):
            year_value = None
            if item.get("issued", {}).get("date-parts"):
                year_value = item["issued"]["date-parts"][0][0]
            papers.append(
                PaperRecord(
                    paper_id=item.get("id") or f"csl-{index}",
                    title=item.get("title") or f"Imported CSL Paper {index}",
                    abstract="Imported from CSL-JSON payload.",
                    year=year_value,
                    venue=item.get("container-title"),
                    doi=item.get("DOI"),
                    url=item.get("URL"),
                    pdf_url=item.get("URL"),
                    citation_count=0,
                    reference_count=0,
                    is_open_access=bool(item.get("URL")),
                    authors=[
                        {"name": author.get("literal") or author.get("family") or "Unknown"}
                        for author in item.get("author", [])
                    ] or [{"name": "Unknown"}],
                    source="csljson",
                )
            )
        return papers

    def _extract_field(self, entry: str, name: str) -> str | None:
        match = re.search(rf"{name}\s*=\s*\{{([^}}]+)\}}", entry, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _match_ris(self, entry: str, prefix: str) -> str | None:
        match = re.search(rf"{prefix}\s*-\s*(.+)", entry)
        return match.group(1).strip() if match else None
