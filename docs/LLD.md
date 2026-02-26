# Low-Level Design (LLD) - Ride-Hailing Platform

## 1. Codebase Structure
The project follows a clean, modular structure:

- `app/models/`: SQLAlchemy ORM definitions (Data Layer).
- `app/routers/`: FastAPI route handlers (API Layer).
- `app/services/`: Core business logic (Service Layer).
- `app/schemas/`: Pydantic models for request/response (Schema Layer).
- `app/middleware/`: Authentication and Idempotency logic.

## 2. Database Schema

### 2.1 Drivers (`drivers`)
- Maintains driver state, profile, and last known location.
- **Indexes**: `status`, `phone` (unique), `id`.

### 2.2 Rides (`rides`)
- Stores ride requests, pickup/drop locations, and assigned drivers.
- **Statuses**: `REQUESTED`, `MATCHED`, `STARTED`, `COMPLETED`, `CANCELLED`.
- **Spatial Data**: PostGIS `GEOMETRY` used for pickup/destination.

### 2.3 Trips (`trips`)
- Detailed record of an active ride, including distance and actual fare.
- **Status**: `ACTIVE`, `COMPLETED`.

### 2.4 Payments (`payments`)
- Financial transactions associated with trips.
- **Fields**: `trip_id`, `amount`, `status` (PENDING, SUCCESS, FAILED), `psp_ref`.

## 3. Service Logic

### 3.1 Matching Service (`matching.py`)
- **Action**: Nearest Neighbor Search.
- **Logic**:
    1. Query Redis `GEOSEARCH` for drivers in `drivers:geo:{tier}`.
    2. Iterate through found drivers and attempt to acquire a Redis lock using `SET NX`.
    3. If lock acquired, use Postgres `SELECT FOR UPDATE` to check DB availability.
    4. Transition Ride to `MATCHED` and Driver to `ON_TRIP`.

### 3.2 Pricing Service (`pricing.py`)
- **Formula**: `Total Fare = (Base Fare + (Distance * Rate)) * SurgeMultiplier`.
- **Surge Calculation**: Uses Redis counters to track active rides vs available drivers in the last 1-5 minutes to calculate a multiplier (1.0x to 5.0x).

### 3.3 Payment Service (`payment.py`)
- Implements idempotency using a unique `Idempotency-Key` provided by the client.
- Validates the payment amount against the server-calculated fare to prevent client-side manipulation.

## 4. State Machine Transitions

| Entity | Old Status | Command | New Status |
|---|---|---|---|
| **Ride** | `None` | Create | `REQUESTED` |
| **Ride** | `REQUESTED` | Accept | `MATCHED` |
| **Ride** | `MATCHED` | End Trip | `COMPLETED` |
| **Driver** | `available` | Assigned | `on_trip` |
| **Driver** | `on_trip` | End Trip | `available` |

## 5. Implementation Details

### 5.1 Concurrency Control
- **Optimistic Concurrency**: Handled via state checks.
- **Pessimistic Locking**: `SELECT FOR UPDATE` in PostgreSQL ensures that only one worker can process a driver/ride transition at a time.
- **Idempotency Middleware**: Checks Redis for a previously processed `Idempotency-Key` and returns the cached response if found.

### 5.2 Performance Optimizations
- **Connection Management**: Asyncpg with PGBouncer for high-performance DB access.
- **Hot-Path Writes**: Location updates skip the DB write buffer; they are written to Redis immediately and queued for background DB sync.
- **Cache Invalidation**: Whenever a ride's status changes, the corresponding Redis key is purged to ensure data consistency.

## 6. Security
- **JWT (JSON Web Tokens)**: Secure stateless authentication.
- **Scope-based Auth**: (Future) Distinguishing between Driver and Rider permissions.
- **Input Sanitization**: Pydantic for strict type checking and validation.
