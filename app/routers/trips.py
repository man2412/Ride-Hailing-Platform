"""
Trips router — POST /v1/trips/{id}/end
"""
import logging
from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.models.trip import Trip
from app.models.ride import Ride
from app.models.driver import Driver
from app.models.payment import Payment
from app.redis_client import get_redis, cache_delete
from app.schemas.schemas import TripEndRequest, TripEndResponse
from app.services.pricing import calculate_fare

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/trips", tags=["Trips"])


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


@router.post("/{trip_id}/end", response_model=TripEndResponse)
async def end_trip(
    trip_id: str,
    payload: TripEndRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    End a trip:
      1. Validate trip is ACTIVE
      2. Calculate distance + fare (in-memory, no extra DB round trips)
      3. Atomically update Trip, Ride, Driver in one transaction
      4. Create PENDING payment record
      5. Invalidate ride status cache
    """
    # Fetch trip with associated ride in one query
    result = await db.execute(select(Trip).where(Trip.id == trip_id))
    trip = result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(status_code=409, detail=f"Trip is already {trip.status}")

    ride_result = await db.execute(select(Ride).where(Ride.id == trip.ride_id))
    ride = ride_result.scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=500, detail="Associated ride not found")

    # Distance from pickup to final drop-off
    distance_km = _haversine_km(
        ride.pickup_lat, ride.pickup_lng, payload.final_lat, payload.final_lng
    )

    base_fare, surge_fare, total_fare = calculate_fare(
        ride.tier, distance_km, float(ride.surge_multiplier)
    )

    now = datetime.now(timezone.utc)

    # Atomic update: trip → COMPLETED, ride → TRIP_ENDED, driver → available
    async with db.begin_nested():
        trip.status = "COMPLETED"
        trip.ended_at = now
        trip.distance_km = round(distance_km, 3)
        trip.base_fare = base_fare
        trip.surge_fare = surge_fare
        trip.total_fare = total_fare

        ride.status = "PAYMENT_PENDING"

        # Free the driver
        await db.execute(
            update(Driver).where(Driver.id == trip.driver_id).values(status="available")
        )

        # Create payment record
        payment = Payment(
            trip_id=trip.id,
            rider_id=trip.rider_id,
            amount=total_fare,
            currency="INR",
            status="PENDING",
        )
        db.add(payment)

    await db.commit()

    # Invalidate cached ride status
    redis = await get_redis()
    await cache_delete(redis, f"ride:{ride.id}:status")

    return TripEndResponse(
        trip_id=trip.id,
        distance_km=round(distance_km, 3),
        base_fare=float(base_fare),
        surge_fare=float(surge_fare),
        total_fare=float(total_fare),
        currency="INR",
        payment_status="PAYMENT_PENDING",
    )
