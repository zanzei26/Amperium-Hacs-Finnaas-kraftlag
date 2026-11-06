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
    # Amperium's Kraft in this fake (10 - 5 = 5) is far from the prices, which have every hour: the
    # one rebuilt from the prices is used, and Amperium's stays next to it.
    assert out["kraft_fra_priser"] is not None
    assert out["energy_gross"] == pytest.approx(out["kraft_fra_priser"])
    assert out["energy_gross_amperium"] == pytest.approx(5.0)
    assert out["kraft_kilde"] == "priser"


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


# --- Kraft from the prices replaces Amperium's when every hour has a price ---------------------------

def _october_like_client(amperium_total, prices_answer, fixed=25.0, energy_rows=None):
    """Two hours of 2 kWh; Amperium's Kraft is ``amperium_total`` - 5 (the grid rent after support)."""
    rows = energy_rows if energy_rows is not None else energy([2, 2])

    class Client:
        async def async_get_energy(self, site_id, start, end):
            return rows

        async def async_get_charges(self, site_id, start, end):
            return {
                "energy": [{"start": START + i * HOUR, "end": START + (i + 1) * HOUR, "energy": 1.0,
                            "tax": 0.2, "norgespris": 0.5, "norgespris_kwh": 2.0} for i in range(2)],
                "outer_total": amperium_total, "fixed_total": fixed,
                "grid": {"total": 5.0, "compensation": 1.0, "capacity_amount": 0.0,
                         "capacity_avg_kw": 1.0},
            }

        async def async_get_prices(self, site_id, start, end):
            return prices_answer

    return Client()


def _run(client, scheme="norgespris"):
    import asyncio

    from conftest import period

    return asyncio.run(period.async_period_summary(client, 1, START, START + 2 * HOUR, OSLO,
                                                   scheme, now=NOW))


FROM_PRICES = 2 * 1.0392 * 1.25 + 2 * 2.0392 * 1.25 + 25.0       # Kraft rebuilt from the two hours


def test_kraft_from_the_prices_is_returned_with_its_vat():
    out = spot.kraft_from_prices(energy([2, 2]), prices([1.0, 2.0]), START, START + 2 * HOUR, NOW, 25.0)
    kraft, vat = out
    assert kraft == pytest.approx(FROM_PRICES)
    assert vat == pytest.approx(FROM_PRICES * 0.2)       # 25 % VAT is 20 % of the amount incl. VAT


@pytest.mark.parametrize("case", ["no prices", "empty prices", "a price missing", "no fixed price",
                                  "a consumption hour missing", "no consumption"])
def test_kraft_from_the_prices_is_not_used_unless_every_hour_has_consumption_and_a_price(case):
    cons, series, fixed = energy([2, 2]), prices([1.0, 2.0]), 25.0
    if case == "no prices":
        series = None
    elif case == "empty prices":
        series = []
    elif case == "a price missing":
        series = series[:1]
    elif case == "no fixed price":
        fixed = None
    elif case == "a consumption hour missing":
        cons = cons[:1]
    elif case == "no consumption":
        cons = energy([0, 0])
    assert spot.kraft_from_prices(cons, series, START, START + 2 * HOUR, NOW, fixed) is None


def test_kraft_from_the_prices_works_on_the_day_with_25_hours():
    day = dt.datetime(2026, 10, 25, tzinfo=OSLO).astimezone(UTC)
    end = dt.datetime(2026, 10, 26, tzinfo=OSLO).astimezone(UTC)
    assert (end - day) == 25 * HOUR
    out = spot.kraft_from_prices(energy([1] * 25, day), prices([1.0] * 25, day), day, end, NOW, 0.0)
    assert out is not None and out[0] == pytest.approx(25 * 1.0392 * 1.25)


def test_a_month_where_amperium_is_too_low_gets_kraft_from_the_prices_in_everything_made_from_it():
    low = FROM_PRICES + 5.0 - 7.54                       # Amperium: 7.54 kr under the prices
    out = _run(_october_like_client(low, prices([1.0, 2.0])))
    assert out["kraft_kilde"] == "priser"
    assert out["energy_gross"] == pytest.approx(FROM_PRICES, abs=0.005)
    assert out["energy_gross_amperium"] == pytest.approx(FROM_PRICES - 7.54, abs=0.005)
    assert out["kraft_avvik_fra_priser"] == pytest.approx(-7.54, abs=0.005)      # the difference stays visible
    assert out["vat_on_energy"] == pytest.approx(FROM_PRICES * 0.2, abs=0.005)
    # house cost = Kraft + grid rent before support - Norgespris, from the corrected Kraft
    expected_cost = FROM_PRICES + 5.0 + 1.0 - out["norgespris_compensation"]
    assert out["house_cost_norgespris"] == pytest.approx(expected_cost, abs=0.01)
    assert out["price_per_kwh_norgespris"] == pytest.approx(expected_cost / 4, abs=1e-4)
    assert "kraft_fra_priser_brukt" in out["warnings"]
    assert "kraft_avviker_fra_priser" not in out["warnings"]


