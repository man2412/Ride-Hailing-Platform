import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, func, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    # offline | available | on_trip
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="offline", index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
