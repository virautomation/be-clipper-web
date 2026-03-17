from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Autoclipper MVP Backend", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(default="sqlite:///./autoclipper.db", alias="DATABASE_URL")

    supabase_url: str = Field(default="https://example.supabase.co", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="dummy-service-role-key", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_storage_bucket: str = Field(default="autoclipper-renders", alias="SUPABASE_STORAGE_BUCKET")
    supabase_signed_url_expires_in: int = Field(default=3600, alias="SUPABASE_SIGNED_URL_EXPIRES_IN")

    temp_dir: str = Field(default="/tmp/autoclipper", alias="TEMP_DIR")
    ffmpeg_binary: str = Field(default="ffmpeg", alias="FFMPEG_BINARY")
    ytdlp_binary: str = Field(default="yt-dlp", alias="YTDLP_BINARY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
