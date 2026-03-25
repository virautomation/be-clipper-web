from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ClipJobMode
from app.utils.youtube import extract_video_id


class DiscoverJobCreateRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=255)
    niche: str = Field(min_length=2, max_length=255)
    goal: str = Field(min_length=4, max_length=1000)


class DiscoverJobOut(BaseModel):
    id: str
    topic: str
    niche: str
    goal: str
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class DiscoverJobCreateResponse(BaseModel):
    item: DiscoverJobOut
    message: str


class DiscoverJobListResponse(BaseModel):
    items: list[DiscoverJobOut]
    total: int
    limit: int
    offset: int


class AnalyzeJobRequest(BaseModel):
    mode: ClipJobMode = Field(default=ClipJobMode.auto_detect)
    youtube_url: str
    clip_count: int = Field(default=5, ge=1, le=12)
    duration_target: int = Field(default=20, ge=10, le=90)
    tone: str | None = Field(default=None, max_length=120)
    audience: str | None = Field(default=None, max_length=120)
    keyword: str | None = Field(default=None, max_length=255)

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
    topic_title: str
    score: float
    semantic_score: float | None = None
    selection_reason: str
    rank: int
    preview_url: str
    embed_url: str


class AnalyzeJobResponse(BaseModel):
    job_id: str
    mode: str
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
    thumbnail_path: str
    thumbnail_signed_url: str
    hook_text: str
    final_video_path: str
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
    topic_title: str
    score: float
    semantic_score: float | None = None
    selection_reason: str
    rank: int
    created_at: datetime


class JobDetailResponse(BaseModel):
    id: str
    mode: str
    youtube_url: str | None
    youtube_video_id: str | None
    keyword: str | None
    clip_count: int
    duration_target: int
    tone: str | None
    audience: str | None
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
    mode: str
    youtube_url: str | None
    keyword: str | None
    status: str
    transcript_found: bool
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobListItem]
    total: int
    limit: int
    offset: int
