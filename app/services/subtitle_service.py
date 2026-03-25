from __future__ import annotations

from dataclasses import dataclass
import logging
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ASS_HEADER_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,{active_color},&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass(frozen=True)
class WordTimestamp:
    word: str
    start: float
    end: float


def _normalize_word(value: str) -> str:
    return re.sub(r"[^\w]+", "", (value or "").lower(), flags=re.UNICODE)


def _is_word_token(value: str) -> bool:
    return bool(re.search(r"\w", value or "", flags=re.UNICODE))


def _tokenize_text(value: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", value or "", flags=re.UNICODE)


@lru_cache(maxsize=2)
def _get_whisper_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device=device, compute_type=compute_type)


def transcribe_with_word_timestamps(input_path: str) -> list[WordTimestamp]:
    settings = get_settings()
    model = _get_whisper_model(
        settings.render_whisper_model,
        settings.render_whisper_device,
        settings.render_whisper_compute_type,
    )
    segments, _info = model.transcribe(
        input_path,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
    )

    words: list[WordTimestamp] = []
    for segment in segments:
        segment_words = getattr(segment, "words", None) or []
        for word in segment_words:
            text = (getattr(word, "word", "") or "").strip()
            start = float(getattr(word, "start", 0.0) or 0.0)
            end = float(getattr(word, "end", start) or start)
            if not text:
                continue
            words.append(WordTimestamp(word=text, start=max(0.0, start), end=max(start, end)))

    if not words:
        raise RuntimeError("faster-whisper returned no word timestamps")
    return words


def align_cleaned_words_to_timestamps(
    original_words: list[WordTimestamp],
    cleaned_text: str,
) -> list[WordTimestamp]:
    if not original_words:
        return []

    cleaned_tokens = _tokenize_text(cleaned_text)
    if not cleaned_tokens:
        return original_words

    cleaned_display_words: list[str] = []
    for token in cleaned_tokens:
        if _is_word_token(token):
            cleaned_display_words.append(token)
        elif cleaned_display_words:
            cleaned_display_words[-1] = f"{cleaned_display_words[-1]}{token}"

    if not cleaned_display_words:
        return original_words

    original_norm = [_normalize_word(item.word) for item in original_words if _normalize_word(item.word)]
    cleaned_norm = [_normalize_word(item) for item in cleaned_display_words if _normalize_word(item)]

    if len(original_norm) != len(cleaned_norm):
        logger.warning(
            "Subtitle alignment fallback: word count changed too much (original=%s cleaned=%s)",
            len(original_norm),
            len(cleaned_norm),
        )
        return original_words

    mismatches = sum(1 for original, cleaned in zip(original_norm, cleaned_norm) if original != cleaned)
    mismatch_ratio = mismatches / max(1, len(original_norm))
    if mismatch_ratio > 0.4:
        logger.warning("Subtitle alignment fallback: mismatch ratio too high (%.2f)", mismatch_ratio)
        return original_words

    aligned: list[WordTimestamp] = []
    clean_index = 0
    for original in original_words:
        if not _normalize_word(original.word):
            continue
        if clean_index >= len(cleaned_display_words):
            return original_words
        aligned.append(
            WordTimestamp(
                word=cleaned_display_words[clean_index],
                start=original.start,
                end=original.end,
            )
        )
        clean_index += 1

    return aligned if len(aligned) == len(original_words) else original_words


