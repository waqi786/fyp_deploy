from app.services.verification.reports import VerificationReportService


def test_master_feature_assurance_tracks_prompt_scale_and_status_language() -> None:
    matrix = VerificationReportService().build_feature_matrix()
    assert matrix.total_features_checked >= 353
    assert matrix.passed_count >= 300
    assert matrix.pending_count == 6
    assert {item.enforcement_status for item in matrix.items} == {"DONE", "BLOCKED"}

    by_key = {item.feature_key: item for item in matrix.items}
    assert by_key["search_discovery"].acceptance_criteria_count >= 34
    assert by_key["developer_platform"].route == "/developer-ai"
    assert by_key["advanced_ai"].enforcement_status == "DONE"
    assert by_key["public_launch_readiness"].enforcement_status == "BLOCKED"
    assert by_key["public_launch_readiness"].blocking is True


def test_every_assurance_item_has_user_route_evidence_and_verification_command() -> None:
    matrix = VerificationReportService().build_feature_matrix()
    for item in matrix.items:
        assert item.route.startswith("/")
        assert item.evidence
        assert item.user_flow
        assert item.verification_command
        assert item.acceptance_criteria_count == len(item.capabilities)
