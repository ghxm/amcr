"""Read/write the append-only picks ledger (data/picks.csv).

Schema: date, album_id, storefront, fetched_at

Kept tiny on purpose. The ledger is the source of truth for "what was
picked on which day"; album details live in data/cache/<id>.json.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PICKS_PATH = Path(__file__).resolve().parent.parent / "data" / "picks.csv"
FIELDNAMES = ["date", "album_id", "storefront", "fetched_at"]


@dataclass(frozen=True)
class Pick:
    date: str        # YYYY-MM-DD (local timezone of the run)
    album_id: str    # catalog album id
    storefront: str  # storefront the album was fetched from
    fetched_at: str  # ISO-8601 UTC timestamp of the API fetch


def read_picks() -> list[Pick]:
    if not PICKS_PATH.exists():
        return []
    with PICKS_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [Pick(**row) for row in reader if row.get("date")]


def append_pick(pick: Pick) -> None:
    file_exists = PICKS_PATH.exists() and PICKS_PATH.stat().st_size > 0
    PICKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PICKS_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "date": pick.date,
            "album_id": pick.album_id,
            "storefront": pick.storefront,
            "fetched_at": pick.fetched_at,
        })


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
