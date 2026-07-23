import os
from dataclasses import dataclass

REQUIRED_VARS = ("DATABASE_URL", "OBJECT_STORE_ROOT", "COMFYUI_BASE_URL", "UTCC_OFFICIAL_DOMAIN")


class MissingConfigError(RuntimeError):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingConfigError(f"required environment variable {name} is not set")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    object_store_root: str
    comfyui_base_url: str
    utcc_official_domain: str


def load_settings() -> Settings:
    return Settings(
        database_url=_require("DATABASE_URL"),
        object_store_root=_require("OBJECT_STORE_ROOT"),
        comfyui_base_url=_require("COMFYUI_BASE_URL"),
        utcc_official_domain=_require("UTCC_OFFICIAL_DOMAIN"),
    )
