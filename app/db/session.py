from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
database_url = (
    settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if settings.database_url.startswith("postgresql://")
    else settings.database_url
)

is_sqlite = database_url.startswith("sqlite")
engine = create_engine(
    database_url,
    pool_pre_ping=True,
    future=True,
    connect_args={"check_same_thread": False} if is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for request lifecycle."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
