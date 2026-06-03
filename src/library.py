"""List the user's Apple Music library albums.

We need the catalog ID (not the library ID) for every album, because preview
URLs only exist on catalog tracks. The catalog ID is exposed via
relationships.catalog.data[0].id when the request includes 'catalog'.
Albums that aren't matched to the public catalog (e.g. user uploads,
region-unavailable items) have an empty catalog relationship; we surface
them with catalog_id=None and let the sampler filter them out.

CLI:
    python -m src.library
        Print "N albums" and the first five (artist - name [catalog_id]).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from .api import get


@dataclass(frozen=True)
class LibraryAlbum:
    library_id: str
    catalog_id: str | None  # None for purely user-uploaded items
    artist: str
    name: str
    artwork_url_template: str  # populated for uploads so we can still render a cover
    artwork_bg_color: str | None


def list_albums(page_size: int = 100) -> list[LibraryAlbum]:
    """Return every album in the user's library (paginated under the hood)."""
    out: list[LibraryAlbum] = []
    offset = 0
    while True:
        resp = get(
            "/v1/me/library/albums",
            params={"limit": page_size, "offset": offset, "include": "catalog"},
            user=True,
        )
        for item in resp.get("data", []):
            attrs = item.get("attributes", {})
            cat_data = (
                item.get("relationships", {}).get("catalog", {}).get("data") or []
            )
            catalog_id = cat_data[0]["id"] if cat_data else None
            artwork = attrs.get("artwork", {}) or {}
            out.append(
                LibraryAlbum(
                    library_id=item.get("id", ""),
                    catalog_id=catalog_id,
                    artist=attrs.get("artistName", "Unknown Artist"),
                    name=attrs.get("name", "Untitled"),
                    artwork_url_template=artwork.get("url", ""),
                    artwork_bg_color=artwork.get("bgColor"),
                )
            )
        if "next" not in resp:
            break
        offset += page_size
    return out


def _main() -> int:
    albums = list_albums()
    print(f"{len(albums)} albums in library "
          f"({sum(1 for a in albums if a.catalog_id)} have catalog IDs)")
    for a in albums[:5]:
        cid = a.catalog_id or "<no catalog id>"
        print(f"  {a.artist} - {a.name} [{cid}]")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
