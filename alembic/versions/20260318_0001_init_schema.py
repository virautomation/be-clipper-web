"""init schema

Revision ID: 20260318_0001
Revises: 
Create Date: 2026-03-18 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260318_0001"
down_revision = None
branch_labels = None
depends_on = None


clip_job_status_enum = postgresql.ENUM(
    "queued",
    "analyzed",
    "rendering",
    "rendered",
    "scheduled",
    "uploaded",
    "failed",
    name="clip_job_status",
    create_type=False,
)


def upgrade() -> None:
    clip_job_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "clip_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("youtube_url", sa.Text(), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("duration_target", sa.Integer(), nullable=False),
        sa.Column("status", clip_job_status_enum, nullable=False),
        sa.Column("transcript_found", sa.Boolean(), nullable=False),
        sa.Column("selected_candidate_id", sa.String(length=36), nullable=True),
        sa.Column("render_storage_path", sa.Text(), nullable=True),
        sa.Column("render_signed_url", sa.Text(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clip_jobs_youtube_video_id", "clip_jobs", ["youtube_video_id"])

    op.create_table(
        "clip_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("transcript_snippet", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["clip_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clip_candidates_job_id", "clip_candidates", ["job_id"])

    op.create_table(
        "clip_metrics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("likes", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["clip_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clip_metrics_job_id", "clip_metrics", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_clip_metrics_job_id", table_name="clip_metrics")
    op.drop_table("clip_metrics")

    op.drop_index("ix_clip_candidates_job_id", table_name="clip_candidates")
    op.drop_table("clip_candidates")

    op.drop_index("ix_clip_jobs_youtube_video_id", table_name="clip_jobs")
    op.drop_table("clip_jobs")

    clip_job_status_enum.drop(op.get_bind(), checkfirst=True)
