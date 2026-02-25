import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    ride_id: Mapped[str] = mapped_column(String, ForeignKey("rides.id"), unique=True, nullable=False, index=True)
    driver_id: Mapped[str] = mapped_column(String, ForeignKey("drivers.id"), nullable=False)
    rider_id: Mapped[str] = mapped_column(String, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    base_fare: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    surge_fare: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_fare: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # ACTIVE | PAUSED | COMPLETED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
