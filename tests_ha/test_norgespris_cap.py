"""Norgespris with the invoice's ceiling in a real Home Assistant (see tests/test_norgespris_cap.py).

The fake Amperium cuts one long request short at 4 000 kWh, like the real one. October here has
36 hours of 200 kWh (7 200 kWh), so the month is over both that cut and the ceiling of 5 000 kWh.
"""
from __future__ import annotations

import pytest
from ha_helpers import make_entry, setup_entry, value

PER_HOUR_KWH = 200.0
COMP_PER_KWH = 0.3


def charge_calls(api):
    return [path for _, path in api.calls if "/consumption/charges" in path]


async def test_a_month_over_the_ceiling_gets_the_first_5000_kwh_not_amperiums_cut(hass, api):
    api.oct_hourly_kwh = PER_HOUR_KWH
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    # 5 000 kWh = 25 of the 36 hours; Amperium's cut at 4 000 kWh would give 1 200.
    assert float(value(hass, entry, "norgespris_month")) == pytest.approx(
        COMP_PER_KWH * 5000.0, abs=0.01
    )


async def test_the_long_month_was_asked_for_in_pieces(hass, api):
    api.oct_hourly_kwh = PER_HOUR_KWH
    await setup_entry(hass, make_entry(scheme="norgespris"))
    this_month = [p for p in charge_calls(api) if "from=2026-08-31T22" not in p]   # not September
    assert len(this_month) >= 4                  # the whole month for its totals, then the pieces


async def test_a_small_month_is_asked_for_once(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    this_month = [p for p in charge_calls(api) if "from=2026-09-30T22" in p]
    assert len(this_month) == 1
    assert float(value(hass, entry, "norgespris_month")) == pytest.approx(
        COMP_PER_KWH * 2.0 * 36, abs=0.01
    )


async def test_a_piece_that_fails_leaves_norgespris_unknown_and_the_rest_working(hass, api):
    api.oct_hourly_kwh = PER_HOUR_KWH
    api.fail_short_charge_windows = True
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    assert value(hass, entry, "norgespris_month") == "unknown"     # not a wrong figure
    assert float(value(hass, entry, "energy_month")) == pytest.approx(36 * PER_HOUR_KWH)