def test_when_amperium_and_the_prices_agree_nothing_changes_and_nothing_is_warned():
    out = _run(_october_like_client(FROM_PRICES + 5.0, prices([1.0, 2.0])))
    assert out["energy_gross"] == pytest.approx(FROM_PRICES, abs=0.005)
    assert out["energy_gross_amperium"] == pytest.approx(FROM_PRICES, abs=0.005)
    assert not any(w.startswith("kraft_") for w in out["warnings"])


@pytest.mark.parametrize("case", ["a price missing", "no fixed price", "prices not fetched"])
def test_amperiums_kraft_stays_when_the_prices_cannot_be_trusted(case):
    series, fixed = prices([1.0, 2.0]), 25.0
    if case == "a price missing":
        series = series[:1]
    elif case == "no fixed price":
        fixed = None
    elif case == "prices not fetched":
        series = None
    low = FROM_PRICES + 5.0 - 7.54
    out = _run(_october_like_client(low, series, fixed=fixed))
    assert out["kraft_kilde"] == "amperium"
    assert out["energy_gross"] == pytest.approx(low - 5.0, abs=0.005)       # Amperium's figure, untouched
    assert "kraft_fra_priser_brukt" not in out["warnings"]


def test_amperiums_kraft_stays_when_an_hour_of_consumption_is_missing():
    low = FROM_PRICES + 5.0 - 7.54
    out = _run(_october_like_client(low, prices([1.0, 2.0]), energy_rows=energy([2])))
    assert out["kraft_kilde"] == "amperium"
    assert any(w.startswith("hours_missing") for w in out["warnings"])


def test_the_check_of_the_fixed_price_in_amperiums_total_is_made_on_amperiums_figure_not_the_replacement():
    # Amperium's own numbers are consistent: hours 2.00 + fixed 25.00 = 27.00 (32.00 - grid 5.00).
    out = _run(_october_like_client(32.0, prices([1.0, 2.0])))
    assert out["kraft_kilde"] == "priser" and out["energy_gross_amperium"] == pytest.approx(27.0)
    assert "fixed_monthly_price_not_in_energy_total" not in out["warnings"]


def test_a_month_with_the_autumn_clock_change_has_745_hours_when_the_ends_are_local_times():
    """The coordinator passes the month's ends as local times (not UTC), which is where 744 came from."""
    first = dt.datetime(2026, 10, 1, tzinfo=OSLO)
    after = dt.datetime(2026, 11, 1, tzinfo=OSLO)
    assert (after - first) == dt.timedelta(days=31)            # the trap: the same zone ignores the change
    assert spot.expected_hours(first, after, dt.datetime(2026, 11, 5, tzinfo=UTC)) == 745
    spring_first, spring_after = dt.datetime(2027, 3, 1, tzinfo=OSLO), dt.datetime(2027, 4, 1, tzinfo=OSLO)
    assert spot.expected_hours(spring_first, spring_after, dt.datetime(2027, 4, 5, tzinfo=UTC)) == 743


def test_kraft_from_the_prices_is_used_for_october_when_called_the_way_the_coordinator_calls_it():
    first = dt.datetime(2026, 10, 1, tzinfo=OSLO)
    after = dt.datetime(2026, 11, 1, tzinfo=OSLO)
    start = first.astimezone(UTC)
    cons, series = energy([1] * 745, start), prices([1.0] * 745, start)
    out = spot.kraft_from_prices(cons, series, first, after, dt.datetime(2026, 11, 5, tzinfo=UTC), 25.0)
    assert out is not None and out[0] == pytest.approx(745 * 1.0392 * 1.25 + 25.0)
    # one hour short, as it would be if a price were missing, is still refused
    assert spot.kraft_from_prices(cons[:-1], series, first, after,
                                  dt.datetime(2026, 11, 5, tzinfo=UTC), 25.0) is None


# --- Norgespris rebuilt from the prices -------------------------------------------------------------

def test_norgespris_from_the_prices_is_kwh_times_spot_incl_vat_minus_50_ore():
    # 2 kWh at spot 1.0 -> 1.25 incl. VAT, 2 kWh at spot 2.0 -> 2.50
    out = spot.norgespris_from_prices(energy([2, 2]), prices([1.0, 2.0]), START, START + 2 * HOUR, NOW, OSLO)
    assert out == pytest.approx((2 * 0.75 + 2 * 2.0, 4.0))


