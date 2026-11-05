"""The consumption-weighted spot price and the split at the Norgespris ceiling (invented figures)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from conftest import spot

OSLO = ZoneInfo("Europe/Oslo")
UTC = dt.timezone.utc
HOUR = dt.timedelta(hours=1)
NOW = dt.datetime(2026, 12, 1, tzinfo=UTC)
START = dt.datetime(2026, 10, 1, tzinfo=OSLO).astimezone(UTC)


def stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def energy(kwh_by_hour, start=START):
    return [{"start": start + i * HOUR, "end": start + (i + 1) * HOUR, "import": kwh}
            for i, kwh in enumerate(kwh_by_hour)]


def prices(spot_by_hour, start=START, vat=25.0, surcharge=0.0392):
    return [{"start": stamp(start + i * HOUR), "end": stamp(start + (i + 1) * HOUR), "spot": value,
             "official": True, "surcharge": surcharge, "vat_percent": vat}
            for i, value in enumerate(spot_by_hour)]


def test_the_average_is_weighted_by_the_consumption_of_each_hour():
    out = spot.weighted_spot(energy([1, 3]), prices([1.0, 2.0]), START, START + 2 * HOUR, NOW)
    assert out["spotsnitt"] == pytest.approx((1 * 1.25 + 3 * 2.5) / 4)       # incl. VAT: 2.1875
    assert out["borspris"] == pytest.approx((1 * 1 + 3 * 2) / 4)             # without VAT: 1.75
    assert out["paslag"] == pytest.approx(0.0392 * 1.25)                     # 4.9 øre incl. VAT
    assert out["inkl_paslag"] == pytest.approx(out["spotsnitt"] + out["paslag"])
    assert (out["kwh"], out["timer"], out["manglende_timer"]) == (4, 2, 0)
    assert out["sum_spot_inkl_mva"] == pytest.approx(8.75)


def test_an_hour_without_a_price_is_counted_and_left_out_not_made_up():
    prices_without = prices([1.0, 2.0])[:1]                                  # the second hour has none
    out = spot.weighted_spot(energy([1, 3]), prices_without, START, START + 2 * HOUR, NOW)
    assert out["spotsnitt"] == pytest.approx(1.25)
    assert (out["kwh"], out["timer"], out["manglende_timer"]) == (1, 1, 1)
    assert out["manglende_timer_liste"] == [(START + HOUR).strftime("%Y-%m-%dT%H:%MZ")]


def test_a_spot_price_of_none_counts_as_missing_but_a_price_of_zero_is_a_price():
    series = prices([0.0, 2.0, 1.0])
    series[2]["spot"] = None
    out = spot.weighted_spot(energy([2, 2, 2]), series, START, START + 3 * HOUR, NOW)
    assert (out["timer"], out["manglende_timer"], out["timer_med_pris_null"]) == (2, 1, 1)
    assert out["spotsnitt"] == pytest.approx((0 + 2 * 2.5) / 4)


def test_only_the_hours_inside_the_period_count():
    out = spot.weighted_spot(energy([1, 1, 1, 1]), prices([1.0, 2.0, 3.0, 4.0]),
                             START + HOUR, START + 3 * HOUR, NOW)
    assert out["borspris"] == pytest.approx(2.5) and out["timer"] == 2


def test_nothing_to_average_gives_none_and_not_zero():
    out = spot.weighted_spot(energy([0, 0]), prices([1.0, 2.0]), START, START + 2 * HOUR, NOW)
    assert out["spotsnitt"] is None and out["inkl_paslag"] is None and out["kwh"] == 0


def test_both_hours_of_the_autumn_change_get_their_own_price():
    """25 October 2026 has two 02:00-03:00 hours (00:00Z and 01:00Z); each has its own price."""
    day = dt.datetime(2026, 10, 25, tzinfo=OSLO).astimezone(UTC)
    values = [1.0] * 25
    values[2], values[3] = 5.0, 9.0                                          # the repeated hour
    kwh = [2.0] * 25
    out = spot.weighted_spot(energy(kwh, day), prices(values, day), day, day + 25 * HOUR, NOW)
    assert out["timer"] == 25 and out["manglende_timer"] == 0
    assert out["borspris"] == pytest.approx((23 * 1.0 + 5.0 + 9.0) / 25)


def test_a_price_without_vat_is_not_used():
    series = prices([1.0])
    series[0]["vat_percent"] = None
    out = spot.weighted_spot(energy([1]), series, START, START + HOUR, NOW)
    assert out["manglende_timer"] == 1 and out["spotsnitt"] is None


# --- above the Norgespris ceiling ----------------------------------------------------------------
def test_the_part_above_the_ceiling_is_priced_with_surcharge_and_vat():
    # 3 hours of 2 000 kWh: the ceiling (5 000) is crossed in the third, which is half under it.
    cons = energy([2000, 2000, 2000])
    pr = prices([1.0, 2.0, 4.0], surcharge=0.0)
    out = spot.cap_split(cons, pr, NOW, OSLO)
    assert out["norgespris_kwh"] == pytest.approx(5000)
    assert out["over_tak_kwh"] == pytest.approx(1000)
    assert out["spotsnitt_over_tak"] == pytest.approx(4.0 * 1.25)            # only the third hour
    assert out["spotsnitt_over_tak_uten_paslag"] == pytest.approx(4.0 * 1.25)
    assert out["over_tak_uten_pris_kwh"] == 0


def test_the_surcharge_is_in_the_over_ceiling_price_but_not_in_the_one_without():
    out = spot.cap_split(energy([6000]), prices([2.0], surcharge=0.04), NOW, OSLO)
    assert out["spotsnitt_over_tak"] == pytest.approx((2.0 + 0.04) * 1.25)
    assert out["spotsnitt_over_tak_uten_paslag"] == pytest.approx(2.0 * 1.25)


def test_under_the_ceiling_nothing_is_above_it_and_there_is_no_price_for_it():
    out = spot.cap_split(energy([100, 100]), prices([1.0, 2.0]), NOW, OSLO)
    assert out["over_tak_kwh"] == 0 and out["norgespris_kwh"] == pytest.approx(200)
    assert out["spotsnitt_over_tak"] is None and out["spotsnitt_over_tak_uten_paslag"] is None


def test_kwh_above_the_ceiling_in_an_hour_without_a_price_is_counted_apart():
    out = spot.cap_split(energy([5000, 300, 200]), prices([1.0, 2.0, 3.0])[:2], NOW, OSLO)
    assert out["over_tak_kwh"] == pytest.approx(500)
    assert out["over_tak_uten_pris_kwh"] == pytest.approx(200)               # the third hour has no price
    assert out["spotsnitt_over_tak"] == pytest.approx((2.0 + 0.0392) * 1.25)


# --- the fields hent_periode adds from the prices ---------------------------------------------------
def test_kraft_is_rebuilt_from_the_prices_and_compared_with_amperiums():
    cons = energy([2, 2])
    # per hour: 2 kWh x (spot + 0.0392) x 1.25 = 2 x (1.0392 x 1.25) and 2 x (2.0392 x 1.25)
    expected = 2 * 1.0392 * 1.25 + 2 * 2.0392 * 1.25 + 25.0
    fields, warnings = spot.period_price_fields(
        cons, prices([1.0, 2.0]), START, START + 2 * HOUR, NOW, energy_gross=expected + 0.4, fixed=25.0
    )
    assert fields["kraft_fra_priser"] == pytest.approx(expected, abs=0.005)
    assert fields["kraft_avvik_fra_priser"] == pytest.approx(0.4, abs=0.005)
    assert fields["spotsnitt"] == pytest.approx((1.25 + 2.5) / 2)
    assert (fields["spot_kwh"], fields["spot_timer"], fields["spot_manglende_timer"]) == (4, 2, 0)
    assert warnings == []                                           # 0.4 kr is within the margin


def test_a_difference_over_a_krone_between_amperium_and_the_prices_is_a_warning():
    fields, warnings = spot.period_price_fields(
        energy([2, 2]), prices([1.0, 2.0]), START, START + 2 * HOUR, NOW, energy_gross=100.0, fixed=0.0
    )
    assert warnings == ["kraft_avviker_fra_priser"]
    assert fields["kraft_avvik_fra_priser"] > 1


def test_missing_prices_are_reported_as_hours_and_no_deviation_warning_is_made_on_a_partial_sum():
    fields, warnings = spot.period_price_fields(
        energy([2, 2]), prices([1.0, 2.0])[:1], START, START + 2 * HOUR, NOW, energy_gross=999.0, fixed=0.0
    )
    assert warnings == ["priser_mangler:1"] and fields["spot_manglende_timer"] == 1


def test_prices_that_could_not_be_fetched_give_empty_fields_and_a_warning():
    fields, warnings = spot.period_price_fields(
        energy([2]), None, START, START + HOUR, NOW, energy_gross=10.0, fixed=0.0
    )
    assert warnings == ["priser_ikke_hentet"]
    assert all(value is None for value in fields.values())


def _period_client(prices_answer):
    class Client:
        def __init__(self):
            self.calls = []

        async def async_get_energy(self, site_id, start, end):
            return energy([2, 2])

        async def async_get_charges(self, site_id, start, end):
            return {
                "energy": [{"start": START + i * HOUR, "end": START + (i + 1) * HOUR, "energy": 1.0,
                            "tax": 0.2, "norgespris": 0.5, "norgespris_kwh": 2.0} for i in range(2)],
                "outer_total": 10.0, "fixed_total": 25.0,
                "grid": {"total": 5.0, "compensation": 0.0, "capacity_amount": 0.0,
                         "capacity_avg_kw": 1.0},
            }

        async def async_get_prices(self, site_id, start, end):
            if isinstance(prices_answer, Exception):
                raise prices_answer
            return prices_answer

    return Client()


def test_the_period_answer_has_the_price_fields():
    import asyncio

    from conftest import period

    out = asyncio.run(period.async_period_summary(
        _period_client(prices([1.0, 2.0])), 1, START, START + 2 * HOUR, OSLO, now=NOW
    ))
    assert out["spotsnitt"] == pytest.approx(1.875) and out["spot_manglende_timer"] == 0
    assert out["kraft_fra_priser"] is not None and out["energy_gross"] == pytest.approx(5.0)


def test_a_failing_price_request_does_not_take_the_rest_of_the_answer_with_it():
    import asyncio

    from conftest import api, period

    out = asyncio.run(period.async_period_summary(
        _period_client(api.AmperiumError("HTTP 500")), 1, START, START + 2 * HOUR, OSLO, now=NOW
    ))
    assert "priser_ikke_hentet" in out["warnings"] and out["spotsnitt"] is None
    assert out["consumption_kwh"] == pytest.approx(4.0)


def test_a_price_request_refused_for_the_login_is_not_swallowed():
    import asyncio

    from conftest import api, period

    with pytest.raises(api.AmperiumAuthError):
        asyncio.run(period.async_period_summary(
            _period_client(api.AmperiumAuthError("no")), 1, START, START + 2 * HOUR, OSLO, now=NOW
        ))
