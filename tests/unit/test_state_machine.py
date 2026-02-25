"""
Unit tests for ride status state machine validations.
"""
import pytest

# Valid transitions for the ride state machine
VALID_TRANSITIONS = {
    "REQUESTED": {"MATCHED", "CANCELLED"},
    "MATCHED": {"DRIVER_EN_ROUTE", "CANCELLED", "REQUESTED"},
    "DRIVER_EN_ROUTE": {"TRIP_STARTED", "CANCELLED"},
    "TRIP_STARTED": {"TRIP_PAUSED", "TRIP_ENDED"},
    "TRIP_PAUSED": {"TRIP_STARTED"},
    "TRIP_ENDED": {"PAYMENT_PENDING"},
    "PAYMENT_PENDING": {"COMPLETED", "PAYMENT_FAILED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "PAYMENT_FAILED": {"PAYMENT_PENDING"},
}


def is_valid_transition(current: str, next_state: str) -> bool:
    return next_state in VALID_TRANSITIONS.get(current, set())


class TestRideStateMachine:
    def test_requested_to_matched(self):
        assert is_valid_transition("REQUESTED", "MATCHED")

    def test_requested_to_cancelled(self):
        assert is_valid_transition("REQUESTED", "CANCELLED")

    def test_matched_to_driver_en_route(self):
        assert is_valid_transition("MATCHED", "DRIVER_EN_ROUTE")

    def test_driver_en_route_to_trip_started(self):
        assert is_valid_transition("DRIVER_EN_ROUTE", "TRIP_STARTED")

    def test_trip_started_to_trip_ended(self):
        assert is_valid_transition("TRIP_STARTED", "TRIP_ENDED")

    def test_trip_ended_to_payment_pending(self):
        assert is_valid_transition("TRIP_ENDED", "PAYMENT_PENDING")

    def test_payment_pending_to_completed(self):
        assert is_valid_transition("PAYMENT_PENDING", "COMPLETED")

    def test_payment_failed_can_retry(self):
        assert is_valid_transition("PAYMENT_FAILED", "PAYMENT_PENDING")

    def test_completed_is_terminal(self):
        assert not is_valid_transition("COMPLETED", "REQUESTED")
        assert not is_valid_transition("COMPLETED", "MATCHED")

    def test_cancelled_is_terminal(self):
        assert not is_valid_transition("CANCELLED", "REQUESTED")

    def test_invalid_backward_skip(self):
        # Cannot jump from TRIP_STARTED back to REQUESTED
        assert not is_valid_transition("TRIP_STARTED", "REQUESTED")

    def test_invalid_forward_skip(self):
        # Cannot skip DRIVER_EN_ROUTE
        assert not is_valid_transition("MATCHED", "TRIP_STARTED")
