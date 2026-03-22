import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.config import Settings, get_settings
from app.joplin_errors import JoplinAmbiguousTitleError, JoplinError, JoplinNotFoundError
from app.models import (
    NOTE_TITLE_MAX_LEN,
    ApplyEditRequest,
    ApplyEditResponse,
    CreateNoteRequest,
    JoplinNote,
    PreviewEditRequest,
    PreviewEditResponse,
)
from app.services.joplin_service import JoplinClient
from app.services.openai_service import OpenAINoteError, OpenAINoteService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["notes"])


def joplin_dep(settings: Settings = Depends(get_settings)) -> JoplinClient:
    return JoplinClient(settings.joplin_base_url, settings.joplin_token)


def openai_dep(settings: Settings = Depends(get_settings)) -> OpenAINoteService:
    return OpenAINoteService(settings.openai_api_key, settings.openai_model)


@router.get("/by-title/{title}", response_model=JoplinNote)
async def get_note_by_title(
    title: Annotated[str, Path(..., min_length=1, max_length=NOTE_TITLE_MAX_LEN)],
    joplin: JoplinClient = Depends(joplin_dep),
) -> JoplinNote:
    try:
        return await joplin.get_note_by_title(title)
    except JoplinNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except JoplinAmbiguousTitleError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    except JoplinError as e:
        logger.error("Joplin error in by-title: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/create", response_model=JoplinNote, status_code=status.HTTP_201_CREATED)
async def create_note(
    body: CreateNoteRequest,
    settings: Settings = Depends(get_settings),
    joplin: JoplinClient = Depends(joplin_dep),
) -> JoplinNote:
    parent = body.parent_id or settings.joplin_default_parent_id
    if not parent:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="parent_id is required (or set JOPLIN_DEFAULT_PARENT_ID in the environment)",
        )
    try:
        return await joplin.create_note(parent, body.note_title, body.markdown)
    except JoplinError as e:
        logger.error("Joplin error in create: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/preview-edit", response_model=PreviewEditResponse)
async def preview_edit(
    body: PreviewEditRequest,
    joplin: JoplinClient = Depends(joplin_dep),
    openai: OpenAINoteService = Depends(openai_dep),
) -> PreviewEditResponse:
    logger.info("preview-edit: resolve note title=%r", body.note_title)
    try:
        note = await joplin.get_note_by_title(body.note_title)
    except JoplinNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except JoplinAmbiguousTitleError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    except JoplinError as e:
        logger.error("preview-edit: Joplin error: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    logger.info(
        "preview-edit: calling OpenAI note_id=%s body_len=%s instruction_len=%s",
        note.id,
        len(note.body),
        len(body.instruction),
    )
    try:
        result = await openai.edit_note_markdown(
            note_title=note.title,
            current_markdown=note.body,
            instruction=body.instruction,
        )
    except OpenAINoteError as e:
        logger.error("preview-edit: OpenAI error: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    logger.info(
        "preview-edit: done note_id=%s changed=%s updated_len=%s",
        note.id,
        result.changed,
        len(result.markdown),
    )
    return PreviewEditResponse(
        title=result.title,
        current_markdown=note.body,
        updated_markdown=result.markdown,
        summary=result.summary,
        changed=result.changed,
    )


@router.post("/apply-edit", response_model=ApplyEditResponse)
async def apply_edit(
    body: ApplyEditRequest,
    joplin: JoplinClient = Depends(joplin_dep),
) -> ApplyEditResponse:
    logger.info(
        "apply-edit: resolve note title=%r markdown_len=%s",
        body.note_title,
        len(body.updated_markdown),
    )
    try:
        note = await joplin.get_note_by_title(body.note_title)
    except JoplinNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except JoplinAmbiguousTitleError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    except JoplinError as e:
        logger.error("apply-edit: Joplin error: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    try:
        updated = await joplin.update_note_body(note.id, body.updated_markdown)
    except JoplinNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except JoplinError as e:
        logger.error("apply-edit: Joplin update error: %s", e)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e

    logger.info("apply-edit: done note_id=%s title=%r", updated.id, updated.title)
    return ApplyEditResponse(note_id=updated.id, title=updated.title, updated=True)
