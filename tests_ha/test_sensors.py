"""What the sensors show, from the fake API's answers all the way to the entity states.

September 2026 is last month and uses invoice 3551273 (Kraft 4028.94, Nettleie 1655.30,
Norgespris -2819.94, Totalt 2864.30, 2156.638 kWh, 1.3281 kr/kWh).
"""
from __future__ import annotations

import datetime as dt

import pytest
from fake_api import OCT_START
from ha_helpers import entity_id, make_entry, setup_entry, value
from homeassistant.helpers import entity_registry as er


def number(hass, entry, key):
    return float(value(hass, entry, key))


async def test_last_month_reproduces_the_september_invoice(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    assert number(hass, entry, "energy_last_month") == pytest.approx(2156.64, abs=0.005)
    assert number(hass, entry, "cost_energy_last_month") == pytest.approx(4028.94, abs=0.005)   # Kraft
    assert number(hass, entry, "grid_gross_last_month") == pytest.approx(1655.30, abs=0.005)    # Nettleie
    assert number(hass, entry, "norgespris_last_month") == pytest.approx(2819.94, abs=0.005)
    assert number(hass, entry, "fixed_last_month") == pytest.approx(25.0)
    assert number(hass, entry, "subsidy_applied_last_month") == pytest.approx(1795.27, abs=0.005)
    # Kraft + Nettleie - Norgespris, with the fixed monthly price counted once (it is inside Kraft).
    assert number(hass, entry, "net_cost_last_month") == pytest.approx(2864.30, abs=0.005)
    assert number(hass, entry, "avg_price_last_month") == pytest.approx(1.3281, abs=5e-5)


async def test_last_month_for_a_customer_on_the_regular_subsidy(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="subsidy"))
    # Energy + grid rent after subsidy: no Norgespris, and still no second fixed price.
    assert number(hass, entry, "net_cost_last_month") == pytest.approx(3888.97, abs=0.005)
    assert number(hass, entry, "avg_price_last_month") == pytest.approx(3888.97 / 2156.638, abs=5e-5)


async def test_this_month_counts_the_fixed_price_once_and_gives_the_vat_on_it(hass, api):
    """36 hours of October: 72 kWh, hourly energy 54.00, fixed price 25.00, grid rent 120.00."""
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    total = number(hass, entry, "cost_total")
    assert total == pytest.approx(54.0 + 25.0 + 120.0)                  # Amperium's total, after subsidy
    subsidy = number(hass, entry, "subsidy_applied_month")
    norgespris = number(hass, entry, "norgespris_month")
    assert (subsidy, norgespris) == (pytest.approx(40.0), pytest.approx(21.6))
    assert number(hass, entry, "net_cost_month") == pytest.approx(total + subsidy - norgespris)
    assert number(hass, entry, "gross_total_month") == pytest.approx(total + subsidy)
    assert number(hass, entry, "energy_gross_month") == pytest.approx(54.0)       # the hours only
    assert number(hass, entry, "vat_month") == pytest.approx(0.2 * (54.0 + 25.0))  # 20 % of the gross


async def test_the_fixed_price_sensor_is_named_for_what_it_is(hass, api):
    entry = await setup_entry(hass, make_entry())
    state = hass.states.get(entity_id(hass, entry, "fixed_month"))
    assert state.state == "25.0"
    assert state.attributes["friendly_name"].endswith("Fixed monthly price (electricity supply) this month")


async def test_han_status_and_the_newest_data(hass, api):
    entry = await setup_entry(hass, make_entry())
    assert value(hass, entry, "han_signal") == "1"
    assert value(hass, entry, "han_signal_quality") == "poor"
    assert value(hass, entry, "han_last_data") == "2026-10-02T09:00:00+00:00"
    assert value(hass, entry, "han_online", "binary_sensor") == "on"


async def test_the_han_module_being_offline_is_shown(hass, api):
    api.han_online = False
    entry = await setup_entry(hass, make_entry())
    assert value(hass, entry, "han_online", "binary_sensor") == "off"
    assert value(hass, entry, "han_signal_quality") == "offline"


async def test_missing_hours_are_counted_and_listed(hass, api):
    gone = [OCT_START + dt.timedelta(hours=10), OCT_START + dt.timedelta(hours=11)]
    api.missing_hours = set(gone)
    entry = await setup_entry(hass, make_entry())
    state = hass.states.get(entity_id(hass, entry, "hours_missing_month"))
    assert state.state == "2"
    assert state.attributes["hours"] == [h.isoformat() for h in gone]


async def test_the_newest_hours_are_not_missing_yet(hass, api):
    api.missing_hours = {dt.datetime(2026, 10, 2, 8, tzinfo=dt.timezone.utc),
                         dt.datetime(2026, 10, 2, 9, tzinfo=dt.timezone.utc)}
    entry = await setup_entry(hass, make_entry())
    assert value(hass, entry, "hours_missing_month") == "0"


async def test_no_holes_means_zero_missing_hours(hass, api):
    entry = await setup_entry(hass, make_entry())
    assert value(hass, entry, "hours_missing_month") == "0"


async def test_entity_ids_and_unique_ids_are_stable(hass, api):
    """Every sensor key the integration has had keeps its unique id, so entity ids never change."""
    entry = await setup_entry(hass, make_entry())
    registry = er.async_get(hass)
    keys = {e.unique_id.removeprefix(f"{entry.entry_id}_")
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    for key in ("energy_month", "cost_total", "fixed_month", "fixed_last_month", "net_cost_month",
                "net_cost_last_month", "avg_price_month", "avg_price_last_month", "han_signal",
                "han_signal_quality", "han_online", "login_renews_at", "norgespris_month"):
        assert key in keys, key
