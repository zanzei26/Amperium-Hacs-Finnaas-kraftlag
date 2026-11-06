"""Last month holds the autumn clock change (October 2026, 745 hours): sensors and the action.

The September of the other tests has no clock change, which is how a bug in the hour count of a month
with one got through once. Here the whole path runs on a month with 745 hours: the coordinator, the
sensors and ``amperium.hent_periode``. The fake Amperium in ``fake_clock_change`` copies what a real
installation showed for that month (see its docstring).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fake_api import hours_between
from fake_clock_change import (
    FIXED,
    GRID_AFTER,
    GRID_COMPENSATION,
    NOV_FIRST,
    NOW_CLOCK,
    OCT_FIRST,
    REPEATED_1,
    REPEATED_2,
    ClockChangeAmperium,
    compensation,
    energy_amount,
)
from ha_helpers import entity_id, make_entry, setup_entry, value

from custom_components.amperium.api import AmperiumClient
from custom_components.amperium.const import DOMAIN

OCTOBER = hours_between(OCT_FIRST, NOV_FIRST)
KRAFT = sum(energy_amount(h) for h in OCTOBER) + FIXED                        # from the hours and prices
NORGESPRIS = sum(compensation(h) for h in OCTOBER)
AMPERIUM_NORGESPRIS = NORGESPRIS - compensation(REPEATED_1) - compensation(REPEATED_2)
DEFICIT = 7.54


@pytest.fixture
def clock_api(freezer):
    """The fake with October as last month; the time is 5 November 2026."""
    freezer.move_to(NOW_CLOCK)
    fake = ClockChangeAmperium()

    async def request(self, method, path, **kwargs):
        return await fake.request(self, method, path, **kwargs)

    with patch.object(AmperiumClient, "_request", request):
        yield fake


def entry_for_november():
    return make_entry(scheme="norgespris", access_expires="2026-11-10T10:30:00Z")


def attributes(hass, entry, key):
    return hass.states.get(entity_id(hass, entry, key)).attributes


def test_the_scenario_is_the_one_it_says_it_is():
    assert len(OCTOBER) == 745
    assert abs(KRAFT - 25 - sum(energy_amount(h) for h in OCTOBER)) < 1e-9
    assert any(compensation(h) < 0 for h in OCTOBER)                 # some hours are under Norgespris


async def test_last_months_kraft_follows_the_prices_for_a_month_with_the_clock_change(hass, clock_api):
    entry = await setup_entry(hass, entry_for_november())
    assert float(value(hass, entry, "cost_energy_last_month")) == pytest.approx(KRAFT, abs=0.01)
    attrs = attributes(hass, entry, "cost_energy_last_month")
    assert attrs["kilde"] == "priser"
    assert attrs["fra_amperium"] == pytest.approx(KRAFT - DEFICIT, abs=0.01)
    assert float(value(hass, entry, "cost_last_month")) == pytest.approx(KRAFT + GRID_AFTER, abs=0.01)


async def test_last_months_norgespris_follows_the_prices_and_so_does_the_total(hass, clock_api):
    entry = await setup_entry(hass, entry_for_november())
    assert float(value(hass, entry, "norgespris_last_month")) == pytest.approx(NORGESPRIS, abs=0.01)
    attrs = attributes(hass, entry, "norgespris_last_month")
    assert attrs["kilde"] == "priser"
    assert attrs["fra_amperium"] == pytest.approx(AMPERIUM_NORGESPRIS, abs=0.01)
    assert attrs["norgespris_kwh"] == pytest.approx(745 * 3.0)
    total = KRAFT + GRID_AFTER + GRID_COMPENSATION - NORGESPRIS           # the subsidy is added back
    assert float(value(hass, entry, "net_cost_last_month")) == pytest.approx(total, abs=0.01)
    assert float(value(hass, entry, "avg_price_last_month")) == pytest.approx(total / (745 * 3.0), abs=5e-5)


async def test_this_month_is_not_disturbed_by_the_month_before(hass, clock_api):
    entry = await setup_entry(hass, entry_for_november())
    expected = sum(compensation(h) for h in hours_between(NOV_FIRST, NOW_CLOCK.replace(minute=0)))
    assert float(value(hass, entry, "norgespris_month")) == pytest.approx(expected, abs=0.01)


async def test_hent_periode_for_october_uses_the_prices_for_kraft_and_norgespris(hass, clock_api):
    await setup_entry(hass, entry_for_november())
    out = await hass.services.async_call(
        DOMAIN, "hent_periode", {"fra": "2026-10-01", "til": "2026-11-01"},
        blocking=True, return_response=True,
    )
    assert out["hours_expected"] == out["hours_with_data"] == 745
    assert out["kraft_kilde"] == "priser" and out["norgespris_kilde"] == "priser"
    assert out["energy_gross"] == pytest.approx(KRAFT, abs=0.01)
    assert out["energy_gross_amperium"] == pytest.approx(KRAFT - DEFICIT, abs=0.01)
    assert out["norgespris_compensation"] == pytest.approx(NORGESPRIS, abs=0.01)
    assert out["norgespris_compensation_amperium"] == pytest.approx(AMPERIUM_NORGESPRIS, abs=0.01)
    assert out["norgespris_avvik_fra_priser"] == pytest.approx(AMPERIUM_NORGESPRIS - NORGESPRIS, abs=0.01)
    assert out["norgespris_kwh"] == pytest.approx(745 * 3.0)
    assert out["house_cost_norgespris"] == pytest.approx(
        KRAFT + GRID_AFTER + GRID_COMPENSATION - NORGESPRIS, abs=0.01)
    assert "kraft_fra_priser_brukt" in out["warnings"]


async def test_without_prices_amperiums_own_figures_stay(hass, clock_api):
    clock_api.fail_long_price_windows = True               # the month-sized price requests fail
    entry = await setup_entry(hass, entry_for_november())
    assert float(value(hass, entry, "cost_energy_last_month")) == pytest.approx(KRAFT - DEFICIT, abs=0.01)
    assert attributes(hass, entry, "cost_energy_last_month")["kilde"] == "amperium"
    assert float(value(hass, entry, "norgespris_last_month")) == pytest.approx(AMPERIUM_NORGESPRIS, abs=0.01)
    assert attributes(hass, entry, "norgespris_last_month")["kilde"] == "amperium"
