import pytest
from pydantic import ValidationError

from app.schemas.comparison import InsightEvidenceRef, InsightKeyNumber, InsightsModel


def test_insights_model_rejects_takeaways_over_25_words():
    with pytest.raises(ValidationError, match="25 words or fewer"):
        InsightsModel(takeaway="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty one twenty two twenty three twenty four twenty five twenty six")


def test_key_numbers_require_clickable_source_evidence():
    evidence = InsightEvidenceRef(paper_id="pdf:a", field="dataset", quote="We evaluate the model on the CIFAR-10 benchmark.", page=4)
    fact = InsightKeyNumber(value="1", label="Named datasets found", source="Uploaded PDF", evidence=[evidence])
    model = InsightsModel(takeaway="Review the shared benchmark and confirm each test protocol.", key_numbers=[fact], takeaway_evidence=[evidence])

    assert model.key_numbers[0].evidence[0].page == 4
    with pytest.raises(ValidationError):
        InsightKeyNumber(value="1", label="Named datasets found", source="Uploaded PDF", evidence=[])


def test_evidence_page_must_be_a_positive_page_number():
    with pytest.raises(ValidationError):
        InsightEvidenceRef(paper_id="pdf:a", field="result", quote="Accuracy was 92 percent.", page=0)
