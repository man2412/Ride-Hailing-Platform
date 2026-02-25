"""
Driver–rider matching engine.

Flow:
  1. Receive ride_id + pickup coords + tier
  2. GEOSEARCH Redis for nearest available drivers
  3. Lock top candidate with a Redis NX key (prevents double-assignment)
  4. Atomically update Ride + Driver rows in Postgres
  5. On failure/timeout → try next candidate; after max_retries → cancel
"""
import asyncio
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.driver import Driver
from app.models.ride import Ride
from app.models.trip import Trip
from app.redis_client import geo_nearby_drivers, cache_delete

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_matching(
    ride_id: str,
    pickup_lat: float,
    pickup_lng: float,
    tier: str,
    redis: aioredis.Redis,
) -> bool:
    """
    Attempts to find and assign a driver for the given ride.
    Returns True on success, False if no driver found.
    """
    async with AsyncSessionLocal() as db:
        candidates = await geo_nearby_drivers(
            redis,
            tier,
            pickup_lat,
            pickup_lng,
            radius_km=settings.matching_radius_km,
            count=settings.matching_max_retries * 5,
        )

        if not candidates:
            await _cancel_ride(ride_id, db)
            return False

        for driver_id in candidates:
            lock_key = f"driver:{driver_id}:lock"
            acquired = await redis.set(
                lock_key,
                ride_id,
                nx=True,
                px=settings.matching_timeout_seconds * 1000,
            )
            if not acquired:
                continue  # driver locked by another ride

            # Verify driver is still available in DB (ground truth)
            driver = await db.get(Driver, driver_id)
            if driver is None or driver.status != "available":
                await redis.delete(lock_key)
                continue

            # Atomic assignment
            try:
                assigned = await _assign_driver(ride_id, driver_id, db)
                if assigned:
                    logger.info("Matched ride=%s to driver=%s", ride_id, driver_id)
                    # Invalidate cached ride status
                    await cache_delete(redis, f"ride:{ride_id}:status")
                    return True
            except Exception as exc:
                logger.error(
                    "Assignment error ride=%s driver=%s: %s", ride_id, driver_id, exc
                )
                await redis.delete(lock_key)
                continue

        # All candidates exhausted
        await _cancel_ride(ride_id, db)
        return False


async def _assign_driver(ride_id: str, driver_id: str, db: AsyncSession) -> bool:
    """
    Atomically:
      - Update ride status → MATCHED with driver_id
      - Update driver status → on_trip
      - Create a Trip record
    Uses SELECT FOR UPDATE to prevent race conditions.
    """
    async with db.begin_nested():
        # Lock the driver row
        result = await db.execute(
            select(Driver).where(Driver.id == driver_id, Driver.status == "available").with_for_update(skip_locked=True)
        )
        driver = result.scalar_one_or_none()
        if driver is None:
            return False

        # Lock the ride row
        ride_result = await db.execute(
            select(Ride).where(Ride.id == ride_id, Ride.status == "REQUESTED").with_for_update()
        )
        ride = ride_result.scalar_one_or_none()
        if ride is None:
            return False

        # Transition states
        driver.status = "on_trip"
        ride.status = "MATCHED"
        ride.driver_id = driver_id

        # Create trip
        trip = Trip(
            ride_id=ride_id,
            driver_id=driver_id,
            rider_id=ride.rider_id,
            started_at=datetime.now(timezone.utc),
            status="ACTIVE",
        )
        db.add(trip)

    await db.commit()
    return True


async def _cancel_ride(ride_id: str, db: AsyncSession) -> None:
    await db.execute(
        update(Ride).where(Ride.id == ride_id).values(status="CANCELLED")
    )
    await db.commit()
    logger.warning("Ride %s cancelled (no driver found)", ride_id)
