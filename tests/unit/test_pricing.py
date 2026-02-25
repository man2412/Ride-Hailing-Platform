"""
Unit tests for pricing service — surge computation and fare calculation.
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.services.pricing import calculate_fare, estimate_fare_range


class TestCalculateFare:
    def test_standard_no_surge(self):
        base, surge, total = calculate_fare("standard", 10.0, 1.0)
        # base = 30 + 10*10 = 130, surge = 0, total = 130
        assert base == Decimal("130.00")
        assert surge == Decimal("0.00")
        assert total == Decimal("130.00")

    def test_standard_with_surge(self):
        base, surge, total = calculate_fare("standard", 10.0, 2.0)
        # base = 130, surge = 130, total = 260
        assert base == Decimal("130.00")
        assert surge == Decimal("130.00")
        assert total == Decimal("260.00")

    def test_premium_no_surge(self):
        base, surge, total = calculate_fare("premium", 5.0, 1.0)
        # base = 60 + 15*5 = 135, surge = 0
        assert base == Decimal("135.00")
        assert surge == Decimal("0.00")
        assert total == Decimal("135.00")

    def test_xl_with_surge(self):
        base, surge, total = calculate_fare("xl", 20.0, 1.5)
        # base = 80 + 20*20 = 480
        # surge = 480 * 0.5 = 240
        # total = 720
        assert base == Decimal("480.00")
        assert surge == Decimal("240.00")
        assert total == Decimal("720.00")

    def test_zero_distance(self):
        base, surge, total = calculate_fare("standard", 0.0, 1.0)
        assert base == Decimal("30.00")
        assert total == Decimal("30.00")

    def test_max_surge(self):
        base, surge, total = calculate_fare("standard", 10.0, 5.0)
        assert total == base * 5

    def test_unknown_tier_uses_defaults(self):
        """Falls back to standard rates for unrecognised tier."""
        base, _, total = calculate_fare("unknown_tier", 10.0, 1.0)
        assert base == Decimal("130.00")


class TestEstimateFareRange:
    def test_range_width(self):
        result = estimate_fare_range("standard", 10.0, 1.0)
        assert result["min"] == pytest.approx(result["max"] * 0.9 / 1.1 * 1.1, rel=0.02)
        assert result["min"] < result["max"]
        assert result["currency"] == "INR"

    def test_range_contains_calculated_fare(self):
        _, _, total = calculate_fare("standard", 10.0, 1.0)
        result = estimate_fare_range("standard", 10.0, 1.0)
        assert result["min"] <= float(total) <= result["max"]


@pytest.mark.asyncio
class TestComputeSurge:
    async def test_no_demand_returns_1x(self):
        from app.services.pricing import compute_surge

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # 0 demand
        mock_redis.zcard = AsyncMock(return_value=10)  # 10 drivers

        result = await compute_surge(mock_redis, 12.97, 77.59, "standard")
        assert result == 1.0

    async def test_high_demand_returns_surge(self):
        from app.services.pricing import compute_surge

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="20")  # 20 requests
        mock_redis.zcard = AsyncMock(return_value=5)   # 5 drivers → ratio=4

        result = await compute_surge(mock_redis, 12.97, 77.59, "standard")
        assert result >= 3.0

    async def test_surge_capped_at_max(self):
        from app.services.pricing import compute_surge

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="100")
        mock_redis.zcard = AsyncMock(return_value=1)

        result = await compute_surge(mock_redis, 12.97, 77.59, "standard")
        assert result <= 5.0
