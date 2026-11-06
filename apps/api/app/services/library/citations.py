"""Citations for the Library: six reference styles, seven export formats and importers for .bib, .ris and CSL-JSON.

Everything here is deterministic and works offline. Styles follow the published rules closely enough for coursework
and journal submission drafts (APA 7, MLA 9, Chicago author-date 17, Harvard, IEEE, Vancouver); every formatted
entry is also returned as parts (plain / italic) so the interface can render italics without HTML.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

STYLES = ("apa", "mla", "chicago", "harvard", "ieee", "vancouver")
EXPORT_FORMATS = ("bibtex", "biblatex", "ris", "endnote", "csljson", "markdown", "text")
NUMBERED = {"ieee", "vancouver"}


@dataclass
class Reference:
    id: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    arxiv_id: str | None = None
    abstract: str | None = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_item(cls, item: dict[str, Any]) -> "Reference":
        return cls(
            id=str(item.get("id") or ""),
            title=str(item.get("title") or "").strip(),
            authors=[str(name) for name in item.get("authors") or []],
            year=item.get("year") if isinstance(item.get("year"), int) else None,
            venue=item.get("venue") or None,
            doi=item.get("doi") or None,
            url=item.get("url") or None,
            arxiv_id=item.get("arxiv_id") or None,
            abstract=item.get("abstract") or None,
            tags=list(item.get("tags") or []),
        )

    @property
    def link(self) -> str | None:
        if self.doi:
            return f"https://doi.org/{self.doi}"
        if self.arxiv_id:
            return f"https://arxiv.org/abs/{self.arxiv_id}"
        return self.url


# --------------------------------------------------------------------------- names


@dataclass
class Name:
    family: str
    given: str = ""

    @property
    def initials(self) -> list[str]:
        parts = [part for part in re.split(r"[\s.]+", self.given) if part]
        result = []
        for part in parts:
            pieces = [piece for piece in part.split("-") if piece]
            result.append("-".join(f"{piece[0].upper()}." for piece in pieces))
        return result


PARTICLES = {"van", "von", "der", "den", "de", "del", "della", "da", "di", "du", "la", "le", "bin", "al", "el", "dos", "das", "ter", "ten"}
SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}


def parse_name(raw: str) -> Name:
    text = re.sub(r"\s+", " ", raw or "").strip().strip(",")
    if not text:
        return Name(family="")
    if "," in text:
        family, _, given = text.partition(",")
        return Name(family=family.strip(), given=given.strip())
    words = text.split(" ")
    if len(words) == 1:
        return Name(family=words[0])
    if words[-1].lower() in SUFFIXES and len(words) > 2:
        words = words[:-1]
    index = len(words) - 1
    while index > 1 and words[index - 1].lower() in PARTICLES:
        index -= 1
    return Name(family=" ".join(words[index:]), given=" ".join(words[:index]))


def _join(names: list[str], last: str, comma_before_last: bool = True) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} {last} {names[1]}"
    return ", ".join(names[:-1]) + ("," if comma_before_last else "") + f" {last} {names[-1]}"


def _end(text: str, mark: str = ".") -> str:
    text = text.strip()
    return text if not text or text[-1] in ".?!" else text + mark


# --------------------------------------------------------------------------- styles

Part = dict[str, Any]


def _p(text: str, italic: bool = False) -> Part:
    return {"text": text, "italic": italic}


def _authors_apa(names: list[Name]) -> str:
    formatted = [f"{name.family}, {' '.join(name.initials)}".strip().rstrip(",") for name in names]
    if len(formatted) > 20:
        formatted = formatted[:19] + ["…", formatted[-1]]
        return ", ".join(formatted[:-2]) + ", … " + formatted[-1]
    if len(formatted) == 2:
        return f"{formatted[0]}, & {formatted[1]}"
    return _join(formatted, "&")


def format_apa(ref: Reference) -> list[Part]:
    names = [parse_name(author) for author in ref.authors]
    year = f"({ref.year})" if ref.year else "(n.d.)"
    lead = f"{_authors_apa(names)} {year}." if names else ""
    parts = []
    if lead:
        parts.append(_p(lead + " "))
        parts.append(_p(_end(ref.title)))
    else:
        parts.append(_p(_end(ref.title) + f" {year}."))
    if ref.venue:
        parts += [_p(" "), _p(ref.venue, True), _p(".")]
    if ref.link:
        parts.append(_p(f" {ref.link}"))
    return parts


def format_mla(ref: Reference) -> list[Part]:
    names = [parse_name(author) for author in ref.authors]
    if not names:
        lead = ""
    elif len(names) == 1:
        lead = ", ".join(part for part in (names[0].family, names[0].given) if part)
    elif len(names) == 2:
        lead = ", ".join(part for part in (names[0].family, names[0].given) if part) + f", and {names[1].given} {names[1].family}".replace("  ", " ")
    else:
        lead = ", ".join(part for part in (names[0].family, names[0].given) if part) + ", et al"
    parts = [_p(_end(lead) + " ")] if lead else []
    parts.append(_p(f"“{_end(ref.title)}”"))
    tail = [value for value in (str(ref.year) if ref.year else "", ref.link.removeprefix("https://") if ref.link else "") if value]
    if ref.venue:
        parts += [_p(" "), _p(ref.venue, True), _p((", " + ", ".join(tail) + ".") if tail else ".")]
    elif tail:
        parts.append(_p(" " + ", ".join(tail) + "."))
    return parts


def format_chicago(ref: Reference) -> list[Part]:
    names = [parse_name(author) for author in ref.authors]
    shown = names[:7] if len(names) > 10 else names
    formatted = [f"{name.family}, {name.given}".strip(", ") if index == 0 else f"{name.given} {name.family}".strip() for index, name in enumerate(shown)]
    lead = (", ".join(formatted) + ", et al.") if len(names) > 10 else _join(formatted, "and")
    parts = [_p(_end(lead) + " ")] if lead else []
    parts.append(_p(f"{str(ref.year) + '.' if ref.year else 'n.d.'} “{_end(ref.title)}”"))
    if ref.venue:
        parts += [_p(" "), _p(ref.venue, True), _p(".")]
    if ref.link:
        parts.append(_p(f" {ref.link}."))
    return parts


def format_harvard(ref: Reference) -> list[Part]:
    names = [parse_name(author) for author in ref.authors]
    formatted = [f"{name.family}, {''.join(name.initials)}".strip().rstrip(",") for name in names]
    lead = f"{formatted[0]} et al." if len(formatted) >= 4 else _join(formatted, "and", comma_before_last=False)
    parts = [_p(f"{lead} ({ref.year or 'n.d.'}) ")] if lead else [_p(f"({ref.year or 'n.d.'}) ")]
    parts.append(_p(f"‘{ref.title.rstrip('.')}’"))
    if ref.venue:
        parts += [_p(", "), _p(ref.venue, True)]
    parts.append(_p("."))
    if ref.link:
        parts.append(_p(f" Available at: {ref.link}."))
    return parts


def format_ieee(ref: Reference, number: int) -> list[Part]:
    names = [parse_name(author) for author in ref.authors]
    formatted = [f"{' '.join(name.initials)} {name.family}".strip() for name in names]
    lead = f"{formatted[0]} et al." if len(formatted) > 6 else _join(formatted, "and")
    tail = [str(ref.year)] if ref.year else []
    if ref.doi:
        tail.append(f"doi: {ref.doi}")
    elif ref.link:
        tail.append(ref.link)
    parts = [_p(f"[{number}] ")]
    if lead:
        parts.append(_p(f"{lead}, "))
    if not ref.venue and not tail:
        parts.append(_p(f"“{_end(ref.title)}”"))
        return parts
    parts.append(_p(f"“{ref.title.rstrip('.')},”"))
    if ref.venue:
        parts += [_p(" "), _p(ref.venue, True), _p((", " + ", ".join(tail) + ".") if tail else ".")]
    else:
        parts.append(_p(" " + ", ".join(tail) + "."))
    return parts


def format_vancouver(ref: Reference, number: int) -> list[Part]:
    names = [parse_name(author) for author in ref.authors]
    formatted = [f"{name.family} {''.join(initial.replace('.', '') for initial in name.initials)}".strip() for name in names]
    lead = ", ".join(formatted[:6]) + (", et al." if len(formatted) > 6 else ".") if formatted else ""
    parts = [_p(f"{number}. ")]
    if lead:
        parts.append(_p(lead + " "))
    parts.append(_p(_end(ref.title)))
    if ref.venue:
        parts.append(_p(f" {_end(ref.venue)}"))
    if ref.year:
        parts.append(_p(f" {ref.year}."))
    if ref.doi:
        parts.append(_p(f" doi:{ref.doi}"))
    elif ref.link:
        parts.append(_p(f" Available from: {ref.link}"))
    return parts


def sort_key(ref: Reference) -> tuple:
    first = parse_name(ref.authors[0]).family if ref.authors else ref.title
    return (_fold(first), ref.year or 0, _fold(ref.title))


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold() or (value or "").casefold()


def bibliography(refs: list[Reference], style: str) -> list[dict[str, Any]]:
    """Formatted entries in the style's order: alphabetical for author-date styles, as given for numbered styles."""
    style = style if style in STYLES else "apa"
    ordered = refs if style in NUMBERED else sorted(refs, key=sort_key)
    entries = []
    for index, ref in enumerate(ordered, start=1):
        if style == "apa":
            parts = format_apa(ref)
        elif style == "mla":
            parts = format_mla(ref)
        elif style == "chicago":
            parts = format_chicago(ref)
        elif style == "harvard":
            parts = format_harvard(ref)
        elif style == "ieee":
            parts = format_ieee(ref, index)
        else:
            parts = format_vancouver(ref, index)
        parts = [part for part in parts if part["text"]]
        entries.append({"id": ref.id, "parts": parts, "text": re.sub(r"\s+", " ", "".join(part["text"] for part in parts)).strip()})
    return entries


