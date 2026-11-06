from pathlib import Path

from app.schemas.entities import (
    ApiKeyEntity,
    BackupRunEntity,
    CitationEntity,
    CollaboratorEntity,
    ComparisonRowEntity,
    ExportJobEntity,
    GapReportEntity,
    ImportJobEntity,
    LiteratureReviewEntity,
    MessageEntity,
    NoteEntity,
    PluginRegistrationEntity,
    PlagiarismCheckResultEntity,
    PrivateNoteEntity,
    PromptTemplateEntity,
    RefreshTokenEntity,
    ReviewSubscriptionEntity,
    ShareLinkEntity,
    SummaryEntity,
    WebhookSubscriptionEntity,
)


SCHEMA_PATH = Path(__file__).resolve().parents[4] / "infra" / "db" / "schema.sql"


def test_schema_contains_required_extended_tables() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()
    required_tables = [
        "create table if not exists notes",
        "create table if not exists private_notes",
        "create table if not exists refresh_tokens",
        "create table if not exists backup_runs",
        "create table if not exists push_subscriptions",
        "create table if not exists offline_actions",
        "create table if not exists api_keys",
        "create table if not exists webhook_subscriptions",
        "create table if not exists prompt_templates",
        "create table if not exists import_jobs",
        "create table if not exists plugin_registrations",
        "create table if not exists review_subscriptions",
        "create table if not exists collaborators",
        "create table if not exists share_links",
        "create table if not exists folder_items",
        "create table if not exists tag_assignments",
    ]
    for table in required_tables:
        assert table in schema


def test_ai_output_tables_carry_traceability_fields() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()
    required_sections = [
        "create table if not exists summaries",
        "create table if not exists messages",
        "create table if not exists comparisons",
        "create table if not exists comparison_rows",
        "create table if not exists gap_reports",
        "create table if not exists literature_reviews",
        "create table if not exists citations",
        "create table if not exists plagiarism_check_results",
    ]
    for section in required_sections:
        start = schema.index(section)
        excerpt = schema[start : start + 700]
        assert "confidence_score" in excerpt
        assert "source_span" in excerpt
        assert "model_used" in excerpt
        assert "generated_at" in excerpt


def test_entity_models_cover_new_data_model_objects() -> None:
    summary = SummaryEntity(id="1", paper_id="p1", tier="short", content={}, confidence_score=0.8, source_span=[], model_used="x", generated_at="now")
    message = MessageEntity(id="2", workspace_id="w1", role="assistant", content="hi", citations=[], confidence_score=0.9, source_span=[], model_used="x", generated_at="now", created_at="now")
    gap = GapReportEntity(id="3", workspace_id="w1", title="Gap", findings=[], confidence_score=0.7, source_span=[], model_used="x", generated_at="now")
    review = LiteratureReviewEntity(id="4", workspace_id="w1", title="Review", sections=[], confidence_score=0.7, source_span=[], model_used="x", generated_at="now")
    citation = CitationEntity(id="5", source_paper_id="p1", target_paper_id="p2", sentiment="support", confidence_score=0.6, source_span=[], model_used="x", generated_at="now")
    row = ComparisonRowEntity(id="6", comparison_id="c1", paper_id="p1", confidence_score=0.6, source_span=[], model_used="x", generated_at="now")
    note = NoteEntity(id="7", user_id="u1", workspace_id="w1", title="n", content="body", created_at="now", updated_at="now")
    collaborator = CollaboratorEntity(id="8", workspace_id="w1", role="editor", status="active", invited_at="now")
    share = ShareLinkEntity(id="9", workspace_id="w1", resource_type="review", resource_id="r1", permission="view", token="abc", created_at="now")
    plagiarism = PlagiarismCheckResultEntity(id="10", literature_review_id="r1", score=0.2, flagged_spans=[], confidence_score=0.5, source_span=[], model_used="x", generated_at="now", created_at="now")
    export_job = ExportJobEntity(id="11", workspace_id="w1", export_type="bibtex", status="pending", created_at="now")
    refresh_token = RefreshTokenEntity(id="12", user_id="u1", workspace_id="w1", token_hash="hash", expires_at="later", created_at="now")
    private_note = PrivateNoteEntity(id="13", user_id="u1", workspace_id="w1", title="Secret", encrypted_content="abc", created_at="now", updated_at="now")
    backup = BackupRunEntity(id="14", scope="daily", status="ok", storage_uri="s3://backup", verified_at="now", created_at="now")
    api_key = ApiKeyEntity(id="15", user_id="u1", workspace_id="w1", name="Default", key_prefix="rsr", key_hash="hash", created_at="now")
    webhook = WebhookSubscriptionEntity(id="16", workspace_id="w1", target_url="https://example.org", created_at="now")
    prompt = PromptTemplateEntity(id="17", user_id="u1", workspace_id="w1", name="Debate", body="Prompt", created_at="now", updated_at="now")
    import_job = ImportJobEntity(id="18", workspace_id="w1", format="json", item_count=2, status="done", created_at="now")
    plugin = PluginRegistrationEntity(id="19", name="openalex", plugin_type="data_source", status="active", created_at="now")
    review_subscription = ReviewSubscriptionEntity(id="20", workspace_id="w1", query="rag", created_at="now")

    assert summary.paper_id == "p1"
    assert message.workspace_id == "w1"
    assert gap.title == "Gap"
    assert review.title == "Review"
    assert citation.sentiment == "support"
    assert row.comparison_id == "c1"
    assert note.title == "n"
    assert collaborator.role == "editor"
    assert share.token == "abc"
    assert plagiarism.score == 0.2
    assert export_job.export_type == "bibtex"
    assert refresh_token.token_hash == "hash"
    assert private_note.title == "Secret"
    assert backup.scope == "daily"
    assert api_key.key_prefix == "rsr"
    assert webhook.target_url == "https://example.org"
    assert prompt.name == "Debate"
    assert import_job.item_count == 2
    assert plugin.plugin_type == "data_source"
    assert review_subscription.query == "rag"
