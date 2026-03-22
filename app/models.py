from pydantic import BaseModel, ConfigDict, Field, field_validator

NOTE_TITLE_MAX_LEN = 500
INSTRUCTION_MAX_LEN = 8000
MARKDOWN_MAX_LEN = 1_000_000
PARENT_ID_MAX_LEN = 128


class JoplinNote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    parent_id: str = ""
    title: str = ""
    body: str = Field(default="", description="Note body as markdown from Joplin")


class CreateNoteRequest(BaseModel):
    note_title: str = Field(..., min_length=1, max_length=NOTE_TITLE_MAX_LEN)
    markdown: str = Field(default="", max_length=MARKDOWN_MAX_LEN)
    parent_id: str | None = Field(
        default=None,
        max_length=PARENT_ID_MAX_LEN,
        description="Joplin notebook (folder) id; falls back to JOPLIN_DEFAULT_PARENT_ID",
    )

    @field_validator("note_title", mode="before")
    @classmethod
    def strip_note_title(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("parent_id", mode="before")
    @classmethod
    def normalize_parent_id(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v


class PreviewEditRequest(BaseModel):
    note_title: str = Field(..., min_length=1, max_length=NOTE_TITLE_MAX_LEN)
    instruction: str = Field(..., min_length=1, max_length=INSTRUCTION_MAX_LEN)

    @field_validator("note_title", "instruction", mode="before")
    @classmethod
    def strip_text(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class PreviewEditResponse(BaseModel):
    title: str = Field(..., description="Proposed note title after the edit")
    current_markdown: str
    updated_markdown: str
    summary: str
    changed: bool


class ApplyEditRequest(BaseModel):
    note_title: str = Field(..., min_length=1, max_length=NOTE_TITLE_MAX_LEN)
    updated_markdown: str = Field(..., max_length=MARKDOWN_MAX_LEN)

    @field_validator("note_title", mode="before")
    @classmethod
    def strip_note_title(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class ApplyEditResponse(BaseModel):
    note_id: str
    title: str
    updated: bool = True


class ListEditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., max_length=NOTE_TITLE_MAX_LEN)
    markdown: str = Field(..., max_length=MARKDOWN_MAX_LEN)
    summary: str = Field(..., max_length=INSTRUCTION_MAX_LEN)
    changed: bool
