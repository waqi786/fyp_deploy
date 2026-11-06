"""Exports for Write documents: DOCX, Markdown, LaTeX (+ .bib) and print-ready HTML (the browser saves it as PDF).

In-text [n] markers become the citation style's form: numbered styles (IEEE, Vancouver) are renumbered by first
appearance; author-date styles (APA, Harvard, Chicago, MLA) become (Author, Year). The reference list contains exactly
the sources that are cited, in the style's order."""

from __future__ import annotations

import html
import io
import re
import zipfile
from typing import Any

from app.services.library import citations as C
from app.services.write.grounding import MARKER, cited_numbers

NUMBERED = {"ieee", "vancouver"}


def _refs(sources: list[dict[str, Any] | None]) -> list[C.Reference | None]:
    return [C.Reference.from_item({**source, "id": str(index + 1)}) if source else None for index, source in enumerate(sources)]


def _first_appearance(sections: list[dict[str, Any]], count: int) -> list[int]:
    order: list[int] = []
    for section in sections:
        for number in cited_numbers(section.get("text", "")):
            if 1 <= number <= count and number not in order:
                order.append(number)
    return order


def _author_date(ref: C.Reference, style: str) -> str:
    families = [C.parse_name(author).family for author in ref.authors]
    lead = families[0] if len(families) == 1 else f"{families[0]} and {families[1]}" if len(families) == 2 else f"{families[0]} et al." if families else ref.title.split(":")[0][:40]
    if style == "apa" and len(families) == 2:
        lead = f"{families[0]} & {families[1]}"
    if style == "mla":
        return lead
    return f"{lead}, {ref.year or 'n.d.'}" if style != "chicago" else f"{lead} {ref.year or 'n.d.'}"


def render(doc: dict[str, Any]) -> dict[str, Any]:
    """Sections with converted in-text citations, plus the bibliography entries (dicts with parts/text)."""
    sources = doc.get("sources") or []
    sections = doc.get("content", {}).get("sections", [])
    style = doc.get("citation_style") or "apa"
    refs = _refs(sources)
    order = [number for number in _first_appearance(sections, len(sources)) if refs[number - 1]]
    renumber = {old: new for new, old in enumerate(order, start=1)}

    def convert(match: re.Match[str]) -> str:
        numbers = [number for number in cited_numbers(match.group(0)) if number in renumber]
        if not numbers:
            return ""
        if style in NUMBERED:
            return "[" + ", ".join(str(renumber[number]) for number in numbers) + "]"
        return "(" + "; ".join(_author_date(refs[number - 1], style) for number in numbers) + ")"

    rendered = [{"heading": section.get("heading", ""), "text": MARKER.sub(convert, section.get("text", "")).replace(" ,", ",").replace(" .", ".")} for section in sections]
    cited_refs = [refs[number - 1] for number in order]
    entries = C.bibliography(cited_refs, style)
    return {"title": doc.get("title", ""), "sections": rendered, "references": entries, "cited": order, "style": style}


def to_markdown(doc: dict[str, Any]) -> str:
    data = render(doc)
    lines = [f"# {data['title']}", ""]
    for section in data["sections"]:
        lines += [f"## {section['heading']}", "", section["text"].strip(), ""]
    if data["references"]:
        lines += ["## References", ""]
        for entry in data["references"]:
            lines.append("- " + "".join(f"*{part['text'].strip()}*" + (" " if part["text"].endswith(" ") else "") if part["italic"] else part["text"] for part in entry["parts"]).strip())
    return "\n".join(lines).strip() + "\n"


def to_html(doc: dict[str, Any], *, rtl: bool = False, language: str = "en", labels: dict[str, str] | None = None) -> str:
    data = render(doc)
    labels = labels or {}
    body = []
    for section in data["sections"]:
        paragraphs = "".join(f"<p>{html.escape(paragraph.strip())}</p>" for paragraph in re.split(r"\n\s*\n", section["text"]) if paragraph.strip())
        body.append(f"<h2>{html.escape(section['heading'])}</h2>{paragraphs}")
    refs = "".join("<li>" + "".join(f"<i>{html.escape(part['text'])}</i>" if part["italic"] else html.escape(part["text"]) for part in entry["parts"]) + "</li>" for entry in data["references"])
    ref_block = f"<h2>{html.escape(labels.get('references', 'References'))}</h2><ol class='refs{' numbered' if data['style'] in NUMBERED else ''}'>{refs}</ol>" if refs else ""
    return (
        f"<!doctype html><html lang='{html.escape(language)}' dir='{'rtl' if rtl else 'ltr'}'><head><meta charset='utf-8'><title>{html.escape(data['title'])}</title>"
        "<style>@page{size:A4;margin:22mm}body{font:12pt/1.6 'Newsreader','Noto Serif','Noto Nastaliq Urdu',Georgia,serif;color:#111;margin:0}"
        "h1{font-size:22pt;margin:0 0 12pt}h2{font-size:14pt;margin:18pt 0 6pt}p{margin:0 0 8pt;text-align:justify}"
        ".refs{padding-inline-start:0;list-style:none;direction:ltr;text-align:left}.refs li{padding-left:2em;text-indent:-2em;margin:0 0 6pt}"
        ".refs.numbered{list-style:none}.refs.numbered li{padding-left:0;text-indent:0}</style></head>"
        f"<body><h1>{html.escape(data['title'])}</h1>{''.join(body)}{ref_block}</body></html>"
    )


