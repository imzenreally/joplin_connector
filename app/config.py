from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    openai_api_key: str
    openai_model: str = "gpt-4o"
    joplin_base_url: str = "http://127.0.0.1:41184"
    joplin_token: str
    joplin_default_parent_id: str | None = Field(
        default=None,
        description="Notebook id used by /notes/create when parent_id is not sent",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
