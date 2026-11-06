from pydantic import BaseModel, ConfigDict, Field


class ChatFigure(BaseModel):
    figure_id: str
    caption: str
    description: str = ""


class ChatTable(BaseModel):
    table_id: str
    caption: str
    summary: str = ""


class ChatCitationEdge(BaseModel):
    source_paper_id: str
    target_paper_id: str
    context: str = ""
    sentiment: str = "mention"


class ChatDocument(BaseModel):
    paper_id: str
    title: str
    content: str
    figures: list[ChatFigure] = Field(default_factory=list)
    tables: list[ChatTable] = Field(default_factory=list)
    equations: list[str] = Field(default_factory=list)
    code_snippets: list[str] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    session_id: str | None = None
    workspace_id: str | None = None
    paper_ids: list[str] = Field(default_factory=list)
    question: str = Field(min_length=3)
    language: str = "en"
    show_your_work: bool = False
    voice_transcript: str | None = None
    voice_output: bool = False
    stream: bool = False
    conversation_history: list[str] = Field(default_factory=list)
    citation_edges: list[ChatCitationEdge] = Field(default_factory=list)
    documents: list[ChatDocument] = Field(default_factory=list)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    answer: str
    confidence_score: float
    citations: list[str]
    source_spans: list[str]
    inline_citations: list[dict[str, str]] = Field(default_factory=list)
    highlighted_source_spans: list[dict[str, str]] = Field(default_factory=list)
    retrieval_mode: str = "text"
    chat_scope: str = "none"
    condensed_question: str | None = None
    follow_up_suggestions: list[str] = Field(default_factory=list)
    automatic_literature_suggestions: list[str] = Field(default_factory=list)
    retrieved_chunks: list[str] = Field(default_factory=list)
    citation_context_answers: list[str] = Field(default_factory=list)
    citation_sentiment_labels: list[dict[str, str]] = Field(default_factory=list)
    comparison_from_chat: str | None = None
    voice_output_text: str | None = None
    feedback_token: str | None = None
    pinned: bool = False
    starred: bool = False
    export_markdown: str | None = None
    shareable_thread_token: str | None = None
    traceability_passed: bool = False
    traceability_coverage: float = 0.0
    traceable_sentences: list[dict[str, str | bool | None]] = Field(default_factory=list)
    unsupported_sentences: list[str] = Field(default_factory=list)
    model_used: str
    generated_at: str | None = None
    fallback_reason: str | None = None
    session_turns: int = 0


class ChatFeedbackRequest(BaseModel):
    feedback_token: str
    rating: int = Field(ge=1, le=5)
    note: str | None = None
    helpful: bool = True
    user_id: str | None = None


class ChatFeedbackResponse(BaseModel):
    feedback_id: str
    feedback_token: str
    status: str
    stored_at: str


class ChatPinRequest(BaseModel):
    feedback_token: str
    shareable_thread_token: str
    answer: str
    starred: bool = True
    user_id: str | None = None


class ChatPinResponse(BaseModel):
    pin_id: str
    feedback_token: str
    shareable_thread_token: str
    pinned: bool
    starred: bool
    stored_at: str
