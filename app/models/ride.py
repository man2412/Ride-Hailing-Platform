import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Float, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Ride(Base):
    __tablename__ = "rides"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rider_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    driver_id: Mapped[str | None] = mapped_column(String, ForeignKey("drivers.id"), nullable=True, index=True)

    pickup_lat: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_lng: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Float, nullable=False)
    dest_lng: Mapped[float] = mapped_column(Float, nullable=False)

    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    # REQUESTED | MATCHED | DRIVER_EN_ROUTE | TRIP_STARTED | TRIP_PAUSED |
    # TRIP_ENDED | PAYMENT_PENDING | COMPLETED | CANCELLED | PAYMENT_FAILED
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="REQUESTED", index=True)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    surge_multiplier: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.0"))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
