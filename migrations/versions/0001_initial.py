"""Initial schema — rides, drivers, trips, payments"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drivers",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(20), unique=True, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(20), nullable=False, server_default="offline"),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_drivers_status", "drivers", ["status"])
    op.create_index("idx_drivers_tier_status", "drivers", ["tier", "status"])

    op.create_table(
        "rides",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("rider_id", sa.String, nullable=False),
        sa.Column("driver_id", sa.String, sa.ForeignKey("drivers.id"), nullable=True),
        sa.Column("pickup_lat", sa.Float, nullable=False),
        sa.Column("pickup_lng", sa.Float, nullable=False),
        sa.Column("dest_lat", sa.Float, nullable=False),
        sa.Column("dest_lng", sa.Float, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(30), nullable=False, server_default="REQUESTED"),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("surge_multiplier", sa.Numeric(4, 2), server_default="1.0"),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_rides_status", "rides", ["status"])
    op.create_index("idx_rides_rider", "rides", ["rider_id"])
    op.create_index("idx_rides_driver", "rides", ["driver_id"])
    op.create_index("idx_rides_created", "rides", ["created_at"])

    op.create_table(
        "trips",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("ride_id", sa.String, sa.ForeignKey("rides.id"), unique=True, nullable=False),
        sa.Column("driver_id", sa.String, sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("rider_id", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distance_km", sa.Numeric(10, 3), nullable=True),
        sa.Column("base_fare", sa.Numeric(10, 2), nullable=True),
        sa.Column("surge_fare", sa.Numeric(10, 2), nullable=True),
        sa.Column("total_fare", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_trips_ride", "trips", ["ride_id"])
    op.create_index("idx_trips_status", "trips", ["status"])

    op.create_table(
        "payments",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("trip_id", sa.String, sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("rider_id", sa.String, nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(5), server_default="INR"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("psp_ref", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_payments_trip", "payments", ["trip_id"])
    op.create_index("idx_payments_status", "payments", ["status"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("trips")
    op.drop_table("rides")
    op.drop_table("drivers")
