from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import settings

# Enterprise-grade PostgreSQL connection pooling setup
# pool_pre_ping=True: runs a select 1-like query on check-out to avoid broken pipes/closed connections
# pool_recycle=3600: recycles open pool connections after 1 hour (3600 seconds)
engine: Engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DB_ECHO,
)
