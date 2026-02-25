from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TierEnum(str, Enum):
    standard = "standard"
    premium = "premium"
    xl = "xl"


class PaymentMethodEnum(str, Enum):
    card = "card"
    wallet = "wallet"
    cash = "cash"


class RideStatusEnum(str, Enum):
    REQUESTED = "REQUESTED"
    MATCHED = "MATCHED"
    DRIVER_EN_ROUTE = "DRIVER_EN_ROUTE"
    TRIP_STARTED = "TRIP_STARTED"
    TRIP_PAUSED = "TRIP_PAUSED"
    TRIP_ENDED = "TRIP_ENDED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class DriverStatusEnum(str, Enum):
    offline = "offline"
    available = "available"
    on_trip = "on_trip"


class PaymentStatusEnum(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


# ---------------------------------------------------------------------------
# Ride schemas
# ---------------------------------------------------------------------------

class RideCreateRequest(BaseModel):
    pickup_lat: float = Field(..., ge=-90, le=90)
    pickup_lng: float = Field(..., ge=-180, le=180)
    dest_lat: float = Field(..., ge=-90, le=90)
    dest_lng: float = Field(..., ge=-180, le=180)
    tier: TierEnum = TierEnum.standard
    payment_method: PaymentMethodEnum


class EstimatedFare(BaseModel):
    min: float
    max: float
    currency: str = "INR"


class RideCreateResponse(BaseModel):
    id: str
    status: RideStatusEnum
    surge_multiplier: float
    estimated_fare: EstimatedFare
    created_at: datetime

    model_config = {"from_attributes": True}


class DriverBrief(BaseModel):
    id: str
    name: str
    phone: str
    eta_minutes: Optional[int] = None


class RideStatusResponse(BaseModel):
    id: str
    status: RideStatusEnum
    driver: Optional[DriverBrief] = None
    surge_multiplier: float
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Driver schemas
# ---------------------------------------------------------------------------

class DriverCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., min_length=10, max_length=20)
    tier: TierEnum = TierEnum.standard


class DriverResponse(BaseModel):
    id: str
    name: str
    phone: str
    tier: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LocationUpdateRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    timestamp: Optional[datetime] = None


class AcceptRideRequest(BaseModel):
    ride_id: str


class AcceptRideResponse(BaseModel):
    trip_id: str
    status: str


# ---------------------------------------------------------------------------
# Trip schemas
# ---------------------------------------------------------------------------

class TripEndRequest(BaseModel):
    final_lat: float = Field(..., ge=-90, le=90)
    final_lng: float = Field(..., ge=-180, le=180)


class TripEndResponse(BaseModel):
    trip_id: str
    distance_km: float
    base_fare: float
    surge_fare: float
    total_fare: float
    currency: str = "INR"
    payment_status: str


# ---------------------------------------------------------------------------
# Payment schemas
# ---------------------------------------------------------------------------

class PaymentRequest(BaseModel):
    trip_id: str
    payment_method: PaymentMethodEnum
    amount: Decimal = Field(..., gt=0)


class PaymentResponse(BaseModel):
    payment_id: str
    status: PaymentStatusEnum
    psp_ref: Optional[str] = None
    amount: float
    currency: str
