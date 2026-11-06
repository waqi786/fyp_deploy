from app.services.roadmap.planner import DevelopmentRoadmapService


def test_development_roadmap_preserves_requested_order_and_counts() -> None:
    roadmap = DevelopmentRoadmapService().build()
    assert roadmap.project == "Resora"
    assert len(roadmap.phases) == 14
    assert roadmap.phases[0].title == "Migrate Cost-Bearing Dependencies"
    assert roadmap.phases[-1].title == "Final Integration, Load Testing, Documentation, Deployment"
    assert roadmap.completed_count >= 1
    assert roadmap.in_progress_count >= 1
    assert roadmap.pending_count >= 1


def test_development_roadmap_highlights_validation_gates() -> None:
    roadmap = DevelopmentRoadmapService().build()
    phase_one = roadmap.phases[0]
    final_phase = roadmap.phases[-1]
    assert "74% accuracy" in phase_one.verification_gate
    assert "50+ concurrent" in final_phase.verification_gate
    assert final_phase.status == "pending"

