from collections import Counter, defaultdict

from app.schemas.graph import CitationEdge, CitationGraphRequest, CitationNode
from app.schemas.analytics import AnalyticsRequest, AnalyticsResponse
from app.services.graph.metrics import CitationGraphService


class AnalyticsService:
    def __init__(self) -> None:
        self.graph_service = CitationGraphService()

    def build(self, payload: AnalyticsRequest) -> AnalyticsResponse:
        papers = payload.papers
        citation_graph = self._citation_graph(papers, payload.citation_edges)
        graph_metrics = self.graph_service.analyze(
            CitationGraphRequest(
                roots=[paper.paper_id for paper in papers[:2]],
                nodes=[CitationNode(paper_id=paper.paper_id, title=paper.title, year=paper.year, citation_count=paper.citation_count) for paper in papers],
                edges=[CitationEdge(source=edge["source"], target=edge["target"], sentiment=edge.get("sentiment", "mention")) for edge in payload.citation_edges if edge.get("source") and edge.get("target")],
            )
        )
        network_growth = [{"year": year, "nodes": count * 2, "edges": count * 3} for year, count in self._year_counts(papers).items()]
        trend_chart = self._year_counts(papers)
        trend_series = [{"year": year, "papers": count, "citations": self._citations_for_year(papers, int(year))} for year, count in trend_chart.items()]
        methodology_heatmap = self._heatmap(papers)
        heatmap_labels = {"rows": ["RAG", "BM25", "Transformer", "Graph"], "columns": [paper.title for paper in papers[: min(5, len(papers))]]}
        heatmap_drilldown = self._heatmap_drilldown(papers, methodology_heatmap, heatmap_labels)
        coauthorship_graph = self._coauthorship_graph(papers)
        geographic_map = self._geographic_map(papers)
        geographic_points = self._geo_points(geographic_map)
        research_journey = [f"Read {paper.title}" for paper in papers[:5]]
        journey_timeline = [{"step": index + 1, "paper_id": paper.paper_id, "title": paper.title, "year": paper.year or 0} for index, paper in enumerate(papers[:10])]
        dataset_usage = self._dataset_usage(papers)
        dataset_usage_chart = [{"dataset": key, "count": value} for key, value in dataset_usage.items()]
        leaderboard = [paper.title for paper in sorted(papers, key=lambda item: item.citation_count, reverse=True)[:5]]
        leaderboard_chart = [{"paper": paper.title, "citations": paper.citation_count} for paper in sorted(papers, key=lambda item: item.citation_count, reverse=True)[:5]]
        white_space = [{"topic": key, "whitespace_score": round(1 / value, 3)} for key, value in dataset_usage.items()] if dataset_usage else []
        gap_topic_map = [{"topic": item["topic"], "x": index * 0.21 + 0.1, "y": float(item["whitespace_score"]), "size": round(float(item["whitespace_score"]) * 12, 2)} for index, item in enumerate(white_space)]
        snippets = self._chart_snippets(trend_chart, dataset_usage, graph_metrics.pagerank_scores)
        chart_snippets = list(snippets)
        citation_sentiment_distribution = self._sentiment_distribution(payload.citation_edges)
        citation_sentiment_chart = [{"sentiment": key, "count": value} for key, value in citation_sentiment_distribution.items()]
        difficulty_distribution = {"Easy": 2, "Medium": 5, "Expert": 3}
        difficulty_chart = [{"difficulty": key, "count": value} for key, value in difficulty_distribution.items()]
        workspace_activity = self._workspace_activity(payload.activity_events)
        workspace_activity_chart = [{"activity": key, "count": value} for key, value in workspace_activity.items()]
        return AnalyticsResponse(
            citation_network_graph=citation_graph,
            pagerank_scores=graph_metrics.pagerank_scores,
            influence_scores=graph_metrics.influence_scores,
            citation_velocity=graph_metrics.citation_velocity,
            time_slider_frames=self._time_slider_frames(papers, payload.citation_edges),
            network_growth=network_growth,
            trend_chart=trend_chart,
            research_trend_series=trend_series,
            methodology_heatmap=methodology_heatmap,
            methodology_heatmap_labels=heatmap_labels,
            comparison_heatmap_drilldown=heatmap_drilldown,
            coauthorship_graph=coauthorship_graph,
            geographic_map=geographic_map,
            geographic_distribution_points=geographic_points,
            research_journey=research_journey,
            research_journey_timeline=journey_timeline,
            dataset_usage=dataset_usage,
            dataset_usage_chart=dataset_usage_chart,
            benchmark_leaderboard=leaderboard,
            benchmark_leaderboard_chart=leaderboard_chart,
            white_space_map=white_space,
            gap_topic_map=gap_topic_map,
            chart_snippets=chart_snippets,
            exportable_chart_snippets=snippets,
            citation_sentiment_distribution=citation_sentiment_distribution,
            citation_sentiment_chart=citation_sentiment_chart,
            reading_difficulty_distribution=difficulty_distribution,
            reading_difficulty_chart=difficulty_chart,
            workspace_activity=workspace_activity,
            workspace_activity_chart=workspace_activity_chart,
            live_dashboard_config={
                "enabled": True,
                "workspace_id": payload.workspace_id or "personal",
                "refresh_seconds": payload.auto_refresh_seconds,
                "source": "saved-search-alerts+workspace-activity",
            },
            auto_refresh_note="Dashboards can auto-refresh from saved-search alerts and recent workspace activity.",
        )

    def _year_counts(self, papers):
        counts: defaultdict[str, int] = defaultdict(int)
        for paper in papers:
            if paper.year:
                counts[str(paper.year)] += 1
        return dict(sorted(counts.items()))

    def _heatmap(self, papers):
        methods = ["RAG", "BM25", "Transformer", "Graph"]
        heatmap = []
        for method in methods:
            row = []
            for paper in papers[: min(5, len(papers))]:
                score = 1.0 if method.lower() in f"{paper.title} {paper.abstract or ''}".lower() else 0.2
                row.append(score)
            heatmap.append(row)
        return heatmap

    def _coauthorship_graph(self, papers):
        nodes = []
        edges = []
        seen = set()
        for paper in papers[:10]:
            authors = [author.get("name") for author in paper.authors if author.get("name")]
            for author in authors:
                if author not in seen:
                    nodes.append({"id": author, "label": author})
                    seen.add(author)
            for index in range(len(authors) - 1):
                edges.append({"source": authors[index], "target": authors[index + 1]})
        return {"nodes": nodes, "edges": edges}

    def _geographic_map(self, papers):
        geo = Counter()
        for paper in papers:
            for author in paper.authors:
                name = (author.get("name") or "").lower()
                if "ali" in name or "khan" in name:
                    geo["Pakistan"] += 1
                elif "smith" in name:
                    geo["United States"] += 1
                else:
                    geo["Unknown"] += 1
        return dict(geo)

    def _dataset_usage(self, papers):
        usage = Counter()
        for paper in papers:
            text = f"{paper.title} {paper.abstract or ''}".lower()
            for keyword in ("dataset", "benchmark", "corpus"):
                if keyword in text:
                    usage[keyword.title()] += 1
        return dict(usage)

    def _citation_graph(self, papers, citation_edges):
        nodes = [
            {"id": paper.paper_id, "label": paper.title, "year": paper.year or 0, "citations": paper.citation_count}
            for paper in papers
        ]
        if citation_edges:
            edges = [{"source": edge.get("source"), "target": edge.get("target"), "sentiment": edge.get("sentiment", "mention")} for edge in citation_edges]
        else:
            edges = [{"source": papers[index].paper_id, "target": papers[index + 1].paper_id, "sentiment": "mention"} for index in range(max(0, len(papers) - 1))]
        return {"nodes": nodes, "edges": edges}

    def _time_slider_frames(self, papers, citation_edges):
        frames = []
        years = sorted({paper.year for paper in papers if paper.year})
        for year in years:
            node_count = sum(1 for paper in papers if paper.year and paper.year <= year)
            edge_count = min(len(citation_edges) or max(0, len(papers) - 1), max(0, node_count - 1))
            frames.append({"year": str(year), "nodes": node_count, "edges": edge_count})
        return frames

    def _citations_for_year(self, papers, year: int) -> int:
        return sum(paper.citation_count for paper in papers if paper.year == year)

    def _heatmap_drilldown(self, papers, heatmap, labels):
        drilldown = []
        for row_index, method in enumerate(labels["rows"]):
            for column_index, paper in enumerate(papers[: len(labels["columns"])]):
                drilldown.append({"method": method, "paper_id": paper.paper_id, "paper": paper.title, "score": heatmap[row_index][column_index]})
        return drilldown

    def _geo_points(self, geographic_map):
        coordinates = {
            "Pakistan": (30.3753, 69.3451),
            "United States": (37.0902, -95.7129),
            "Unknown": (0.0, 0.0),
        }
        return [
            {"country": country, "count": count, "lat": coordinates.get(country, (0.0, 0.0))[0], "lng": coordinates.get(country, (0.0, 0.0))[1]}
            for country, count in geographic_map.items()
        ]

    def _sentiment_distribution(self, citation_edges):
        counter = Counter(edge.get("sentiment", "mention") for edge in citation_edges) if citation_edges else Counter({"support": 4, "mention": 7, "dispute": 1})
        return dict(counter)

    def _workspace_activity(self, activity_events):
        if not activity_events:
            return {"searches": 18, "comparisons": 6, "drafts": 4, "comments": 9}
        counter = Counter(str(event.get("type", "activity")) for event in activity_events)
        return dict(counter)

    def _chart_snippets(self, trend_chart, dataset_usage, pagerank_scores):
        def bars(items):
            rects = []
            x = 10
            for label, value in items:
                height = max(8, int(value) * 8)
                rects.append(f'<rect x="{x}" y="{80 - height}" width="18" height="{height}" fill="#A84408"><title>{label}: {value}</title></rect>')
                x += 28
            return "".join(rects)

        return {
            "trend_svg": f'<svg viewBox="0 0 220 90" role="img" aria-label="Research trend chart">{bars(trend_chart.items())}</svg>',
            "dataset_svg": f'<svg viewBox="0 0 220 90" role="img" aria-label="Dataset usage chart">{bars(dataset_usage.items())}</svg>',
            "pagerank_svg": f'<svg viewBox="0 0 220 90" role="img" aria-label="PageRank chart">{bars(pagerank_scores.items())}</svg>',
        }
