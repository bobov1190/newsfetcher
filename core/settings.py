from pydantic_settings import BaseSettings
from typing import Optional
from datetime import date, timedelta


class Settings(BaseSettings):
    mistral_api_key: str = "4xplCdRHKwQ6F565dRNPi48Sa7yVhhtu"
    default_limit: int = 50
    default_date_from: Optional[str] = None
    default_date_to: Optional[str] = None

    model_config = {"env_file": ".env"}


settings = Settings()


def get_default_date_from() -> str:
    if settings.default_date_from:
        return settings.default_date_from
    return (date.today() - timedelta(days=7)).isoformat()


def get_default_date_to() -> str:
    if settings.default_date_to:
        return settings.default_date_to
    return date.today().isoformat()
