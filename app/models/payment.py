import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    trip_id: Mapped[str] = mapped_column(String, ForeignKey("trips.id"), nullable=False, index=True)
    rider_id: Mapped[str] = mapped_column(String, nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), default="INR")
    # PENDING | SUCCESS | FAILED | REFUNDED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    psp_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
