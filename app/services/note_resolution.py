"""Resolve a Joplin note by human title against search results (exact match, case-insensitive)."""

from __future__ import annotations

from app.joplin_errors import JoplinAmbiguousTitleError, JoplinNotFoundError
from app.models import JoplinNote


def title_match_key(title: str) -> str:
    return title.strip().casefold()


def notes_matching_exact_title(wanted_title: str, candidates: list[JoplinNote]) -> list[JoplinNote]:
    """Return notes whose title equals `wanted_title` after strip + casefold on both sides."""
    key = title_match_key(wanted_title)
    if not key:
        return []
    return [n for n in candidates if title_match_key(n.title) == key]


def require_single_note_by_title(wanted_title: str, candidates: list[JoplinNote]) -> JoplinNote:
    """
    Pick the unique note matching `wanted_title` exactly (case-insensitive, trimmed).

    Raises JoplinNotFoundError or JoplinAmbiguousTitleError.
    """
    stripped = wanted_title.strip()
    if not stripped:
        raise JoplinNotFoundError("Empty note title")
    matches = notes_matching_exact_title(stripped, candidates)
    if not matches:
        raise JoplinNotFoundError(f"No note with title {stripped!r}")
    if len(matches) > 1:
        ids = [m.id for m in matches]
        raise JoplinAmbiguousTitleError(
            f"Multiple notes titled {stripped!r}; ids={ids}. Rename or merge in Joplin."
        )
    return matches[0]
