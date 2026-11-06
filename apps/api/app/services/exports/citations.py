import json

from app.schemas.export import CitationExportRequest, CitationExportResponse


class CitationExportService:
    def export(self, payload: CitationExportRequest) -> CitationExportResponse:
        formatter = {
            "bibtex": self._to_bibtex,
            "ris": self._to_ris,
            "csljson": self._to_csljson,
        }[payload.format]
        content = formatter(payload)
        return CitationExportResponse(
            format=payload.format,
            content=content,
            item_count=len(payload.papers),
        )

    def _to_bibtex(self, payload: CitationExportRequest) -> str:
        entries = []
        for paper in payload.papers:
            key = self._citation_key(paper.title, paper.year)
            authors = " and ".join(author.get("name", "Unknown") for author in paper.authors) or "Unknown"
            entries.append(
                "\n".join(
                    [
                        f"@article{{{key},",
                        f"  title = {{{paper.title}}},",
                        f"  author = {{{authors}}},",
                        f"  journal = {{{paper.venue or 'Unknown Venue'}}},",
                        f"  year = {{{paper.year or ''}}},",
                        f"  doi = {{{paper.doi or ''}}},",
                        f"  url = {{{paper.url or ''}}}",
                        "}",
                    ]
                )
            )
        return "\n\n".join(entries)

    def _to_ris(self, payload: CitationExportRequest) -> str:
        records = []
        for paper in payload.papers:
            lines = [
                "TY  - JOUR",
                f"TI  - {paper.title}",
                *(f"AU  - {author.get('name', 'Unknown')}" for author in paper.authors),
                f"JO  - {paper.venue or 'Unknown Venue'}",
                f"PY  - {paper.year or ''}",
                f"DO  - {paper.doi or ''}",
                f"UR  - {paper.url or ''}",
                "ER  -",
            ]
            records.append("\n".join(lines))
        return "\n\n".join(records)

    def _to_csljson(self, payload: CitationExportRequest) -> str:
        items = []
        for paper in payload.papers:
            items.append(
                {
                    "id": paper.paper_id,
                    "type": "article-journal",
                    "title": paper.title,
                    "container-title": paper.venue,
                    "DOI": paper.doi,
                    "URL": paper.url,
                    "issued": {"date-parts": [[paper.year]]} if paper.year else None,
                    "author": [{"literal": author.get("name", "Unknown")} for author in paper.authors],
                }
            )
        return json.dumps(items, indent=2)

    def _citation_key(self, title: str, year: int | None) -> str:
        compact = "".join(character.lower() for character in title if character.isalnum())[:20]
        return f"{compact}{year or ''}"