# --------------------------------------------------------------------------- exports

_BIB_ESCAPE = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_"}


def _bib_value(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = "".join(_BIB_ESCAPE.get(character, character) for character in text)
    depth = 0
    balanced = []
    for character in text:  # never emit unbalanced braces
        if character == "{":
            depth += 1
        elif character == "}":
            if depth == 0:
                continue
            depth -= 1
        balanced.append(character)
    return "".join(balanced) + "}" * depth


def citation_keys(refs: list[Reference]) -> list[str]:
    keys: list[str] = []
    for ref in refs:
        family = parse_name(ref.authors[0]).family if ref.authors else "anon"
        word = next((word for word in re.findall(r"[^\W\d_]+", ref.title) if len(word) > 3), "paper")
        base = re.sub(r"[^a-z0-9]", "", _fold(family)) or "anon"
        key = f"{base}{ref.year or ''}{re.sub(r'[^a-z0-9]', '', _fold(word))}"
        candidate, suffix = key, 0
        while candidate in keys:
            suffix += 1
            candidate = f"{key}{chr(96 + suffix) if suffix < 27 else suffix}"
        keys.append(candidate)
    return keys


def _bib_authors(ref: Reference) -> str:
    names = [parse_name(author) for author in ref.authors]
    return " and ".join(f"{name.family}, {name.given}".strip(", ") for name in names)


def to_bibtex(refs: list[Reference], biblatex: bool = False) -> str:
    entries = []
    for ref, key in zip(refs, citation_keys(refs)):
        kind = "article" if ref.venue else ("online" if biblatex and ref.url else "misc")
        fields = [("title", "{" + _bib_value(ref.title) + "}")]
        if ref.authors:
            fields.append(("author", _bib_value(_bib_authors(ref))))
        if ref.venue:
            fields.append(("journaltitle" if biblatex else "journal", _bib_value(ref.venue)))
        if ref.year:
            fields.append(("date" if biblatex else "year", str(ref.year)))
        if ref.doi:
            fields.append(("doi", ref.doi))
        if ref.arxiv_id:
            fields += [("eprint", ref.arxiv_id), ("eprinttype" if biblatex else "archivePrefix", "arxiv" if biblatex else "arXiv")]
        if ref.url and not ref.doi:
            fields.append(("url", ref.url))
        if ref.tags:
            fields.append(("keywords", _bib_value(", ".join(ref.tags))))
        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
        entries.append(f"@{kind}{{{key},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def to_ris(refs: list[Reference]) -> str:
    records = []
    for ref in refs:
        lines = [f"TY  - {'JOUR' if ref.venue else 'GEN'}", f"TI  - {ref.title}"]
        lines += [f"AU  - {parse_name(author).family}, {parse_name(author).given}".rstrip(", ") for author in ref.authors]
        if ref.year:
            lines.append(f"PY  - {ref.year}")
        if ref.venue:
            lines.append(f"T2  - {ref.venue}")
        if ref.doi:
            lines.append(f"DO  - {ref.doi}")
        if ref.link:
            lines.append(f"UR  - {ref.link}")
        if ref.abstract:
            lines.append("AB  - " + re.sub(r"\s+", " ", ref.abstract))
        lines += [f"KW  - {tag}" for tag in ref.tags]
        lines.append("ER  - ")
        records.append("\n".join(lines))
    return "\n\n".join(records) + ("\n" if records else "")


def to_endnote(refs: list[Reference]) -> str:
    records = []
    for ref in refs:
        lines = [f"%0 {'Journal Article' if ref.venue else 'Generic'}", f"%T {ref.title}"]
        lines += [f"%A {parse_name(author).family}, {parse_name(author).given}".rstrip(", ") for author in ref.authors]
        if ref.year:
            lines.append(f"%D {ref.year}")
        if ref.venue:
            lines.append(f"%J {ref.venue}")
        if ref.doi:
            lines.append(f"%R {ref.doi}")
        if ref.link:
            lines.append(f"%U {ref.link}")
        if ref.abstract:
            lines.append("%X " + re.sub(r"\s+", " ", ref.abstract))
        if ref.tags:
            lines.append(f"%K {', '.join(ref.tags)}")
        records.append("\n".join(lines))
    return "\n\n".join(records) + ("\n" if records else "")


def to_csljson(refs: list[Reference]) -> str:
    items = []
    for ref, key in zip(refs, citation_keys(refs)):
        item: dict[str, Any] = {"id": key, "type": "article-journal" if ref.venue else "article", "title": ref.title}
        if ref.authors:
            item["author"] = [{"family": name.family, "given": name.given} if name.given else {"literal": name.family} for name in map(parse_name, ref.authors)]
        if ref.year:
            item["issued"] = {"date-parts": [[ref.year]]}
        if ref.venue:
            item["container-title"] = ref.venue
        if ref.doi:
            item["DOI"] = ref.doi
        if ref.link:
            item["URL"] = ref.link
        if ref.abstract:
            item["abstract"] = ref.abstract
        if ref.tags:
            item["keyword"] = ", ".join(ref.tags)
        items.append(item)
    return json.dumps(items, ensure_ascii=False, indent=2) + "\n"


def to_markdown(refs: list[Reference], style: str) -> str:
    lines = []
    for entry in bibliography(refs, style):
        text = "".join(f"*{part['text'].strip()}*" + (" " if part["text"].endswith(" ") else "") if part["italic"] else part["text"] for part in entry["parts"])
        lines.append(f"- {text.strip()}")
    return "\n".join(lines) + ("\n" if lines else "")


def export(refs: list[Reference], fmt: str, style: str = "apa") -> tuple[str, str, str]:
    """Returns (content, file extension, mime type)."""
    if fmt == "bibtex":
        return to_bibtex(refs), "bib", "application/x-bibtex"
    if fmt == "biblatex":
        return to_bibtex(refs, biblatex=True), "bib", "application/x-bibtex"
    if fmt == "ris":
        return to_ris(refs), "ris", "application/x-research-info-systems"
    if fmt == "endnote":
        return to_endnote(refs), "enw", "application/x-endnote-refer"
    if fmt == "csljson":
        return to_csljson(refs), "json", "application/vnd.citationstyles.csl+json"
    if fmt == "markdown":
        return to_markdown(refs, style), "md", "text/markdown"
    return "\n".join(entry["text"] for entry in bibliography(refs, style)) + "\n", "txt", "text/plain"


# --------------------------------------------------------------------------- import

_LATEX = {
    r'\"a': "ä", r'\"o': "ö", r'\"u': "ü", r'\"A': "Ä", r'\"O': "Ö", r'\"U': "Ü", r"\'e": "é", r"\'a": "á", r"\'i": "í", r"\'o": "ó", r"\'u": "ú",
    r"\`e": "è", r"\`a": "à", r"\^e": "ê", r"\^o": "ô", r"\~n": "ñ", r"\c c": "ç", r"\c{c}": "ç", r"\ss": "ß", r"\o": "ø", r"\aa": "å", r"\&": "&", r"\%": "%", r"\_": "_", r"\$": "$", r"\#": "#",
}


def _delatex(value: str) -> str:
    text = value
    text = re.sub(r"\{\\([\"'`^~])\{?([A-Za-z])\}?\}", lambda match: _LATEX.get(f"\\{match.group(1)}{match.group(2)}", match.group(2)), text)
    text = re.sub(r"\\([\"'`^~])\{?([A-Za-z])\}?", lambda match: _LATEX.get(f"\\{match.group(1)}{match.group(2)}", match.group(2)), text)
    for latex, plain in _LATEX.items():
        text = text.replace(latex, plain)
    text = re.sub(r"\\(?:emph|textit|textbf|mathrm|textsc)\{([^{}]*)\}", r"\1", text)
    text = text.replace("{", "").replace("}", "").replace("~", " ").replace("--", "–")
    return re.sub(r"\s+", " ", text).strip()


def _year(value: Any) -> int | None:
    match = re.search(r"(1[5-9]\d\d|20\d\d|21\d\d)", str(value or ""))
    return int(match.group(1)) if match else None


def _read_bib_value(text: str, index: int) -> tuple[str, int]:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    if index >= len(text):
        return "", index
    opener = text[index]
    if opener == "{":
        depth, start = 0, index
        while index < len(text):
            if text[index] == "{" and text[index - 1:index] != "\\":
                depth += 1
            elif text[index] == "}" and text[index - 1:index] != "\\":
                depth -= 1
                if depth == 0:
                    return text[start + 1:index], index + 1
            index += 1
        return text[start + 1:], index
    if opener == '"':
        start = index + 1
        index += 1
        depth = 0
        while index < len(text):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            elif text[index] == '"' and depth <= 0:
                return text[start:index], index + 1
            index += 1
        return text[start:], index
    match = re.match(r"[^,}\s]+", text[index:])
    value = match.group(0) if match else ""
    return value, index + len(value)


def parse_bibtex(raw: str) -> list[dict[str, Any]]:
    papers = []
    for match in re.finditer(r"@\s*([A-Za-z]+)\s*[{(]", raw):
        kind = match.group(1).lower()
        if kind in {"comment", "preamble", "string"}:
            continue
        index = match.end()
        comma = raw.find(",", index)
        if comma < 0:
            continue
        index = comma + 1
        fields: dict[str, str] = {}
        while index < len(raw):
            field_match = re.match(r"\s*([A-Za-z][\w\-:]*)\s*=", raw[index:])
            if not field_match:
                break
            name = field_match.group(1).lower()
            value, index = _read_bib_value(raw, index + field_match.end())
            fields[name] = value
            rest = re.match(r"\s*(?:#\s*\S+\s*)*,?", raw[index:])
            index += rest.end() if rest else 0
            if raw[index:index + 1] in {"}", ")"}:
                break
        title = _delatex(fields.get("title", ""))
        if not title:
            continue
        authors = [_delatex(name) for name in re.split(r"\s+and\s+", fields.get("author", ""), flags=re.IGNORECASE) if name.strip()]
        eprint = fields.get("eprint") if "arxiv" in (fields.get("archiveprefix", "") + fields.get("eprinttype", "")).lower() else None
        papers.append({
            "title": title,
            "authors": authors,
            "year": _year(fields.get("year") or fields.get("date")),
            "venue": _delatex(fields.get("journal") or fields.get("journaltitle") or fields.get("booktitle") or fields.get("publisher") or "") or None,
            "doi": fields.get("doi") or None,
            "arxiv_id": eprint,
            "url": fields.get("url") or None,
            "abstract": _delatex(fields.get("abstract", "")) or None,
            "tags": [tag.strip() for tag in re.split(r"[,;]", _delatex(fields.get("keywords", ""))) if tag.strip()],
        })
    return papers


def parse_ris(raw: str) -> list[dict[str, Any]]:
    papers, current = [], None
    for line in raw.splitlines():
        match = re.match(r"^([A-Z][A-Z0-9])\s{1,2}-\s?(.*)$", line.rstrip())
        if not match:
            continue
        tag, value = match.group(1), match.group(2).strip()
        if tag == "TY":
            current = {"title": "", "authors": [], "year": None, "venue": None, "doi": None, "url": None, "abstract": None, "tags": []}
            continue
        if current is None:
            continue
        if tag == "ER":
            if current["title"]:
                papers.append(current)
            current = None
        elif tag in {"TI", "T1"} and not current["title"]:
            current["title"] = value
        elif tag in {"AU", "A1"}:
            current["authors"].append(value)
        elif tag in {"PY", "Y1", "DA"} and not current["year"]:
            current["year"] = _year(value)
        elif tag in {"T2", "JO", "JF", "JA", "BT"} and not current["venue"]:
            current["venue"] = value
        elif tag == "DO":
            current["doi"] = value
        elif tag == "UR" and not current["url"]:
            current["url"] = value
        elif tag in {"AB", "N2"}:
            current["abstract"] = value
        elif tag == "KW":
            current["tags"].append(value)
    if current and current["title"]:
        papers.append(current)
    return papers


def parse_csljson(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    items = data if isinstance(data, list) else data.get("items", [data]) if isinstance(data, dict) else []
    papers = []
    for item in items:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        authors = []
        for author in item.get("author") or []:
            if isinstance(author, dict):
                name = author.get("literal") or " ".join(part for part in (author.get("given"), author.get("family")) if part)
                if name:
                    authors.append(name if author.get("literal") else f"{author.get('family', '')}, {author.get('given', '')}".strip(", "))
        venue = item.get("container-title")
        issued = (item.get("issued") or {}).get("date-parts") or [[None]]
        papers.append({
            "title": str(item["title"]).strip(),
            "authors": authors,
            "year": _year(issued[0][0] if issued and issued[0] else None),
            "venue": (venue[0] if isinstance(venue, list) and venue else venue) or None,
            "doi": item.get("DOI") or None,
            "url": item.get("URL") or None,
            "abstract": item.get("abstract") or None,
            "tags": [tag.strip() for tag in re.split(r"[,;]", str(item.get("keyword") or "")) if tag.strip()],
        })
    return papers


IDENTIFIER = re.compile(r"(10\.\d{4,9}/[^\s,;\"'<>]+)|(?:arxiv[:\s]*|arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)


def parse_identifiers(raw: str) -> list[tuple[str, str]]:
    """DOIs and arXiv ids found in free text, in order, without repeats: [("doi", "10.…"), ("arxiv", "2301.01234")]."""
    found: list[tuple[str, str]] = []
    for match in IDENTIFIER.finditer(raw):
        kind, value = ("doi", match.group(1).rstrip(".)]")) if match.group(1) else ("arxiv", match.group(2))
        if (kind, value.lower()) not in {(k, v.lower()) for k, v in found}:
            found.append((kind, value))
    return found[:200]


def detect_format(raw: str, filename: str | None = None) -> str:
    name = (filename or "").lower()
    if name.endswith((".bib", ".bibtex")):
        return "bibtex"
    if name.endswith((".ris", ".txt")) and re.search(r"^TY\s{1,2}-", raw, re.MULTILINE):
        return "ris"
    if name.endswith(".json"):
        return "csljson"
    stripped = raw.lstrip()
    if stripped.startswith("@"):
        return "bibtex"
    if re.search(r"^TY\s{1,2}-", raw, re.MULTILINE):
        return "ris"
    if stripped.startswith(("[", "{")):
        return "csljson"
    return "ids"


def parse(raw: str, fmt: str) -> list[dict[str, Any]]:
    if fmt == "bibtex":
        return parse_bibtex(raw)
    if fmt == "ris":
        return parse_ris(raw)
    if fmt == "csljson":
        return parse_csljson(raw)
    return []


def refs_from_items(items: Iterable[dict[str, Any]]) -> list[Reference]:
    return [Reference.from_item(item) for item in items]
