"""Deterministic, evidence-bearing profiles derived only from uploaded paper text."""
from __future__ import annotations

import re
from typing import Any

from app.schemas.comparison import PaperProfile
from app.schemas.paper import PaperRecord


_PAGE = re.compile(r"\[PDF page (\d+)\]\s*", re.IGNORECASE)
_URL = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|huggingface\.co)/[^\s<>()\]\[\"']+", re.I)
_FRAMEWORKS = re.compile(r"\b(PyTorch|TensorFlow|Keras|JAX|scikit-learn|\\texttt\{[^}]+\})\b", re.I)


def _sentences(text: str) -> list[tuple[str, int | None]]:
    page: int | None = None
    result: list[tuple[str, int | None]] = []
    for block in _PAGE.split(text or ""):
        if not block:
            continue
        if block.isdigit():
            page = int(block)
            continue
        result.extend((sentence.strip(), page) for sentence in re.split(r"(?<=[.!?])\s+|\n+", block) if len(sentence.strip()) >= 35)
    if not result and text:
        result = [(sentence.strip(), None) for sentence in re.split(r"(?<=[.!?])\s+", text) if len(sentence.strip()) >= 35]
    return result


def _evidence(sentence: str, page: int | None, section: str) -> dict[str, Any]:
    return {"quote": sentence[:700], "page": page, "section": section}


def _matches(sentences: list[tuple[str, int | None]], cues: tuple[str, ...], section: str, limit: int = 8) -> list[dict[str, Any]]:
    return [_evidence(sentence, page, section) for sentence, page in sentences if any(cue in sentence.casefold() for cue in cues)][:limit]


