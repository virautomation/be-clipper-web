from datetime import datetime

from pydantic import BaseModel


class CandidateOut(BaseModel):
    id: str
    start_time: float
    end_time: float
    transcript_snippet: str
    score: float
    rank: int
    created_at: datetime


class JobRenderInfo(BaseModel):
    storage_path: str | None = None
    signed_url: str | None = None


class JobBaseOut(BaseModel):
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
