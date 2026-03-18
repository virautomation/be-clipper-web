from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Any

from app.core.config import get_settings


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _score_entry(entry: dict[str, Any], keyword: str, rank_index: int) -> float:
    title = _normalize(str(entry.get("title", "")))
    description = _normalize(str(entry.get("description", "")))
    keyword_norm = _normalize(keyword)

    title_hits = title.count(keyword_norm)
    description_hits = description.count(keyword_norm)
    token_hits = 0
    for token in keyword_norm.split():
        if token:
            token_hits += title.count(token) * 2
            token_hits += description.count(token)

    rank_bonus = max(0, 10 - rank_index)
    duration = int(entry.get("duration") or 0)
    duration_bonus = 2 if 60 <= duration <= 1200 else 0

    return round((title_hits * 5) + (description_hits * 2) + token_hits + rank_bonus + duration_bonus, 3)


def search_videos_by_keyword(keyword: str, limit: int = 3) -> list[dict[str, Any]]:
    settings = get_settings()
    fetch_count = max(limit * 4, 8)
    search_query = f"ytsearch{fetch_count}:{keyword}"

    if shutil.which(settings.ytdlp_binary):
        command = [
            settings.ytdlp_binary,
            "--dump-single-json",
            "--skip-download",
            "--no-warnings",
            "--extractor-args",
            "youtube:skip=dash,hls",
            search_query,
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--dump-single-json",
            "--skip-download",
            "--no-warnings",
            "--extractor-args",
            "youtube:skip=dash,hls",
            search_query,
        ]

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Video discovery failed: {result.stderr.strip()}")

    payload = json.loads(result.stdout)
    entries = payload.get("entries", []) if isinstance(payload, dict) else []

    discovered: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue

        video_id = str(entry.get("id") or "").strip()
        title = str(entry.get("title") or "").strip()
        if not video_id or not title:
            continue

        youtube_url = str(entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}")
        channel = str(entry.get("channel") or entry.get("uploader") or "Unknown channel")
        thumbnail = str(entry.get("thumbnail") or "")
        duration_seconds = int(entry.get("duration") or 0)

        discovered.append(
            {
                "youtube_url": youtube_url,
                "youtube_video_id": video_id,
                "title": title,
                "channel": channel,
                "thumbnail_url": thumbnail,
                "duration_seconds": duration_seconds,
                "relevance_score": _score_entry(entry, keyword, idx),
            }
        )

    discovered.sort(key=lambda item: item["relevance_score"], reverse=True)
    return discovered[:limit]
