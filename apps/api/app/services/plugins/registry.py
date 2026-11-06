from dataclasses import dataclass

from app.services.models.adapters import build_llm_adapter


class FallbackSearchProvider:
    def __init__(self, source_name: str) -> None:
        self.source_name = source_name

    async def search(self, request):
        return []


@dataclass
class PluginDescriptor:
    name: str
    plugin_type: str
    capabilities: list[str]


class PluginRegistryService:
    def source_plugins(self) -> dict[str, object]:
        try:
            from app.services.search.registry import build_search_provider_registry

            return build_search_provider_registry()
        except Exception:
            return {
                name: FallbackSearchProvider(name)
                for name in (
                    "openalex",
                    "semantic_scholar",
                    "crossref",
                    "arxiv",
                    "pubmed",
                    "pmc",
                    "europe_pmc",
                    "core",
                    "doaj",
                    "unpaywall",
                    "google_scholar",
                    "scopus",
                    "web_of_science",
                    "ieee_xplore",
                    "acm_digital_library",
                    "springer_nature",
                    "science_direct",
                    "wiley",
                    "dblp",
                    "dimensions",
                )
            }

    def llm_plugins(self) -> dict[str, object]:
        names = ["groq", "openai", "claude", "ollama", "gemini"]
        return {name: build_llm_adapter(name) for name in names}

    def list_descriptors(self) -> list[PluginDescriptor]:
        descriptors = [
            PluginDescriptor(
                name=name,
                plugin_type="data_source",
                capabilities=["search", "metadata", "dedup-ready"],
            )
            for name in self.source_plugins()
        ]
        descriptors.extend(
            PluginDescriptor(
                name=name,
                plugin_type="llm_provider",
                capabilities=["completion", "structured-sections", "agent-ready"],
            )
            for name in self.llm_plugins()
        )
        return descriptors

    def summary(self) -> dict[str, list[str]]:
        descriptors = self.list_descriptors()
        grouped: dict[str, list[str]] = {"data_source": [], "llm_provider": []}
        for descriptor in descriptors:
            grouped.setdefault(descriptor.plugin_type, []).append(descriptor.name)
        return grouped

    def capability_summary(self, plugin_filters: list[str] | None = None) -> list[dict[str, object]]:
        descriptors = self.list_descriptors()
        grouped: dict[str, list[PluginDescriptor]] = {}
        for descriptor in descriptors:
            if plugin_filters and descriptor.plugin_type not in plugin_filters:
                continue
            grouped.setdefault(descriptor.plugin_type, []).append(descriptor)
        return [
            {
                "plugin_type": plugin_type,
                "names": [descriptor.name for descriptor in items],
                "capabilities": {descriptor.name: descriptor.capabilities for descriptor in items},
            }
            for plugin_type, items in grouped.items()
        ]
