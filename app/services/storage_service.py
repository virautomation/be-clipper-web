from __future__ import annotations

from pathlib import Path

from supabase import Client, create_client
from storage3.exceptions import StorageApiError

from app.core.config import get_settings


def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _ensure_bucket_exists(client: Client, bucket_name: str) -> None:
    """Ensure the target storage bucket exists (private by default)."""

    buckets = client.storage.list_buckets()
    for bucket in buckets:
        if bucket.get("name") == bucket_name or bucket.get("id") == bucket_name:
            return

    client.storage.create_bucket(bucket_name, options={"public": False})


def upload_clip_and_get_signed_url(local_file_path: str, destination_path: str) -> str:
    """Upload clip to Supabase Storage private bucket and return signed URL."""

    settings = get_settings()
    client = get_supabase_client()
    _ensure_bucket_exists(client, settings.supabase_storage_bucket)
    bucket = client.storage.from_(settings.supabase_storage_bucket)

    file_bytes = Path(local_file_path).read_bytes()
    try:
        bucket.upload(
            path=destination_path,
            file=file_bytes,
            file_options={"content-type": "video/mp4", "upsert": "true"},
        )
    except StorageApiError as exc:
        # Handle race/partially configured environments where bucket is missing.
        if "Bucket not found" in str(exc):
            _ensure_bucket_exists(client, settings.supabase_storage_bucket)
            bucket.upload(
                path=destination_path,
                file=file_bytes,
                file_options={"content-type": "video/mp4", "upsert": "true"},
            )
        else:
            raise

    signed = bucket.create_signed_url(destination_path, settings.supabase_signed_url_expires_in)
    return str(signed.get("signedURL") or signed.get("signedUrl") or "")
