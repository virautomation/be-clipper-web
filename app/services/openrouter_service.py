from __future__ import annotations

import json
import logging
import re
from dataclasses import replace

import httpx

from app.core.config import get_settings
from app.services.candidate_service import CandidateProposal

logger = logging.getLogger(__name__)
HOOK_FALLBACK_TEXT = "Ini yang orang nggak tahu"
HOOK_MODEL = "arcee-ai/trinity-large-preview:free"
THUMBNAIL_FALLBACK_TEXT = "Ini yang belum tahu"


class OpenRouterError(RuntimeError):
    pass


def _clean_hook_text(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*", "", text).strip()
        text = text.replace("```", "").strip()

    # Handle lightweight JSON-like responses from the model.
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for key in ("hook", "hook_text", "text", "result", "output"):
                    value = parsed.get(key)
                    if isinstance(value, str) and value.strip():
                        text = value.strip()
                        break
        except Exception:
            pass

    text = text.strip().strip('"').strip("'")
    text = " ".join(text.replace("\n", " ").split())

    words = text.split()
    if len(words) > 10:
        text = " ".join(words[:10]).strip()

    return text


def _remove_emoji(value: str) -> str:
    return re.sub(
        r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF\U0000FE00-\U0000FE0F]",
        "",
        value or "",
    )


def _clean_thumbnail_text(raw: str) -> str:
    text = _clean_hook_text(raw)
    text = _remove_emoji(text)
    # Thumbnail text must be plain words only: strip punctuation/symbols aggressively.
    text = re.sub(r"[^0-9A-Za-z\u00C0-\u024F\s]", " ", text)
    text = " ".join(text.split())

    words = text.split()
    if len(words) > 4:
        text = " ".join(words[:4]).strip()
    return text


