# GoComet Ride-Hailing Platform

A multi-tenant, multi-region ride-hailing backend (Uber/Ola-like) built for the GoComet SDE-2 assignment.

## Tech Stack

| Layer | Technology |
|---|---|
| **Framework** | Python 3.12 + FastAPI |
| **Database** | PostgreSQL 15 (PostGIS extension) |
| **Cache / GEO** | Redis 7 (GEOSEARCH, GEOADD) |
| **Connection Pool** | PgBouncer (transaction mode) |
| **Migrations** | Alembic |
| **Auth** | JWT (HS256) |
| **Monitoring** | New Relic APM |
| **Container** | Docker + Docker Compose |

---

## Quick Start

### 1. Clone & configure

```bash
git clone <repo-url>
cd Ride-Hailing-Platform
cp .env.example .env
# Edit .env — set NEW_RELIC_LICENSE_KEY, PSP_API_KEY if needed
```

### 2. Start the full stack

```bash
docker-compose up --build
```

The API will be available at **http://localhost:8000**
Interactive docs at **http://localhost:8000/docs**

### 3. Run tests

```bash
# Unit tests only (no DB/Redis needed)
pip install -r requirements.txt
pytest tests/unit/ -v

# All tests (requires docker-compose up)
docker-compose exec app sh -c "PYTHONPATH=/app pytest tests/ -v"

# Full end-to-end flow hitting all core APIs
docker-compose exec app python test_flow.py
```

---

## API Reference (vs Assignment Requirements)

### Authentication
All endpoints except `POST /v1/drivers` require a JWT Bearer token in the `Authorization` header.

To get a token (dev only):
```python
from app.middleware.auth import create_access_token
token = create_access_token({"sub": "your-user-id"})
```

### Core Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/v1/rides` | Create ride request (idempotent) |
| `GET` | `/v1/rides/{id}` | Get ride status (cached) |
| `POST` | `/v1/drivers` | Register a driver |
| `PATCH` | `/v1/drivers/{id}/status` | Toggle driver availability |
| `POST` | `/v1/drivers/{id}/location` | Send location update (hot path) |
| `POST` | `/v1/drivers/{id}/accept` | Accept a matched ride |
| `POST` | `/v1/trips/{id}/end` | End trip + calculate fare |
| `POST` | `/v1/payments` | Trigger payment (idempotent) |

All core APIs requested in the assignment are implemented with validation, idempotency where required, and clean state transitions:

- **`POST /v1/rides`**: creates a ride request, computes surge and estimated fare, persists to Postgres, and asynchronously kicks off the matching engine.
- **`GET /v1/rides/{id}`**: returns ride status and (optional) assigned driver, with Redis cache-aside for fast reads.
- **`POST /v1/drivers/{id}/location`**: writes to Redis GEO (hot path) and asynchronously flushes to Postgres.
- **`POST /v1/drivers/{id}/accept`**: driver accepts assignment; uses `SELECT FOR UPDATE` and Redis locking to avoid double-acceptance.
- **`POST /v1/trips/{id}/end`**: computes distance + fare, transitions trip/ride/driver state, and creates a pending payment.
- **`POST /v1/payments`**: idempotent payment trigger that validates amount against server-side fare and updates ride/payment status accordingly.

### Example: Full ride lifecycle (happy path)

```bash
# 1. Register driver
curl -X POST http://localhost:8000/v1/drivers \
  -H "Content-Type: application/json" \
  -d '{"name":"Ramesh K","phone":"+919876543210","tier":"standard"}'

# 2. Driver goes online
curl -X PATCH "http://localhost:8000/v1/drivers/{DRIVER_ID}/status?new_status=available"

# 3. Driver sends location
curl -X POST http://localhost:8000/v1/drivers/{DRIVER_ID}/location \
  -H "Authorization: Bearer {TOKEN}" \
  -d '{"lat":12.9716,"lng":77.5946}'

# 4. Rider creates ride
curl -X POST http://localhost:8000/v1/rides \
  -H "Authorization: Bearer {RIDER_TOKEN}" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"pickup_lat":12.9716,"pickup_lng":77.5946,"dest_lat":13.0827,"dest_lng":80.2707,"tier":"standard","payment_method":"card"}'

# 5. Poll ride status until matched (simplified)
curl -X GET http://localhost:8000/v1/rides/{RIDE_ID} \
  -H "Authorization: Bearer {RIDER_TOKEN}"

# 6. Driver accepts (use the driver id returned from GET /v1/rides/{id})
curl -X POST http://localhost:8000/v1/drivers/{MATCHED_DRIVER_ID}/accept \
  -H "Authorization: Bearer {DRIVER_TOKEN}" \
  -d '{"ride_id":"{RIDE_ID}"}'

# 7. End trip
curl -X POST http://localhost:8000/v1/trips/{TRIP_ID}/end \
  -d '{"final_lat":13.0827,"final_lng":80.2707}'

# 8. Pay (use the total_fare returned from /v1/trips/{id}/end)
curl -X POST http://localhost:8000/v1/payments \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"trip_id":"{TRIP_ID}","payment_method":"card","amount":{TOTAL_FARE_FROM_SERVER}}'
```

