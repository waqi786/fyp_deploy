from collections import defaultdict

from app.schemas.graph import CitationGraphRequest, CitationGraphResponse


class CitationGraphService:
    def analyze(self, graph: CitationGraphRequest) -> CitationGraphResponse:
        indegree = defaultdict(int)
        outgoing = defaultdict(list)
        nodes = {node.paper_id: node for node in graph.nodes}
        for edge in graph.edges:
            indegree[edge.target] += 1
            outgoing[edge.source].append(edge.target)

        max_indegree = max(indegree.values(), default=1)
        influence_scores = {
            paper_id: round(indegree.get(paper_id, 0) / max_indegree, 3)
            for paper_id in nodes
        }

        pagerank_scores = {paper_id: 1 / max(len(nodes), 1) for paper_id in nodes}
        damping = 0.85
        for _ in range(10):
            updated = {}
            for paper_id in nodes:
                inbound = [edge.source for edge in graph.edges if edge.target == paper_id]
                rank_sum = 0.0
                for source in inbound:
                    out_degree = max(len(outgoing.get(source, [])), 1)
                    rank_sum += pagerank_scores[source] / out_degree
                updated[paper_id] = (1 - damping) / max(len(nodes), 1) + damping * rank_sum
            pagerank_scores = updated

        citation_velocity = {}
        for paper_id, node in nodes.items():
            if node.year:
                age = max(1, 2026 - node.year)
                citation_velocity[paper_id] = round(node.citation_count / age, 3)
            else:
                citation_velocity[paper_id] = 0.0

        root_set = set(graph.roots)
        bridge_nodes = []
        for paper_id in nodes:
            linked_roots = set()
            for edge in graph.edges:
                if edge.source == paper_id and edge.target in root_set:
                    linked_roots.add(edge.target)
                if edge.target == paper_id and edge.source in root_set:
                    linked_roots.add(edge.source)
            if len(linked_roots) >= 2:
                bridge_nodes.append(paper_id)

        return CitationGraphResponse(
            influence_scores=influence_scores,
            pagerank_scores={key: round(value, 5) for key, value in pagerank_scores.items()},
            citation_velocity=citation_velocity,
            bridge_nodes=bridge_nodes,
        )
