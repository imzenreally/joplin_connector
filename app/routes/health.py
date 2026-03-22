import logging

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.joplin_errors import JoplinError
from app.services.joplin_service import JoplinClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def joplin_dep(settings: Settings = Depends(get_settings)) -> JoplinClient:
    return JoplinClient(settings.joplin_base_url, settings.joplin_token)


@router.get("/health")
async def health(
    joplin: JoplinClient = Depends(joplin_dep),
) -> dict[str, str]:
    try:
        banner = (await joplin.ping()).strip()
    except JoplinError as e:
        logger.warning("Health: Joplin unavailable: %s", e)
        return {"status": "degraded", "joplin": "unavailable"}
    return {"status": "ok", "joplin": banner[:120]}
