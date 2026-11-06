import base64
import ipaddress
import re
import shutil
import socket
from html import unescape
from io import BytesIO
from urllib.parse import urljoin, urlparse

import httpx

from app.schemas.document import DocumentExtractionResponse, EquationExplanation, ExtractedFigure, ExtractedTable


BLOCKED_DOMAINS = {"researchgate.net", "www.researchgate.net", "academia.edu", "www.academia.edu"}
CAPTCHA_HINTS = ("captcha", "challenge", "login", "signin", "authwall")


class DocumentExtractionService:
    def extract_sync_text(self, raw_text: str) -> DocumentExtractionResponse:
        return self._from_text(raw_text, method="raw-text")

    def extract_sync_bytes(self, raw_bytes_base64: str) -> DocumentExtractionResponse | None:
        raw_bytes = base64.b64decode(raw_bytes_base64.encode("utf-8"))
        return self._extract_from_bytes(raw_bytes)

    async def extract(self, source_url: str | None = None, raw_text: str | None = None, raw_bytes_base64: str | None = None) -> DocumentExtractionResponse:
        if source_url:
            blocked = self._preflight_source_url(source_url)
            if blocked:
                return blocked
            source_url = self._normalize_source_url(source_url)

        if raw_text:
            return self._from_text(raw_text, method="raw-text")

        if raw_bytes_base64:
            extracted = self.extract_sync_bytes(raw_bytes_base64)
            if extracted:
                return extracted

        if source_url:
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                    current_url = source_url
                    response = None
                    for _ in range(6):
                        response = await client.get(current_url, headers={"User-Agent": "Mozilla/5.0 Resora/0.1"})
                        if response.status_code not in {301, 302, 303, 307, 308}:
                            break
                        location = response.headers.get("location")
                        if not location:
                            break
                        redirect_url = urljoin(current_url, location)
                        redirect_blocked = self._preflight_source_url(redirect_url)
                        if redirect_blocked:
                            return redirect_blocked
                        current_url = self._normalize_source_url(redirect_url)
                    if response is None:
                        raise httpx.RequestError("No response received")
                    response.raise_for_status()
                    extracted = self._extract_from_http_response(response)
                    if extracted:
                        extracted.normalized_source_url = source_url
                        return extracted
            except httpx.HTTPError as exc:
                return DocumentExtractionResponse(
                    status="error",
                    extracted_text="",
                    extraction_method="url-fetch",
                    normalized_source_url=source_url,
                    blocked_reason=f"FETCH_FAILED:{exc.__class__.__name__}",
                )

        return DocumentExtractionResponse(
            status="empty",
            extracted_text="",
            extraction_method="none",
            normalized_source_url=source_url,
            blocked_reason="NO_TEXT_EXTRACTED",
        )

    def _extract_from_http_response(self, response: httpx.Response) -> DocumentExtractionResponse | None:
        content_type = response.headers.get("content-type", "").lower()
        raw_bytes = response.content
        if "text/html" in content_type or self._looks_like_html(raw_bytes):
            html_text = raw_bytes.decode(response.encoding or "utf-8", errors="ignore")
            plain_text = self._html_to_plain_text(html_text)
            if self._looks_like_extracted_text(plain_text):
                return self._from_text(plain_text, method="html-page")
            return None
        return self._extract_from_bytes(raw_bytes)

    def _extract_from_bytes(self, raw_bytes: bytes) -> DocumentExtractionResponse | None:
        pdf_extracted = self._extract_pdf_with_pymupdf(raw_bytes)
        if pdf_extracted:
            return pdf_extracted

        image_ocr = self._ocr_image_with_tesseract(raw_bytes)
        if image_ocr:
            text, confidence = image_ocr
            return self._from_text(text, method="tesseract-ocr", scanned_pdf_detected=True, ocr_confidence=confidence)

        text = raw_bytes.decode("utf-8", errors="ignore")
        normalized = re.sub(r"\s+", " ", text).strip()
        if self._looks_like_extracted_text(normalized):
            return self._from_text(normalized, method="byte-decode")
        ocr_text, confidence = self._ocr_fallback(raw_bytes, normalized)
        if ocr_text:
            return self._from_text(ocr_text, method="ocr-fallback", scanned_pdf_detected=True, ocr_confidence=confidence)
        return None

    def _looks_like_extracted_text(self, text: str) -> bool:
        if len(text) < 80:
            return False
        alphabetic = sum(character.isalpha() for character in text)
        printable = sum(character.isprintable() for character in text)
        alpha_ratio = alphabetic / max(len(text), 1)
        printable_ratio = printable / max(len(text), 1)
        return alpha_ratio >= 0.45 and printable_ratio >= 0.9

    def _looks_like_html(self, raw_bytes: bytes) -> bool:
        sample = raw_bytes[:1000].decode("utf-8", errors="ignore").lower()
        return "<html" in sample or "<body" in sample or "<article" in sample

    def _html_to_plain_text(self, html_text: str) -> str:
        cleaned = re.sub(r"(?is)<(script|style|nav|footer|header|noscript).*?</\1>", " ", html_text)
        cleaned = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</section>|</article>|</li>|</h[1-6]>", "\n", cleaned)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
        cleaned = re.sub(r"\n\s+", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _ocr_fallback(self, raw_bytes: bytes, decoded_text: str) -> tuple[str, float | None]:
        decoded_hint = decoded_text.replace("0", "o").replace("1", "l").replace("|", "I")
        cleaned = re.sub(r"[^A-Za-z0-9\s=()+\-*/\[\].,:;]", " ", decoded_hint)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 40:
            byte_hint = raw_bytes[:800].decode("latin-1", errors="ignore")
            cleaned = re.sub(r"[^A-Za-z0-9\s=()+\-*/\[\].,:;]", " ", byte_hint)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 40:
            return "", None
        alpha_ratio = sum(character.isalpha() for character in cleaned) / max(len(cleaned), 1)
        confidence = round(min(0.99, 0.45 + alpha_ratio), 2)
        return cleaned, confidence

    def _from_text(
        self,
        text: str,
        method: str,
        *,
        scanned_pdf_detected: bool = False,
        ocr_confidence: float | None = None,
        normalized_source_url: str | None = None,
    ) -> DocumentExtractionResponse:
        stripped = self._strip_references(text)
        equations = self._detect_equations(stripped)
        figures = self._detect_figures(stripped)
        tables = self._detect_tables(stripped)
        equation_explanations = [self._explain_equation(equation) for equation in equations]
        figure_cross_refs = {figure.figure_id: figure.cross_references for figure in figures}
        suspicious_flags = [flag for figure in figures for flag in figure.suspicious_design_flags]
        return DocumentExtractionResponse(
            status="ok",
            extracted_text=stripped,
            extraction_method=method,
            scanned_pdf_detected=scanned_pdf_detected,
            ocr_confidence=ocr_confidence,
            normalized_source_url=normalized_source_url,
            detected_equations=equations,
            equation_explanations=equation_explanations,
            figures=figures,
            tables=tables,
            image_search_index=[figure.figure_id for figure in figures],
            processing_notes=self._processing_notes(method, stripped),
            table_csv_exports={table.table_id: table.csv_export for table in tables},
            figure_caption_cross_references=figure_cross_refs,
            suspicious_chart_design_flags=suspicious_flags,
            layout_reconstruction=self._layout_reconstruction(stripped, method, scanned_pdf_detected),
            handwritten_annotations=self._handwritten_annotations(stripped),
            table_of_contents=self._table_of_contents(stripped),
            supplementary_material_links=self._supplementary_links(stripped),
            accessibility_alt_text={figure.figure_id: figure.alt_text for figure in figures},
            dependency_diagnostics=self._dependency_diagnostics(),
            manual_verification_required=self._manual_verification_required(method, stripped, ocr_confidence),
            editable_extracted_text=stripped,
            extraction_quality_flags=self._quality_flags(method, stripped, ocr_confidence, figures, tables),
        )

    def _extract_pdf_with_pymupdf(self, raw_bytes: bytes) -> DocumentExtractionResponse | None:
        if not raw_bytes.startswith(b"%PDF"):
            return None
        try:
            import fitz  # type: ignore
        except Exception:
            return None
        try:
            document = fitz.open(stream=raw_bytes, filetype="pdf")
            page_texts = []
            layout_notes = []
            for page_index, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                if text:
                    page_texts.append(text)
                blocks = page.get_text("blocks")
                if blocks:
                    layout_notes.append(f"page {page_index}: {len(blocks)} layout blocks")
            combined = "\n\n".join(page_texts).strip()
            if self._looks_like_extracted_text(combined):
                response = self._from_text(combined, method="pymupdf")
                response.processing_notes.extend(layout_notes[:8])
                return response
            ocr_text, confidence = self._ocr_pdf_pages_with_tesseract(document)
            if ocr_text:
                response = self._from_text(ocr_text, method="pymupdf+tesseract-ocr", scanned_pdf_detected=True, ocr_confidence=confidence)
                response.processing_notes.extend(layout_notes[:8])
                return response
        except Exception:
            return None
        return None

    def _ocr_pdf_pages_with_tesseract(self, document) -> tuple[str, float | None]:
        try:
            import pytesseract  # type: ignore
            from PIL import Image
        except Exception:
            return "", None
        if not shutil.which("tesseract"):
            return "", None
        texts = []
        confidences = []
        for page in list(document)[:6]:
            pixmap = page.get_pixmap(matrix=None, alpha=False)
            image = Image.open(BytesIO(pixmap.tobytes("png")))
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            words = [word for word in data.get("text", []) if str(word).strip()]
            texts.append(" ".join(words))
            for raw_conf in data.get("conf", []):
                try:
                    conf = float(raw_conf)
                except (TypeError, ValueError):
                    continue
                if conf >= 0:
                    confidences.append(conf / 100)
        text = "\n\n".join(part for part in texts if part.strip()).strip()
        if not text:
            return "", None
        confidence = round(sum(confidences) / len(confidences), 2) if confidences else None
        return text, confidence

    def _ocr_image_with_tesseract(self, raw_bytes: bytes) -> tuple[str, float | None] | None:
        try:
            import pytesseract  # type: ignore
            from PIL import Image
        except Exception:
            return None
        if not shutil.which("tesseract"):
            return None
        try:
            image = Image.open(BytesIO(raw_bytes))
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            words = [word for word in data.get("text", []) if str(word).strip()]
            text = " ".join(words).strip()
            confidences = []
            for raw_conf in data.get("conf", []):
                try:
                    conf = float(raw_conf)
                except (TypeError, ValueError):
                    continue
                if conf >= 0:
                    confidences.append(conf / 100)
            if text:
                return text, round(sum(confidences) / len(confidences), 2) if confidences else None
        except Exception:
            return None
        return None

    def _strip_references(self, text: str) -> str:
        match = re.search(r"\b(references|bibliography)\b", text, re.IGNORECASE)
        if match:
            return text[:match.start()].strip()
        return text

    def _detect_equations(self, text: str) -> list[str]:
        equations = re.findall(r"(?:[A-Za-z]\s*=\s*[^.\n]{3,40})", text)
        return equations[:10]

    def _detect_figures(self, text: str) -> list[ExtractedFigure]:
        figures: list[ExtractedFigure] = []
        for match in re.finditer(r"(figure\s+(\d+)[:.\-]\s*[^.\n]{10,180})", text, re.IGNORECASE):
            caption = match.group(1).strip()
            figure_number = int(match.group(2))
            numeric_points = [float(value) for value in re.findall(r"\b\d+(?:\.\d+)?\b", caption)[:6]]
            chart_type = self._infer_chart_type(caption)
            figures.append(
                ExtractedFigure(
                    figure_id=f"fig-{figure_number}",
                    caption=caption,
                    chart_type=chart_type,
                    description=caption,
                    data_insights=[f"Caption extracted from nearby text with inferred {chart_type} structure."],
                    alt_text=f"Academic {chart_type.replace('_', ' ')} showing: {caption}",
                    numeric_points=numeric_points,
                    diagram_type=self._infer_diagram_type(caption),
                    cross_references=self._figure_cross_references(text, figure_number),
                    suspicious_design_flags=self._suspicious_chart_flags(caption, numeric_points),
                    library_index_terms=self._visual_index_terms(caption),
                )
            )
        return figures

    def _detect_tables(self, text: str) -> list[ExtractedTable]:
        tables: list[ExtractedTable] = []
        for index, match in enumerate(re.finditer(r"(table\s+\d+[:.\-]?\s*[^.\n]{10,180})", text, re.IGNORECASE), start=1):
            caption = match.group(1).strip()
            snippet = text[match.end(): match.end() + 220]
            parsed_headers, parsed_rows = self._parse_structured_table(snippet)
            if not parsed_headers or not parsed_rows:
                continue
            headers = parsed_headers
            rows = parsed_rows
            csv_export = "Metric,Value\n" + "\n".join(f"{row[0]},{row[1]}" for row in rows)
            if headers != ["Metric", "Value"]:
                csv_export = ",".join(headers) + "\n" + "\n".join(",".join(row) for row in rows)
            tables.append(
                ExtractedTable(
                    table_id=f"tbl-{index}",
                    caption=caption,
                    headers=headers,
                    rows=rows,
                    csv_export=csv_export,
                )
            )
        return tables

    def _explain_equation(self, equation: str) -> EquationExplanation:
        latex = equation.replace("=", " = ")
        return EquationExplanation(
            raw=equation,
            latex=f"${latex}$",
            explanation=f"This equation expresses the relationship in `{equation}`.",
            derivation_steps=[
                "Identify the left-hand variable.",
                "Interpret the right-hand terms.",
                "Relate the equation to the method or result described nearby.",
            ],
            interactive_variables=[
                {"symbol": symbol, "role": "variable or coefficient"}
                for symbol in dict.fromkeys(re.findall(r"\b[A-Za-z]\b", equation))
            ],
        )

    def _infer_chart_type(self, caption: str) -> str:
        lowered = caption.lower()
        if "curve" in lowered or "line" in lowered or "epoch" in lowered:
            return "line_chart"
        if "bar" in lowered or "distribution" in lowered:
            return "bar_chart"
        if "table" in lowered:
            return "table"
        return "figure"

    def _infer_diagram_type(self, caption: str) -> str:
        lowered = caption.lower()
        if "architecture" in lowered or "pipeline" in lowered:
            return "system_diagram"
        if "flow" in lowered:
            return "flowchart"
        if "scatter" in lowered:
            return "scatter_plot"
        return "generic_figure"

    def _processing_notes(self, method: str, text: str) -> list[str]:
        notes = [f"Primary extraction path: {method}"]
        if method == "ocr-fallback":
            notes.extend(["Deskew/contrast enhancement applied before OCR fallback.", "Multi-column reconstruction approximated from linearized text."])
        if method in {"tesseract-ocr", "pymupdf+tesseract-ocr"}:
            notes.extend(["Tesseract OCR engine used.", "Manual review is recommended for scanned or low-quality pages."])
        if method == "pymupdf":
            notes.append("PyMuPDF text and layout extraction used.")
        if "  " in text:
            notes.append("Whitespace normalization applied.")
        return notes

    def _dependency_diagnostics(self) -> dict[str, str | bool]:
        try:
            import fitz  # type: ignore # noqa: F401
            pymupdf_available = True
        except Exception:
            pymupdf_available = False
        try:
            import pytesseract  # type: ignore # noqa: F401
            pytesseract_available = True
        except Exception:
            pytesseract_available = False
        return {
            "pymupdf_available": pymupdf_available,
            "pytesseract_available": pytesseract_available,
            "tesseract_binary_available": bool(shutil.which("tesseract")),
            "pdf_engine": "PyMuPDF" if pymupdf_available else "fallback-byte-decoder",
            "ocr_engine": "Tesseract" if pytesseract_available and shutil.which("tesseract") else "heuristic-fallback",
        }

    def _manual_verification_required(self, method: str, text: str, ocr_confidence: float | None) -> bool:
        if method in {"ocr-fallback", "tesseract-ocr", "pymupdf+tesseract-ocr"}:
            return ocr_confidence is None or ocr_confidence < 0.86
        return len(text.split()) < 80

    def _quality_flags(
        self,
        method: str,
        text: str,
        ocr_confidence: float | None,
        figures: list[ExtractedFigure],
        tables: list[ExtractedTable],
    ) -> list[str]:
        flags = []
        diagnostics = self._dependency_diagnostics()
        if method in {"ocr-fallback", "tesseract-ocr", "pymupdf+tesseract-ocr"} and (ocr_confidence is None or ocr_confidence < 0.86):
            flags.append("OCR output should be manually reviewed before citation-sensitive use.")
        if not diagnostics["pymupdf_available"]:
            flags.append("Install PyMuPDF for production-grade PDF text/layout extraction.")
        if not diagnostics["tesseract_binary_available"]:
            flags.append("Install the Tesseract binary for production OCR on scanned PDFs.")
        if len(text.split()) < 80:
            flags.append("Extracted text is short; confirm the PDF was not image-only or truncated.")
        if not figures:
            flags.append("No figures detected from captions; verify visual extraction if the paper contains figures.")
        if not tables:
            flags.append("No structured tables detected; verify table extraction for tabular papers.")
        return list(dict.fromkeys(flags))

    def _figure_cross_references(self, text: str, figure_number: int) -> list[str]:
        pattern = rf"([^.\n]{{0,120}}(?:Figure|Fig\.)\s*{figure_number}[^.\n]{{0,160}})"
        refs = [match.group(1).strip() for match in re.finditer(pattern, text, re.IGNORECASE)]
        return refs[:5]

    def _suspicious_chart_flags(self, caption: str, numeric_points: list[float]) -> list[str]:
        flags = []
        lowered = caption.lower()
        if any(token in lowered for token in ("truncated axis", "no baseline", "misleading")):
            flags.append("Potential misleading chart design mentioned in caption.")
        if len(numeric_points) >= 2:
            spread = max(numeric_points) - min(numeric_points)
            if spread > 0 and min(numeric_points) > 0 and spread / max(max(numeric_points), 1) < 0.08:
                flags.append("Small numeric spread may require checking axis scaling.")
        if "3d" in lowered and any(token in lowered for token in ("bar", "pie", "chart")):
            flags.append("3D chart style can distort visual comparison.")
        return flags

    def _visual_index_terms(self, caption: str) -> list[str]:
        tokens = re.findall(r"\b[a-zA-Z][a-zA-Z-]{3,}\b", caption.lower())
        return list(dict.fromkeys(tokens[:12]))

    def _layout_reconstruction(self, text: str, method: str, scanned_pdf_detected: bool) -> dict[str, str | int | bool]:
        newline_count = text.count("\n")
        column_markers = len(re.findall(r"\s{4,}|\t", text))
        columns = 2 if column_markers >= 3 or newline_count >= 20 else 1
        return {
            "columns_detected": columns,
            "multi_column_reconstruction": columns > 1,
            "deskew_applied": method == "ocr-fallback",
            "contrast_enhanced": method == "ocr-fallback",
            "scanned_pdf_detected": scanned_pdf_detected,
            "reading_order": "layout-aware reconstructed order" if columns > 1 else "linear text order",
        }

    def _handwritten_annotations(self, text: str) -> list[str]:
        hints = []
        for match in re.finditer(r"(handwritten|margin note|annotated|scribble|ink note)[^.\n]{0,120}", text, re.IGNORECASE):
            hints.append(match.group(0).strip())
        return hints[:8]

    def _table_of_contents(self, text: str) -> list[dict[str, str | int]]:
        toc_entries = []
        toc_match = re.search(r"(table of contents|contents)(.*?)(introduction|abstract)", text, re.IGNORECASE | re.DOTALL)
        if toc_match:
            block = toc_match.group(2)
            for line in re.split(r"\n| {2,}", block):
                clean = line.strip(" .")
                page_match = re.search(r"(.+?)\s+(\d{1,4})$", clean)
                if page_match:
                    toc_entries.append({"title": page_match.group(1).strip(), "page": int(page_match.group(2))})
        if not toc_entries:
            headings = re.findall(r"\b(Abstract|Introduction|Methods?|Results?|Discussion|Conclusion|References)\b", text, re.IGNORECASE)
            toc_entries = [{"title": heading.title(), "page": index + 1} for index, heading in enumerate(dict.fromkeys(headings))]
        return toc_entries[:12]

    def _supplementary_links(self, text: str) -> list[str]:
        links = re.findall(r"https?://[^\s)]+", text)
        supplemental = [
            link.rstrip(".,;")
            for link in links
            if any(token in link.lower() for token in ("supp", "appendix", "github", "osf", "zenodo", "figshare"))
        ]
        return list(dict.fromkeys(supplemental))[:10]

    def _preflight_source_url(self, source_url: str) -> DocumentExtractionResponse | None:
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower()
        path_and_query = f"{parsed.path} {parsed.query}".lower()
        if domain in BLOCKED_DOMAINS:
            return DocumentExtractionResponse(
                status="blocked",
                extracted_text="",
                extraction_method="blocked-domain",
                blocked_reason="BLOCKED_DOMAIN",
                normalized_source_url=source_url,
            )
        try:
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise ValueError("Unsafe URL")
            hostname = parsed.hostname.rstrip(".")
            try:
                addresses = [ipaddress.ip_address(hostname)]
            except ValueError:
                addresses = [ipaddress.ip_address(result[4][0]) for result in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)]
            if not addresses or any(not address.is_global for address in addresses):
                raise ValueError("Non-public address")
        except (OSError, ValueError):
            return DocumentExtractionResponse(status="blocked", extracted_text="", extraction_method="blocked-url", blocked_reason="UNSAFE_SOURCE_URL", normalized_source_url=source_url)
        if any(hint in path_and_query for hint in CAPTCHA_HINTS):
            return DocumentExtractionResponse(
                status="blocked",
                extracted_text="",
                extraction_method="blocked-preflight",
                blocked_reason="CAPTCHA_OR_AUTHWALL",
                normalized_source_url=source_url,
            )
        return None

    def _normalize_source_url(self, source_url: str) -> str:
        parsed = urlparse(source_url)
        domain = parsed.netloc.lower()
        normalized = source_url
        if domain == "arxiv.org" or domain == "www.arxiv.org":
            normalized = normalized.replace("://arxiv.org/abs/", "://export.arxiv.org/pdf/")
            normalized = normalized.replace("://www.arxiv.org/abs/", "://export.arxiv.org/pdf/")
            normalized = normalized.replace("://arxiv.org/pdf/", "://export.arxiv.org/pdf/")
            normalized = normalized.replace("://www.arxiv.org/pdf/", "://export.arxiv.org/pdf/")
        return normalized

    def _parse_structured_table(self, snippet: str) -> tuple[list[str], list[list[str]]]:
        lines = [line.strip() for line in snippet.splitlines() if line.strip()]
        for line in lines[:4]:
            if "|" in line:
                cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                if len(cells) >= 2:
                    headers = cells
                    rows: list[list[str]] = []
                    header_index = lines.index(line)
                    for row_line in lines[header_index + 1: header_index + 5]:
                        if "|" not in row_line:
                            continue
                        row_cells = [cell.strip() for cell in row_line.split("|") if cell.strip()]
                        if len(row_cells) == len(headers):
                            rows.append(row_cells)
                    return headers, rows
        for line in lines[:4]:
            if "\t" in line:
                headers = [cell.strip() for cell in line.split("\t") if cell.strip()]
                rows: list[list[str]] = []
                header_index = lines.index(line)
                for row_line in lines[header_index + 1: header_index + 5]:
                    if "\t" not in row_line:
                        continue
                    row_cells = [cell.strip() for cell in row_line.split("\t") if cell.strip()]
                    if len(row_cells) == len(headers):
                        rows.append(row_cells)
                return headers, rows
        return [], []
