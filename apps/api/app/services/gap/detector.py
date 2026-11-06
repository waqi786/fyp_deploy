import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json

from app.schemas.gap import (
    ContradictionEvidenceEntry,
    FutureWorkSuggestion,
    GapReportRequest,
    GapReportResponse,
    WhiteSpaceEntry,
)


class GapDetectionService:
    def analyze(self, payload: GapReportRequest) -> GapReportResponse:
        papers = payload.papers
        unstudied_combinations = self._unstudied_combinations(papers)
        white_space_map = self._white_space_map(papers)
        white_space_visual_map = self._white_space_visual_map(white_space_map)
        contradiction_evidence = self._contradictions(papers)
        future_work = self._future_work_suggestions(papers)
        volume_trend = self._publication_trend(papers)
        publication_chart = [{"year": int(year), "count": count} for year, count in volume_trend.items()]
        emerging, declining = self._topic_trends(papers)
        adoption = self._method_adoption(papers)
        adoption_chart = self._method_adoption_chart(adoption, papers)
        datasets = self._dataset_popularity(papers)
        dataset_trend = self._dataset_popularity_trend(papers)
        geography = self._geography_distribution(papers)
        institution_map = self._institutional_distribution_map(papers)
        funding_correlation = self._funding_trend_correlation(papers, volume_trend)
        coauthors = self._coauthorship_evolution(papers)
        coauthor_network = self._coauthorship_network_evolution(papers)
        cross_gaps = self._cross_disciplinary_gaps(papers)
        population_flags = self._underexplored_population_flags(papers)
        saturation = self._benchmark_saturation(papers)
        preprints = self._recent_preprint_radar(papers, payload.current_year)
        preprint_details = self._recent_preprint_details(papers, payload.current_year)
        questions = self._research_questions(payload.focus, future_work, contradiction_evidence)
        export_markdown = self._export_markdown(
            payload.focus,
            white_space_map,
            contradiction_evidence,
            future_work,
            emerging,
            declining,
            questions,
        )
        export_json = json.dumps(
            {
                "focus": payload.focus,
                "white_space_map": [item.model_dump() for item in white_space_map],
                "unstudied_combinations": unstudied_combinations,
                "contradiction_evidence": [item.model_dump() for item in contradiction_evidence],
                "future_work_suggestions": [item.model_dump() for item in future_work],
                "research_questions": questions,
            },
            indent=2,
        )
        export_csv = self._export_csv(white_space_map, future_work, questions)
        return GapReportResponse(
            unstudied_combinations=unstudied_combinations,
            white_space_map=white_space_map,
            white_space_visual_map=white_space_visual_map,
            contradiction_evidence=contradiction_evidence,
            future_work_suggestions=future_work,
            publication_volume_trend=volume_trend,
            publication_volume_chart=publication_chart,
            emerging_topics=emerging,
            declining_topics=declining,
            method_adoption_curves=adoption,
            method_adoption_chart=adoption_chart,
            dataset_popularity=datasets,
            dataset_popularity_trend=dataset_trend,
            geography_distribution=geography,
            institutional_distribution_map=institution_map,
            funding_trend_correlation=funding_correlation,
            coauthorship_evolution=coauthors,
            coauthorship_network_evolution=coauthor_network,
            cross_disciplinary_gaps=cross_gaps,
            underexplored_population_flags=population_flags,
            benchmark_saturation=saturation,
            recent_preprint_radar=preprints,
            recent_preprint_details=preprint_details,
            export_markdown=export_markdown,
            export_json=export_json,
            export_csv=export_csv,
            research_questions=questions,
            trend_summary={
                "emerging_topics": emerging,
                "declining_topics": declining,
                "publication_volume_trend": volume_trend,
            },
            generated_at=datetime.now(UTC).isoformat(),
        )

    def _white_space_map(self, papers):
        topic_years: defaultdict[str, list[int]] = defaultdict(list)
        topic_papers: defaultdict[str, list[str]] = defaultdict(list)
        for paper in papers:
            for topic in self._topics(paper):
                if paper.year:
                    topic_years[topic].append(paper.year)
                topic_papers[topic].append(paper.paper_id)
        result: list[WhiteSpaceEntry] = []
        for topic, years in topic_years.items():
            density = len(years)
            whitespace = 1 / density if density else 1.0
            result.append(
                WhiteSpaceEntry(
                    topic=topic,
                    density=float(density),
                    whitespace_score=round(whitespace, 3),
                    supporting_paper_ids=topic_papers.get(topic, [])[:8],
                    x=round((sum(ord(char) for char in topic) % 100) / 100, 2),
                    y=round((len(topic) * 13 % 100) / 100, 2),
                    gap_type="topic-density",
                )
            )
        return sorted(result, key=lambda item: item.whitespace_score, reverse=True)

    def _unstudied_combinations(self, papers):
        methods = ["RAG", "BM25", "Transformer", "Graph", "CNN"]
        domains = ["Clinical", "Education", "Multimodal", "Translation", "Dataset"]
        observed = set()
        for paper in papers:
            topics = set(self._topics(paper))
            text = f"{paper.title} {paper.abstract or ''}".lower()
            for method in methods:
                if method.lower() in text:
                    for domain in topics:
                        observed.add((method, domain))
        combinations = []
        for method in methods:
            for domain in domains:
                if (method, domain) not in observed:
                    combinations.append(
                        {
                            "method": method,
                            "domain": domain,
                            "gap_score": 0.8 if domain in {"Clinical", "Education"} else 0.65,
                            "rationale": f"{method} plus {domain} is weakly represented in the current evidence set.",
                            "supporting_paper_ids": [paper.paper_id for paper in papers[:3]],
                        }
                    )
        return combinations[:10]

    def _white_space_visual_map(self, white_space_map):
        return [
            {
                "topic": entry.topic,
                "x": entry.x,
                "y": entry.y,
                "radius": round(max(0.12, entry.whitespace_score), 2),
                "density": entry.density,
                "paper_ids": entry.supporting_paper_ids,
            }
            for entry in white_space_map
        ]

    def _contradictions(self, papers):
        contradictions: list[ContradictionEvidenceEntry] = []
        positive = [paper for paper in papers if any(key in (paper.abstract or "").lower() for key in ("outperform", "improve", "better than"))]
        negative = [paper for paper in papers if any(key in (paper.abstract or "").lower() for key in ("limitation", "underperform", "challenge"))]
        for left in positive[:2]:
            for right in negative[:2]:
                contradictions.append(
                    ContradictionEvidenceEntry(
                        summary=f"{left.title} reports strong gains, while {right.title} emphasizes limitations or weaker outcomes.",
                        positive_paper_id=left.paper_id,
                        negative_paper_id=right.paper_id,
                        supporting_evidence=[
                            (left.abstract or "")[:220],
                            (right.abstract or "")[:220],
                        ],
                    )
                )
        return contradictions

    def _future_work_suggestions(self, papers):
        suggestions: list[FutureWorkSuggestion] = []
        for paper in papers[:5]:
            abstract = paper.abstract or ""
            match = re.search(r"(future work[^.]*\.)", abstract, re.IGNORECASE)
            suggestion = match.group(1).strip() if match else f"Extend {paper.title} with broader datasets and stronger replication."
            suggestions.append(
                FutureWorkSuggestion(
                    paper_id=paper.paper_id,
                    suggestion=suggestion,
                    evidence=match.group(1).strip() if match else (paper.abstract or "")[:220],
                )
            )
        return suggestions

    def _publication_trend(self, papers):
        trend: defaultdict[str, int] = defaultdict(int)
        for paper in papers:
            if paper.year:
                trend[str(paper.year)] += 1
        return dict(sorted(trend.items()))

    def _topic_trends(self, papers):
        recent_counter = Counter()
        older_counter = Counter()
        for paper in papers:
            target = recent_counter if (paper.year or 0) >= 2024 else older_counter
            target.update(self._topics(paper))
        emerging = [topic for topic, count in recent_counter.most_common(5) if count > older_counter.get(topic, 0)]
        declining = [topic for topic, count in older_counter.most_common(5) if count > recent_counter.get(topic, 0)]
        return emerging, declining

    def _method_adoption(self, papers):
        curves: defaultdict[str, list[int]] = defaultdict(list)
        year_index = sorted({paper.year for paper in papers if paper.year})
        years = year_index or [2026]
        for method in ("RAG", "BM25", "Transformer", "Graph", "CNN"):
            counts = []
            for year in years:
                counts.append(sum(1 for paper in papers if (paper.year == year and method.lower() in f"{paper.title} {paper.abstract or ''}".lower())))
            curves[method] = counts
        return dict(curves)

    def _method_adoption_chart(self, adoption, papers):
        years = sorted({paper.year for paper in papers if paper.year}) or [2026]
        chart = []
        for method, counts in adoption.items():
            for index, year in enumerate(years):
                chart.append({"method": method, "year": year, "count": counts[index] if index < len(counts) else 0})
        return chart

    def _dataset_popularity(self, papers):
        popularity = Counter()
        for paper in papers:
            for match in re.findall(r"\b([A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+){0,2}\s+(?:dataset|benchmark|corpus))\b", paper.abstract or "", re.IGNORECASE):
                popularity[match.strip()] += 1
        return dict(popularity.most_common(10))

    def _dataset_popularity_trend(self, papers):
        trend = []
        for paper in papers:
            year = paper.year or 0
            for dataset in re.findall(r"\b([A-Za-z0-9-]+(?:\s+[A-Za-z0-9-]+){0,2}\s+(?:dataset|benchmark|corpus))\b", paper.abstract or "", re.IGNORECASE):
                trend.append({"dataset": dataset.strip(), "year": year, "count": 1})
        return trend

    def _geography_distribution(self, papers):
        distribution = Counter()
        for paper in papers:
            for author in paper.authors:
                name = (author.get("name") or "").lower()
                if "khan" in name or "ali" in name:
                    distribution["Pakistan"] += 1
                elif "smith" in name or "john" in name:
                    distribution["United States"] += 1
                else:
                    distribution["Unknown"] += 1
        return dict(distribution)

    def _institutional_distribution_map(self, papers):
        items = []
        for paper in papers:
            for author in paper.authors:
                institution = author.get("institution") or author.get("affiliation") or paper.venue or "Unknown institution"
                country = "Pakistan" if any(token in (author.get("name") or "").lower() for token in ("ali", "khan")) else "Unknown"
                items.append(
                    {
                        "institution": institution,
                        "country": country,
                        "paper_id": paper.paper_id,
                        "lat": 31.52 if country == "Pakistan" else 0.0,
                        "lng": 74.35 if country == "Pakistan" else 0.0,
                    }
                )
        return items[:50]

    def _funding_trend_correlation(self, papers, volume_trend):
        funded_by_year = defaultdict(int)
        for paper in papers:
            text = (paper.abstract or "").lower()
            if paper.year and any(token in text for token in ("funded", "grant", "supported by", "funding")):
                funded_by_year[str(paper.year)] += 1
        return [
            {
                "year": year,
                "publication_count": count,
                "funded_paper_count": funded_by_year.get(year, 0),
                "correlation_hint": round(funded_by_year.get(year, 0) / max(count, 1), 2),
            }
            for year, count in volume_trend.items()
        ]

    def _coauthorship_evolution(self, papers):
        evolution = []
        for paper in sorted(papers, key=lambda item: item.year or 0):
            evolution.append(
                {
                    "year": paper.year or 0,
                    "paper": paper.title,
                    "author_count": len(paper.authors),
                }
            )
        return evolution

    def _coauthorship_network_evolution(self, papers):
        network = []
        for paper in sorted(papers, key=lambda item: item.year or 0):
            authors = [author.get("name", "Unknown") for author in paper.authors]
            if len(authors) == 1:
                network.append({"year": paper.year or 0, "source": authors[0], "target": "solo-author", "paper_id": paper.paper_id})
            for index, author in enumerate(authors):
                for collaborator in authors[index + 1:]:
                    network.append({"year": paper.year or 0, "source": author, "target": collaborator, "paper_id": paper.paper_id})
        return network[:80]

    def _cross_disciplinary_gaps(self, papers):
        topics = Counter(topic for paper in papers for topic in self._topics(paper))
        gaps = []
        if "Clinical" in topics and "Education" not in topics:
            gaps.append("Clinical methods appear under-connected to education-oriented evaluation settings.")
        if "Graph" in topics and "Retrieval" in topics:
            gaps.append("Graph methods and retrieval pipelines are both present but weakly integrated across studies.")
        return gaps or ["Cross-disciplinary linkage opportunities remain underexplored."]

    def _underexplored_population_flags(self, papers):
        text = " ".join(paper.abstract or "" for paper in papers).lower()
        flags = []
        for population in ("children", "elderly", "low-resource", "rural", "non-english", "urdu", "women"):
            if population not in text:
                flags.append(f"{population.title()} population appears underexplored.")
        return flags[:6]

    def _benchmark_saturation(self, papers):
        datasets = self._dataset_popularity(papers)
        saturated = [f"{dataset} appears repeatedly and may be reaching saturation." for dataset, count in datasets.items() if count >= 2]
        return saturated or ["No benchmark looks clearly saturated in the current set."]

    def _recent_preprint_radar(self, papers, current_year):
        return [paper.title for paper in papers if (paper.year or 0) >= current_year - 1 and ("arxiv" in (paper.source or "").lower() or "preprint" in (paper.abstract or "").lower())][:10]

    def _recent_preprint_details(self, papers, current_year):
        return [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "year": paper.year or 0,
                "source": paper.source,
            }
            for paper in papers
            if (paper.year or 0) >= current_year - 1 and ("arxiv" in (paper.source or "").lower() or "preprint" in (paper.abstract or "").lower())
        ][:10]

    def _research_questions(self, focus, future_work, contradictions):
        questions = []
        if future_work:
            questions.append(f"What happens if {focus} systems are evaluated on broader, more diverse datasets?")
        if contradictions:
            questions.append(f"Why do some {focus} papers report gains while others emphasize limitations?")
        questions.append(f"Which underexplored benchmark or domain could shift {focus} research next?")
        return questions[:5]

    def _export_markdown(self, focus, white_space_map, contradictions, future_work, emerging, declining, questions):
        lines = [f"# Gap Report for {focus}", "", "## White-space map"]
        for item in white_space_map[:5]:
            lines.append(f"- {item.topic}: whitespace score {item.whitespace_score}")
        lines.append("")
        lines.append("## Contradictions")
        for item in contradictions[:5]:
            lines.append(f"- {item.summary}")
        lines.append("")
        lines.append("## Future work")
        for item in future_work[:5]:
            lines.append(f"- {item.suggestion}")
        lines.append("")
        lines.append(f"Emerging topics: {', '.join(emerging[:5]) or 'None'}")
        lines.append(f"Declining topics: {', '.join(declining[:5]) or 'None'}")
        lines.append("")
        lines.append("## Research questions")
        for question in questions:
            lines.append(f"- {question}")
        return "\n".join(lines)

    def _export_csv(self, white_space_map, future_work, questions):
        lines = ["type,label,score,evidence"]
        for item in white_space_map[:10]:
            lines.append(f"white_space,{item.topic},{item.whitespace_score},{'|'.join(item.supporting_paper_ids)}")
        for item in future_work[:10]:
            lines.append(f"future_work,{item.paper_id},,{(item.suggestion or '').replace(',', ';')}")
        for question in questions:
            lines.append(f"research_question,{question.replace(',', ';')},,")
        return "\n".join(lines)

    def _topics(self, paper):
        text = f"{paper.title} {paper.abstract or ''}".lower()
        topics = []
        for topic in ("Retrieval", "Graph", "Clinical", "Education", "Benchmark", "Multimodal", "Translation", "Dataset"):
            if topic.lower() in text:
                topics.append(topic)
        return topics or ["General"]
