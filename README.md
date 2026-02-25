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
docker-compose run app pytest tests/ -v
```

---

## API Reference

### Authentication
All endpoints except `POST /v1/drivers` require a JWT Bearer token in the `Authorization` header.

To get a token (dev only):
```python
from app.middleware.auth import create_access_token
token = create_access_token({"sub": "your-user-id"})
```

### Endpoints

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

### Example: Full ride lifecycle

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

# 5. Driver accepts
curl -X POST http://localhost:8000/v1/drivers/{DRIVER_ID}/accept \
  -H "Authorization: Bearer {DRIVER_TOKEN}" \
  -d '{"ride_id":"{RIDE_ID}"}'

# 6. End trip
curl -X POST http://localhost:8000/v1/trips/{TRIP_ID}/end \
  -d '{"final_lat":13.0827,"final_lng":80.2707}'

# 7. Pay
curl -X POST http://localhost:8000/v1/payments \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{"trip_id":"{TRIP_ID}","payment_method":"card","amount":480.00}'
```

---

## Architecture Highlights

### Matching Engine (≤1s p95)
- Redis `GEOSEARCH` finds nearest available drivers in the target tier
- Redis `SET NX` lock prevents double-assignment
- PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` for atomic state transition

### Location Updates (200k/sec)
- **Fast path**: `GEOADD` to Redis (in-memory, sub-millisecond)
- **Slow path**: async `asyncio.create_task` flushes to Postgres in background

### Surge Pricing
- Demand/supply ratio per spatial tier computed from Redis counters
- Returns 1.0×–5.0× multiplier, updated every 30 seconds

### Idempotency
- `Idempotency-Key` header on `POST /v1/rides` and `POST /v1/payments`
- Response cached in Redis for 24 hours — identical key returns cached response

### Concurrency Safety
- `SELECT FOR UPDATE SKIP LOCKED` prevents race conditions on driver assignment
- Redis `NX` lock prevents a driver from being offered two rides simultaneously

---

## Monitoring (New Relic)

1. Add your license key to `.env`: `NEW_RELIC_LICENSE_KEY=<key>`
2. Start the app — New Relic agent auto-instruments FastAPI
3. Dashboard shows API p50/p95/p99 latencies, error rates, slow DB queries

Alert thresholds suggested:
- API p95 > 500ms → Warning
- Error rate > 1% → Critical  
- Redis connection failures → Critical

---

## Project Structure

```
app/
├── main.py               # FastAPI app + lifespan
├── config.py             # Pydantic settings
├── database.py           # Async SQLAlchemy engine
├── redis_client.py       # Redis pool + GEO helpers
├── models/               # SQLAlchemy ORM models
├── schemas/              # Pydantic request/response schemas
├── routers/              # API route handlers
├── services/             # Business logic (matching, pricing, payment)
└── middleware/           # Auth (JWT) + Idempotency
migrations/               # Alembic migrations
tests/
├── unit/                 # Pricing, state machine tests
└── integration/          # End-to-end API tests
```

---

## Performance Report

Run the load test locally:
```bash
pip install locust
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

See New Relic dashboard for real APM data under load.
