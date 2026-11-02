"""Tests for the hourly average power tracker."""
from __future__ import annotations

import datetime as dt

import pytest
from conftest import derived, hourpower
from helpers import (
    UTC,
)


# --- hourly power --------------------------------------------------------------
def test_hour_integrator_forecast_and_rollover():
    t0 = dt.datetime(2026, 10, 3, 10, tzinfo=UTC)
    minute = lambda m: t0 + dt.timedelta(minutes=m)  # noqa: E731
    h = hourpower.HourIntegrator()
    h.update(t0, 2.0)
    h.update(minute(30), 6.0)
    snap = h.snapshot(minute(45))
    assert snap["average_so_far_kw"] == pytest.approx((2 * 0.5 + 6 * 0.25) / 0.75)
    assert snap["forecast_kw"] == pytest.approx(4.0)
    h.snapshot(minute(75))
    assert h.last_complete["average_kw"] == pytest.approx(4.0)


def test_power_unit_conversion():
    assert hourpower.to_kw("2500", "W") == 2.5
    assert hourpower.to_kw("2.5", "kW") == 2.5
    assert hourpower.to_kw("unavailable", "W") is None
    assert hourpower.to_kw("5", None) is None


def test_power_now_local_value_from_the_live_tracker_units():
    # The tracker hands over kW already converted by to_kw (W, kW and MW supported).
    assert derived.choose_power_now(hourpower.to_kw("2500", "W"), None) == (2.5, "local_sensor")
    assert derived.choose_power_now(hourpower.to_kw("unavailable", "W"), 0.4) == (0.4, "amperium")
