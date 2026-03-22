from __future__ import annotations

import logging
from typing import Any

from openai import APIError, AsyncOpenAI, RateLimitError

from app.models import ListEditResult
from app.services import list_editor

logger = logging.getLogger(__name__)

_RETRY_HINT = (
    "\n\nYour previous reply could not be parsed. Respond with one JSON object only, "
    "matching the required schema, with no markdown code fences or extra text."
)


class OpenAINoteError(Exception):
    pass


def _response_status_error_message(response: Any) -> str | None:
    st = getattr(response, "status", None)
    if st == "incomplete":
        return "Model response was incomplete"
    if st == "failed":
        err = getattr(response, "error", None)
        return f"Model request failed: {err}" if err else "Model request failed"
    return None


def _first_refusal_text(response: Any) -> str | None:
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for block in getattr(item, "content", None) or []:
            if getattr(block, "type", None) == "refusal":
                return getattr(block, "refusal", None) or "Model refused the request"
    return None


def _extract_output_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    parts: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for block in getattr(item, "content", None) or []:
            if getattr(block, "type", None) == "output_text":
                parts.append(getattr(block, "text", "") or "")
    return "".join(parts)


class OpenAINoteService:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def _create_response(self, user_content: str) -> Any:
        schema = list_editor.structured_output_schema()
        return await self._client.responses.create(
            model=self._model,
            input=[
                {"role": "developer", "content": list_editor.SYSTEM_INSTRUCTION},
                {"role": "user", "content": user_content},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "list_edit_result",
                    "strict": True,
                    "schema": schema,
                }
            },
        )

    def _validate_response(self, response: Any) -> str:
        status_msg = _response_status_error_message(response)
        if status_msg:
            logger.warning("OpenAI response status: %s", getattr(response, "status", None))
            raise OpenAINoteError(status_msg)

        refusal = _first_refusal_text(response)
        if refusal:
            logger.warning("OpenAI model refusal")
            raise OpenAINoteError("Model refused to process this request")

        raw = _extract_output_text(response).strip()
        if not raw:
            logger.error("Empty model output (response id=%s)", getattr(response, "id", ""))
            raise OpenAINoteError("Empty model output")
        return raw

    async def edit_note_markdown(
        self,
        *,
        note_title: str,
        current_markdown: str,
        instruction: str,
    ) -> ListEditResult:
        user_msg = list_editor.build_user_message(
            note_title=note_title,
            current_markdown=current_markdown,
            instruction=instruction,
        )
        try:
            response = await self._create_response(user_msg)
        except RateLimitError as e:
            logger.warning("OpenAI rate limited: %s", e)
            raise OpenAINoteError("OpenAI rate limit exceeded") from e
        except APIError as e:
            logger.error("OpenAI API error: %s", e)
            raise OpenAINoteError("OpenAI request failed") from e

        raw = self._validate_response(response)

        try:
            return list_editor.parse_list_edit_result_loose(raw)
        except ValueError as e:
            logger.warning("Structured output parse failed, retrying once: %s", e)

        try:
            response2 = await self._create_response(user_msg + _RETRY_HINT)
        except RateLimitError as e:
            logger.warning("OpenAI rate limited on retry: %s", e)
            raise OpenAINoteError("OpenAI rate limit exceeded") from e
        except APIError as e:
            logger.error("OpenAI API error on retry: %s", e)
            raise OpenAINoteError("OpenAI request failed") from e

        raw2 = self._validate_response(response2)
        try:
            return list_editor.parse_list_edit_result_loose(raw2)
        except ValueError as e:
            logger.warning("Structured output parse failed after retry: %s", e)
            raise OpenAINoteError(str(e)) from e