def test_an_hour_with_a_spot_price_under_norgespris_gives_a_negative_compensation_like_amperiums_own():
    # 0.2 + 25 % VAT = 0.25, which is 0.25 under the 0.50 Norgespris
    out = spot.norgespris_from_prices(energy([2]), prices([0.2]), START, START + HOUR, NOW, OSLO)
    assert out[0] == pytest.approx(-0.5)


def test_the_example_of_5600_kwh_in_a_month_gives_the_first_5000_kwh_norgespris():
    """100 kWh an hour for 56 hours at a spot price of 1.80 incl. VAT (1.44 ex VAT)."""
    cons, series = energy([100.0] * 56), prices([1.80 / 1.25] * 56, surcharge=0.049 / 1.25)
    end = START + 56 * HOUR
    krone, under = spot.norgespris_from_prices(cons, series, START, end, NOW, OSLO)
    assert under == pytest.approx(5000.0)
    assert krone == pytest.approx(5000 * (1.80 - 0.50))                    # 6 500.00
    kraft, _vat = spot.kraft_from_prices(cons, series, START, end, NOW, 25.0)
    assert kraft == pytest.approx(5600 * (1.80 + 0.049) + 25.0)            # 10 379.40
    assert kraft - krone == pytest.approx(3879.40, abs=0.005)               # Kraft - Norgespris


def test_the_hour_that_crosses_the_ceiling_gets_the_part_under_it():
    cons, series = energy([800.0] * 7), prices([1.0] * 7)                  # 5 600 kWh; hour 7 starts at 4 800
    krone, under = spot.norgespris_from_prices(cons, series, START, START + 7 * HOUR, NOW, OSLO)
    assert under == pytest.approx(5000.0)                                  # 200 of the last 800 kWh
    assert krone == pytest.approx(5000 * 0.75)


def test_a_period_in_the_middle_of_the_month_counts_the_ceiling_from_the_1st():
    cons, series = energy([100.0] * 56), prices([1.0] * 56)
    # the period is the last 10 hours; the 46 hours before it have used 4 600 kWh
    start, end = START + 46 * HOUR, START + 56 * HOUR
    krone, under = spot.norgespris_from_prices(cons, series[46:], start, end, NOW, OSLO)
    assert under == pytest.approx(400.0)                                    # 4 600 + 400 = 5 000
    assert krone == pytest.approx(400 * 0.75)


@pytest.mark.parametrize("case", ["no prices", "a price missing", "a consumption hour missing", "no consumption"])
def test_norgespris_from_the_prices_needs_every_hour_to_have_consumption_and_a_price(case):
    cons, series = energy([2, 2]), prices([1.0, 2.0])
    if case == "no prices":
        series = None
    elif case == "a price missing":
        series = series[:1]
    elif case == "a consumption hour missing":
        cons = cons[:1]
    elif case == "no consumption":
        cons = energy([0, 0])
    assert spot.norgespris_from_prices(cons, series, START, START + 2 * HOUR, NOW, OSLO) is None


def test_norgespris_from_the_prices_counts_all_25_hours_of_the_day_with_the_clock_change():
    day = dt.datetime(2026, 10, 25, tzinfo=OSLO).astimezone(UTC)
    end = dt.datetime(2026, 10, 26, tzinfo=OSLO).astimezone(UTC)
    krone, under = spot.norgespris_from_prices(energy([2.0] * 25, day), prices([1.0] * 25, day), day, end, NOW, OSLO)
    assert under == pytest.approx(50.0) and krone == pytest.approx(25 * 2 * 0.75)


def test_norgespris_from_the_prices_works_for_october_with_local_time_ends():
    first, after = dt.datetime(2026, 10, 1, tzinfo=OSLO), dt.datetime(2026, 11, 1, tzinfo=OSLO)
    start = first.astimezone(UTC)
    out = spot.norgespris_from_prices(energy([3.0] * 745, start), prices([1.0] * 745, start), first, after,
                                      dt.datetime(2026, 11, 5, tzinfo=UTC), OSLO)
    assert out is not None and out[1] == pytest.approx(2235.0)


