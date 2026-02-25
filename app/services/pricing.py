"""
Surge pricing and fare calculation service.
"""
from decimal import Decimal, ROUND_HALF_UP

import redis.asyncio as aioredis

from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Tier rates (INR)
# ---------------------------------------------------------------------------
BASE_FEE: dict[str, float] = {"standard": 30, "premium": 60, "xl": 80}
RATE_PER_KM: dict[str, float] = {"standard": 10, "premium": 15, "xl": 20}


# ---------------------------------------------------------------------------
# Surge computation
# ---------------------------------------------------------------------------

async def compute_surge(
    redis: aioredis.Redis,
    lat: float,
    lng: float,
    tier: str,
) -> float:
    """
    Returns a surge multiplier (1.0 – MAX_SURGE) based on the
    demand/supply ratio in the nearby area.

    Keys used:
      surge:demand:{tier}  – count of REQUESTED rides (incr on create, decr on match)
      drivers:geo:{tier}   – ZSet of available drivers (maintained by location updates)
    """
    demand_key = f"surge:demand:{tier}"
    geo_key = f"drivers:geo:{tier}"

    demand_raw = await redis.get(demand_key)
    supply_raw = await redis.zcard(geo_key)

    demand = int(demand_raw or 0)
    supply = max(int(supply_raw or 0), 1)  # avoid div-by-zero

    ratio = demand / supply

    if ratio < 0.5:
        multiplier = 1.0
    elif ratio < 1.0:
        multiplier = 1.5
    elif ratio < 2.0:
        multiplier = 2.0
    elif ratio < 3.0:
        multiplier = 3.0
    else:
        multiplier = min(ratio, settings.max_surge_multiplier)

    return round(multiplier, 2)


async def increment_demand(redis: aioredis.Redis, tier: str) -> None:
    """Call when a new ride is requested."""
    await redis.incr(f"surge:demand:{tier}")
    await redis.expire(f"surge:demand:{tier}", 120)  # auto-expiry safety net


async def decrement_demand(redis: aioredis.Redis, tier: str) -> None:
    """Call when a ride is matched, cancelled, or timed out."""
    key = f"surge:demand:{tier}"
    current = await redis.get(key)
    if current and int(current) > 0:
        await redis.decr(key)


# ---------------------------------------------------------------------------
# Fare calculation
# ---------------------------------------------------------------------------

def calculate_fare(
    tier: str,
    distance_km: float,
    surge_multiplier: float,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Returns (base_fare, surge_fare, total_fare) as Decimals.
    total = base + surge_component
    """
    base = BASE_FEE.get(tier, 30) + RATE_PER_KM.get(tier, 10) * distance_km
    surge_component = base * (surge_multiplier - 1.0)
    total = base + surge_component

    to_dec = lambda v: Decimal(str(round(v, 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return to_dec(base), to_dec(surge_component), to_dec(total)


def estimate_fare_range(
    tier: str,
    distance_km: float,
    surge_multiplier: float,
) -> dict:
    """Used in the ride creation response (min/max window ±10%)."""
    _, _, total = calculate_fare(tier, distance_km, surge_multiplier)
    total_f = float(total)
    return {
        "min": round(total_f * 0.9, 2),
        "max": round(total_f * 1.1, 2),
        "currency": "INR",
    }
