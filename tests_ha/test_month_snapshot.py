"""This month's figures come from one snapshot, so they agree with each other and with the action.

/api/sites gives Kraft and Nettleie for the month every 15 minutes, but as of another moment than the
hourly figures that Norgespris is summed from. The month's sensors used to mix the two, so Totalt
could be off by an hour's worth. Now Kraft, Nettleie, Norgespris and kWh all cover the same hours,
from the 1st to ``til``, and are the same numbers ``amperium.hent_periode`` gives for that period.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fake_api import NOW, OCT_START, hours_between
from ha_helpers import advance, entity_id, make_entry, setup_entry, value
from homeassistant.helpers import entity_registry as er  # noqa: F401  (entity_id uses it)

from custom_components.amperium.const import DOMAIN
from custom_components.amperium.sensor import MONTH_SNAPSHOT_KEYS

HOUR = dt.timedelta(hours=1)
LAST_WHOLE_HOUR_END = NOW.replace(minute=0, second=0)             # 2 October 10:00 UTC


async def period(hass, until: dt.datetime = LAST_WHOLE_HOUR_END) -> dict:
    """amperium.hent_periode from 1 October (local) to ``until``."""
    return await hass.services.async_call(
        DOMAIN, "hent_periode",
        {"fra": "2026-09-30T22:00:00Z", "til": until.strftime("%Y-%m-%dT%H:%M:%SZ")},
        blocking=True, return_response=True,
    )


def num(hass, entry, key) -> float:
    return float(value(hass, entry, key))


def attrs(hass, entry, key):
    return hass.states.get(entity_id(hass, entry, key)).attributes


def this_month_charge_calls(api):
    return [path for _, path in api.calls if "/consumption/charges" in path and "from=2026-09-30T22" in path]


def assert_agrees_with(hass, entry, out):
    assert num(hass, entry, "cost_energy") == pytest.approx(out["energy_gross"], abs=0.01)           # Kraft
    assert num(hass, entry, "cost_grid_rent") == pytest.approx(out["grid_after_support"], abs=0.01)  # Nettleie
    assert num(hass, entry, "cost_total") == pytest.approx(
        out["energy_gross"] + out["grid_after_support"], abs=0.01)
    assert num(hass, entry, "norgespris_month") == pytest.approx(out["norgespris_compensation"], abs=0.01)
    assert num(hass, entry, "net_cost_month") == pytest.approx(out["house_cost_norgespris"], abs=0.01)  # Totalt
    assert num(hass, entry, "energy_month") == pytest.approx(out["consumption_kwh"], abs=0.001)
    assert num(hass, entry, "avg_price_month") == pytest.approx(out["price_per_kwh_norgespris"], abs=5e-5)


async def test_this_months_sensors_are_the_numbers_hent_periode_gives_for_the_same_hours(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    assert_agrees_with(hass, entry, await period(hass))
    assert attrs(hass, entry, "cost_energy")["til"] == LAST_WHOLE_HOUR_END.isoformat()
    assert attrs(hass, entry, "net_cost_month")["til"] == LAST_WHOLE_HOUR_END.isoformat()
    assert attrs(hass, entry, "norgespris_month")["til"] == LAST_WHOLE_HOUR_END.isoformat()


async def test_a_sites_total_that_is_ahead_of_the_hours_does_not_leak_into_the_month(hass, api):
    api.sites_skew_kr = 7.0                                   # /api/sites has an hour more than the rows
    api.sites_skew_kwh = 5.0
    api.sites_skew_grid_kr = 3.0
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    assert_agrees_with(hass, entry, await period(hass))
    assert num(hass, entry, "energy_month") == pytest.approx(72.0)        # not 77
    assert num(hass, entry, "cost_grid_rent") == pytest.approx(120.0)     # not 123


async def test_the_month_ends_at_the_last_whole_hour_that_has_consumption(hass, api):
    """Amperium is two hours behind: the consumption rows stop at 08:00 UTC."""
    api.missing_hours = {LAST_WHOLE_HOUR_END - HOUR, LAST_WHOLE_HOUR_END - 2 * HOUR}
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    until = LAST_WHOLE_HOUR_END - 2 * HOUR
    assert attrs(hass, entry, "cost_energy")["til"] == until.isoformat()
    assert num(hass, entry, "energy_month") == pytest.approx(68.0)       # 34 hours of 2 kWh
    assert attrs(hass, entry, "norgespris_month")["kilde"] == "priser"   # every hour up to `til` has a price
    assert_agrees_with(hass, entry, await period(hass, until))
    # the costs and the prices were asked for exactly that window
    ends = until.strftime("to=%Y-%m-%dT%H:%M:%SZ")
    assert all(ends in path for path in this_month_charge_calls(api))


async def test_new_data_from_amperium_makes_the_hourly_read_run_again_without_waiting_an_hour(hass, api, freezer):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    first = len(this_month_charge_calls(api))
    await advance(hass, freezer, dt.timedelta(minutes=15, seconds=1))     # the main poll: nothing new
    assert len(this_month_charge_calls(api)) == first
    assert value(hass, entry, "energy_month") not in ("unknown", "unavailable")
    api.energy_updated_on = "2026-10-02T10:05:00Z"                        # Amperium has new consumption data
    await advance(hass, freezer, dt.timedelta(minutes=15, seconds=1))
    assert len(this_month_charge_calls(api)) > first


async def test_without_the_hourly_read_the_sites_figures_stay_and_say_nothing_about_a_snapshot(hass, api):
    api.sites_skew_kr = 7.0
    api.overrides["/api/sites/7001/consumption/charges"] = (500, None)
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    hours = hours_between(OCT_START, LAST_WHOLE_HOUR_END)
    expected = sum(2.0 * (0.5 + h.hour * 0.01 + 0.05) * 1.25 for h in hours) + 25.0 + 7.0
    assert num(hass, entry, "cost_energy") == pytest.approx(expected, abs=0.01)     # /api/sites as it was
    assert "til" not in attrs(hass, entry, "cost_energy")


async def test_this_months_kraft_follows_the_prices_when_amperiums_total_is_too_low(hass, api):
    api.oct_total_deficit = 7.54                              # as a month with a clock change was
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    hours = hours_between(OCT_START, LAST_WHOLE_HOUR_END)
    kraft = sum(2.0 * (0.5 + h.hour * 0.01 + 0.05) * 1.25 for h in hours) + 25.0
    assert num(hass, entry, "cost_energy") == pytest.approx(kraft, abs=0.01)
    assert attrs(hass, entry, "cost_energy")["kilde"] == "priser"
    assert attrs(hass, entry, "cost_energy")["fra_amperium"] == pytest.approx(kraft - 7.54, abs=0.01)
    assert_agrees_with(hass, entry, await period(hass))


async def test_every_figure_of_the_months_snapshot_says_how_far_it_goes(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    checked = []
    for key in sorted(MONTH_SNAPSHOT_KEYS):
        state = hass.states.get(entity_id(hass, entry, key))
        if state is None:                                    # a sensor that is off by default
            continue
        assert state.attributes.get("til") == LAST_WHOLE_HOUR_END.isoformat(), key
        checked.append(key)
    # the ones asked for: Nettleie before support, the fixed price and the capacity figures
    assert {"grid_gross_month", "fixed_month", "capacity_avg_kw", "capacity_amount",
            "capacity_headroom_kw", "cost_total", "cost_energy", "norgespris_month",
            "net_cost_month", "energy_month"} <= set(checked)


async def test_figures_that_are_not_part_of_the_snapshot_do_not_claim_a_til(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    for key in ("cost_energy_last_month", "grid_gross_last_month", "norgespris_last_month",
                "net_cost_last_month", "energy_today", "han_signal", "hours_missing_month"):
        assert "til" not in attrs(hass, entry, key), key
