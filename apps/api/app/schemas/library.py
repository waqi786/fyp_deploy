from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.paper import PaperRecord


# --------------------------------------------------------------------------- legacy citation library (Write tab)


class CitationLibraryRequest(BaseModel):
    papers: list[PaperRecord] = Field(default_factory=list)
    folder: str | None = None
    collection: str | None = None
    tags: list[str] = Field(default_factory=list)
    workspace_id: str | None = None
    preferred_export_format: str = "bibtex"
    one_click_save: bool = True
    shared_team_library: bool = False
    persistent_highlights: dict[str, list[str]] = Field(default_factory=dict)


class LibraryItem(BaseModel):
    paper_id: str
    title: str
    author_line: str | None = None
    folder: str | None = None
    tags: list[str] = Field(default_factory=list)
    duplicate_group: str | None = None
    citation_count_trend: list[int] = Field(default_factory=list)
    citation_velocity: float = 0.0
    unread: bool = True
    broken_link: bool = False
    dead_doi: bool = False
    open_access_resolution: str | None = None
    doi_lookup: str | None = None
    isbn_lookup: str | None = None
    annotations: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    import_source: str = "manual-save"
    saved_at: str


class CitationPreviewRequest(BaseModel):
    paper: PaperRecord
    style: str = "apa"


class CitationLibraryResponse(BaseModel):
    saved_items: list[LibraryItem]
    bibliography_export: str
    shared_library_summary: str
    duplicate_groups: dict[str, list[str]] = Field(default_factory=dict)
    unread_queue: list[str] = Field(default_factory=list)
    library_stats: dict[str, int | str] = Field(default_factory=dict)
    export_artifacts: dict[str, str] = Field(default_factory=dict)
    folder_tree: dict[str, list[str]] = Field(default_factory=dict)
    tag_index: dict[str, list[str]] = Field(default_factory=dict)
    citation_impact_tracking: dict[str, list[int]] = Field(default_factory=dict)
    personal_citation_graph: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    full_library_bibliography_exports: dict[str, str] = Field(default_factory=dict)
    annotated_pdf_library: dict[str, list[str]] = Field(default_factory=dict)
    persistence_uri: str | None = None


class CitationPreviewResponse(BaseModel):
    preview: str
    style: str
    broken_link_resolution: str
    doi_lookup: str | None = None
    format_options: list[str] = Field(default_factory=list)
    library_action_hint: str | None = None
    live_style_previews: dict[str, str] = Field(default_factory=dict)
    dead_doi_check: str = "not_checked"


class CitationImportRequest(BaseModel):
    format: str = Field(pattern="^(bibtex|ris|csljson)$")
    payload: str
    folder: str | None = None
    tags: list[str] = Field(default_factory=list)


class CitationImportResponse(BaseModel):
    imported_items: list[LibraryItem]
    detected_duplicates: dict[str, list[str]] = Field(default_factory=dict)
    import_summary: str
    roundtrip_exports: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- Library tab (owner-scoped, persistent)

ReadingStatus = Literal["to_read", "reading", "read"]
SaveSource = Literal["search", "reader", "compare", "import", "manual"]
ListKind = Literal["project", "collection"]
NoteKind = Literal["note", "idea"]
IdeaStatus = Literal["new", "exploring", "parked", "done"]
CitationStyle = Literal["apa", "mla", "chicago", "harvard", "ieee", "vancouver"]
ExportFormat = Literal["bibtex", "biblatex", "ris", "endnote", "csljson", "markdown", "text"]


class LibraryPaperIn(BaseModel):
    title: str = Field(min_length=1, max_length=600)
    authors: list[Any] = Field(default_factory=list, max_length=200)
    year: int | None = Field(default=None, ge=1000, le=2200)
    venue: str | None = Field(default=None, max_length=300)
    doi: str | None = Field(default=None, max_length=300)
    arxiv_id: str | None = Field(default=None, max_length=60)
    url: str | None = Field(default=None, max_length=1000)
    pdf_url: str | None = Field(default=None, max_length=1000)
    abstract: str | None = Field(default=None, max_length=20000)
    reader_doc_id: str | None = Field(default=None, max_length=120)


class LibrarySaveRequest(BaseModel):
    papers: list[LibraryPaperIn] = Field(min_length=1, max_length=200)
    source: SaveSource = "manual"
    list_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    read_later: bool = False


