import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=100,
        )
    return _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


# ---------------------------------------------------------------------------
# GEO helpers
# ---------------------------------------------------------------------------

async def geo_add_driver(redis: aioredis.Redis, tier: str, driver_id: str, lat: float, lng: float) -> None:
    """Add / update driver position in the geospatial index."""
    key = f"drivers:geo:{tier}"
    await redis.geoadd(key, [lng, lat, driver_id])
    # Refresh individual location key (used by matching engine)
    await redis.setex(f"driver:{driver_id}:loc", 30, f"{lat},{lng}")


async def geo_nearby_drivers(
    redis: aioredis.Redis,
    tier: str,
    lat: float,
    lng: float,
    radius_km: float,
    count: int = 15,
) -> list[str]:
    """Return up to `count` driver IDs nearest to the given coordinates."""
    key = f"drivers:geo:{tier}"
    results = await redis.geosearch(
        key,
        longitude=lng,
        latitude=lat,
        radius=radius_km,
        unit="km",
        sort="ASC",
        count=count,
    )
    return results  # type: ignore[return-value]


async def cache_set(redis: aioredis.Redis, key: str, value: str, ttl: int) -> None:
    await redis.setex(key, ttl, value)


async def cache_get(redis: aioredis.Redis, key: str) -> str | None:
    return await redis.get(key)


async def cache_delete(redis: aioredis.Redis, key: str) -> None:
    await redis.delete(key)