def test_amperiums_norgespris_is_only_replaced_when_the_rebuilt_one_is_close_to_it():
    rebuilt = (2500.51, 1800.0)
    assert spot.trusted_norgespris(2500.17, rebuilt)                        # 0.34 kr apart: the clock change
    assert spot.trusted_norgespris(2500.51 + 20, rebuilt)                   # inside 1 % of a large amount
    assert not spot.trusted_norgespris(2500.51 + 40, rebuilt)               # over 1 %: other rate or rules
    assert spot.trusted_norgespris(1.0, (5.9, 4.0))                         # small amounts: 5 kr margin
    assert not spot.trusted_norgespris(1.0, (6.1, 4.0))
    assert not spot.trusted_norgespris(None, rebuilt)                       # unknown stays unknown
    assert not spot.trusted_norgespris(2500.17, None)


def _np_client(amperium_total):
    """Two hours of 2 kWh at spot 1.0 and 2.0 (rebuilt Norgespris 5.5); Amperium's rows add up to ``amperium_total``."""
    class Client:
        async def async_get_energy(self, site_id, start, end):
            return energy([2, 2])

        async def async_get_charges(self, site_id, start, end):
            return {
                "energy": [{"start": START + i * HOUR, "end": START + (i + 1) * HOUR, "energy": 1.0,
                            "tax": 0.2, "norgespris": amperium_total / 2, "norgespris_kwh": 2.0} for i in range(2)],
                "outer_total": 32.0, "fixed_total": 25.0,
                "grid": {"total": 5.0, "compensation": 1.0, "capacity_amount": 0.0, "capacity_avg_kw": 1.0},
            }

        async def async_get_prices(self, site_id, start, end):
            return prices([1.0, 2.0])

    return Client()


def test_the_period_uses_norgespris_from_the_prices_and_keeps_amperiums_figure():
    out = _run(_np_client(5.5 - 0.34))                                      # Amperium 0.34 kr under
    assert out["norgespris_kilde"] == "priser"
    assert out["norgespris_compensation"] == pytest.approx(5.5, abs=0.005)
    assert out["norgespris_compensation_amperium"] == pytest.approx(5.16, abs=0.005)
    assert out["norgespris_avvik_fra_priser"] == pytest.approx(-0.34, abs=0.005)
    assert out["norgespris_kwh"] == pytest.approx(4.0)
    # the total follows: Kraft + Nettleie before support - Norgespris
    assert out["house_cost_norgespris"] == pytest.approx(
        out["energy_gross"] + 5.0 + 1.0 - 5.5, abs=0.01)
    assert not any(w.startswith("norgespris_") for w in out["warnings"])    # 0.34 kr is not worth a warning


def test_a_difference_over_a_krone_in_norgespris_is_a_warning_but_still_used():
    out = _run(_np_client(5.5 - 3.0))
    assert out["norgespris_kilde"] == "priser" and "norgespris_fra_priser_brukt" in out["warnings"]


def test_a_norgespris_far_from_amperiums_is_not_used_and_says_so():
    out = _run(_np_client(5.5 + 60.0))                                      # beyond the 5 kr margin
    assert out["norgespris_kilde"] == "amperium"
    assert out["norgespris_compensation"] == pytest.approx(65.5, abs=0.005)  # Amperium's, untouched
    assert "norgespris_avviker_fra_priser" in out["warnings"]
    assert out["norgespris_avvik_fra_priser"] == pytest.approx(60.0, abs=0.005)


def test_a_period_in_the_middle_of_a_month_counts_the_ceiling_from_the_1st_also_for_norgespris_from_prices():
    """46 hours of 100 kWh have passed when the period starts, so only 400 kWh of its 1 000 are under 5 000."""
    import asyncio

    from conftest import period

    all_energy = energy([100.0] * 56)
    all_prices = prices([1.0] * 56)
    first, last = START + 46 * HOUR, START + 56 * HOUR

    class Client:
        async def async_get_energy(self, site_id, start, end):
            return [b for b in all_energy if start <= b["start"] < end]

        async def async_get_charges(self, site_id, start, end):
            return {
                "energy": [{"start": b["start"], "end": b["end"], "energy": 100.0, "tax": 20.0,
                            "norgespris": 100 * 0.75, "norgespris_kwh": 100.0}
                           for b in all_energy if start <= b["start"] < end],
                "outer_total": 1025.0, "fixed_total": 25.0,
                "grid": {"total": 0.0, "compensation": 0.0, "capacity_amount": 0.0, "capacity_avg_kw": 1.0},
            }

        async def async_get_prices(self, site_id, start, end):
            return all_prices[46:]                       # the prices of the period's own 10 hours

    out = asyncio.run(period.async_period_summary(Client(), 1, first, last, OSLO, "norgespris", now=NOW))
    assert out["norgespris_kilde"] == "priser"
    assert out["norgespris_compensation"] == pytest.approx(400 * 0.75)
    assert out["norgespris_kwh"] == pytest.approx(400.0)
