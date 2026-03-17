from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.utils.youtube import extract_video_id


class AnalyzeJobRequest(BaseModel):
    youtube_url: str
    keyword: str = Field(min_length=1, max_length=255)
    duration_target: int = Field(default=20, ge=15, le=20)

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        extract_video_id(value)
        return value


class AnalyzeCandidateOut(BaseModel):
    id: str
    start_time: float
    end_time: float
    transcript_snippet: str
    score: float
    rank: int


class AnalyzeJobResponse(BaseModel):
    job_id: str
    status: str
    transcript_found: bool
    candidates: list[AnalyzeCandidateOut]


class RenderCandidateRequest(BaseModel):
    candidate_id: str


class RenderCandidateResponse(BaseModel):
    job_id: str
    render_status: str
    storage_path: str
    signed_url: str
    clip_start: float
    clip_end: float


class ScheduleRequest(BaseModel):
    scheduled_at: datetime
    caption: str = Field(min_length=1, max_length=2200)


class ScheduleResponse(BaseModel):
    job_id: str
    scheduled_at: datetime
    caption: str
    status: str


class CandidateDetail(BaseModel):
    id: str
    start_time: float
    end_time: float
    transcript_snippet: str
    score: float
    rank: int
    created_at: datetime


class JobDetailResponse(BaseModel):
    id: str
    youtube_url: str
    youtube_video_id: str
    keyword: str
    duration_target: int
    status: str
    transcript_found: bool
    selected_candidate_id: str | None = None
    render_storage_path: str | None = None
    render_signed_url: str | None = None
    scheduled_at: datetime | None = None
    caption: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    candidates: list[CandidateDetail]


class JobListItem(BaseModel):
    id: str
    youtube_url: str
    keyword: str
    status: str
    transcript_found: bool
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int
