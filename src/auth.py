"""Apple Music developer token signing.

Produces an ES256 JWT signed with the MusicKit private key (.p8). The token
is required (as Authorization: Bearer ...) on every Apple Music API call.

Env vars:
    APPLE_TEAM_ID         10-char Apple Developer team identifier.
    APPLE_KEY_ID          10-char MusicKit key identifier.
    APPLE_KEY_PATH        Path to the .p8 private-key file (local dev).
    APPLE_PRIVATE_KEY     Inline .p8 contents (used in GitHub Actions where
                          a file path is awkward). If both are set,
                          APPLE_PRIVATE_KEY wins.

CLI:
    python -m src.auth
        Smoke test: mint a token, hit /v1/storefronts/<storefront>,
        print "OK" or the HTTP error.

    python -m src.auth --print
        Mint a token and print only the JWT (for pasting into
        tools/mint_user_token.html).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import jwt
import requests
from dotenv import load_dotenv

# Apple caps developer-token lifetime at 6 months (15777000 s).
# We sign for the max so a re-build of the workflow image doesn't churn tokens.
MAX_LIFETIME_SECONDS = 15_777_000

# Smoke-test endpoint: returns the storefront object. Only needs a dev token.
STOREFRONT_URL = "https://api.music.apple.com/v1/storefronts/{code}"


class AuthConfigError(RuntimeError):
    """Raised when required env vars are missing or unreadable."""


def _read_private_key() -> str:
    inline = os.environ.get("APPLE_PRIVATE_KEY")
    if inline:
        return inline
    path = os.environ.get("APPLE_KEY_PATH")
    if not path:
        raise AuthConfigError(
            "Set APPLE_PRIVATE_KEY (inline .p8) or APPLE_KEY_PATH (file path)."
        )
    p = Path(path).expanduser()
    if not p.is_file():
        raise AuthConfigError(f"APPLE_KEY_PATH does not point to a file: {p}")
    return p.read_text()


def make_developer_token(lifetime_seconds: int = MAX_LIFETIME_SECONDS) -> str:
    """Sign and return an Apple Music developer JWT."""
    load_dotenv()

    team_id = os.environ.get("APPLE_TEAM_ID")
    key_id = os.environ.get("APPLE_KEY_ID")
    if not team_id or not key_id:
        raise AuthConfigError("APPLE_TEAM_ID and APPLE_KEY_ID must both be set.")

    private_key = _read_private_key()
    now = int(time.time())
    token = jwt.encode(
        payload={"iss": team_id, "iat": now, "exp": now + lifetime_seconds},
        key=private_key,
        algorithm="ES256",
        headers={"kid": key_id, "alg": "ES256"},
    )
    return token


def _smoke_test() -> int:
    load_dotenv()
    storefront = os.environ.get("APPLE_STOREFRONT", "de")
    try:
        token = make_developer_token()
    except AuthConfigError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 2

    r = requests.get(
        STOREFRONT_URL.format(code=storefront),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if r.status_code == 200:
        name = r.json()["data"][0]["attributes"]["name"]
        print(f"OK: developer token accepted (storefront='{storefront}' -> {name})")
        return 0
    print(f"FAIL: HTTP {r.status_code} {r.reason}", file=sys.stderr)
    print(r.text[:500], file=sys.stderr)
    return 1


def _main() -> int:
    parser = argparse.ArgumentParser(description="Apple Music developer token utility.")
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the JWT and exit (skip the API smoke test).",
    )
    args = parser.parse_args()
    if args.print:
        try:
            print(make_developer_token())
            return 0
        except AuthConfigError as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 2
    return _smoke_test()


if __name__ == "__main__":
    sys.exit(_main())
