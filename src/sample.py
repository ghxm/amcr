"""Pick today's album, optionally backfilling missing days.

Default mode picks one unseen album for today (no-op if today is already
in picks.csv). With --backfill, picks one album for every missing date
between the last entry in picks.csv and today (exclusive of dates already
present).

Exit codes:
  0  - one or more new picks written
  78 - nothing to do (today already picked, or backfill found no gaps)
  1  - library exhausted or other fatal error
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .catalog import CachedAlbum, fetch_album, fetch_library_album, to_dict
from .config import load_config
from .library import LibraryAlbum, list_albums
from .picks import Pick, append_pick, read_picks, utc_now_iso

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _today_local(tz_name: str) -> str:
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d")


def _cache_path(album_id: str) -> Path:
    return CACHE_DIR / f"{album_id}.json"


def _ensure_cached(
    chosen: LibraryAlbum,
    storefront: str,
    language: str,
) -> CachedAlbum:
    """Return cached album metadata, fetching it on first use.

    For catalog-matched library items we hit the public catalog endpoint
    (previews + canonical URL). For pure uploads we build the same
    CachedAlbum shape from the library endpoint, with no previews and an
    empty apple_music_url.
    """
    album_id = chosen.catalog_id or chosen.library_id
    path = _cache_path(album_id)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        from .catalog import Track
        data["tracks"] = [Track(**t) for t in data.get("tracks", [])]
        return CachedAlbum(**data)
    if chosen.catalog_id:
        album = fetch_album(chosen.catalog_id, storefront, language)
    else:
        album = fetch_library_album(chosen.library_id, language)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_dict(album), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return album


def _album_id(a: LibraryAlbum) -> str:
    return a.catalog_id or a.library_id


def _pickable(
    albums: list[LibraryAlbum],
    used_ids: set[str],
    include_uploads: bool,
) -> list[LibraryAlbum]:
    return [
        a for a in albums
        if (a.catalog_id or (include_uploads and a.library_id))
        and _album_id(a) not in used_ids
    ]


def _missing_dates(existing_dates: set[str], today_str: str) -> list[str]:
    """Dates between max(existing_dates)+1 and today_str (inclusive) that
    aren't already in existing_dates. Empty if there are no gaps."""
    if not existing_dates:
        return [today_str]
    last = datetime.strptime(max(existing_dates), "%Y-%m-%d").date()
    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    out: list[str] = []
    d = last + timedelta(days=1)
    while d <= today:
        ds = d.strftime("%Y-%m-%d")
        if ds not in existing_dates:
            out.append(ds)
        d += timedelta(days=1)
    return out


def run(backfill: bool = False) -> int:
    cfg = load_config()
    today = _today_local(cfg.timezone)
    existing = read_picks()
    existing_dates = {p.date for p in existing}

    if backfill:
        dates_to_pick = _missing_dates(existing_dates, today)
        if not dates_to_pick:
            print(f"nothing to backfill (latest pick {max(existing_dates)} >= today {today})")
            return 78
    else:
        if today in existing_dates:
            already = next(p for p in existing if p.date == today)
            print(f"already picked for {today}: {already.album_id} (no-op)")
            return 78
        dates_to_pick = [today]

    used = {p.album_id for p in existing}
    print("loading library...")
    library = list_albums()
    catalog_total = sum(1 for a in library if a.catalog_id)
    upload_total = sum(1 for a in library if not a.catalog_id)
    print(
        f"library: {len(library)} albums "
        f"({catalog_total} catalog, {upload_total} uploads, "
        f"include_uploads={cfg.include_uploads})"
    )
    print(f"picking for {len(dates_to_pick)} date(s): "
          f"{dates_to_pick[0]}{' ... ' + dates_to_pick[-1] if len(dates_to_pick) > 1 else ''}")

    rng = random.SystemRandom()
    for date in dates_to_pick:
        pool = _pickable(library, used, cfg.include_uploads)
        if not pool:
            print(f"FAIL: library exhausted at {date}.", file=sys.stderr)
            return 1
        chosen = rng.choice(pool)
        album = _ensure_cached(chosen, cfg.storefront, cfg.language)
        pick_id = _album_id(chosen)
        pick = Pick(
            date=date,
            album_id=pick_id,
            storefront=cfg.storefront,
            fetched_at=utc_now_iso(),
        )
        append_pick(pick)
        used.add(pick_id)
        print(f"picked {date}: {album.artist} - {album.album} [{album.id}]")

    return 0


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Pick today's album, optionally backfilling missing days.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Pick one album per missing day since the last entry in picks.csv.",
    )
    args = parser.parse_args()
    return run(backfill=args.backfill)


if __name__ == "__main__":
    sys.exit(_main())
