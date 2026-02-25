"""
Rides router — POST /v1/rides, GET /v1/rides/{id}
"""
import json
import logging
import asyncio
from math import radians, sin, cos, sqrt, atan2

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.middleware.auth import get_current_rider
from app.middleware.idempotency import check_idempotency, store_idempotency_result
from app.models.ride import Ride
from app.models.driver import Driver
from app.redis_client import get_redis, cache_get, cache_set
from app.schemas.schemas import (
    RideCreateRequest, RideCreateResponse, RideStatusResponse, DriverBrief, EstimatedFare
)
from app.services.pricing import compute_surge, estimate_fare_range, increment_demand
from app.services.matching import run_matching

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/rides", tags=["Rides"])


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate straight-line distance in km (good enough for fare estimate)."""
    R = 6371
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RideCreateResponse)
async def create_ride(
    payload: RideCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    rider_id: str = Depends(get_current_rider),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    # 1. Idempotency check
    if idempotency_key:
        cached = await check_idempotency(request, db)
        if cached:
            return cached

    redis = await get_redis()

    # 2. Surge pricing
    surge = await compute_surge(redis, payload.pickup_lat, payload.pickup_lng, payload.tier.value)

    # 3. Estimated distance
    distance_km = _haversine_km(
        payload.pickup_lat, payload.pickup_lng, payload.dest_lat, payload.dest_lng
    )
    fare_range = estimate_fare_range(payload.tier.value, distance_km, surge)

    # 4. Create ride record
    ride = Ride(
        rider_id=rider_id,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        dest_lat=payload.dest_lat,
        dest_lng=payload.dest_lng,
        tier=payload.tier.value,
        status="REQUESTED",
        payment_method=payload.payment_method.value,
        surge_multiplier=surge,
        idempotency_key=idempotency_key,
    )
    db.add(ride)
    await db.flush()  # get ride.id before commit
    await db.commit()
    await db.refresh(ride)

    # 5. Increment surge demand counter
    await increment_demand(redis, payload.tier.value)

    # 6. Kick off matching asynchronously (fire-and-forget)
    asyncio.create_task(
        run_matching(
            ride_id=ride.id,
            pickup_lat=payload.pickup_lat,
            pickup_lng=payload.pickup_lng,
            tier=payload.tier.value,
            redis=redis,
        )
    )

    response_body = {
        "id": ride.id,
        "status": ride.status,
        "surge_multiplier": float(ride.surge_multiplier),
        "estimated_fare": fare_range,
        "created_at": ride.created_at.isoformat(),
    }

    # 7. Store idempotency result
    if idempotency_key:
        await store_idempotency_result(idempotency_key, 201, response_body)

    return RideCreateResponse(
        id=ride.id,
        status=ride.status,
        surge_multiplier=float(ride.surge_multiplier),
        estimated_fare=EstimatedFare(**fare_range),
        created_at=ride.created_at,
    )


@router.get("/{ride_id}", response_model=RideStatusResponse)
async def get_ride(
    ride_id: str,
    db: AsyncSession = Depends(get_db),
    rider_id: str = Depends(get_current_rider),
):
    redis = await get_redis()

    # Cache-aside: check Redis first
    cache_key = f"ride:{ride_id}:status"
    cached = await cache_get(redis, cache_key)
    if cached:
        data = json.loads(cached)
        return RideStatusResponse(**data)

    # DB fallback
    result = await db.execute(select(Ride).where(Ride.id == ride_id))
    ride = result.scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    driver_brief = None
    if ride.driver_id:
        drv = await db.get(Driver, ride.driver_id)
        if drv:
            driver_brief = DriverBrief(id=drv.id, name=drv.name, phone=drv.phone)

    resp = RideStatusResponse(
        id=ride.id,
        status=ride.status,
        driver=driver_brief,
        surge_multiplier=float(ride.surge_multiplier),
        updated_at=ride.updated_at,
    )

    # Populate cache (60s TTL)
    await cache_set(redis, cache_key, resp.model_dump_json(), ttl=60)
    return resp
