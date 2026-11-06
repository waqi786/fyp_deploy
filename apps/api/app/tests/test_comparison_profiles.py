from app.schemas.paper import PaperRecord
from app.services.comparison.profiles import build_paper_profile


def test_profile_extracts_full_text_facts_with_page_evidence_and_references():
    paper = PaperRecord(
        paper_id="pdf:one",
        title="A Study of Reliable Classification",
        source="uploaded_pdf",
        parsed_tables=[{"table_id": "tbl-1", "caption": "Table 1. Classification results", "headers": ["Method", "Accuracy"], "rows": [["Ours", "0.91"]]}],
        full_text=(
            "[PDF page 1]\nIntroduction\nWe investigate whether a calibrated classifier improves clinical decisions. "
            "Our main contribution is a new evaluation protocol.\n"
            "[PDF page 2]\nMethods\nWe evaluate the model on the MIMIC-III dataset with 12,000 patients. "
            "We compare against logistic regression as a baseline. We conducted three experiments. "
            "The code is available at https://github.com/example/project.\n"
            "[PDF page 3]\nFuture work\nFuture work should study additional hospitals.\n"
            "References\nSmith et al. 2022. Reliable evaluation. https://doi.org/10.1234/example."
        ),
    )

    profile = build_paper_profile(paper)

    assert profile.profile_version == 2
    assert profile.research_questions[0]["page"] == 1
    assert "new evaluation protocol" in profile.contributions[0]["quote"]
    assert any(item["name"] == "MIMIC-III" for item in profile.datasets_detail)
    assert profile.reproducibility["code"]["status"] == "reported"
    assert profile.reproducibility["code"]["page"] == 2
    assert profile.repo_url == "https://github.com/example/project"
    assert profile.future_work[0]["page"] == 3
    assert profile.parsed_references[0]["doi"] == "10.1234/example"
    assert profile.key_tables[0]["headers"] == ["Method", "Accuracy"]
    assert profile.key_tables[0]["rows"] == [["Ours", "0.91"]]


def test_profile_does_not_fill_missing_source_facts():
    paper = PaperRecord(
        paper_id="pdf:two",
        title="Short paper",
        source="uploaded_pdf",
        full_text="[PDF page 1]\nIntroduction\nThis brief text describes a general problem and contains no experiment.",
    )

    profile = build_paper_profile(paper)

    assert profile.experiments == []
    assert profile.parsed_references == []
    assert profile.datasets_detail == []
    assert all(item["status"] == "not stated" for item in profile.reproducibility.values())
