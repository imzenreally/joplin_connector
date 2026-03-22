"""Prompts and JSON schema for LLM-assisted markdown note edits."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.models import ListEditResult

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You edit markdown notes for Joplin. You receive the current title and body plus a user instruction.

Rules:
- Only change what the instruction asks for; preserve all other useful content.
- Do not invent facts, links, people, or items that the user did not imply.
- Preserve headings, lists, and structure unless the instruction asks to change them.
- Keep bullet/heading style consistent with the existing note.
- Remove or merge obvious duplicate lines or list items when cleaning up.
- Return JSON only, matching the required schema (no markdown fences around the JSON).

The JSON fields:
- title: full note title after edits (unchanged if the instruction only affects the body).
- markdown: full markdown body after edits.
- summary: 1–3 sentences describing what you changed for the user.
- changed: true if title or body meaningfully differs from the input; false if nothing to do.
"""

_FENCE = re.compile(
    r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def structured_output_schema() -> dict[str, Any]:
    return ListEditResult.model_json_schema()


def build_user_message(*, note_title: str, current_markdown: str, instruction: str) -> str:
    return (
        f"Current title: {note_title}\n\n"
        f"Current markdown:\n{current_markdown}\n\n"
        f"User instruction:\n{instruction}\n"
    )


def _unwrap_json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("\ufeff"):
        text = text[1:].lstrip()
    m = _FENCE.match(text)
    if m:
        return m.group(1).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 2 and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _extract_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _fallback_json_strings(raw: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    unwrapped = _unwrap_json_text(raw)
    for blob in (_extract_balanced_object(unwrapped), _extract_balanced_object(raw)):
        if blob and blob not in seen:
            seen.add(blob)
            out.append(blob)
    return out


def parse_list_edit_result(raw: str, *, log_failures: bool = True) -> ListEditResult:
    unwrapped = _unwrap_json_text(raw)
    try:
        data = json.loads(unwrapped)
    except json.JSONDecodeError as e:
        if log_failures:
            logger.warning("Model output is not valid JSON: %s", e)
        raise ValueError("Model returned invalid JSON") from e
    if not isinstance(data, dict):
        if log_failures:
            logger.warning("Model JSON root is %s, expected object", type(data).__name__)
        raise ValueError("Model returned JSON that is not an object")
    try:
        return ListEditResult.model_validate(data)
    except ValidationError as e:
        if log_failures:
            logger.warning("Model JSON failed validation: %s", e)
        raise ValueError("Model output does not match expected schema") from e


def parse_list_edit_result_loose(raw: str) -> ListEditResult:
    """Parse structured output; try fence unwrap, then balanced `{...}` extraction."""
    first: ValueError | None = None
    try:
        return parse_list_edit_result(raw, log_failures=False)
    except ValueError as e:
        first = e
    for candidate in _fallback_json_strings(raw):
        try:
            return parse_list_edit_result(candidate, log_failures=False)
        except ValueError:
            continue
    assert first is not None
    logger.warning("Structured output parse failed after fallbacks: %s", first)
    raise first
