import html
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class PackagedArtifact:
    format: str
    file_name: str
    storage_uri: str
    content_type: str
    byte_size: int


class WritingArtifactPackager:
    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or os.getenv("RESORA_EXPORT_DIR", "storage/exports"))

    def package(self, title: str, exports: dict[str, str]) -> list[PackagedArtifact]:
        job_id = f"writing-{uuid4().hex[:12]}"
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        packaged = []
        for export_format, content in exports.items():
            file_name = f"{self._slug(title)}.{self._extension_for(export_format)}"
            path = job_dir / file_name
            data = self._bytes_for(export_format, title, content)
            path.write_bytes(data)
            packaged.append(
                PackagedArtifact(
                    format=export_format,
                    file_name=file_name,
                    storage_uri=path.as_posix(),
                    content_type=self._content_type_for(export_format),
                    byte_size=len(data),
                )
            )
        return packaged

    def _bytes_for(self, export_format: str, title: str, content: str) -> bytes:
        if export_format == "docx":
            return self._docx_bytes(title, content)
        if export_format == "pdf":
            return self._pdf_bytes(title, content)
        return content.encode("utf-8")

    def _docx_bytes(self, title: str, content: str) -> bytes:
        temp_name = f"resora-docx-{uuid4().hex}.docx"
        temp_path = self.base_dir / temp_name
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        paragraphs = [title, *[line.strip() for line in content.splitlines() if line.strip()][:80]]
        paragraph_xml = "".join(f"<w:p><w:r><w:t>{html.escape(paragraph)}</w:t></w:r></w:p>" for paragraph in paragraphs)
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", self._docx_content_types())
            archive.writestr("_rels/.rels", self._docx_relationships())
            archive.writestr("word/document.xml", self._docx_document(paragraph_xml))
        data = temp_path.read_bytes()
        temp_path.unlink(missing_ok=True)
        return data

    def _pdf_bytes(self, title: str, content: str) -> bytes:
        safe_lines = [self._pdf_escape(title), *[self._pdf_escape(line.strip()) for line in content.splitlines() if line.strip()][:40]]
        text_commands = []
        y = 760
        for line in safe_lines:
            text_commands.append(f"BT /F1 10 Tf 50 {y} Td ({line[:95]}) Tj ET")
            y -= 16
            if y < 80:
                break
        stream = "\n".join(text_commands)
        objects = [
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
            "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
            f"5 0 obj << /Length {len(stream.encode('utf-8'))} >> stream\n{stream}\nendstream endobj",
        ]
        pdf = "%PDF-1.4\n"
        offsets = []
        for obj in objects:
            offsets.append(len(pdf.encode("utf-8")))
            pdf += obj + "\n"
        xref_start = len(pdf.encode("utf-8"))
        pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
        for offset in offsets:
            pdf += f"{offset:010d} 00000 n \n"
        pdf += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF"
        return pdf.encode("utf-8")

    def _docx_content_types(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        )

    def _docx_relationships(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        )

    def _docx_document(self, paragraph_xml: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{paragraph_xml}</w:body></w:document>"
        )

    def _slug(self, title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug[:80] or "resora-writing-export"

    def _pdf_escape(self, text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _extension_for(self, export_format: str) -> str:
        return {
            "markdown": "md",
            "latex": "tex",
            "overleaf_latex": "tex",
            "docx": "docx",
            "pdf": "pdf",
            "bibtex": "bib",
            "endnote": "enw",
            "ris": "ris",
        }.get(export_format, "txt")

    def _content_type_for(self, export_format: str) -> str:
        return {
            "markdown": "text/markdown",
            "latex": "application/x-tex",
            "overleaf_latex": "application/x-tex",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pdf": "application/pdf",
            "bibtex": "application/x-bibtex",
            "endnote": "application/x-endnote-refer",
            "ris": "application/x-research-info-systems",
        }.get(export_format, "text/plain")
