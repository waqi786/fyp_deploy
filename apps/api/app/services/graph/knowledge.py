from dataclasses import dataclass

from app.schemas.paper import PaperRecord


@dataclass
class KnowledgeNode:
    node_id: str
    node_type: str
    label: str


@dataclass
class KnowledgeEdge:
    source: str
    target: str
    relation: str


class KnowledgeGraphService:
    def build(self, papers: list[PaperRecord]) -> dict[str, list[dict[str, str]]]:
        nodes: list[KnowledgeNode] = []
        edges: list[KnowledgeEdge] = []
        seen_nodes: set[str] = set()

        for paper in papers:
            paper_node = f"paper:{paper.paper_id}"
            self._add_node(nodes, seen_nodes, paper_node, "paper", paper.title)
            for author in paper.authors:
                name = author.get("name")
                if not name:
                    continue
                author_node = f"author:{name.lower().replace(' ', '-')}"
                self._add_node(nodes, seen_nodes, author_node, "author", name)
                edges.append(KnowledgeEdge(source=paper_node, target=author_node, relation="written_by"))

            for concept in self._extract_concepts(paper):
                concept_node = f"concept:{concept.lower().replace(' ', '-')}"
                self._add_node(nodes, seen_nodes, concept_node, "concept", concept)
                edges.append(KnowledgeEdge(source=paper_node, target=concept_node, relation="mentions"))

        return {
            "nodes": [node.__dict__ for node in nodes],
            "edges": [edge.__dict__ for edge in edges],
        }

    def _add_node(self, nodes: list[KnowledgeNode], seen_nodes: set[str], node_id: str, node_type: str, label: str) -> None:
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        nodes.append(KnowledgeNode(node_id=node_id, node_type=node_type, label=label))

    def _extract_concepts(self, paper: PaperRecord) -> list[str]:
        text = f"{paper.title} {paper.abstract or ''}".lower()
        concepts = []
        for keyword in ("dataset", "benchmark", "retrieval", "transformer", "graph", "rag", "evaluation", "method"):
            if keyword in text:
                concepts.append(keyword.title())
        return concepts
