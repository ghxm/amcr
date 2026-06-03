"""Fetch an album from the public catalog (with tracks and preview URLs).

Library tracks don't expose preview URLs; catalog tracks do. The catalog
endpoint also gives us the canonical music.apple.com URL and the artwork
URL template we hotlink in templates.

CLI:
    python -m src.catalog <catalog_album_id> [<storefront>]
        Fetch and pretty-print the cached JSON we'd write for this album.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass

from dotenv import load_dotenv

from .api import get


@dataclass
class Track:
    n: int               # disc-aware track number in album order
    title: str
    duration_ms: int
    preview_url: str | None


@dataclass
class CachedAlbum:
    id: str              # catalog album ID
    artist: str
    album: str
    year: int | None
    apple_music_url: str
    artwork_url_template: str  # e.g. "https://.../{w}x{h}bb.jpg"
    artwork_bg_color: str | None
    tracks: list[Track]


def _storefront() -> str:
    load_dotenv()
    return os.environ.get("APPLE_STOREFRONT", "de")


def _language() -> str:
    load_dotenv()
    return os.environ.get("APPLE_LANGUAGE", "en-US")


def fetch_album(
    catalog_id: str,
    storefront: str | None = None,
    language: str | None = None,
) -> CachedAlbum:
    sf = storefront or _storefront()
    lang = language or _language()
    resp = get(
        f"/v1/catalog/{sf}/albums/{catalog_id}",
        params={"include": "tracks", "l": lang},
        user=False,  # catalog endpoints only need the developer token
    )
    data = resp["data"][0]
    attrs = data["attributes"]
    artwork = attrs.get("artwork", {}) or {}

    year: int | None = None
    release = attrs.get("releaseDate", "")
    if release[:4].isdigit():
        year = int(release[:4])

    tracks: list[Track] = []
    for i, item in enumerate(
        data.get("relationships", {}).get("tracks", {}).get("data", []),
        start=1,
    ):
        t_attrs = item.get("attributes", {})
        previews = t_attrs.get("previews") or []
        tracks.append(
            Track(
                n=i,
                title=t_attrs.get("name", "Untitled"),
                duration_ms=int(t_attrs.get("durationInMillis", 0)),
                preview_url=previews[0].get("url") if previews else None,
            )
        )

    return CachedAlbum(
        id=catalog_id,
        artist=attrs.get("artistName", "Unknown Artist"),
        album=attrs.get("name", "Untitled"),
        year=year,
        apple_music_url=attrs.get("url", ""),
        artwork_url_template=artwork.get("url", ""),
        artwork_bg_color=artwork.get("bgColor"),
        tracks=tracks,
    )


def fetch_library_album(library_id: str, language: str | None = None) -> CachedAlbum:
    """Build a CachedAlbum from a library-only (uploaded) album.

    These have no catalog match, so no preview URLs and no music.apple.com
    URL. Artwork and bgColor are taken from the library item attributes
    when present. Track list comes from the embedded tracks relationship
    (Apple caps at 100 per page; uploads exceeding that are not paginated
    here, intentional KISS).
    """
    lang = language or _language()
    resp = get(
        f"/v1/me/library/albums/{library_id}",
        params={"include": "tracks", "l": lang, "limit[tracks]": 100},
        user=True,
    )
    data = resp["data"][0]
    attrs = data["attributes"]
    artwork = attrs.get("artwork", {}) or {}

    year: int | None = None
    release = attrs.get("releaseDate", "")
    if release[:4].isdigit():
        year = int(release[:4])

    tracks: list[Track] = []
    for i, item in enumerate(
        data.get("relationships", {}).get("tracks", {}).get("data", []),
        start=1,
    ):
        t_attrs = item.get("attributes", {})
        tracks.append(
            Track(
                n=i,
                title=t_attrs.get("name", "Untitled"),
                duration_ms=int(t_attrs.get("durationInMillis", 0)),
                preview_url=None,
            )
        )

    return CachedAlbum(
        id=library_id,
        artist=attrs.get("artistName", "Unknown Artist"),
        album=attrs.get("name", "Untitled"),
        year=year,
        apple_music_url="",
        artwork_url_template=artwork.get("url", ""),
        artwork_bg_color=artwork.get("bgColor"),
        tracks=tracks,
    )


def to_dict(album: CachedAlbum) -> dict:
    d = asdict(album)
    return d


def _main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m src.catalog <catalog_album_id> [<storefront>] [<language>]",
              file=sys.stderr)
        return 2
    cid = sys.argv[1]
    sf = sys.argv[2] if len(sys.argv) > 2 else None
    lang = sys.argv[3] if len(sys.argv) > 3 else None
    print(json.dumps(to_dict(fetch_album(cid, sf, lang)), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