class LibraryItemOut(BaseModel):
    id: str
    paper_key: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    abstract: str | None = None
    reader_doc_id: str | None = None
    source: str
    status: ReadingStatus
    important: bool = False
    read_later: bool = False
    tags: list[str] = Field(default_factory=list)
    list_ids: list[str] = Field(default_factory=list)
    added_at: str
    updated_at: str
    opened_at: str | None = None


class LibrarySaveResponse(BaseModel):
    items: list[LibraryItemOut]
    already_saved: list[str] = Field(default_factory=list)


class LibraryItemUpdate(BaseModel):
    status: ReadingStatus | None = None
    important: bool | None = None
    read_later: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    opened: bool = False
    reader_doc_id: str | None = Field(default=None, max_length=120)


class LibraryBulkRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    action: Literal["set_status", "add_tag", "remove_tag", "add_to_list", "remove_from_list", "important", "read_later", "delete"]
    value: str | bool | None = None


class LibraryLookupRequest(BaseModel):
    papers: list[LibraryPaperIn] = Field(min_length=1, max_length=200)


class LibraryListIn(BaseModel):
    kind: ListKind
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class LibraryListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class LibraryListOut(BaseModel):
    id: str
    kind: ListKind
    name: str
    description: str | None = None
    created_at: str
    updated_at: str
    item_count: int = 0
    item_ids: list[str] | None = None
    stats: dict[str, int] | None = None


class LibraryNoteIn(BaseModel):
    kind: NoteKind = "note"
    title: str | None = Field(default=None, max_length=300)
    body: str = Field(default="", max_length=20000)
    quote: str | None = Field(default=None, max_length=2000)
    page: int | None = Field(default=None, ge=1, le=99999)
    item_id: str | None = None
    project_id: str | None = None
    status: IdeaStatus | None = None


class LibraryNoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=20000)
    quote: str | None = Field(default=None, max_length=2000)
    page: int | None = Field(default=None, ge=1, le=99999)
    item_id: str | None = None
    project_id: str | None = None
    status: IdeaStatus | None = None


class LibraryNoteOut(BaseModel):
    id: str
    kind: NoteKind
    title: str | None = None
    body: str = ""
    quote: str | None = None
    page: int | None = None
    item_id: str | None = None
    project_id: str | None = None
    status: IdeaStatus | None = None
    created_at: str
    updated_at: str


class LibraryTaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    due_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    priority: Literal["normal", "high"] = "normal"
    project_id: str | None = None
    item_id: str | None = None


class LibraryTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    due_date: str | None = Field(default=None, pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    done: bool | None = None
    priority: Literal["normal", "high"] | None = None
    project_id: str | None = None
    item_id: str | None = None


class LibraryTaskOut(BaseModel):
    id: str
    title: str
    due_date: str | None = None
    done: bool = False
    priority: Literal["normal", "high"] = "normal"
    project_id: str | None = None
    item_id: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class LibraryOverview(BaseModel):
    counts: dict[str, int]
    tags: list[dict[str, Any]] = Field(default_factory=list)


class CitationScope(BaseModel):
    item_ids: list[str] | None = Field(default=None, max_length=2000)
    list_id: str | None = None


class LibraryCiteRequest(CitationScope):
    style: CitationStyle = "apa"


class CitationPart(BaseModel):
    text: str
    italic: bool = False


class CitationEntry(BaseModel):
    id: str
    text: str
    parts: list[CitationPart]


class LibraryCiteResponse(BaseModel):
    style: CitationStyle
    entries: list[CitationEntry]


class LibraryExportRequest(CitationScope):
    format: ExportFormat
    style: CitationStyle = "apa"


class LibraryExportResponse(BaseModel):
    content: str
    filename: str
    mime: str
    count: int


class LibraryImportRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2_000_000)
    filename: str | None = Field(default=None, max_length=200)
    format: Literal["auto", "bibtex", "ris", "csljson", "ids"] = "auto"
    list_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class LibraryImportResponse(BaseModel):
    format: str
    added: int
    already_saved: int
    items: list[LibraryItemOut]
    not_found: list[str] = Field(default_factory=list)


class LibraryAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    project_id: str | None = None
    language: str = Field(default="en", max_length=16)


class LibraryAskSource(BaseModel):
    n: int
    kind: Literal["paper", "note", "idea"]
    id: str
    title: str
    snippet: str = ""
    item_id: str | None = None


class LibraryAskResponse(BaseModel):
    mode: Literal["answer", "matches"]
    answer: str | None = None
    not_found: bool = False
    sources: list[LibraryAskSource] = Field(default_factory=list)
    window_applied: bool = False
    credits_used: int = 0
