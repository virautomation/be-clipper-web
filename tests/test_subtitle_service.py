from pathlib import Path

from app.services.subtitle_service import (
    WordTimestamp,
    _build_active_window,
    align_cleaned_words_to_timestamps,
    generate_word_level_ass,
)


def test_align_cleaned_words_preserves_timestamps() -> None:
    original = [
        WordTimestamp(word="halo", start=0.0, end=0.3),
        WordTimestamp(word="teman", start=0.3, end=0.6),
        WordTimestamp(word="semua", start=0.6, end=1.0),
    ]

    aligned = align_cleaned_words_to_timestamps(original, "Halo, teman semua.")

    assert [item.word for item in aligned] == ["Halo,", "teman", "semua."]
    assert [item.start for item in aligned] == [0.0, 0.3, 0.6]
    assert [item.end for item in aligned] == [0.3, 0.6, 1.0]


def test_align_cleaned_words_falls_back_when_word_count_changes() -> None:
    original = [
        WordTimestamp(word="ini", start=0.0, end=0.2),
        WordTimestamp(word="contoh", start=0.2, end=0.5),
    ]

    aligned = align_cleaned_words_to_timestamps(original, "Ini adalah contoh baru")

    assert aligned == original


def test_generate_word_level_ass_writes_highlighted_dialogue(tmp_path: Path) -> None:
    ass_path = tmp_path / "subtitle.ass"
    words = [
        WordTimestamp(word="halo", start=0.0, end=0.2),
        WordTimestamp(word="semua", start=0.2, end=0.5),
    ]

    output = generate_word_level_ass(words, str(ass_path), video_width=720, video_height=1280)

    content = Path(output).read_text(encoding="utf-8")
    assert "Style: Default" in content
    assert "Dialogue:" in content
    assert r"{\c&H0000FFFF&\bord5\fscx112\fscy112}halo{\c&H00FFFFFF&\bord4\fscx100\fscy100}" in content


def test_active_window_follows_active_word() -> None:
    words = [
        WordTimestamp(word="ini", start=0.0, end=0.1),
        WordTimestamp(word="contoh", start=0.1, end=0.2),
        WordTimestamp(word="subtitle", start=0.2, end=0.3),
        WordTimestamp(word="yang", start=0.3, end=0.4),
        WordTimestamp(word="geser", start=0.4, end=0.5),
    ]

    window, active_index = _build_active_window(
        words,
        active_index=3,
        context_before=1,
        context_after=2,
        max_words_per_line=4,
        max_chars_per_line=18,
    )

    assert [item.word for item in window] == ["subtitle", "yang", "geser"]
    assert active_index == 1
