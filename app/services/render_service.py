from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import sys
from functools import lru_cache
import textwrap

from gtts import gTTS

from app.core.config import get_settings
from app.models.clip_candidate import ClipCandidate
from app.models.clip_job import ClipJob
from app.services.openrouter_service import clean_transcript_with_llm, generate_hook_text, generate_thumbnail_text
from app.services.storage_service import upload_clip_and_get_signed_url, upload_file_and_get_signed_url
from app.services.subtitle_service import (
    align_cleaned_words_to_timestamps,
    burn_subtitles,
    generate_word_level_ass,
    transcribe_with_word_timestamps,
)

logger = logging.getLogger(__name__)


@dataclass
class RenderArtifacts:
    final_video_storage_path: str
    final_video_signed_url: str
    thumbnail_storage_path: str
    thumbnail_signed_url: str
    hook_text: str
    local_final_video_path: str
    local_thumbnail_path: str


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


def _run_command(command: list[str], timeout_seconds: int | None = None) -> None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Command timed out after {timeout_seconds}s: {' '.join(command)}"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit={result.returncode}): {' '.join(command)} | stderr={result.stderr}"
        )


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
    cleaned = value.strip()
    return (
        cleaned.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _wrap_text_for_overlay(value: str, max_chars_per_line: int = 16, max_lines: int = 3) -> str:
    normalized = " ".join((value or "").split())
    if not normalized:
        return ""

    wrapped = textwrap.wrap(normalized, width=max_chars_per_line, break_long_words=False, break_on_hyphens=False)
    if len(wrapped) > max_lines:
        wrapped = wrapped[:max_lines]
        if len(wrapped[-1]) >= 3:
            wrapped[-1] = f"{wrapped[-1][:-3]}..."
        else:
            wrapped[-1] = f"{wrapped[-1]}..."
    return "\n".join(wrapped)


def _normalize_drawtext_file_content(value: str) -> str:
    # ffmpeg drawtext can render CR/control characters as visible glyph boxes.
    normalized = (value or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n").replace("\u2029", "\n")
    cleaned_chars: list[str] = []
    for char in normalized:
        if char == "\n" or char == "\t" or char.isprintable():
            cleaned_chars.append(char)
    return "".join(cleaned_chars)


def _escape_drawtext_value(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _build_multiline_drawtext(
    *,
    font_path: Path,
    text: str,
    font_size: int,
    line_spacing: int,
    box_border: int,
    box_color: str,
    border_width: int,
    border_color: str,
    enable_expr: str | None = None,
) -> str:
    lines = [line.strip() for line in _normalize_drawtext_file_content(text).split("\n") if line.strip()]
    if not lines:
        return ""

    safe_font = str(font_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    line_height = font_size + line_spacing
    total_height = (len(lines) * font_size) + ((len(lines) - 1) * line_spacing)
    start_y = f"(h-{total_height})/2"

    filters: list[str] = []

    for index, line in enumerate(lines):
        y_expr = start_y if index == 0 else f"{start_y}+{index * line_height}"
        filter_expr = (
            "drawtext="
            f"fontfile='{safe_font}':"
            f"text='{_escape_drawtext_value(line)}':"
            f"fontcolor=white:fontsize={font_size}:"
            "x=(w-text_w)/2:"
            f"y={y_expr}:"
            f"borderw={border_width}:bordercolor={border_color}"
        )
        if enable_expr:
            filter_expr += f":enable='{enable_expr}'"
        filters.append(filter_expr)
    return ",".join(filters)


def _resolve_font_path(configured_font_path: str) -> Path:
    configured_font = Path(configured_font_path).expanduser()
    fallback_fonts = [
        configured_font,
        Path("/Library/Fonts/Montserrat-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Verdana Bold.ttf"),
    ]
    font_path = next((candidate for candidate in fallback_fonts if candidate.exists()), None)
    if not font_path:
        raise RuntimeError(
            "Thumbnail/video text font file not found. Set RENDER_THUMBNAIL_FONT_PATH to a valid .ttf path."
        )
    if font_path != configured_font:
        logger.warning(
            "Configured text font not found at %s, using fallback font %s",
            configured_font,
            font_path,
        )
    return font_path


def _get_audio_duration_seconds(audio_path: str, ffmpeg_binary: str) -> float:
    ffprobe_binary = str(Path(ffmpeg_binary).with_name("ffprobe"))
    if not Path(ffprobe_binary).exists():
        ffprobe_binary = "ffprobe"

    result = subprocess.run(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed while reading intro duration: {result.stderr}")
    try:
        return max(0.01, float(result.stdout.strip()))
    except ValueError as exc:
        raise RuntimeError(f"Invalid intro duration value from ffprobe: {result.stdout!r}") from exc


def generate_intro_audio(text: str, output_dir: str | None = None) -> str:
    settings = get_settings()
    base_dir = Path(output_dir) if output_dir else Path(settings.temp_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    raw_output_path = base_dir / "intro_raw.mp3"
    output_path = base_dir / "intro.mp3"
    tts = gTTS(text=text.strip() or "Ini yang orang nggak tahu", lang=settings.render_intro_voice_lang)
    tts.save(str(raw_output_path))

    intro_voice_speed = min(2.0, max(0.5, float(settings.render_intro_voice_speed)))
    if abs(intro_voice_speed - 1.0) < 0.01:
        shutil.move(str(raw_output_path), str(output_path))
        return str(output_path)

    _run_command(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(raw_output_path),
            "-filter:a",
            f"atempo={intro_voice_speed:.2f}",
            "-vn",
            str(output_path),
        ],
        timeout_seconds=settings.render_command_timeout_seconds,
    )
    return str(output_path)


def merge_intro_with_video(
    intro_audio_path: str,
    clip_video_path: str,
    hook_text: str,
    output_dir: str | None = None,
) -> str:
    settings = get_settings()
    base_dir = Path(output_dir) if output_dir else Path(settings.temp_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    output_path = base_dir / "final_with_intro.mp4"
    intro_duration = _get_audio_duration_seconds(intro_audio_path, settings.ffmpeg_binary)
    intro_duration_str = f"{intro_duration:.3f}"

    # Keep the rendered 9:16 video stream and prepend intro audio at the beginning.
    # Video gets a cloned-frame intro segment with the same duration as intro audio.
    video_chain = f"tpad=start_duration={intro_duration_str}:start_mode=clone"
    if settings.render_hook_text_overlay_enabled and hook_text.strip():
        font_path = _resolve_font_path(settings.render_thumbnail_font_path)
        wrapped_hook = _wrap_text_for_overlay(
            hook_text,
            max_chars_per_line=max(8, settings.render_hook_text_max_chars_per_line),
            max_lines=max(1, settings.render_hook_text_max_lines),
        )
        overlay_seconds = max(1, int(settings.render_hook_text_overlay_seconds))
        overlay_filter = _build_multiline_drawtext(
            font_path=font_path,
            text=wrapped_hook,
            font_size=56,
            line_spacing=12,
            box_border=26,
            box_color="black@0.72",
            border_width=4,
            border_color="black",
            enable_expr=f"between(t,0,{overlay_seconds})",
        )
        if overlay_filter:
            video_chain += f",{overlay_filter}"

    filter_complex = (
        f"[0:v]{video_chain}[v];"
        f"[1:a]atrim=0:{intro_duration_str},asetpts=PTS-STARTPTS[ia];"
        "[0:a]asetpts=PTS-STARTPTS[ca];"
        "[ia][ca]concat=n=2:v=0:a=1[a]"
    )

    _run_command(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            clip_video_path,
            "-i",
            intro_audio_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-threads",
            str(max(1, settings.render_ffmpeg_threads)),
            "-preset",
            settings.render_video_preset,
            "-crf",
            str(settings.render_video_crf),
            "-c:a",
            "aac",
            "-b:a",
            settings.render_audio_bitrate,
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        timeout_seconds=settings.render_command_timeout_seconds,
    )
    return str(output_path)


def generate_thumbnail(video_path: str, thumbnail_text: str, output_dir: str | None = None) -> str:
    settings = get_settings()
    base_dir = Path(output_dir) if output_dir else Path(settings.temp_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    output_path = base_dir / "thumbnail.jpg"

    font_path = _resolve_font_path(settings.render_thumbnail_font_path)

    has_drawtext = _ffmpeg_has_filter(settings.ffmpeg_binary, "drawtext")
    if not has_drawtext:
        raise RuntimeError("FFmpeg build has no drawtext filter support for thumbnail rendering.")

    wrapped_thumbnail = _wrap_text_for_overlay(
        thumbnail_text,
        max_chars_per_line=max(8, settings.render_hook_text_max_chars_per_line),
        max_lines=max(1, settings.render_hook_text_max_lines),
    )
    logger.info("Rendering thumbnail with text: %r", wrapped_thumbnail)
    drawtext = _build_multiline_drawtext(
        font_path=font_path,
        text=wrapped_thumbnail,
        font_size=32,
        line_spacing=12,
        box_border=24,
        box_color="black@0.72",
        border_width=4,
        border_color="black",
    )

    _run_command(
        [
            settings.ffmpeg_binary,
            "-y",
            "-ss",
            "2",
            "-i",
            video_path,
            "-frames:v",
            "1",
            "-vf",
            drawtext,
            str(output_path),
        ],
        timeout_seconds=settings.render_command_timeout_seconds,
    )
    return str(output_path)


def _download_youtube_video(
    youtube_url: str,
    output_pattern: str,
    ytdlp_binary: str,
    ytdlp_format: str,
    timeout_seconds: int,
) -> Path:
    ffmpeg_location = shutil.which(get_settings().ffmpeg_binary) or get_settings().ffmpeg_binary
    js_runtime = shutil.which("node")

    common_args = [
        "--no-playlist",
        "--ffmpeg-location",
        ffmpeg_location,
        "-o",
        output_pattern,
        youtube_url,
    ]
    if js_runtime:
        common_args = ["--js-runtimes", f"node:{js_runtime}", *common_args]

    if shutil.which(ytdlp_binary):
        command = [
            ytdlp_binary,
            "-f",
            ytdlp_format,
            "--merge-output-format",
            "mp4",
            *common_args,
        ]
        fallback_command = [
            ytdlp_binary,
            "-f",
            "b[ext=mp4]/best[ext=mp4]/best",
            *common_args,
        ]
    else:
        # Fallback when yt-dlp executable is not on PATH but package exists in venv.
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            ytdlp_format,
            "--merge-output-format",
            "mp4",
            *common_args,
        ]
        fallback_command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "b[ext=mp4]/best[ext=mp4]/best",
            *common_args,
        ]

    try:
        _run_command(command, timeout_seconds=timeout_seconds)
    except RuntimeError:
        # Retry with a simpler single-stream format when merge/conversion fails.
        _run_command(fallback_command, timeout_seconds=timeout_seconds)

    parent = Path(output_pattern).parent
    candidates = sorted(parent.glob("source.*"))
    if not candidates:
        raise RuntimeError("yt-dlp finished but source file not found")
    return candidates[0]


def render_candidate_and_upload(job: ClipJob, candidate: ClipCandidate) -> RenderArtifacts:
    """Render candidate clip, prepend intro voice, generate thumbnail, and upload artifacts."""

    settings = get_settings()
    _ensure_ffmpeg_available(settings.ffmpeg_binary)
    temp_root = Path(settings.temp_dir)
    temp_root.mkdir(parents=True, exist_ok=True)

    duration = max(0.1, candidate.end_time - candidate.start_time)

    with tempfile.TemporaryDirectory(dir=temp_root) as temp_dir:
        tmp = Path(temp_dir)
        source_pattern = str(tmp / "source.%(ext)s")
        source_file = _download_youtube_video(
            job.youtube_url,
            source_pattern,
            settings.ytdlp_binary,
            settings.ytdlp_format,
            timeout_seconds=settings.render_command_timeout_seconds,
        )

        output_path = tmp / "output.mp4"
        target_width = max(360, settings.render_target_width)
        target_height = max(640, settings.render_target_height)
        color_grading_layer = ""
        if settings.render_color_grading_enabled:
            color_grading_layer = (
                ",eq="
                f"contrast={settings.render_color_grading_contrast}:"
                f"brightness={settings.render_color_grading_brightness}:"
                f"saturation={settings.render_color_grading_saturation}"
            )

        vf = (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height},"
            f"setsar=1{color_grading_layer}"
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
                "-threads",
                str(max(1, settings.render_ffmpeg_threads)),
                "-preset",
                settings.render_video_preset,
                "-crf",
                str(settings.render_video_crf),
                "-c:a",
                "aac",
                "-b:a",
                settings.render_audio_bitrate,
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            timeout_seconds=settings.render_command_timeout_seconds,
        )

        rendered_clip_path = output_path
        if settings.render_burn_subtitle:
            try:
                whisper_words = transcribe_with_word_timestamps(str(output_path))
                whisper_text = " ".join(item.word for item in whisper_words)
                cleaned_text = clean_transcript_with_llm(whisper_text)
                aligned_words = align_cleaned_words_to_timestamps(whisper_words, cleaned_text)
                ass_path = tmp / "word_level_subtitles.ass"
                generate_word_level_ass(
                    aligned_words,
                    str(ass_path),
                    video_width=target_width,
                    video_height=target_height,
                )
                subtitled_output_path = tmp / "output_subtitled.mp4"
                burn_subtitles(str(output_path), str(ass_path), str(subtitled_output_path))
                rendered_clip_path = subtitled_output_path
            except Exception as exc:
                logger.warning("Word-level subtitle pipeline failed, continuing without burned subtitles: %s", exc)

        hook_text = generate_hook_text(candidate.transcript_snippet)
        intro_audio_path = generate_intro_audio(hook_text, output_dir=str(tmp))
        final_video_local_path = merge_intro_with_video(
            intro_audio_path,
            str(rendered_clip_path),
            hook_text,
            output_dir=str(tmp),
        )
        thumbnail_text = generate_thumbnail_text(candidate.transcript_snippet)
        thumbnail_local_path = generate_thumbnail(str(output_path), thumbnail_text, output_dir=str(tmp))

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        final_video_storage_path = f"renders/{job.id}/{candidate.id}_{timestamp}_final_with_intro.mp4"
        final_video_signed_url = upload_clip_and_get_signed_url(final_video_local_path, final_video_storage_path)

        thumbnail_storage_path = f"renders/{job.id}/{candidate.id}_{timestamp}_thumbnail.jpg"
        thumbnail_signed_url = upload_file_and_get_signed_url(
            thumbnail_local_path,
            thumbnail_storage_path,
            content_type="image/jpeg",
        )

    return RenderArtifacts(
        final_video_storage_path=final_video_storage_path,
        final_video_signed_url=final_video_signed_url,
        thumbnail_storage_path=thumbnail_storage_path,
        thumbnail_signed_url=thumbnail_signed_url,
        hook_text=hook_text,
        local_final_video_path=final_video_local_path,
        local_thumbnail_path=thumbnail_local_path,
    )
