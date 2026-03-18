from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

from app.db.session import get_db
from app.models.clip_candidate import ClipCandidate
from app.models.clip_job import ClipJob
from app.models.enums import ClipJobStatus
from app.schemas.jobs import (
    AnalyzeCandidateOut,
    AnalyzeJobRequest,
    AnalyzeJobResponse,
    AnalyzeSelectedVideoRequest,
    CandidateDetail,
    DiscoverVideoOut,
    DiscoverVideosRequest,
    DiscoverVideosResponse,
    JobDetailResponse,
    JobListItem,
    JobListResponse,
    RenderCandidateRequest,
    RenderCandidateResponse,
    ScheduleRequest,
    ScheduleResponse,
)
from app.services.candidate_service import select_candidates
from app.services.discovery_service import search_videos_by_keyword
from app.services.render_service import render_candidate_and_upload
from app.services.transcript_service import fetch_transcript
from app.utils.youtube import extract_video_id

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_preview_urls(video_id: str, start_time: float, end_time: float) -> tuple[str, str]:
    start_sec = max(0, int(start_time))
    end_sec = max(start_sec + 1, int(end_time))
    preview_url = f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s"
    embed_url = (
        f"https://www.youtube.com/embed/{video_id}?start={start_sec}&end={end_sec}"
        "&autoplay=0&rel=0&modestbranding=1"
    )
    return preview_url, embed_url


def _run_analyze(
    *,
    youtube_url: str,
    video_id: str,
    keyword: str,
    duration_target: int,
    db: Session,
) -> AnalyzeJobResponse:
    job = ClipJob(
        youtube_url=youtube_url,
        youtube_video_id=video_id,
        keyword=keyword,
        duration_target=duration_target,
        status=ClipJobStatus.queued,
        transcript_found=False,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        transcript = fetch_transcript(video_id)
        job.transcript_found = True
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as exc:
        job.status = ClipJobStatus.failed
        job.failure_reason = f"Transcript unavailable: {exc}"
        db.commit()
        return AnalyzeJobResponse(job_id=job.id, status=job.status.value, transcript_found=False, candidates=[])
    except Exception as exc:
        logger.exception("Analyze failed while fetching transcript for job_id=%s", job.id)
        job.status = ClipJobStatus.failed
        job.failure_reason = f"Analyze failed: {exc}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Analyze failed") from exc

    proposals = select_candidates(transcript=transcript, keyword=keyword, duration_target=duration_target)

    candidates_out: list[AnalyzeCandidateOut] = []
    for proposal in proposals:
        preview_url, embed_url = _build_preview_urls(video_id, proposal.start_time, proposal.end_time)
        candidate = ClipCandidate(
            job_id=job.id,
            start_time=proposal.start_time,
            end_time=proposal.end_time,
            transcript_snippet=proposal.transcript_snippet,
            score=proposal.score,
            rank=proposal.rank,
        )
        db.add(candidate)
        db.flush()
        candidates_out.append(
            AnalyzeCandidateOut(
                id=candidate.id,
                start_time=candidate.start_time,
                end_time=candidate.end_time,
                transcript_snippet=candidate.transcript_snippet,
                score=candidate.score,
                rank=candidate.rank,
                preview_url=preview_url,
                embed_url=embed_url,
            )
        )

    if proposals:
        job.status = ClipJobStatus.analyzed
    else:
        job.status = ClipJobStatus.failed
        job.failure_reason = "No relevant transcript segment found for keyword"

    db.commit()

    return AnalyzeJobResponse(
        job_id=job.id,
        status=job.status.value,
        transcript_found=job.transcript_found,
        candidates=candidates_out,
    )


@router.post("/discover", response_model=DiscoverVideosResponse)
def discover_videos(payload: DiscoverVideosRequest) -> DiscoverVideosResponse:
    try:
        videos = search_videos_by_keyword(keyword=payload.keyword, limit=payload.limit)
    except Exception as exc:
        logger.exception("Video discovery failed for keyword=%s", payload.keyword)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Video discovery failed") from exc

    return DiscoverVideosResponse(
        keyword=payload.keyword,
        videos=[DiscoverVideoOut(**video) for video in videos],
    )


