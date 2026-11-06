from pydantic import BaseModel, Field

from app.schemas.paper import PaperRecord


class AnalyticsRequest(BaseModel):
    papers: list[PaperRecord] = Field(default_factory=list)
    workspace_id: str | None = None
    citation_edges: list[dict[str, str]] = Field(default_factory=list)
    activity_events: list[dict[str, str | int]] = Field(default_factory=list)
    auto_refresh_seconds: int = 30


class AnalyticsResponse(BaseModel):
    citation_network_graph: dict[str, list[dict]]
    pagerank_scores: dict[str, float]
    influence_scores: dict[str, float]
    citation_velocity: dict[str, float]
    time_slider_frames: list[dict[str, int | str]]
    network_growth: list[dict[str, int]]
    trend_chart: dict[str, int]
    research_trend_series: list[dict[str, int | str]]
    methodology_heatmap: list[list[float]]
    methodology_heatmap_labels: dict[str, list[str]]
    comparison_heatmap_drilldown: list[dict[str, str | float]]
    coauthorship_graph: dict[str, list[dict]]
    geographic_map: dict[str, int]
    geographic_distribution_points: list[dict[str, str | float | int]]
    research_journey: list[str]
    research_journey_timeline: list[dict[str, str | int]]
    dataset_usage: dict[str, int]
    dataset_usage_chart: list[dict[str, str | int]]
    benchmark_leaderboard: list[str]
    benchmark_leaderboard_chart: list[dict[str, str | int]]
    white_space_map: list[dict[str, str | float]]
    gap_topic_map: list[dict[str, str | float]]
    chart_snippets: list[str]
    exportable_chart_snippets: dict[str, str]
    citation_sentiment_distribution: dict[str, int]
    citation_sentiment_chart: list[dict[str, str | int]]
    reading_difficulty_distribution: dict[str, int]
    reading_difficulty_chart: list[dict[str, str | int]]
    workspace_activity: dict[str, int]
    workspace_activity_chart: list[dict[str, str | int]]
    live_dashboard_config: dict[str, str | int | bool]
    auto_refresh_note: str
