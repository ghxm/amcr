"""Load config.yaml once and expose it as a typed-ish object.

Env vars override file values where applicable so GH Actions can change
behaviour without touching the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass(frozen=True)
class ArtworkSizes:
    day_page: int
    archive_tile: int


@dataclass(frozen=True)
class SiteMeta:
    title: str
    description: str
    url: str


@dataclass(frozen=True)
class Config:
    storefront: str
    timezone: str
    artwork: ArtworkSizes
    site: SiteMeta
    accent_enabled: bool


def _truthy(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Config:
    load_dotenv()
    raw = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    art = raw.get("artwork", {})
    site = raw.get("site", {})
    return Config(
        storefront=os.environ.get("APPLE_STOREFRONT") or raw.get("storefront", "us"),
        timezone=os.environ.get("TIMEZONE") or raw.get("timezone", "UTC"),
        artwork=ArtworkSizes(
            day_page=int(art.get("day_page", 1200)),
            archive_tile=int(art.get("archive_tile", 400)),
        ),
        site=SiteMeta(
            title=site.get("title", "one album"),
            description=site.get("description", ""),
            url=site.get("url", ""),
        ),
        accent_enabled=_truthy(
            os.environ.get("ACCENT_ENABLED"),
            bool(raw.get("accent_enabled", True)),
        ),
    )
