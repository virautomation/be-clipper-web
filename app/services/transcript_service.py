from __future__ import annotations

from typing import Any

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

_transcript_api = YouTubeTranscriptApi()


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def fetch_transcript(video_id: str) -> list[dict[str, Any]]:
    """Fetch transcript from YouTube and normalize text payload."""

    raw = _transcript_api.fetch(video_id, languages=["id", "en", "en-US"])
    normalized: list[dict[str, Any]] = []
    for item in raw:
        normalized.append(
            {
                "start": float(item.start),
                "duration": float(item.duration),
                "text": item.text.strip(),
                "normalized_text": normalize_text(item.text),
            }
        )
    return normalized


def transcript_available(video_id: str) -> bool:
    try:
        fetch_transcript(video_id)
        return True
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable):
        return False
