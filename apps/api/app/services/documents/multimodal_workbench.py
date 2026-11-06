from __future__ import annotations

import re

from app.schemas.document import (
    FigureComparisonRequest,
    FigureComparisonResponse,
    FigureQuestionRequest,
    FigureQuestionResponse,
    LibraryImageSearchRequest,
    LibraryImageSearchResponse,
)


class MultimodalWorkbenchService:
    def answer_visual_question(self, payload: FigureQuestionRequest) -> FigureQuestionResponse:
        question = payload.question.lower()
        figure_number = self._requested_number(question)
        selected = None
        if figure_number is not None:
            selected = next((figure for figure in payload.figures if figure.figure_id.endswith(str(figure_number))), None)
        selected = selected or (payload.figures[0] if payload.figures else None)
        if selected:
            answer = (
                f"{selected.figure_id} shows {selected.description}. "
                f"Detected type: {selected.diagram_type}; chart class: {selected.chart_type}. "
                f"Numeric points extracted: {selected.numeric_points or 'none'}."
            )
            if selected.suspicious_design_flags:
                answer += f" Design caveat: {'; '.join(selected.suspicious_design_flags)}"
            return FigureQuestionResponse(
                answer=answer,
                confidence_score=0.82,
                cited_visual_ids=[selected.figure_id],
                source_spans=[selected.caption, *selected.cross_references[:2]],
            )
        if payload.tables and "table" in question:
            table = payload.tables[0]
            return FigureQuestionResponse(
                answer=f"{table.table_id} contains columns {', '.join(table.headers)} with {len(table.rows)} extracted rows.",
                confidence_score=0.76,
                cited_visual_ids=[table.table_id],
                source_spans=[table.caption, table.csv_export],
            )
        if payload.equations and ("equation" in question or "derive" in question):
            equation = payload.equations[0]
            return FigureQuestionResponse(
                answer=f"{equation.raw} reconstructs as {equation.latex}. Steps: {' '.join(equation.derivation_steps)}",
                confidence_score=0.78,
                cited_visual_ids=["equation"],
                source_spans=[equation.raw, equation.latex],
            )
        return FigureQuestionResponse(
            answer="I am not sure because no matching visual, table, or equation was provided.",
            confidence_score=0.0,
            cited_visual_ids=[],
            source_spans=[],
        )

    def compare_figures(self, payload: FigureComparisonRequest) -> FigureComparisonResponse:
        matrix = []
        suspicious = []
        for figure in payload.figures:
            suspicious.extend(figure.suspicious_design_flags)
            matrix.append(
                {
                    "figure_id": figure.figure_id,
                    "chart_type": figure.chart_type,
                    "diagram_type": figure.diagram_type,
                    "numeric_point_count": len(figure.numeric_points),
                    "numeric_range": round(max(figure.numeric_points) - min(figure.numeric_points), 3)
                    if len(figure.numeric_points) >= 2
                    else 0,
                    "index_terms": figure.library_index_terms,
                    "flags": figure.suspicious_design_flags,
                }
            )
        summary = f"Compared {len(payload.figures)} figures across chart type, diagram type, extracted numbers, and design caveats."
        return FigureComparisonResponse(
            comparison_matrix=matrix,
            summary=summary,
            suspicious_flags=list(dict.fromkeys(suspicious)),
        )

    def search_library_images(self, payload: LibraryImageSearchRequest) -> LibraryImageSearchResponse:
        query_terms = {token for token in re.findall(r"\b[a-zA-Z][a-zA-Z-]{2,}\b", payload.query.lower())}
        matches = []
        for figure in payload.figures:
            haystack = set(figure.library_index_terms) | set(re.findall(r"\b[a-zA-Z][a-zA-Z-]{2,}\b", figure.caption.lower()))
            overlap = sorted(query_terms & haystack)
            if overlap:
                matches.append(
                    {
                        "figure_id": figure.figure_id,
                        "caption": figure.caption,
                        "score": round(len(overlap) / max(len(query_terms), 1), 2),
                        "matched_terms": overlap,
                    }
                )
        return LibraryImageSearchResponse(
            query=payload.query,
            matches=sorted(matches, key=lambda item: float(item["score"]), reverse=True),
        )

    def _requested_number(self, question: str) -> int | None:
        match = re.search(r"(?:figure|fig\.?)\s*(\d+)", question)
        return int(match.group(1)) if match else None