def _extract_plain_text(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*", "", text).strip()
        text = text.replace("```", "").strip()

    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for key in ("text", "result", "output", "cleaned_text", "transcript"):
                    value = parsed.get(key)
                    if isinstance(value, str) and value.strip():
                        text = value.strip()
                        break
        except Exception:
            pass

    return text.strip().strip('"').strip("'")


def generate_hook_text(transcript_snippet: str) -> str:
    settings = get_settings()
    snippet = " ".join((transcript_snippet or "").split())[:600]
    if not snippet:
        return HOOK_FALLBACK_TEXT

    if not settings.openrouter_api_key:
        logger.info("OPENROUTER_API_KEY is empty; using fallback hook text")
        return HOOK_FALLBACK_TEXT

    prompt = (
        "You are a viral short-form content creator.\n"
        "Generate a short, catchy hook (max 10 words) for this clip:\n"
        f"{snippet}\n\n"
        "Rules:\n"
        "- max 10 kata\n"
        "- harus menarik dan memicu curiosity\n"
        "- bahasa Indonesia\n"
        "- return plain text saja"
    )

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HOOK_MODEL,
                    "messages": [
                        {"role": "system", "content": "Output plain text only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("OpenRouter hook generation failed: %s", exc)
        return HOOK_FALLBACK_TEXT

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return HOOK_FALLBACK_TEXT

    logger.info("OpenRouter LLM raw response (hook): %r", content)
    cleaned = _clean_hook_text(str(content or ""))
    return cleaned or HOOK_FALLBACK_TEXT


def generate_thumbnail_text(transcript_snippet: str) -> str:
    settings = get_settings()
    snippet = " ".join((transcript_snippet or "").split())[:600]
    if not snippet:
        return THUMBNAIL_FALLBACK_TEXT

    if not settings.openrouter_api_key:
        logger.info("OPENROUTER_API_KEY is empty; using fallback thumbnail text")
        return THUMBNAIL_FALLBACK_TEXT

    prompt = (
        "Kamu adalah kreator konten short video yang bahasanya santai, gaul, dan natural.\n"
        "Buat teks thumbnail yang catchy dari clip berikut.\n"
        "Aturan ketat:\n"
        "- maksimal 4 kata\n"
        "- tanpa emoji\n"
        "- bahasa Indonesia santai, jangan terlalu baku\n"
        "- hindari kata kaku/formal seperti temukan, rahasia suksesnya, strategi, kolaborasi tanpa batas\n"
        "- pilih phrasing yang lebih ngobrol dan enak dilihat di thumbnail\n"
        "- return plain text saja\n\n"
        f"Clip:\n{snippet}"
    )

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HOOK_MODEL,
                    "messages": [
                        {"role": "system", "content": "Output plain text only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.5,
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("OpenRouter thumbnail text generation failed: %s", exc)
        return THUMBNAIL_FALLBACK_TEXT

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return THUMBNAIL_FALLBACK_TEXT

    logger.info("OpenRouter LLM raw response (thumbnail): %r", content)
    cleaned = _clean_thumbnail_text(str(content or ""))
    logger.info("Thumbnail text after cleaning: %r", cleaned)
    return cleaned or THUMBNAIL_FALLBACK_TEXT


def clean_transcript_with_llm(text: str) -> str:
    settings = get_settings()
    source_text = " ".join((text or "").split())
    if not source_text:
        return ""

    if not settings.openrouter_api_key:
        logger.info("OPENROUTER_API_KEY is empty; using original transcript text")
        return source_text

    prompt = (
        "Rapikan transcript berikut dengan perubahan seminimal mungkin.\n"
        "Aturan ketat:\n"
        "- perbaiki typo ringan\n"
        "- rapikan tanda baca seperlunya\n"
        "- jangan ubah makna\n"
        "- jangan rewrite bebas\n"
        "- pertahankan urutan kata semirip mungkin\n"
        "- usahakan jumlah kata tetap hampir sama agar alignment subtitle tidak rusak\n"
        "- return plain text saja\n\n"
        f"Transcript:\n{source_text}"
    )

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openrouter_model or HOOK_MODEL,
                    "messages": [
                        {"role": "system", "content": "Output plain text only. Minimal edits only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("OpenRouter transcript cleanup failed: %s", exc)
        return source_text

    cleaned = " ".join(_extract_plain_text(str(content or "")).split())
    logger.info("Transcript cleanup result: %r", cleaned)
    return cleaned or source_text


def _build_prompt(candidates: list[CandidateProposal], clip_count: int) -> str:
    payload = [
        {
            "id": str(index + 1),
            "start_time": item.start_time,
            "end_time": item.end_time,
            "topic_title": item.topic_title,
            "snippet": item.transcript_snippet[:320],
            "rule_score": item.score,
        }
        for index, item in enumerate(candidates)
    ]

    return (
        "You are ranking short-form clip candidates. "
        "Return ONLY JSON with key 'selected' as an array. "
        "Each item must include: id, semantic_score, topic_title, selection_reason, rank. "
        f"Select at most {clip_count} items.\nCandidates:\n"
        + json.dumps(payload, ensure_ascii=True)
    )


def rerank_candidates_with_openrouter(
    *,
    candidates: list[CandidateProposal],
    clip_count: int,
    tone: str | None,
    audience: str | None,
) -> list[CandidateProposal]:
    settings = get_settings()
    if not candidates:
        return []

    if not settings.openrouter_api_key:
        logger.info("OPENROUTER_API_KEY is empty; skipping semantic rerank")
        return _fallback(candidates, clip_count)

    prompt = _build_prompt(candidates, clip_count)
    if tone or audience:
        prompt += f"\nContext: tone={tone or 'default'}, audience={audience or 'general'}"

    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"

    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openrouter_model,
                    "messages": [
                        {"role": "system", "content": "You output valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
    except Exception as exc:
        logger.warning("OpenRouter request failed: %s", exc)
        return _fallback(candidates, clip_count)

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("OpenRouter LLM raw response (candidate selection): %r", content)
        parsed = json.loads(content)
        selected = parsed.get("selected", [])
        if not isinstance(selected, list):
            raise OpenRouterError("Invalid selected payload")
    except Exception as exc:
        logger.warning("OpenRouter parse failed: %s", exc)
        return _fallback(candidates, clip_count)

    mapped_by_id: dict[str, CandidateProposal] = {str(i + 1): item for i, item in enumerate(candidates)}
    reranked: list[CandidateProposal] = []

    for row in selected:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "")
        base = mapped_by_id.get(row_id)
        if not base:
            continue

        semantic_score_raw = row.get("semantic_score")
        semantic_score = float(semantic_score_raw) if isinstance(semantic_score_raw, (float, int)) else None
        merged = replace(
            base,
            topic_title=str(row.get("topic_title") or base.topic_title),
            semantic_score=semantic_score,
            selection_reason=str(row.get("selection_reason") or "selected by semantic rerank"),
            rank=int(row.get("rank") or 0),
        )
        reranked.append(merged)

    if not reranked:
        return _fallback(candidates, clip_count)

    reranked.sort(key=lambda item: item.rank if item.rank > 0 else 999)
    reranked = reranked[:clip_count]

    for rank, item in enumerate(reranked, start=1):
        item.rank = rank

    return reranked


def _fallback(candidates: list[CandidateProposal], clip_count: int) -> list[CandidateProposal]:
    fallback = [
        replace(
            item,
            semantic_score=item.semantic_score if item.semantic_score is not None else item.score,
            selection_reason=item.selection_reason or "fallback rule-based ranking",
        )
        for item in candidates[:clip_count]
    ]

    for rank, item in enumerate(fallback, start=1):
        item.rank = rank

    return fallback