---

## Architecture Highlights (How This Maps to the Requirements)

### Business Logic & State Machine
- **Trip lifecycle** is modeled via `Ride.status` and `Trip.status`, with a tested state machine ensuring valid transitions (see `tests/unit/test_state_machine.py`).
- **Payments** are handled via a `Payment` model and `/v1/payments` API that enforces server-side fare validation and integrates with a PSP stub for external payments.
- **Idempotency** is implemented for:
  - `POST /v1/rides` and `POST /v1/payments` via the `Idempotency-Key` header and Redis-backed storage.
- **Error handling & edge cases**:
  - 4xx errors for validation/auth failures (`422`, `401`, `400`, `409`).
  - 5xx defensive paths when backend dependencies are unavailable.

### Matching Engine (≤1s p95 goal)
- Redis `GEOSEARCH` finds nearest available drivers in the target tier.
- Redis `SET NX` per-driver lock prevents double-assignment across rides.
- PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` is used to atomically transition ride + driver + trip rows.
- Matching runs asynchronously in the background, keeping `POST /v1/rides` latency low while still assigning drivers quickly.

### Location Updates at Scale (~200k/sec)
- **Fast path**: `GEOADD` to Redis (in-memory, sub-millisecond writes).
- **Slow path**: background task flushes driver locations to Postgres without blocking the hot path.
- Tier-specific GEO keys (`drivers:geo:{tier}`) allow fast queries for nearby drivers.

### Surge Pricing
- Demand/supply ratio per spatial tier computed from Redis counters.
- Returns 1.0×–5.0× multiplier, updated periodically by the pricing service.

### Caching, Latency Optimizations & Indexing
- Redis is used as:
  - GEO index for drivers.
  - Cache-aside for ride status lookups.
  - Store for idempotent responses.
- Database models define indexes on hot columns (e.g. `rider_id`, `driver_id`, `status`, timestamps) to keep queries fast.
- All API handlers are async and stateless so instances can scale horizontally behind a load balancer.

### Concurrency, Atomicity & Consistency
- Critical sections (matching, trip end, payments) are wrapped in transactions and/or `SELECT FOR UPDATE` to avoid race conditions.
- Redis locks (`SET NX` with expiry) plus DB-level locking ensure **driver allocations remain consistent** under contention.
- Cache invalidation is centralized via helpers that delete ride status keys whenever ride/trip/payment state changes.

---

## Monitoring (New Relic)

1. Add your license key to `.env`: `NEW_RELIC_LICENSE_KEY=<key>`
2. Start the app — New Relic agent auto-instruments FastAPI (see `app/main.py`)
3. Dashboard shows API p50/p95/p99 latencies, error rates, slow DB queries

Alert thresholds suggested:
- API p95 > 500ms → Warning
- Error rate > 1% → Critical  
- Redis connection failures → Critical

---

## Project Structure

```
app/
├── main.py               # FastAPI app + lifespan + New Relic init
├── config.py             # Pydantic settings (multi-region, DB, Redis, PSP, etc.)
├── database.py           # Async SQLAlchemy engine + session factory
├── redis_client.py       # Redis pool + GEO + cache helpers
├── models/               # SQLAlchemy ORM models (Driver, Ride, Trip, Payment, Idempotency)
├── schemas/              # Pydantic request/response schemas (rides, drivers, trips, payments)
├── routers/              # API route handlers (rides, drivers, trips, payments)
├── services/             # Business logic (matching, pricing, payment)
└── middleware/           # Auth (JWT), Idempotency
migrations/               # Alembic migrations
tests/
├── unit/                 # Pricing, state machine, service-level tests
└── integration/          # API-level tests (FastAPI + HTTPX)
test_flow.py              # Script that exercises full happy-path lifecycle via HTTP
```

> **Note on Frontend & Notifications:**  
> This repository focuses on the backend and performance aspects of the assignment. A minimal frontend (for live driver/ride updates) and user-facing notification channels (email/SMS/push) can be layered on top of these APIs using WebSockets/SSE or an external notification service, but are not included in this codebase.

---

## Performance Report

Run the load test locally:
```bash
pip install locust
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

See New Relic dashboard for real APM data under load.
