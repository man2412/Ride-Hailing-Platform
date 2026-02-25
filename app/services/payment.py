"""
PSP payment adapter.

In production: swap the _call_psp stub for a real Stripe / Razorpay call.
"""
import logging
import uuid
from decimal import Decimal

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class PSPError(Exception):
    pass


async def charge(
    rider_id: str,
    amount: Decimal,
    payment_method: str,
    idempotency_key: str,
) -> dict:
    """
    Sends payment to PSP with up to 3 retries (exponential backoff).
    Returns: {"psp_ref": str, "status": "SUCCESS"/"FAILED"}
    """
    for attempt in range(1, 4):
        try:
            result = await _call_psp(rider_id, amount, payment_method, idempotency_key)
            logger.info("PSP charge success: ref=%s amount=%s", result["psp_ref"], amount)
            return result
        except PSPError as e:
            if attempt == 3:
                logger.error("PSP charge failed after 3 attempts: %s", e)
                return {"psp_ref": None, "status": "FAILED"}
            wait = 2 ** attempt
            import asyncio
            await asyncio.sleep(wait)

    return {"psp_ref": None, "status": "FAILED"}


async def _call_psp(rider_id: str, amount: Decimal, payment_method: str, idempotency_key: str) -> dict:
    """
    Stub PSP call.  Replace with real SDK/HTTP call in production.
    Currently simulates a successful charge for non-zero amounts.
    """
    if float(amount) <= 0:
        raise PSPError("Amount must be positive")

    # --- Production: use httpx to call Stripe / Razorpay ---
    # async with httpx.AsyncClient(timeout=settings.psp_timeout_seconds) as client:
    #     resp = await client.post(
    #         f"{settings.psp_base_url}/charges",
    #         headers={
    #             "Authorization": f"Bearer {settings.psp_api_key}",
    #             "Idempotency-Key": idempotency_key,
    #         },
    #         json={"amount": int(amount * 100), "currency": "inr", "source": payment_method},
    #     )
    #     if resp.status_code >= 400:
    #         raise PSPError(f"PSP error {resp.status_code}: {resp.text}")
    #     return {"psp_ref": resp.json()["id"], "status": "SUCCESS"}

    # Stub: always succeeds
    return {
        "psp_ref": f"PSP-{uuid.uuid4().hex[:12].upper()}",
        "status": "SUCCESS",
    }
