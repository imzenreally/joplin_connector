from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from app.joplin_errors import JoplinAmbiguousTitleError, JoplinError, JoplinNotFoundError
from app.models import JoplinNote
from app.services.note_resolution import require_single_note_by_title

logger = logging.getLogger(__name__)


class JoplinClient:
    def __init__(self, base_url: str, token: str, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/") + "/"
        self._token = token
        self._timeout = timeout

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        p: dict[str, Any] = {"token": self._token}
        if extra:
            p.update(extra)
        return p

    async def ping(self) -> str:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.get(urljoin(self._base, "ping"), params=self._params())
                r.raise_for_status()
            except httpx.RequestError as e:
                logger.warning("Joplin ping failed: %s", e)
                raise JoplinError("Joplin unreachable") from e
            except httpx.HTTPStatusError as e:
                logger.warning("Joplin ping HTTP error: %s", e.response.status_code)
                raise JoplinError("Joplin returned an error") from e
            return r.text

    async def get_note(self, note_id: str) -> JoplinNote:
        params = self._params({"fields": "id,parent_id,title,body"})
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.get(
                    urljoin(self._base, f"notes/{note_id}"),
                    params=params,
                )
            except httpx.RequestError as e:
                raise JoplinError("Joplin unreachable") from e
            if r.status_code == httpx.codes.NOT_FOUND:
                raise JoplinNotFoundError("Note not found")
            self._raise_http(r, "get_note")
            try:
                payload = r.json()
            except ValueError as e:
                raise JoplinError("Invalid response from Joplin") from e
            return JoplinNote.model_validate(payload)

    async def search_notes(self, query: str) -> list[JoplinNote]:
        params = self._params({"query": query, "fields": "id,parent_id,title,body"})
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.get(urljoin(self._base, "search"), params=params)
            except httpx.RequestError as e:
                raise JoplinError("Joplin unreachable") from e
            self._raise_http(r, "search")
            try:
                data = r.json()
            except ValueError as e:
                logger.warning("Joplin search returned non-JSON body")
                raise JoplinError("Invalid response from Joplin search") from e
        items = data.get("items") or []
        if not isinstance(items, list):
            raise JoplinError("Invalid search response")
        notes: list[JoplinNote] = []
        for item in items:
            try:
                notes.append(JoplinNote.model_validate(item))
            except Exception:
                continue
        return notes

    async def get_note_by_title(self, title: str) -> JoplinNote:
        title = title.strip()
        if not title:
            raise JoplinNotFoundError("Empty note title")
        candidates = await self.search_notes(title)
        return require_single_note_by_title(title, candidates)

    async def create_note(self, parent_id: str, title: str, body: str) -> JoplinNote:
        payload = {"parent_id": parent_id, "title": title, "body": body}
        params = self._params({"fields": "id,parent_id,title,body"})
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.post(
                    urljoin(self._base, "notes"),
                    params=params,
                    json=payload,
                )
            except httpx.RequestError as e:
                raise JoplinError("Joplin unreachable") from e
            self._raise_http(r, "create_note")
            try:
                payload = r.json()
            except ValueError as e:
                raise JoplinError("Invalid response from Joplin") from e
            return JoplinNote.model_validate(payload)

    async def update_note_body(self, note_id: str, body: str) -> JoplinNote:
        params = self._params({"fields": "id,parent_id,title,body"})
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                r = await client.put(
                    urljoin(self._base, f"notes/{note_id}"),
                    params=params,
                    json={"body": body},
                )
            except httpx.RequestError as e:
                raise JoplinError("Joplin unreachable") from e
            if r.status_code == httpx.codes.NOT_FOUND:
                raise JoplinNotFoundError("Note not found")
            self._raise_http(r, "update_note_body")
            try:
                payload = r.json()
            except ValueError as e:
                raise JoplinError("Invalid response from Joplin") from e
            return JoplinNote.model_validate(payload)

    @staticmethod
    def _raise_http(r: httpx.Response, op: str) -> None:
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            snippet = (e.response.text or "")[:200]
            logger.warning(
                "Joplin %s failed: %s %s body=%r",
                op,
                e.response.status_code,
                e.response.reason_phrase,
                snippet,
            )
            raise JoplinError(f"Joplin API error ({op}): {e.response.status_code}") from e


__all__ = ["JoplinClient", "JoplinError", "JoplinNotFoundError", "JoplinAmbiguousTitleError"]
