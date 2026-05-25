"""Render picks.csv + cached album JSONs into the static site in public/.

Flow:
  1. Read picks.csv, sort by date ascending.
  2. For each pick, load data/cache/<id>.json.
  3. Render YYYY-MM-DD.html using day.html, computing prev/next from
     neighbouring picks.
  4. Render archive.html (cover-tile grid, reverse chronological).
  5. Render index.html as the latest day's page, with a canonical link to
     its YYYY-MM-DD.html so search engines/share previews are stable.
  6. Copy static/style.css and static/player.js to public/.

CLI:
    python -m src.build
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Config, load_config
from .picks import read_picks

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
CACHE_DIR = ROOT / "data" / "cache"
PUBLIC_DIR = ROOT / "public"


def _artwork(template: str, size: int) -> str:
    """Substitute Apple's {w}x{h} placeholders in the artwork URL template."""
    if not template:
        return ""
    return template.replace("{w}", str(size)).replace("{h}", str(size))


def _duration_str(ms: int) -> str:
    total = max(0, ms // 1000)
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _load_album(album_id: str) -> dict:
    path = CACHE_DIR / f"{album_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _wipe_public() -> None:
    if PUBLIC_DIR.exists():
        for child in PUBLIC_DIR.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)


def _site_url_for(cfg: Config, page: str) -> str:
    base = cfg.site.url.rstrip("/")
    return f"{base}/{page}" if base else ""


def render_all(cfg: Config) -> int:
    picks = sorted(read_picks(), key=lambda p: p.date)
    if not picks:
        print("FAIL: picks.csv is empty; run `python -m src.sample` first.",
              file=sys.stderr)
        return 1

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    day_tpl = env.get_template("day.html")
    arch_tpl = env.get_template("archive.html")
    sitemap_tpl = env.get_template("sitemap.xml")
    feed_tpl = env.get_template("feed.xml")

    _wipe_public()

    # Pre-load all albums (small JSON, fast). Keeps the render loops simple.
    cache: dict[str, dict] = {p.album_id: _load_album(p.album_id) for p in picks}

    # ---- day pages ----
    site_meta = {
        "title": cfg.site.title,
        "description": cfg.site.description,
        "url": cfg.site.url,
    }
    for i, p in enumerate(picks):
        album = cache[p.album_id]
        prev_date = picks[i - 1].date if i > 0 else None
        next_date = picks[i + 1].date if i < len(picks) - 1 else None

        tracks = [
            {**t, "duration_str": _duration_str(int(t.get("duration_ms", 0)))}
            for t in album["tracks"]
        ]
        album_view = {**album, "tracks": tracks}

        art = album.get("artwork_url_template", "")
        ctx = {
            "site": site_meta,
            "date": p.date,
            "prev_date": prev_date,
            "next_date": next_date,
            "album": album_view,
            "artwork_size": cfg.artwork.day_page,
            "artwork_1x": _artwork(art, cfg.artwork.day_page),
            "artwork_2x": _artwork(art, cfg.artwork.day_page * 2),
            "artwork_og": _artwork(art, 1200),
            "accent_color": album.get("artwork_bg_color") if cfg.accent_enabled else None,
            "canonical_url": _site_url_for(cfg, f"{p.date}.html"),
        }
        (PUBLIC_DIR / f"{p.date}.html").write_text(
            day_tpl.render(**ctx), encoding="utf-8"
        )

    # ---- index = latest day, with canonical pointing at its dated URL ----
    latest = picks[-1]
    album = cache[latest.album_id]
    art = album.get("artwork_url_template", "")
    tracks = [
        {**t, "duration_str": _duration_str(int(t.get("duration_ms", 0)))}
        for t in album["tracks"]
    ]
    album_view = {**album, "tracks": tracks}
    index_ctx = {
        "site": site_meta,
        "date": latest.date,
        "prev_date": picks[-2].date if len(picks) > 1 else None,
        "next_date": None,
        "album": album_view,
        "artwork_size": cfg.artwork.day_page,
        "artwork_1x": _artwork(art, cfg.artwork.day_page),
        "artwork_2x": _artwork(art, cfg.artwork.day_page * 2),
        "artwork_og": _artwork(art, 1200),
        "accent_color": album.get("artwork_bg_color"),
        "canonical_url": _site_url_for(cfg, f"{latest.date}.html"),
    }
    (PUBLIC_DIR / "index.html").write_text(
        day_tpl.render(**index_ctx), encoding="utf-8"
    )

    # ---- archive ----
    tiles = []
    for p in sorted(picks, key=lambda x: x.date, reverse=True):
        album = cache[p.album_id]
        art = album.get("artwork_url_template", "")
        tiles.append({
            "date": p.date,
            "artist": album.get("artist", ""),
            "album": album.get("album", ""),
            "art_1x": _artwork(art, cfg.artwork.archive_tile),
            "art_2x": _artwork(art, cfg.artwork.archive_tile * 2),
        })
    (PUBLIC_DIR / "archive.html").write_text(
        arch_tpl.render(
            site=site_meta,
            tiles=tiles,
            tile_size=cfg.artwork.archive_tile,
            canonical_url=_site_url_for(cfg, "archive.html"),
            accent_color=None,
        ),
        encoding="utf-8",
    )

    # ---- sitemap + RSS ----
    base_url = cfg.site.url.rstrip("/")
    if base_url:
        (PUBLIC_DIR / "sitemap.xml").write_text(
            sitemap_tpl.render(
                base_url=base_url,
                latest_date=latest.date,
                picks=sorted(picks, key=lambda x: x.date, reverse=True),
            ),
            encoding="utf-8",
        )

        feed_items = []
        for p in sorted(picks, key=lambda x: x.date, reverse=True):
            album = cache[p.album_id]
            art = album.get("artwork_url_template", "")
            day_midnight_utc = datetime.combine(
                datetime.strptime(p.date, "%Y-%m-%d").date(),
                time(0, 0),
                tzinfo=timezone.utc,
            )
            feed_items.append({
                "title": f"{album.get('artist', '')} - {album.get('album', '')}",
                "url": f"{base_url}/{p.date}.html",
                "pub_date_rfc822": format_datetime(day_midnight_utc),
                "artwork": _artwork(art, 600),
                "apple_music_url": album.get("apple_music_url", ""),
            })
        (PUBLIC_DIR / "feed.xml").write_text(
            feed_tpl.render(
                site=site_meta,
                base_url=base_url,
                build_date_rfc822=format_datetime(datetime.now(timezone.utc)),
                items=feed_items,
            ),
            encoding="utf-8",
        )
    else:
        print("WARN: site.url is empty; skipping sitemap.xml and feed.xml.")

    # robots.txt: allow everything, point at the sitemap when we have a URL.
    robots = "User-agent: *\nAllow: /\n"
    if base_url:
        robots += f"\nSitemap: {base_url}/sitemap.xml\n"
    (PUBLIC_DIR / "robots.txt").write_text(robots, encoding="utf-8")

    # ---- static assets ----
    shutil.copy(STATIC_DIR / "style.css", PUBLIC_DIR / "style.css")
    shutil.copy(STATIC_DIR / "player.js", PUBLIC_DIR / "player.js")

    extras = "+ sitemap + feed + robots" if base_url else "+ robots (sitemap/feed skipped: no site.url)"
    print(f"built {len(picks)} day page(s) + archive + index {extras} in {PUBLIC_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(render_all(load_config()))
