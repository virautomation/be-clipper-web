from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
import shutil
import sys
from functools import lru_cache

from app.core.config import get_settings
from app.models.clip_candidate import ClipCandidate
from app.models.clip_job import ClipJob
from app.services.storage_service import upload_clip_and_get_signed_url


def _seconds_to_srt_timestamp(value: float) -> str:
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = int(value % 60)
    milliseconds = int((value - int(value)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _write_srt(path: Path, text: str, duration_seconds: float) -> None:
    srt = (
        "1\n"
        f"{_seconds_to_srt_timestamp(0.0)} --> {_seconds_to_srt_timestamp(duration_seconds)}\n"
        f"{text.strip()}\n"
    )
    path.write_text(srt, encoding="utf-8")


def _run_command(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(command)} | stderr={result.stderr}")


def _ensure_ffmpeg_available(ffmpeg_binary: str) -> None:
    if shutil.which(ffmpeg_binary):
        return
    raise RuntimeError(
        f"FFmpeg binary not found: '{ffmpeg_binary}'. Install ffmpeg or set FFMPEG_BINARY to full path."
    )


@lru_cache(maxsize=4)
def _ffmpeg_has_filter(ffmpeg_binary: str, filter_name: str) -> bool:
    result = subprocess.run([ffmpeg_binary, "-hide_banner", "-filters"], capture_output=True, text=True)
    if result.returncode != 0:
        return False
    return f" {filter_name} " in result.stdout or result.stdout.strip().endswith(filter_name)


def _escape_drawtext_text(value: str) -> str:
    cleaned = " ".join(value.replace("\n", " ").split())
    return (
        cleaned.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _download_youtube_video(youtube_url: str, output_pattern: str, ytdlp_binary: str) -> Path:
    if shutil.which(ytdlp_binary):
        command = [ytdlp_binary, "-f", "mp4", "-o", output_pattern, youtube_url]
    else:
        # Fallback when yt-dlp executable is not on PATH but package exists in venv.
        command = [sys.executable, "-m", "yt_dlp", "-f", "mp4", "-o", output_pattern, youtube_url]

    _run_command(command)
    parent = Path(output_pattern).parent
    candidates = sorted(parent.glob("source.*"))
    if not candidates:
        raise RuntimeError("yt-dlp finished but source file not found")
    return candidates[0]


def render_candidate_and_upload(job: ClipJob, candidate: ClipCandidate) -> tuple[str, str]:
    """Render candidate clip to 9:16 with burned subtitles and upload to storage."""

    settings = get_settings()
    _ensure_ffmpeg_available(settings.ffmpeg_binary)
    temp_root = Path(settings.temp_dir)
    temp_root.mkdir(parents=True, exist_ok=True)

    duration = max(0.1, candidate.end_time - candidate.start_time)

    with tempfile.TemporaryDirectory(dir=temp_root) as temp_dir:
        tmp = Path(temp_dir)
        source_pattern = str(tmp / "source.%(ext)s")
        source_file = _download_youtube_video(job.youtube_url, source_pattern, settings.ytdlp_binary)

        subtitle_path = tmp / "subtitle.srt"
        _write_srt(subtitle_path, candidate.transcript_snippet, duration)

        output_path = tmp / "output.mp4"
        subtitle_filter_path = (
            str(subtitle_path)
            .replace("\\", "/")
            .replace("'", "\\'")
            .replace(":", "\\:")
        )

        has_subtitles = _ffmpeg_has_filter(settings.ffmpeg_binary, "subtitles")
        has_drawtext = _ffmpeg_has_filter(settings.ffmpeg_binary, "drawtext")

        if has_subtitles:
            subtitle_layer = f"subtitles=filename='{subtitle_filter_path}'"
        elif has_drawtext:
            drawtext = _escape_drawtext_text(candidate.transcript_snippet)
            subtitle_layer = (
                "drawtext="
                f"text='{drawtext}':"
                "fontcolor=white:fontsize=44:"
                "x=(w-text_w)/2:y=h-(text_h*2):"
                "box=1:boxcolor=black@0.5:boxborderw=18"
            )
        else:
            raise RuntimeError(
                "FFmpeg build has no subtitle-capable filter. Install FFmpeg with 'subtitles' (libass) "
                "or 'drawtext' (libfreetype) support."
            )

        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            f"{subtitle_layer}"
        )

        _run_command(
            [
                settings.ffmpeg_binary,
                "-y",
                "-ss",
                str(candidate.start_time),
                "-to",
                str(candidate.end_time),
                "-i",
                str(source_file),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        storage_path = f"renders/{job.id}/{candidate.id}_{timestamp}.mp4"
        signed_url = upload_clip_and_get_signed_url(str(output_path), storage_path)

    return storage_path, signed_url
