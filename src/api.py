"""Thin Apple Music API client.

Centralises auth headers, base URL, retries, and the typed errors that the
rest of the code distinguishes between (config errors vs expired user token
vs everything else). Keeping this in one place means library.py and catalog.py
don't each reinvent header handling.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from .auth import AuthConfigError, make_developer_token

BASE_URL = "https://api.music.apple.com"


class UserTokenExpired(RuntimeError):
    """HTTP 401 from a /me/* endpoint. The user token needs re-minting."""


class AppleAPIError(RuntimeError):
    """Non-401 HTTP error from Apple Music API."""


def _user_token() -> str:
    load_dotenv()
    tok = os.environ.get("APPLE_MUSIC_USER_TOKEN")
    if not tok:
        raise AuthConfigError(
            "APPLE_MUSIC_USER_TOKEN is not set. "
            "Mint one via tools/mint_user_token.html."
        )
    return tok


def get(path: str, *, params: dict[str, Any] | None = None, user: bool = False) -> dict:
    """GET a single Apple Music API path.

    Args:
        path: Path component, e.g. '/v1/me/library/albums'.
        params: Query params.
        user: If True, include the Music-User-Token header (required for /me/*).
    """
    headers = {"Authorization": f"Bearer {make_developer_token()}"}
    if user:
        headers["Music-User-Token"] = _user_token()

    url = BASE_URL + path
    # One retry on 5xx / network blip; Apple is generally reliable.
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
        except requests.RequestException as e:
            last_exc = e
            time.sleep(1.5)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 401 and user:
            raise UserTokenExpired(
                "Apple returned 401 on a user-scoped request. "
                "Re-mint APPLE_MUSIC_USER_TOKEN via tools/mint_user_token.html."
            )
        if 500 <= r.status_code < 600 and attempt == 0:
            time.sleep(1.5)
            continue
        raise AppleAPIError(f"HTTP {r.status_code} for {url}: {r.text[:300]}")
    raise AppleAPIError(f"Network error for {url}: {last_exc}")