def build_paper_profile(paper: PaperRecord) -> PaperProfile:
    text = paper.full_text or ""
    lines = _sentences(text)
    first_page = re.split(r"\[PDF page 2\]", text, maxsplit=1, flags=re.I)[0][:7000]
    doi_match = re.search(r"(?:https?://doi\.org/|\bdoi\s*:\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", first_page, re.I)
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", first_page)
    preprint_match = re.search(r"\b(preprint|arxiv|arxiv\.org|bioRxiv|medRxiv|ssrn)\b", first_page, re.I)
    body_end = re.search(r"(?im)^\s*(references|bibliography)\s*$", text)
    body_text = text[:body_end.start()] if body_end else text
    body_lines = _sentences(body_text)
    refs_text = text[body_end.start():] if body_end else ""
    refs = []
    ref_page: int | None = None
    for part in _PAGE.split(refs_text):
        if not part:
            continue
        if part.isdigit():
            ref_page = int(part)
            continue
        for line in part.splitlines():
            sentence = " ".join(line.split())
            if not sentence or sentence.casefold() in {"references", "bibliography"}:
                continue
            doi = re.search(r"(?:https?://doi\.org/)?\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", sentence, re.I)
            if len(sentence) > 30 or doi:
                refs.append({"text": sentence[:600], "doi": doi.group(0).removeprefix("https://doi.org/").removeprefix("http://doi.org/").rstrip(".,;)") if doi else None, "page": ref_page})
    datasets = []
    for dataset in dict.fromkeys(paper.datasets or []):
        found = next(((line, page) for line, page in body_lines if dataset.casefold() in line.casefold()), None)
        datasets.append({"name": dataset, **(_evidence(found[0], found[1], "full text") if found else {})})
    dataset_patterns = re.compile(r"\b(?:dataset|corpus|benchmark)\s+(?:called|named|:)?\s*([A-Z][A-Za-z0-9_-]{2,})|\b([A-Z][A-Za-z0-9_-]{2,})\s+(?:dataset|corpus|benchmark)\b", re.I)
    known = {item["name"].casefold() for item in datasets}
    for sentence, page in body_lines:
        for match in dataset_patterns.finditer(sentence):
            name = next(group for group in match.groups() if group).strip(".,:;")
            if name.casefold() not in known and len(name) <= 65:
                datasets.append({"name": name, **_evidence(sentence, page, "full text"), "task": None, "size": None, "splits": [], "access": "not stated", "license": None, "link": None})
                known.add(name.casefold())
    framework_entries = []
    for sentence, page in body_lines:
        for match in _FRAMEWORKS.finditer(sentence):
            framework_entries.append({"name": match.group(1), **_evidence(sentence, page, "full text")})
    repos = _URL.findall(text)
    repo_url = next((url.rstrip(".,;:") for url in repos), None)
    page_one_text = re.split(r"\[PDF page 2\]", text, maxsplit=1, flags=re.I)[0]
    page_one_lines = [" ".join(line.split()) for line in page_one_text.splitlines() if line.strip()]
    title_index = next((index for index, line in enumerate(page_one_lines) if paper.title.casefold() in line.casefold() or line.casefold() in paper.title.casefold()), 0)
    header_lines = page_one_lines[title_index + 1:title_index + 8]
    affiliation_lines = [line for line in header_lines if re.search(r"\b(university|institute|department|school of|faculty of|laboratory|college of|hospital)\b", line, re.I)]
    affiliation = "; ".join(dict.fromkeys(affiliation_lines))[:400] or None
    people = []
    author_line = next((line for line in header_lines if not re.search(r"\b(university|institute|department|school of|faculty of|laboratory|college of|hospital|abstract|keywords?|https?://|@)\b", line, re.I) and len(re.findall(r"[A-Z][a-z]+", line)) >= 2 and len(line) <= 260), None)
    if author_line:
        for name in re.split(r"\s*(?:,|;|\band\b|&)\s*", re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰†*]", "", author_line)):
            clean_name = re.sub(r"\s+", " ", name).strip(" .")
            if re.fullmatch(r"(?:(?:[A-Z][a-z.'-]+|[A-Z]\.)(?:\s+|$)){2,5}", clean_name) and clean_name.casefold() not in {"abstract", "introduction", "keywords"}:
                people.append({"name": clean_name, "affiliation": affiliation, "quote": author_line[:400], "page": 1})
    reproducibility_terms = {
        "code": ("code", "implementation", "github", "gitlab"),
        "dataset": ("dataset", "data are available", "data availability", "zenodo"),
        "hyperparameters": ("hyperparameter", "learning rate", "batch size", "epochs"),
        "experimental_details": ("gpu", "hardware", "random seed", "training time", "compute"),
        "pretrained_model": ("pretrained model", "pre-trained model", "model checkpoint"),
        "license": ("license", "licence"),
    }
    checks: dict[str, Any] = {}
    for key, cues in reproducibility_terms.items():
        match = next(((line, page) for line, page in body_lines if any(cue in line.casefold() for cue in cues)), None)
        checks[key] = {"status": "reported" if match else "not stated", **(_evidence(match[0], match[1], "full text") if match else {})}
    research_questions = _matches(body_lines, ("we ask", "research question", "this paper investigates", "we investigate", "we study", "our goal is"), "full text", 6)
    motivation = _matches(body_lines, ("motivat", "challenge", "however,", "remains an open", "little is known"), "full text", 5)
    contributions = _matches(body_lines, ("our contributions", "we contribute", "our main contribution", "we propose", "we introduce"), "full text", 6)
    baselines = _matches(body_lines, ("baseline", "compared against", "compared with", "state-of-the-art", "competing methods"), "full text", 8)
    experiments = _matches(body_lines, ("we evaluate", "we conducted", "evaluation results", "experimental results", "we tested", "experiments show"), "full text", 12)
    ablation = _matches(body_lines, ("ablation", "component analysis", "without the", "remove the component"), "full text", 6)
    future_work = _matches(body_lines, ("future work", "future research", "further work", "future studies", "remains for future"), "full text", 8)
    captions = []
    for sentence, page in lines:
        if re.match(r"(?i)^(?:table|figure)\s+[\dIVX]+\s*[:.)-]", sentence):
            target = "table" if sentence.lower().startswith("table") else "figure"
            captions.append({"kind": target, "caption": sentence[:400], "page": page, "rows": []})
    parsed_tables = []
    for table in paper.parsed_tables:
        caption = str(table.get("caption") or "").strip()
        if not caption:
            continue
        position = text.casefold().find(caption.casefold())
        page_matches = re.findall(r"\[PDF page (\d+)\]", text[:position], re.I) if position >= 0 else []
        parsed_tables.append({"kind": "table", "caption": caption[:400], "headers": table.get("headers") or [], "rows": table.get("rows") or [], "page": int(page_matches[-1]) if page_matches else None})
    parsed_tables.extend(item for item in captions if item["kind"] == "figure")
    if not paper.parsed_tables:
        parsed_tables.extend(item for item in captions if item["kind"] == "table")
    return PaperProfile(
        paper_id=paper.paper_id,
        doi=doi_match.group(1).rstrip(".,;)") if doi_match else None,
        publication_year=int(year_match.group(1)) if year_match else None,
        preprint_notice=preprint_match.group(0) if preprint_match else None,
        research_questions=research_questions,
        motivation=motivation,
        contributions=contributions,
        baselines=baselines,
        experiments=experiments,
        strongest_experiment=experiments[0] if experiments else None,
        ablation=ablation,
        datasets_detail=datasets,
        reproducibility=checks,
        repo_url=repo_url,
        frameworks=framework_entries[:12],
        future_work=future_work,
        authors_affiliations=people[:20],
        parsed_references=refs[:120],
        key_tables=[item for item in parsed_tables if item["kind"] == "table"][:20],
        key_figures=[item for item in parsed_tables if item["kind"] == "figure"][:20],
        evidence_pages=[item for item in [*research_questions, *motivation, *contributions, *baselines, *experiments, *ablation, *future_work] if item.get("page") is not None],
    )
