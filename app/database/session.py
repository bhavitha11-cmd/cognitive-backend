from typing import Generator
from sqlalchemy.orm import sessionmaker, Session

from app.database.connection import engine

# Create a local session factory
# autoflush=False: avoid premature flushing of model changes during requests
# autocommit=False: standard context transactions managed by SQLAlchemy
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a transactional database session per request.
    Yields the session, and guarantees that it is closed once the request is done.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
