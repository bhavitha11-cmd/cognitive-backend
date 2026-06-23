import uuid
from datetime import date
from sqlalchemy import Date, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base

class Holiday(Base):
    __tablename__ = "holidays"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Holiday {self.name} on {self.date}>"