@router.post("/analyze", response_model=AnalyzeJobResponse, status_code=status.HTTP_201_CREATED)
def analyze_job(payload: AnalyzeJobRequest, db: Session = Depends(get_db)) -> AnalyzeJobResponse:
    video_id = extract_video_id(payload.youtube_url)

    return _run_analyze(
        youtube_url=payload.youtube_url,
        video_id=video_id,
        keyword=payload.keyword,
        duration_target=payload.duration_target,
        db=db,
    )


@router.post("/analyze/by-video", response_model=AnalyzeJobResponse, status_code=status.HTTP_201_CREATED)
def analyze_job_by_video(payload: AnalyzeSelectedVideoRequest, db: Session = Depends(get_db)) -> AnalyzeJobResponse:
    youtube_url = f"https://www.youtube.com/watch?v={payload.youtube_video_id}"

    return _run_analyze(
        youtube_url=youtube_url,
        video_id=payload.youtube_video_id,
        keyword=payload.keyword,
        duration_target=payload.duration_target,
        db=db,
    )


@router.post("/{job_id}/render", response_model=RenderCandidateResponse)
def render_candidate(job_id: str, payload: RenderCandidateRequest, db: Session = Depends(get_db)) -> RenderCandidateResponse:
    job = db.get(ClipJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    candidate = db.get(ClipCandidate, payload.candidate_id)
    if not candidate or candidate.job_id != job.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found for job")

    job.status = ClipJobStatus.rendering
    job.selected_candidate_id = candidate.id
    db.commit()

    try:
        storage_path, signed_url = render_candidate_and_upload(job=job, candidate=candidate)
    except Exception as exc:
        logger.exception("Render failed for job_id=%s", job.id)
        job.status = ClipJobStatus.failed
        job.failure_reason = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Render failed") from exc

    job.status = ClipJobStatus.rendered
    job.render_storage_path = storage_path
    job.render_signed_url = signed_url
    db.commit()

    return RenderCandidateResponse(
        job_id=job.id,
        render_status=job.status.value,
        storage_path=storage_path,
        signed_url=signed_url,
        clip_start=candidate.start_time,
        clip_end=candidate.end_time,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job_detail(job_id: str, db: Session = Depends(get_db)) -> JobDetailResponse:
    job = db.get(ClipJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    candidates_query = select(ClipCandidate).where(ClipCandidate.job_id == job.id).order_by(ClipCandidate.rank.asc())
    candidates = db.execute(candidates_query).scalars().all()

    return JobDetailResponse(
        id=job.id,
        youtube_url=job.youtube_url,
        youtube_video_id=job.youtube_video_id,
        keyword=job.keyword,
        duration_target=job.duration_target,
        status=job.status.value,
        transcript_found=job.transcript_found,
        selected_candidate_id=job.selected_candidate_id,
        render_storage_path=job.render_storage_path,
        render_signed_url=job.render_signed_url,
        scheduled_at=job.scheduled_at,
        caption=job.caption,
        failure_reason=job.failure_reason,
        created_at=job.created_at,
        updated_at=job.updated_at,
        candidates=[
            CandidateDetail(
                id=c.id,
                start_time=c.start_time,
                end_time=c.end_time,
                transcript_snippet=c.transcript_snippet,
                score=c.score,
                rank=c.rank,
                created_at=c.created_at,
            )
            for c in candidates
        ],
    )


@router.get("", response_model=JobListResponse)
def list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> JobListResponse:
    base_query = select(ClipJob)
    count_query = select(func.count()).select_from(ClipJob)

    if status_filter:
        base_query = base_query.where(ClipJob.status == status_filter)
        count_query = count_query.where(ClipJob.status == status_filter)

    rows = db.execute(base_query.order_by(ClipJob.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    total = db.execute(count_query).scalar_one()

    return JobListResponse(
        items=[
            JobListItem(
                id=row.id,
                youtube_url=row.youtube_url,
                keyword=row.keyword,
                status=row.status.value,
                transcript_found=row.transcript_found,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post("/{job_id}/schedule", response_model=ScheduleResponse)
def schedule_job(job_id: str, payload: ScheduleRequest, db: Session = Depends(get_db)) -> ScheduleResponse:
    job = db.get(ClipJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status != ClipJobStatus.rendered:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job must be rendered before scheduling")

    job.scheduled_at = payload.scheduled_at
    job.caption = payload.caption
    job.status = ClipJobStatus.scheduled
    db.commit()

    return ScheduleResponse(
        job_id=job.id,
        scheduled_at=job.scheduled_at,
        caption=job.caption,
        status=job.status.value,
    )
