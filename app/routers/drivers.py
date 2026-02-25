"""
Drivers router — POST /v1/drivers (create), POST /v1/drivers/{id}/location,
                 POST /v1/drivers/{id}/accept, PATCH /v1/drivers/{id}/status
"""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import get_db
from app.middleware.auth import get_current_driver
from app.models.driver import Driver
from app.models.ride import Ride
from app.models.trip import Trip
from app.redis_client import get_redis, geo_add_driver, cache_delete
from app.schemas.schemas import (
    DriverCreateRequest, DriverResponse,
    LocationUpdateRequest, AcceptRideRequest, AcceptRideResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/drivers", tags=["Drivers"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DriverResponse)
async def create_driver(
    payload: DriverCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new driver. No auth required for onboarding."""
    driver = Driver(
        name=payload.name,
        phone=payload.phone,
        tier=payload.tier.value,
        status="offline",
    )
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    return DriverResponse.model_validate(driver)


@router.patch("/{driver_id}/status", status_code=status.HTTP_200_OK)
async def update_driver_status(
    driver_id: str,
    new_status: str,
    db: AsyncSession = Depends(get_db),
):
    """Toggle driver online/offline (available ↔ offline)."""
    valid = {"offline", "available"}
    if new_status not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid}")
    result = await db.execute(select(Driver).where(Driver.id == driver_id))
    driver = result.scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver.status = new_status
    await db.commit()
    return {"id": driver_id, "status": new_status}


@router.post("/{driver_id}/location", status_code=status.HTTP_204_NO_CONTENT)
async def update_location(
    driver_id: str,
    payload: LocationUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    High-frequency endpoint (~200k/sec total).
    Fast path: writes to Redis GEO immediately.
    Slow path: persists to Postgres asynchronously.
    """
    redis = await get_redis()

    # 1. Get driver tier for GEO key (try Redis cache first to save a DB hit)
    tier_key = f"driver:{driver_id}:tier"
    tier = await redis.get(tier_key)

    if not tier:
        result = await db.execute(select(Driver.tier, Driver.status).where(Driver.id == driver_id))
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail="Driver not found")
        tier = row.tier
        await redis.setex(tier_key, 300, tier)  # cache tier for 5 min
        # Only index if driver is available
        if row.status == "available":
            await geo_add_driver(redis, tier, driver_id, payload.lat, payload.lng)
    else:
        await geo_add_driver(redis, tier, driver_id, payload.lat, payload.lng)

    # 2. Async Postgres flush (fire-and-forget)
    asyncio.create_task(_flush_location_to_db(driver_id, payload.lat, payload.lng, db))


async def _flush_location_to_db(driver_id: str, lat: float, lng: float, db: AsyncSession) -> None:
    """Background task: persist driver location to Postgres."""
    try:
        await db.execute(
            update(Driver)
            .where(Driver.id == driver_id)
            .values(lat=lat, lng=lng, location_updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
    except Exception as exc:
        logger.error("Failed to flush driver location to DB: %s", exc)


@router.post("/{driver_id}/accept", response_model=AcceptRideResponse)
async def accept_ride(
    driver_id: str,
    payload: AcceptRideRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Driver accepts a ride offer.
    Uses SELECT FOR UPDATE to prevent double-acceptance.
    """
    # Verify ride is in MATCHED state and assigned to this driver
    result = await db.execute(
        select(Ride).where(
            Ride.id == payload.ride_id,
            Ride.driver_id == driver_id,
            Ride.status == "MATCHED",
        ).with_for_update()
    )
    ride = result.scalar_one_or_none()
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ride not found or already processed",
        )

    # Transition to en route
    ride.status = "DRIVER_EN_ROUTE"

    # Fetch trip
    trip_result = await db.execute(select(Trip).where(Trip.ride_id == ride.id))
    trip = trip_result.scalar_one_or_none()
    if not trip:
        raise HTTPException(status_code=500, detail="Trip record missing")

    await db.commit()

    redis = await get_redis()
    await cache_delete(redis, f"ride:{ride.id}:status")

    return AcceptRideResponse(trip_id=trip.id, status="DRIVER_EN_ROUTE")
