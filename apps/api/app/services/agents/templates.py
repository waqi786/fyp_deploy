AGENT_PROMPT_TEMPLATES = {
    "planner": "Decompose the user request, choose a primary route, and schedule only the specialist agents needed for a grounded answer.",
    "search": "Use federated retrieval, deduplication, and ranking to identify the best evidence pool for the request.",
    "reading": "Summarize the evidence, extract figures/tables/equations, and keep multilingual accessibility in scope.",
    "comparison": "Compare papers across methods, datasets, significance, and strengths/weaknesses using structured extraction columns.",
    "critique": "Score trust, novelty, contradictions, red flags, and reproducibility while avoiding unsupported claims.",
    "gap": "Detect white spaces, trends, contradictions, and future research opportunities across the evidence set.",
    "writing": "Draft structured academic output and run a self-critique pass before returning the result.",
    "citation": "Produce citation exports, citation-context answers, and graph-derived citation intelligence.",
}