def _latex(text: str) -> str:
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}"}
    return "".join(replacements.get(character, character) for character in text)


def to_latex(doc: dict[str, Any]) -> tuple[str, str]:
    sources = doc.get("sources") or []
    sections = doc.get("content", {}).get("sections", [])
    refs = _refs(sources)
    order = [number for number in _first_appearance(sections, len(sources)) if refs[number - 1]]
    cited = [refs[number - 1] for number in order]
    keys = dict(zip(order, C.citation_keys(cited)))
    parts = []
    for section in sections:
        chunks, last = [], 0
        text = section.get("text", "")
        for match in MARKER.finditer(text):
            chunks.append(_latex(text[last:match.start()]))
            numbers = [number for number in cited_numbers(match.group(0)) if number in keys]
            chunks.append(("~\\cite{" + ",".join(keys[number] for number in numbers) + "}") if numbers else "")
            last = match.end()
        chunks.append(_latex(text[last:]))
        parts.append(f"\\section{{{_latex(section.get('heading', ''))}}}\n" + "".join(chunks).strip())
    bibstyle = "ieeetr" if (doc.get("citation_style") or "apa") in NUMBERED else "apalike"
    tex = (
        "\\documentclass[11pt]{article}\n\\usepackage[utf8]{inputenc}\n\\usepackage[T1]{fontenc}\n\\usepackage{hyperref}\n"
        f"\\title{{{_latex(doc.get('title', ''))}}}\n\\date{{}}\n\\begin{{document}}\n\\maketitle\n\n" + "\n\n".join(parts)
        + f"\n\n\\bibliographystyle{{{bibstyle}}}\n\\bibliography{{references}}\n\\end{{document}}\n"
    )
    return tex, C.to_bibtex(cited)


# --------------------------------------------------------------------------- DOCX (Office Open XML, no dependencies)

def _run(text: str, italic: bool = False) -> str:
    return f"<w:r>{'<w:rPr><w:i/></w:rPr>' if italic else ''}<w:t xml:space=\"preserve\">{html.escape(text, quote=False)}</w:t></w:r>"


def _para(runs: str, style: str | None = None, rtl: bool = False) -> str:
    props = "".join(part for part in [f'<w:pStyle w:val="{style}"/>' if style else "", "<w:bidi/>" if rtl else ""] if part)
    return f"<w:p>{f'<w:pPr>{props}</w:pPr>' if props else ''}{runs}</w:p>"


def to_docx(doc: dict[str, Any], *, rtl: bool = False, references_label: str = "References") -> bytes:
    data = render(doc)
    body = [_para(_run(data["title"]), "Title", rtl)]
    for section in data["sections"]:
        body.append(_para(_run(section["heading"]), "Heading1", rtl))
        for paragraph in re.split(r"\n\s*\n", section["text"]):
            if paragraph.strip():
                body.append(_para(_run(re.sub(r"\s*\n\s*", " ", paragraph.strip())), None, rtl))
    if data["references"]:
        body.append(_para(_run(references_label), "Heading1", rtl))
        for entry in data["references"]:
            body.append(_para("".join(_run(part["text"], part["italic"]) for part in entry["parts"]), "Bibliography"))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(body)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia" w:cs="Noto Nastaliq Urdu"/><w:sz w:val="23"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="320"/></w:pPr><w:rPr><w:sz w:val="44"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Bibliography"><w:name w:val="Bibliography"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="720" w:hanging="720"/></w:pPr></w:style>'
        "</w:styles>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
        archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
    return buffer.getvalue()


def consistency(doc: dict[str, Any]) -> dict[str, Any]:
    """Reference checks: markers pointing to no source, sources never cited, and unsupported sentences per section."""
    from app.services.write.grounding import unsupported_sentences

    sources = doc.get("sources") or []
    sections = doc.get("content", {}).get("sections", [])
    cited = {number for section in sections for number in cited_numbers(section.get("text", ""))}
    return {
        "broken_markers": sorted(number for number in cited if not (1 <= number <= len(sources)) or not sources[number - 1]),
        "uncited_sources": [number for number, source in enumerate(sources, start=1) if source and number not in cited],
        "unsupported": [{"section_id": section.get("id"), "sentences": unsupported_sentences(section.get("text", ""), sources)} for section in sections if section.get("text")],
    }
