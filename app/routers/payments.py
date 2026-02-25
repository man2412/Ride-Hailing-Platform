"""
Payments router — POST /v1/payments
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.middleware.idempotency import check_idempotency, store_idempotency_result
from app.models.payment import Payment
from app.models.ride import Ride
from app.models.trip import Trip
from app.redis_client import get_redis, cache_delete
from app.schemas.schemas import PaymentRequest, PaymentResponse
from app.services.payment import charge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/payments", tags=["Payments"])


@router.post("", response_model=PaymentResponse)
async def create_payment(
    payload: PaymentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """
    Trigger payment for a completed trip.
    - Idempotent: repeated calls with the same key return the same result.
    - Amount must match server-side trip total (security: no client-side fare override).
    - PSP charged with retry logic.
    """
    # 1. Idempotency check
    if idempotency_key:
        cached = await check_idempotency(request, db)
        if cached:
            return cached

    # 2. Load trip + existing payment record
    trip_result = await db.execute(select(Trip).where(Trip.id == payload.trip_id))
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.status != "COMPLETED":
        raise HTTPException(status_code=409, detail="Trip is not yet completed")

    pay_result = await db.execute(select(Payment).where(Payment.trip_id == trip.id))
    payment = pay_result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment record not found")
    if payment.status == "SUCCESS":
        return PaymentResponse(
            payment_id=payment.id,
            status=payment.status,
            psp_ref=payment.psp_ref,
            amount=float(payment.amount),
            currency=payment.currency,
        )

    # 3. Server-side amount validation (never trust client)
    server_amount = trip.total_fare
    if abs(float(payload.amount) - float(server_amount)) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Amount mismatch. Expected {server_amount}",
        )

    # 4. Attach idempotency to payment record
    payment.idempotency_key = idempotency_key

    # 5. Charge PSP
    psp_result = await charge(
        rider_id=trip.rider_id,
        amount=server_amount,
        payment_method=payload.payment_method.value,
        idempotency_key=idempotency_key or payment.id,
    )

    # 6. Update payment + ride status
    payment.status = psp_result["status"]
    payment.psp_ref = psp_result.get("psp_ref")

    ride_result = await db.execute(select(Ride).where(Ride.id == trip.ride_id))
    ride = ride_result.scalar_one_or_none()
    if ride:
        ride.status = "COMPLETED" if psp_result["status"] == "SUCCESS" else "PAYMENT_FAILED"

    await db.commit()

    # 7. Cache invalidation
    redis = await get_redis()
    if ride:
        await cache_delete(redis, f"ride:{ride.id}:status")

    response_body = {
        "payment_id": payment.id,
        "status": payment.status,
        "psp_ref": payment.psp_ref,
        "amount": float(payment.amount),
        "currency": payment.currency,
    }

    if idempotency_key:
        await store_idempotency_result(idempotency_key, 200, response_body)

    return PaymentResponse(**response_body)
