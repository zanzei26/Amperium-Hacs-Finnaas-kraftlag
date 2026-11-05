"""The weighted spot price, the price variants with surcharge and VAT, and the ceiling attributes.

The fake Amperium prices an hour (UTC hour h) at spot 0.5 + h x 0.01, surcharge 0.05 and VAT 25 %.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fake_api import NOW, OCT_START, SEPT_END, SEPT_START, hours_between
from ha_helpers import entity_id, make_entry, setup_entry, value
from homeassistant.helpers import entity_registry as er  # noqa: F401  (entity_id uses it)

HOUR = dt.timedelta(hours=1)


def spot_of(hour: dt.datetime) -> float:
    return 0.5 + hour.hour * 0.01


def complete(first, last):
    """The hours [first, last) that are over at NOW."""
    return [h for h in hours_between(first, last) if h + HOUR <= NOW]


def attributes(hass, entry, key):
    return hass.states.get(entity_id(hass, entry, key)).attributes


async def test_this_months_weighted_spot_is_the_hourly_prices_weighted_by_consumption(hass, api):
    entry = await setup_entry(hass, make_entry())
    hours = complete(OCT_START, NOW)
    expected = sum(spot_of(h) * 1.25 for h in hours) / len(hours)       # 2 kWh every hour: equal weights
    assert float(value(hass, entry, "spot_avg_month")) == pytest.approx(expected, abs=1e-4)
    attrs = attributes(hass, entry, "spot_avg_month")
    assert attrs["kwh"] == pytest.approx(2.0 * len(hours))
    assert attrs["timer"] == len(hours) and attrs["manglende_timer"] == 0
    assert attrs["borspris"] == pytest.approx(sum(spot_of(h) for h in hours) / len(hours), abs=1e-4)
    assert attrs["inkl_paslag"] == pytest.approx(expected + 0.05 * 1.25, abs=1e-4)


async def test_last_months_weighted_spot_uses_last_months_hours(hass, api):
    entry = await setup_entry(hass, make_entry())
    hours = hours_between(SEPT_START, SEPT_END)
    expected = sum(spot_of(h) * 1.25 for h in hours) / len(hours)
    assert float(value(hass, entry, "spot_avg_last_month")) == pytest.approx(expected, abs=1e-4)
    assert attributes(hass, entry, "spot_avg_last_month")["timer"] == len(hours)


async def test_last_months_prices_are_fetched_once_not_every_hour(hass, api):
    await setup_entry(hass, make_entry())
    september = [p for _, p in api.calls if "/prices?" in p and "from=2026-08-31T22" in p]
    assert len(september) == 1


async def test_an_hour_without_a_price_is_counted_and_not_made_up(hass, api):
    api.missing_hours = set()
    original = api._prices

    def without_one_hour(query):
        rows = original(query)
        return [r for r in rows if r["startTime"] != OCT_START.strftime("%Y-%m-%dT%H:%M:%SZ")]

    api._prices = without_one_hour
    entry = await setup_entry(hass, make_entry())
    attrs = attributes(hass, entry, "spot_avg_month")
    assert attrs["manglende_timer"] == 1
    assert attrs["timer"] == len(complete(OCT_START, NOW)) - 1


async def test_prices_with_surcharge_and_vat_follow_the_exchange_price_sensors(hass, api):
    entry = await setup_entry(hass, make_entry())
    assert float(value(hass, entry, "price_min_today_incl")) == pytest.approx((0.5 + 0.05) * 1.25, abs=1e-4)
    assert float(value(hass, entry, "price_max_today_incl")) == pytest.approx((0.73 + 0.05) * 1.25, abs=1e-4)
    # The exchange price (without surcharge and VAT) is still there, and says so.
    assert float(value(hass, entry, "price_min_today")) == pytest.approx(0.5, abs=1e-4)
    assert "børspris" in attributes(hass, entry, "price_min_today")["grunnlag"]
    assert attributes(hass, entry, "price_min_today_incl")["borspris"] == pytest.approx(0.5)


async def test_the_exchange_price_sensors_are_named_for_what_they_are(hass, api):
    entry = await setup_entry(hass, make_entry())
    name = hass.states.get(entity_id(hass, entry, "price_min_today")).attributes["friendly_name"]
    assert name.endswith("Lowest exchange price today")


async def test_a_month_over_the_ceiling_says_how_much_is_over_and_what_it_costs(hass, api):
    api.oct_hourly_kwh = 200.0                                          # 7 200 kWh in 36 hours
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    attrs = attributes(hass, entry, "norgespris_month")
    hours = complete(OCT_START, NOW)
    over = hours[25:]                                                   # 25 x 200 = 5 000 kWh under
    assert attrs["norgespris_kwh"] == pytest.approx(5000.0)
    assert attrs["over_tak_kwh"] == pytest.approx(200.0 * len(over))
    expected = sum((spot_of(h) + 0.05) * 1.25 for h in over) / len(over)
    assert attrs["spotsnitt_over_tak"] == pytest.approx(expected, abs=1e-4)
    assert attrs["spotsnitt_over_tak_uten_paslag"] == pytest.approx(
        sum(spot_of(h) * 1.25 for h in over) / len(over), abs=1e-4
    )


async def test_a_small_month_has_nothing_over_the_ceiling(hass, api):
    entry = await setup_entry(hass, make_entry(scheme="norgespris"))
    attrs = attributes(hass, entry, "norgespris_month")
    assert attrs["over_tak_kwh"] == 0 and attrs["spotsnitt_over_tak"] is None


async def test_failing_month_prices_leave_the_spot_sensors_unknown_and_the_rest_working(hass, api):
    api.fail_long_price_windows = True
    entry = await setup_entry(hass, make_entry())
    assert value(hass, entry, "spot_avg_month") == "unknown"
    assert float(value(hass, entry, "price_min_today_incl")) > 0         # today's prices still work
    assert float(value(hass, entry, "energy_month")) == pytest.approx(72.0)
