from app.schemas.agents import MultiAgentWorkflowRequest, SearchAgentOutput
from app.services.agents.templates import AGENT_PROMPT_TEMPLATES
from app.services.plugins.registry import PluginRegistryService
from app.services.search.deduplication import deduplicate_papers
from app.services.search.discovery import enrich_search_results, infer_metadata_fields


class SearchAgent:
    def __init__(self) -> None:
        self.plugins = PluginRegistryService()

    def run(self, payload: MultiAgentWorkflowRequest) -> SearchAgentOutput:
        providers = list(self.plugins.source_plugins().keys())
        deduped = deduplicate_papers(payload.papers)
        enriched = [infer_metadata_fields(paper) for paper in deduped.papers]
        ranked, _, _, _ = enrich_search_results(payload.question, enriched) if enriched else ([], {}, [], [])
        return SearchAgentOutput(
            prompt_template=AGENT_PROMPT_TEMPLATES["search"],
            retrieval_scope="federated multi-source retrieval with deduplication",
            providers=providers,
            total_candidates=len(payload.papers),
            deduplicated_results=len(ranked),
            likely_duplicate_pairs=deduped.likely_duplicate_pairs,
            top_papers=ranked[:10],
            rationale="Search agent reused federated-provider registry, deduplication, and ranking heuristics to form the evidence pool.",
        )

