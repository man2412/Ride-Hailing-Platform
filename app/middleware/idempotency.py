import json
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.redis_client import get_redis


IDEMPOTENCY_TTL = 86400  # 24 hours


async def check_idempotency(
    request: Request,
    db: AsyncSession,
) -> Optional[Response]:
    """
    FastAPI middleware helper.
    Returns a cached Response if the Idempotency-Key was already used,
    otherwise returns None (proceed normally).
    """
    key = request.headers.get("Idempotency-Key")
    if not key:
        return None

    redis = await get_redis()
    cache_key = f"idempotency:{key}"
    cached = await redis.get(cache_key)

    if cached:
        data = json.loads(cached)
        return JSONResponse(
            content=data["body"],
            status_code=data["status_code"],
            headers={"X-Idempotency-Replay": "true"},
        )
    return None


async def store_idempotency_result(key: str, status_code: int, body: dict) -> None:
    """Persist the response for the given idempotency key (24h TTL)."""
    redis = await get_redis()
    cache_key = f"idempotency:{key}"
    await redis.setex(
        cache_key,
        IDEMPOTENCY_TTL,
        json.dumps({"status_code": status_code, "body": body}),
    )
