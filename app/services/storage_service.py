from __future__ import annotations

from pathlib import Path

from supabase import Client, create_client
from storage3.exceptions import StorageApiError

from app.core.config import get_settings


def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _read_field(value: object, field: str) -> object | None:
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)


def _ensure_bucket_exists(client: Client, bucket_name: str) -> None:
    """Ensure the target storage bucket exists (private by default)."""

    buckets = client.storage.list_buckets() or []
    for bucket in buckets:
        name = _read_field(bucket, "name")
        bucket_id = _read_field(bucket, "id")
        if name == bucket_name or bucket_id == bucket_name:
            return

    client.storage.create_bucket(bucket_name, options={"public": False})


def upload_file_and_get_signed_url(local_file_path: str, destination_path: str, content_type: str) -> str:
    settings = get_settings()
    client = get_supabase_client()
    _ensure_bucket_exists(client, settings.supabase_storage_bucket)
    bucket = client.storage.from_(settings.supabase_storage_bucket)

    file_bytes = Path(local_file_path).read_bytes()
    file_options = {"content-type": content_type, "upsert": "true"}

    try:
        bucket.upload(path=destination_path, file=file_bytes, file_options=file_options)
    except StorageApiError as exc:
        if "Bucket not found" in str(exc):
            _ensure_bucket_exists(client, settings.supabase_storage_bucket)
            bucket.upload(path=destination_path, file=file_bytes, file_options=file_options)
        else:
            raise

    signed = bucket.create_signed_url(destination_path, settings.supabase_signed_url_expires_in)
    signed_url = (
        _read_field(signed, "signedURL")
        or _read_field(signed, "signedUrl")
        or _read_field(signed, "signed_url")
        or ""
    )
    return str(signed_url)


def upload_clip_and_get_signed_url(local_file_path: str, destination_path: str) -> str:
    """Upload clip to Supabase Storage private bucket and return signed URL."""
    return upload_file_and_get_signed_url(local_file_path, destination_path, content_type="video/mp4")
