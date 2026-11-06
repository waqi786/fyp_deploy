from app.services.verification.reports import VerificationReportService


def test_verification_reports_cover_all_roadmap_phases() -> None:
    response = VerificationReportService().build()
    assert response.project == "Resora"
    assert len(response.reports) == 14
    assert response.reports[0].phase_title == "Migrate Cost-Bearing Dependencies"
    assert response.reports[-1].status == "pending"


def test_verification_reports_include_samples_and_baseline_comparisons() -> None:
    response = VerificationReportService().build()
    phase_three = response.reports[2]
    phase_fourteen = response.reports[-1]
    assert phase_three.sample.input_summary
    assert phase_three.sample.output_summary
    assert any(metric.better_than_baseline for metric in phase_three.metrics)
    assert phase_fourteen.metrics[0].better_than_baseline is False


def test_feature_verification_matrix_surfaces_passed_and_pending_groups() -> None:
    response = VerificationReportService().build_feature_matrix()
    assert response.project == "Resora"
    assert response.total_features_checked >= 10
    assert response.passed_count > 0
    assert response.pending_count >= 1
    assert any(item.feature_key == "search_discovery" and item.status == "passed" for item in response.items)
    assert any(item.feature_key == "public_launch_readiness" and item.status == "pending" for item in response.items)


def test_proposal_alignment_maps_pdf_objectives_to_verified_product_flows() -> None:
    response = VerificationReportService().build_proposal_alignment()
    objective_by_key = {item.objective_key: item for item in response.objectives}

    assert response.project == "Resora"
    assert response.source_document == "RESORA-Proposal-Final.pdf"
    assert response.readiness_score >= 90
    assert len(response.objectives) == 10
    assert objective_by_key["multi_source_search"].implementation_status == "implemented"
    assert "OpenAlex" in objective_by_key["multi_source_search"].evidence
    assert objective_by_key["english_urdu"].product_route == "/personalization"
    assert "RTL" in objective_by_key["english_urdu"].evidence
    assert objective_by_key["pdf_ocr"].implementation_status == "partial"
    assert any("Tesseract" in caveat for caveat in objective_by_key["pdf_ocr"].caveats)
    assert "BibTeX" in objective_by_key["literature_review_exports"].evidence


def test_complete_feature_list_is_parsed_and_mapped_to_production_gates() -> None:
    response = VerificationReportService().build_complete_feature_checklist()
    by_id = {item.feature_id: item for item in response.items}

    assert response.source_document == "docs/complete-feature-list.md"
    assert response.total_features >= 200
    assert response.implemented_count > 0
    assert response.production_gap_count > 0
    assert by_id["1.1"].mapped_route == "/search"
    assert by_id["7.1"].implementation_status == "partial"
    assert "Tesseract" in (by_id["7.1"].remediation or "")
    assert any(item.module for item in response.items)
