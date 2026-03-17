from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CandidateProposal:
    start_time: float
    end_time: float
    transcript_snippet: str
    score: float
    rank: int


def _normalize(value: str) -> str:
    return " ".join(value.lower().strip().split())


def select_candidates(
    transcript: list[dict[str, float | str]],
    keyword: str,
    duration_target: int,
    max_candidates: int = 3,
) -> list[CandidateProposal]:
    """Generate up to max_candidates from transcript using rule-based scoring."""

    if not transcript:
        return []

    keyword_norm = _normalize(keyword)
    keyword_tokens = [token for token in keyword_norm.split() if token]
    min_duration = 15.0
    max_duration = 20.0
    target_duration = float(max(15, min(20, duration_target)))

    scored: list[CandidateProposal] = []

    for idx, item in enumerate(transcript):
        text = str(item["text"])
        text_norm = _normalize(text)

        exact_hits = text_norm.count(keyword_norm) if keyword_norm else 0
        partial_hits = sum(text_norm.count(token) for token in keyword_tokens if token)
        if exact_hits == 0 and partial_hits == 0:
            continue

        start = float(item["start"])
        end = start + float(item["duration"])
        combined_texts = [text]

        cursor = idx + 1
        while cursor < len(transcript) and (end - start) < target_duration:
            next_item = transcript[cursor]
            next_end = float(next_item["start"]) + float(next_item["duration"])
            if (next_end - start) > max_duration:
                break
            combined_texts.append(str(next_item["text"]))
            end = next_end
            cursor += 1

        if (end - start) < min_duration:
            continue

        snippet = " ".join(combined_texts).strip()
        snippet_norm = _normalize(snippet)

        sentence_bonus = 1.0 if snippet.endswith((".", "!", "?")) else 0.0
        length_penalty = abs((end - start) - target_duration) * 0.1
        exact_score = snippet_norm.count(keyword_norm) * 5.0 if keyword_norm else 0.0
        partial_score = sum(snippet_norm.count(token) for token in keyword_tokens) * 1.0

        score = exact_score + partial_score + sentence_bonus - length_penalty
        scored.append(
            CandidateProposal(
                start_time=round(start, 3),
                end_time=round(end, 3),
                transcript_snippet=snippet,
                score=round(score, 4),
                rank=0,
            )
        )

    scored.sort(key=lambda x: (x.score, -(x.end_time - x.start_time)), reverse=True)

    deduped: list[CandidateProposal] = []
    for candidate in scored:
        overlaps = any(
            not (candidate.end_time <= existing.start_time or candidate.start_time >= existing.end_time)
            for existing in deduped
        )
        if overlaps:
            continue
        deduped.append(candidate)
        if len(deduped) >= max_candidates:
            break

    for rank, candidate in enumerate(deduped, start=1):
        candidate.rank = rank

    return deduped