def _ass_timestamp(seconds: float) -> str:
    clamped = max(0.0, seconds)
    hours = int(clamped // 3600)
    minutes = int((clamped % 3600) // 60)
    secs = int(clamped % 60)
    centiseconds = int(round((clamped - int(clamped)) * 100))
    if centiseconds == 100:
        secs += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_ass_text(value: str) -> str:
    return (value or "").replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _split_word_groups(
    words: list[WordTimestamp],
    *,
    max_words_per_line: int,
    max_chars_per_line: int,
) -> list[list[WordTimestamp]]:
    groups: list[list[WordTimestamp]] = []
    current: list[WordTimestamp] = []
    current_chars = 0

    for word in words:
        pause_before = word.start - current[-1].end if current else 0.0
        next_chars = current_chars + len(word.word) + (1 if current else 0)
        should_break = (
            bool(current)
            and (
                pause_before >= 0.6
                or len(current) >= max_words_per_line
                or next_chars > max_chars_per_line
            )
        )
        if should_break:
            groups.append(current)
            current = []
            current_chars = 0

        current.append(word)
        current_chars += len(word.word) + (1 if len(current) > 1 else 0)

    if current:
        groups.append(current)

    return groups


def _build_active_window(
    words: list[WordTimestamp],
    *,
    active_index: int,
    context_before: int,
    context_after: int,
    max_words_per_line: int,
    max_chars_per_line: int,
) -> tuple[list[WordTimestamp], int]:
    if not words:
        return [], 0

    start = max(0, active_index - context_before)
    end = min(len(words), active_index + context_after + 1)

    while end - start > max_words_per_line:
        if active_index - start > end - active_index - 1:
            start += 1
        else:
            end -= 1

    def _char_len(items: list[WordTimestamp]) -> int:
        return sum(len(item.word) for item in items) + max(0, len(items) - 1)

    window = words[start:end]
    while len(window) > 1 and _char_len(window) > max_chars_per_line:
        if active_index - start >= end - active_index - 1 and start < active_index:
            start += 1
        elif end - 1 > active_index:
            end -= 1
        else:
            break
        window = words[start:end]

    if not window:
        return [words[active_index]], 0
    return window, active_index - start


def _format_group_text(words: list[WordTimestamp], active_index: int) -> str:
    settings = get_settings()
    active_scale = max(100, settings.render_subtitle_active_scale_percent)
    styled_words: list[str] = []
    for index, word in enumerate(words):
        text = _escape_ass_text(word.word)
        if index == active_index:
            styled_words.append(
                r"{\c"
                + settings.render_subtitle_active_color_ass
                + r"\bord5\fscx"
                + str(active_scale)
                + r"\fscy"
                + str(active_scale)
                + r"}"
                + text
                + r"{\c&H00FFFFFF&\bord4\fscx100\fscy100}"
            )
        else:
            styled_words.append(text)
    return " ".join(styled_words)


def generate_word_level_ass(
    words: list[WordTimestamp],
    output_path: str,
    video_width: int,
    video_height: int,
) -> str:
    settings = get_settings()
    font_path = Path(settings.render_thumbnail_font_path).expanduser()
    font_name = font_path.stem.replace("-", " ")
    header = ASS_HEADER_TEMPLATE.format(
        play_res_x=video_width,
        play_res_y=video_height,
        font_name=font_name or "Montserrat Bold",
        font_size=max(24, settings.render_subtitle_font_size),
        active_color=settings.render_subtitle_active_color_ass,
        margin_v=max(80, settings.render_subtitle_margin_bottom),
    )

    events: list[str] = []
    groups = _split_word_groups(
        words,
        max_words_per_line=max(1, settings.render_subtitle_max_words_per_line),
        max_chars_per_line=max(8, settings.render_subtitle_max_chars_per_line),
    )

    for group in groups:
        for index, word in enumerate(group):
            display_words, active_display_index = _build_active_window(
                group,
                active_index=index,
                context_before=max(0, settings.render_subtitle_context_before),
                context_after=max(0, settings.render_subtitle_context_after),
                max_words_per_line=max(1, settings.render_subtitle_max_words_per_line),
                max_chars_per_line=max(8, settings.render_subtitle_max_chars_per_line),
            )
            start = word.start
            if index + 1 < len(group):
                end = max(word.end, group[index + 1].start)
            else:
                end = word.end + 0.08
            if end <= start:
                end = start + 0.08
            events.append(
                "Dialogue: 0,{start},{end},Default,,0,0,0,,{text}".format(
                    start=_ass_timestamp(start),
                    end=_ass_timestamp(end),
                    text=_format_group_text(display_words, active_display_index),
                )
            )

    ass_content = header + "\n".join(events) + "\n"
    Path(output_path).write_text(ass_content, encoding="utf-8")
    return output_path


def burn_subtitles(input_video: str, ass_path: str, output_video: str) -> str:
    settings = get_settings()
    ass_filter_path = str(Path(ass_path)).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    result = subprocess.run(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            input_video,
            "-vf",
            f"ass=filename='{ass_filter_path}'",
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
            output_video,
        ],
        capture_output=True,
        text=True,
        timeout=settings.render_command_timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed burning ASS subtitles: {result.stderr}")
    return output_video
