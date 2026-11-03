"""Tests for the pure calculation helpers in derived.py (no Home Assistant needed)."""
from __future__ import annotations

import datetime as dt

import pytest
from conftest import derived
from helpers import (
    COMP,
    HOURLY_ENERGY,
    HOURLY_VAT,
    INVOICE,
    KRAFT_LINES,
    OSLO,
    PERIOD_NOW,
    SEPT,
    UTC,
    _hourly,
    _sept_inputs,
)


# --- consumer price ---------------------------------------------------------
def test_consumer_price_uses_vat_from_data():
    assert derived.consumer_price(1.0, 0.0, 0) == pytest.approx(1.0)
    assert derived.consumer_price(1.0, 0.0, 15) == pytest.approx(1.15)
    assert derived.consumer_price(1.5892, 0.0392, 25) == pytest.approx(2.0355)


def test_consumer_price_missing_parts():
    assert derived.consumer_price(1.0, None, 25) == pytest.approx(1.25)  # surcharge None -> 0
    assert derived.consumer_price(None, 0.04, 25) is None
    assert derived.consumer_price(1.0, 0.04, None) is None


# --- subsidy sign and grid rent ----------------------------------------------
@pytest.mark.parametrize("comp", [COMP, -COMP])
def test_subsidy_is_sign_independent(comp):
    assert derived.subsidy_applied(comp) == pytest.approx(COMP)
    assert derived.gross_grid_rent(247.15, comp) == pytest.approx(247.15 + COMP)
    assert derived.net_with_norgespris(512.40, derived.subsidy_applied(comp), 186.30) == pytest.approx(
        512.40 + COMP - 186.30
    )


def test_net_models_do_not_add_the_fixed_monthly_price_again():
    # Amperium's month total already holds the kraft's fixed monthly price (25 kr), so the
    # results are the total as it is, with the subsidy added back and Norgespris deducted.
    assert derived.net_with_subsidy(512.40) == pytest.approx(512.40)
    assert derived.net_with_norgespris(512.40, COMP, 186.30) == pytest.approx(444.55, abs=0.01)
    assert derived.net_for_scheme("subsidy", 512.40, COMP, 186.30) == pytest.approx(512.40)
    assert derived.net_for_scheme("norgespris", 512.40, COMP, 186.30) == pytest.approx(444.55, abs=0.01)
    assert derived.compensation_difference(186.30, COMP) == pytest.approx(67.85, abs=0.01)
    assert derived.net_for_scheme(None, 512.40, COMP, 186.30) is None
    assert derived.net_with_subsidy(None) is None
    assert derived.net_with_norgespris(512.40, None, 186.30) is None


def test_charges_summary_has_no_subsidy_key():
    now = dt.datetime(2026, 10, 3, 12, 30, tzinfo=UTC)
    bucket = {"start": dt.datetime(2026, 10, 2, 8, tzinfo=UTC), "end": dt.datetime(2026, 10, 2, 9, tzinfo=UTC),
              "energy": 10.0, "tax": 2.0, "norgespris": 4.0}
    out = derived.summarise_charges([bucket], now, dt.timezone.utc)
    assert "subsidy_month" not in out
    assert out["norgespris_month"] == 4.0 and out["energy_gross_month"] == 10.0


# --- HAN signal -----------------------------------------------------------------
@pytest.mark.parametrize(
    ("signal", "online", "state"),
    [(0, True, "none"), (1, True, "poor"), (2, True, "fair"), (3, True, "good"),
     (4, True, "excellent"), (1, False, "offline"), (None, True, "no_data"), (9, True, None)],
)
def test_han_signal_state(signal, online, state):
    assert derived.han_signal_state(signal, online) == state


# --- capacity peaks (Finnas tariff 2026: three highest hours on three different days) ---
def _hours(values):
    """values: {(day, hour_local_oslo): kwh} in October 2026 (CEST, UTC+2)."""
    out = []
    for (day, hour), kwh in values.items():
        start = dt.datetime(2026, 10, day, hour, tzinfo=dt.timezone(dt.timedelta(hours=2))).astimezone(UTC)
        out.append({"start": start, "end": start + dt.timedelta(hours=1), "import": kwh, "export": 0.0})
    return out


def test_capacity_peaks_use_three_different_days():
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Oslo")
    now = dt.datetime(2026, 10, 10, 12, tzinfo=UTC)
    buckets = _hours({
        (1, 8): 9.0, (1, 9): 8.9, (1, 10): 8.8,   # three high hours, same day: only 9.0 counts
        (2, 18): 6.0, (3, 7): 5.0, (4, 12): 3.0, (5, 12): 1.0,
    })
    out = derived.capacity_peaks(buckets, now, tz)
    assert [p["kw"] for p in out["capacity_peaks"]] == [9.0, 6.0, 5.0]
    assert out["capacity_calc_kw"] == pytest.approx((9.0 + 6.0 + 5.0) / 3)
    assert out["capacity_threshold_kw"] == 5.0  # a new day must beat the third highest
    assert out["capacity_peak_days"] == 5
    assert out["capacity_peaks"][0]["date"] == "2026-10-01"


def test_capacity_threshold_counts_today_once():
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Oslo")
    now = dt.datetime(2026, 10, 10, 12, tzinfo=UTC)
    # today (10th) already at 6.0 and in the top three: only an hour above
    # today's own peak raises the average, not one above the third day (4.0)
    buckets = _hours({(1, 8): 5.0, (2, 8): 4.0, (3, 8): 1.0, (10, 9): 6.0})
    out = derived.capacity_peaks(buckets, now, tz)
    assert out["capacity_threshold_kw"] == 6.0
    # today below the others: it must beat the third highest other day
    buckets = _hours({(1, 8): 5.0, (2, 8): 4.0, (3, 8): 3.5, (10, 9): 2.0})
    assert derived.capacity_peaks(buckets, now, tz)["capacity_threshold_kw"] == 3.5


def test_capacity_peaks_with_fewer_than_three_days():
    from zoneinfo import ZoneInfo

    now = dt.datetime(2026, 10, 3, 12, tzinfo=UTC)
    out = derived.capacity_peaks(_hours({(1, 8): 4.0, (2, 8): 2.0}), now, ZoneInfo("Europe/Oslo"))
    assert out["capacity_calc_kw"] == pytest.approx(3.0)
    assert out["capacity_threshold_kw"] == 0.0


def test_capacity_peaks_ignore_previous_month_and_empty():
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Oslo")
    now = dt.datetime(2026, 10, 3, 12, tzinfo=UTC)
    september = [{"start": dt.datetime(2026, 9, 30, 10, tzinfo=UTC), "end": dt.datetime(2026, 9, 30, 11, tzinfo=UTC),
                  "import": 50.0, "export": 0.0}]
    assert derived.capacity_peaks(september, now, tz) == {}
    assert derived.capacity_peaks([], now, tz) == {}


def test_capacity_peak_day_follows_local_midnight():
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Oslo")
    now = dt.datetime(2026, 10, 4, 12, tzinfo=UTC)
    # 22:30 UTC on 1 Oct is 00:30 local on 2 Oct, so it belongs to 2 Oct, not 1 Oct.
    late = {"start": dt.datetime(2026, 10, 1, 22, tzinfo=UTC), "end": dt.datetime(2026, 10, 1, 23, tzinfo=UTC),
            "import": 7.0, "export": 0.0}
    early = {"start": dt.datetime(2026, 10, 1, 8, tzinfo=UTC), "end": dt.datetime(2026, 10, 1, 9, tzinfo=UTC),
             "import": 6.0, "export": 0.0}
    out = derived.capacity_peaks([late, early], now, tz)
    assert sorted(p["date"] for p in out["capacity_peaks"]) == ["2026-10-01", "2026-10-02"]


# --- days_until (login expiry warning) --------------------------------------------
NOW = dt.datetime(2026, 10, 3, 12, tzinfo=UTC)


def test_days_until_counts_whole_and_part_days():
    assert derived.days_until("2026-10-13T12:00:00Z", NOW) == pytest.approx(10.0)
    assert derived.days_until("2026-10-03T18:00:00Z", NOW) == pytest.approx(0.25)
    assert derived.days_until("2026-10-01T12:00:00Z", NOW) == pytest.approx(-2.0)  # already past


def test_days_until_handles_offsets_and_naive_stamps():
    assert derived.days_until("2026-10-13T14:00:00+02:00", NOW) == pytest.approx(10.0)
    assert derived.days_until("2026-10-13T12:00:00", NOW) == pytest.approx(10.0)  # taken as UTC


@pytest.mark.parametrize("bad", [None, "", "not a date", 12345])
def test_days_until_unknown_is_none(bad):
    assert derived.days_until(bad, NOW) is None


def test_local_month_bounds_across_the_clock_change():
    # The clocks go back on 25 October 2026: October starts at UTC+2, November at UTC+1.
    prev, this, nxt = derived.local_month_bounds(dt.datetime(2026, 11, 10, 12, tzinfo=OSLO))
    assert prev.astimezone(UTC) == dt.datetime(2026, 9, 30, 22, tzinfo=UTC)
    assert this.astimezone(UTC) == dt.datetime(2026, 10, 31, 23, tzinfo=UTC)
    assert nxt.astimezone(UTC) == dt.datetime(2026, 11, 30, 23, tzinfo=UTC)


# --- "power now": local sensor first, Amperium as fallback ----------------------------
def test_power_now_prefers_the_local_sensor():
    assert derived.choose_power_now(2.5, 0.0) == (2.5, "local_sensor")


def test_power_now_local_zero_is_a_real_reading():
    # 0.0 kW from the local sensor must not be mistaken for "no value".
    assert derived.choose_power_now(0.0, 1.2) == (0.0, "local_sensor")


def test_power_now_falls_back_to_amperium_when_local_is_missing():
    assert derived.choose_power_now(None, 1.2) == (1.2, "amperium")


def test_power_now_without_any_value():
    assert derived.choose_power_now(None, None) == (None, None)


# --- before/after subsidy must add up (live figures from 3 October) -------------------
def test_grid_before_minus_subsidy_equals_after():
    before = derived.gross_grid_from_net(251.30, 118.45 + 3.10, 250.60)  # comp = 121.55
    assert before == pytest.approx(251.30 + 121.55)
    assert before == pytest.approx(372.85)
    assert before - derived.subsidy_applied(121.55) == pytest.approx(251.30)  # = "after", exactly


def test_grid_gross_does_not_depend_on_the_age_of_the_charges_total():
    # charges said 250.60 an hour ago; /api/sites says 251.30 now. "After" wins.
    assert derived.gross_grid_from_net(251.30, 121.55, 250.60) == pytest.approx(372.85)


def test_grid_gross_falls_back_to_charges_total_without_site_figure():
    assert derived.gross_grid_from_net(None, 121.55, 250.60) == pytest.approx(372.15)


@pytest.mark.parametrize("compensation", [121.55, -121.55])
def test_grid_gross_is_sign_independent(compensation):
    assert derived.gross_grid_from_net(251.30, compensation) == pytest.approx(372.85)


def test_grid_gross_unknown_without_subsidy_or_figures():
    assert derived.gross_grid_from_net(251.30, None) is None
    assert derived.gross_grid_from_net(None, 121.55) is None


def test_total_before_minus_subsidy_equals_total_after():
    total_after, comp = 530.00, 121.55
    gross = derived.gross_total_from_net(total_after, comp)
    assert gross == pytest.approx(651.55)
    assert gross - derived.subsidy_applied(comp) == pytest.approx(total_after)


def test_total_gross_equals_energy_plus_gross_grid():
    # The energy amount holds the kraft's fixed monthly price; nothing is added for it.
    energy, grid_after, comp = 281.40, 251.30, 121.55
    via_parts = energy + derived.gross_grid_from_net(grid_after, comp)
    assert derived.gross_total_from_net(energy + grid_after, comp) == pytest.approx(via_parts)


def test_total_gross_unknown_when_a_part_is_missing():
    assert derived.gross_total_from_net(530.00, None) is None
    assert derived.gross_total_from_net(None, 121.55) is None


def test_last_month_still_uses_charges_figures():
    assert derived.gross_grid_rent(-112.40, 100.0) == pytest.approx(-12.40)


# --- "power now" with the Amperium live feed in between --------------------------------
def test_power_now_order_local_then_live_then_hourly():
    assert derived.choose_power_now(2.5, 0.0, 1.9) == (2.5, "local_sensor")
    assert derived.choose_power_now(None, 0.0, 1.9) == (1.9, "amperium_live")
    assert derived.choose_power_now(None, 0.4, None) == (0.4, "amperium")
    assert derived.choose_power_now(None, None, None) == (None, None)


def test_power_now_live_zero_is_a_real_reading():
    assert derived.choose_power_now(None, 1.2, 0.0) == (0.0, "amperium_live")


# --- skip state writes that repeat what is shown ------------------------------------------
def test_change_gate_first_value_counts_then_repeats_do_not():
    gate = derived.ChangeGate()
    assert gate.changed((1.2, "local_sensor", "connected")) is True   # first: write
    assert gate.changed((1.2, "local_sensor", "connected")) is False  # same: skip
    assert gate.changed((1.3, "local_sensor", "connected")) is True   # value changed
    assert gate.changed((1.3, "local_sensor", "connected")) is False


def test_change_gate_treats_none_and_zero_as_values():
    gate = derived.ChangeGate()
    assert gate.changed((None, None, "off")) is True      # None is a value too
    assert gate.changed((None, None, "off")) is False
    assert gate.changed((0.0, "amperium_live", "connected")) is True
    assert gate.changed((0.0, "amperium_live", "connected")) is False


def test_live_messages_do_not_cause_writes_while_the_own_sensor_is_shown():
    """The live feed sends a reading every ~2 s; with an own sensor that changes nothing shown."""
    gate = derived.ChangeGate()
    writes = 0
    for live_kw in (1.201, 1.200, 1.200, 1.199, 1.201):   # five live messages
        shown = derived.choose_power_now(1.2, 0.0, live_kw)   # own sensor steady at 1.2 kW
        if gate.changed((shown[0], shown[1], "connected")):
            writes += 1
    assert writes == 1  # only the very first one


def test_a_stale_live_feed_changes_what_is_shown_and_is_written():
    gate = derived.ChangeGate()
    live = derived.choose_power_now(None, 0.0, 1.2)           # live is the source
    assert gate.changed((live[0], live[1], "connected")) is True
    gone = derived.choose_power_now(None, 0.4, None)          # live went stale -> hourly value
    assert gate.changed((gone[0], gone[1], "connected")) is True
    assert gone == (0.4, "amperium")


def test_spot_price_order_official_then_hour_then_preliminary():
    bucket = {"spot": 1.1, "official": False}
    assert derived.current_spot_price(0.9, bucket, 1.2) == (0.9, True)          # official wins
    assert derived.current_spot_price(None, bucket, 1.2) == (1.1, False)        # then the hour
    assert derived.current_spot_price(None, {"spot": 1.1, "official": True}, 1.2) == (1.1, True)
    assert derived.current_spot_price(None, None, 1.2) == (1.2, False)          # then preliminary
    assert derived.current_spot_price(None, {"spot": None}, 1.2) == (1.2, False)
    assert derived.current_spot_price(None, None, None) == (None, None)
    assert derived.current_spot_price(None, {}, None) == (None, None)


def test_a_price_of_zero_or_negative_is_a_price():
    assert derived.current_spot_price(0.0, None, 1.0) == (0.0, True)
    assert derived.current_spot_price(None, {"spot": 0.0, "official": False}, 1.0) == (0.0, False)
    assert derived.current_spot_price(None, {"spot": -0.05, "official": True}, 1.0) == (-0.05, True)


def test_charges_summary_has_last_months_hourly_sums_split_at_local_midnight():
    # 23:00 local on 30 September (21:00 UTC) is September; 00:00 local on 1 October is October.
    sept = {"start": dt.datetime(2026, 9, 30, 21, tzinfo=UTC), "end": dt.datetime(2026, 9, 30, 22, tzinfo=UTC),
            "energy": 10.0, "tax": 2.0, "norgespris": 6.0}
    octo = {"start": dt.datetime(2026, 9, 30, 22, tzinfo=UTC), "end": dt.datetime(2026, 9, 30, 23, tzinfo=UTC),
            "energy": 1.0, "tax": 0.2, "norgespris": 0.6}
    out = derived.summarise_charges([sept, octo], PERIOD_NOW, OSLO)
    assert (out["energy_gross_last_month"], out["vat_last_month"], out["norgespris_last_month"]) == (10.0, 2.0, 6.0)
    assert (out["energy_gross_month"], out["vat_month"], out["norgespris_month"]) == (1.0, 0.2, 0.6)


def test_charges_summary_without_last_month_hours_has_no_last_month_keys():
    octo = {"start": dt.datetime(2026, 10, 1, 8, tzinfo=UTC), "end": dt.datetime(2026, 10, 1, 9, tzinfo=UTC),
            "energy": 1.0, "tax": 0.2, "norgespris": 0.6}
    out = derived.summarise_charges([octo], PERIOD_NOW, OSLO)
    assert "norgespris_last_month" not in out and "energy_gross_last_month" not in out


NETTLEIE_LINES = {"dag": 550.93, "natt": 210.00, "kapasitet": 400.00, "forbruksavgift": 159.36, "enova": 22.36}


def test_the_invoice_lines_add_up_to_the_invoice_totals():
    assert sum(KRAFT_LINES.values()) == pytest.approx(INVOICE["kraft"], abs=0.005)
    assert sum(NETTLEIE_LINES.values()) == pytest.approx(INVOICE["nettleie"], abs=0.005)
    assert INVOICE["kraft"] + INVOICE["nettleie"] - INVOICE["norgespris"] == pytest.approx(INVOICE["total"], abs=0.005)


def test_house_cost_and_price_reproduce_the_september_invoice():
    cost = derived.house_cost("norgespris", SEPT["energy"], SEPT["grid_after"], SEPT["compensation"], SEPT["norgespris"])
    assert cost == pytest.approx(2325.35)                      # the invoice's "Totalt"
    assert derived.price_per_kwh(cost, SEPT["kwh"]) == pytest.approx(1.3002, abs=5e-5)


def test_the_monthly_sensors_give_the_invoice_total_without_a_second_fixed_price():
    # What "net cost last month" and "total gross" now compute from the September figures.
    site_total = SEPT["energy"] + SEPT["grid_after"]                     # Amperium's total, after subsidy
    subsidy = derived.subsidy_applied(SEPT["compensation"])
    assert derived.net_for_scheme("norgespris", site_total, subsidy, SEPT["norgespris"]) == pytest.approx(2325.35, abs=0.005)
    assert derived.net_for_scheme("subsidy", site_total, subsidy, SEPT["norgespris"]) == pytest.approx(3107.10, abs=0.005)
    assert derived.gross_total_from_net(site_total, SEPT["compensation"]) == pytest.approx(3219.50 + 1342.65, abs=0.005)


def test_house_cost_is_sign_independent_for_the_subsidy():
    pos = derived.house_cost("norgespris", 100.0, 10.0, 30.0, 50.0)
    neg = derived.house_cost("norgespris", 100.0, 10.0, -30.0, 50.0)
    assert pos == neg == pytest.approx(100.0 + 10.0 + 30.0 - 50.0)


def test_house_cost_for_the_regular_subsidy_ignores_norgespris():
    assert derived.house_cost("subsidy", 100.0, -20.0, 40.0, None) == pytest.approx(80.0)


@pytest.mark.parametrize("scheme,args", [
    (None, (1, 1, 1, 1)), ("other", (1, 1, 1, 1)),
    ("norgespris", (1, 1, 1, None)), ("norgespris", (None, 1, 1, 1)), ("norgespris", (1, 1, None, 1)),
    ("subsidy", (None, 1, 1, 1)),
])
def test_house_cost_is_unknown_when_something_is_missing(scheme, args):
    assert derived.house_cost(scheme, *args) is None


@pytest.mark.parametrize("cost,kwh", [(None, 10), (10, None), (10, 0), (10, -1), (10, "x"), ("x", 10)])
def test_price_per_kwh_unknown_without_cost_or_consumption(cost, kwh):
    assert derived.price_per_kwh(cost, kwh) is None


def test_price_per_kwh_zero_cost_is_a_price():
    assert derived.price_per_kwh(0.0, 10) == 0.0


# --- VAT inside the fixed monthly price ------------------------------------------------------
def test_vat_includes_the_vat_inside_the_fixed_monthly_price():
    # 25 kr incl. 25 % MVA holds 5.00 kr of VAT: 638.90 + 5.00 = invoice's 643.90
    assert derived.vat_with_fixed_price(HOURLY_VAT, HOURLY_ENERGY, 25.0) == pytest.approx(643.90, abs=0.005)


@pytest.mark.parametrize("vat,energy,fixed,expected", [
    (None, 100.0, 25.0, None),            # no VAT figure at all
    (20.0, 100.0, None, 20.0),            # no fixed price: the hourly VAT as it is
    (20.0, 0.0, 25.0, 20.0),              # no energy to derive the VAT share from
    (20.0, None, 25.0, 20.0),
    (20.0, 100.0, 0.0, 20.0),
])
def test_vat_with_fixed_price_falls_back_on_the_hourly_vat(vat, energy, fixed, expected):
    assert derived.vat_with_fixed_price(vat, energy, fixed) == expected


# --- resolve_period ---------------------------------------------------------------------------
def _iso(instant):
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_period_end_date_is_not_included_and_dates_count_in_local_time_summer():
    start, end = derived.resolve_period("2026-09-01", "2026-10-01", OSLO)    # all of September
    assert (_iso(start), _iso(end)) == ("2026-08-31T22:00:00Z", "2026-09-30T22:00:00Z")


def test_period_across_a_month_end_30_08_to_01_10():
    start, end = derived.resolve_period("2026-08-30", "2026-10-01", OSLO)
    assert (_iso(start), _iso(end)) == ("2026-08-29T22:00:00Z", "2026-09-30T22:00:00Z")
    assert (end - start) == dt.timedelta(hours=32 * 24)       # 30 and 31 August + 30 days of September


def test_period_in_winter_time():
    start, end = derived.resolve_period("2026-12-01", "2027-01-01", OSLO)
    assert (_iso(start), _iso(end)) == ("2026-11-30T23:00:00Z", "2026-12-31T23:00:00Z")


@pytest.mark.parametrize("day,next_day,hours", [
    ("2026-10-25", "2026-10-26", 25), ("2026-03-29", "2026-03-30", 23), ("2026-10-04", "2026-10-05", 24)])
def test_one_day_period_has_the_right_number_of_hours_around_the_clock_change(day, next_day, hours):
    start, end = derived.resolve_period(day, next_day, OSLO)
    assert (end - start) == dt.timedelta(hours=hours)


def test_period_with_times_is_taken_exactly_and_the_end_is_not_included():
    start, end = derived.resolve_period("2026-09-01 06:00:00", "2026-09-02T06:00:00", OSLO)
    assert (_iso(start), _iso(end)) == ("2026-09-01T04:00:00Z", "2026-09-02T04:00:00Z")
    start, end = derived.resolve_period("2026-09-01T06:00:00+00:00", "2026-09-01T12:00:00Z", OSLO)
    assert (_iso(start), _iso(end)) == ("2026-09-01T06:00:00Z", "2026-09-01T12:00:00Z")


def test_period_accepts_date_and_datetime_objects():
    start, end = derived.resolve_period(dt.date(2026, 9, 1), dt.date(2026, 10, 1), OSLO)
    assert _iso(start) == "2026-08-31T22:00:00Z" and _iso(end) == "2026-09-30T22:00:00Z"
    start, end = derived.resolve_period(dt.datetime(2026, 9, 1, 0, 0), dt.datetime(2026, 9, 2, 0, 0), OSLO)
    assert (end - start) == dt.timedelta(hours=24)


@pytest.mark.parametrize("fra,til", [
    ("2026-09-30", "2026-09-01"),                 # ends before it starts
    ("2026-09-01", "2026-09-01"),                 # the end date is not included, so this is empty
    ("2026-09-01 12:00:00", "2026-09-01 12:00:00"),  # empty
    ("2026-01-01", "2026-12-31"),                 # longer than 100 days
    ("not a date", "2026-09-30"), ("2026-09-01", ""), (None, "2026-09-30"), (5, 6),
])
def test_period_rejects_bad_input(fra, til):
    with pytest.raises(ValueError):
        derived.resolve_period(fra, til, OSLO)


def test_period_summary_for_september_matches_the_invoice_figures():
    start, end, hours, charges = _sept_inputs()
    out = derived.summarise_period(hours, charges, start, end, PERIOD_NOW, OSLO)
    assert out["warnings"] == []
    assert out["hours_expected"] == out["hours_with_data"] == 720
    assert out["consumption_kwh"] == pytest.approx(1788.520)
    assert out["energy_gross"] == pytest.approx(3219.50, abs=0.005)           # Kraft, from the aggregate
    assert out["energy_gross_hourly_sum"] == pytest.approx(3194.50, abs=0.005)  # kraftpris + påslag
    assert out["fixed_monthly_price"] == pytest.approx(25.0)
    # the fixed monthly price is a part of Kraft, not an addition to it
    assert out["energy_gross"] - out["energy_gross_hourly_sum"] == pytest.approx(out["fixed_monthly_price"], abs=0.005)
    assert out["vat_on_energy"] == pytest.approx(643.90, abs=0.005)              # the invoice's "Herav MVA"
    assert out["grid_after_support"] == pytest.approx(-112.40)
    assert out["subsidy_applied"] == pytest.approx(1455.05, abs=0.005)
    assert out["grid_before_support"] == pytest.approx(1342.65, abs=0.005)       # the invoice's "Nettleie"
    assert out["capacity_charge"] == pytest.approx(400.0)
    assert out["grid_before_support_excl_capacity"] == pytest.approx(942.65, abs=0.005)
    assert out["norgespris_compensation"] == pytest.approx(2236.80, abs=0.005)
    assert out["house_cost_norgespris"] == pytest.approx(2325.35, abs=0.005)     # the invoice's "Totalt"
    assert out["house_cost_subsidy"] == pytest.approx(3219.50 - 112.40, abs=0.005)
    assert out["price_per_kwh_norgespris"] == pytest.approx(1.3002, abs=5e-5)
    assert "fixed_fee" not in out and "price_per_kwh_norgespris_incl_fixed" not in out
    assert out["from"].startswith("2026-09-01T00:00:00+02:00") and out["to"].startswith("2026-10-01T00:00:00+02:00")


def test_period_summary_warns_when_the_period_spans_a_month_end():
    # 30.08 to 01.10 touches two months: two fixed monthly prices (50), both inside the total.
    start, end = derived.resolve_period("2026-08-30", "2026-10-01", OSLO)
    hours = _hourly(start, 32 * 24)                                  # 1.0 kr per hour: 768 in all
    charges = {"energy": hours, "outer_total": 768.0 + 50.0 + 1.0, "grid": {"total": 1.0, "compensation": 2.0},
               "fixed_total": 50.0}
    out = derived.summarise_period(hours, charges, start, end, PERIOD_NOW, OSLO)
    assert out["warnings"] == ["period_spans_months"]
    assert out["hours_expected"] == out["hours_with_data"] == 32 * 24
    assert out["energy_gross"] == pytest.approx(768.0 + 50.0)
    assert out["fixed_monthly_price"] == pytest.approx(50.0)


def test_period_summary_warns_when_the_total_does_not_hold_the_fixed_monthly_price():
    start, end, hours, charges = _sept_inputs()
    charges["outer_total"] = HOURLY_ENERGY + SEPT["grid_after"]      # hours only, nothing for the fixed price
    out = derived.summarise_period(hours, charges, start, end, PERIOD_NOW, OSLO)
    assert "fixed_monthly_price_not_in_energy_total" in out["warnings"]


def test_period_summary_warns_when_the_fixed_monthly_price_is_missing():
    start, end, hours, charges = _sept_inputs()
    charges["fixed_total"] = None
    out = derived.summarise_period(hours, charges, start, end, PERIOD_NOW, OSLO)
    assert "fixed_monthly_price_missing" in out["warnings"]
    assert out["fixed_monthly_price"] is None
    assert out["vat_on_energy"] == pytest.approx(HOURLY_VAT, abs=0.005)      # nothing to add VAT for


def test_period_summary_warns_for_a_period_that_is_not_over_and_counts_hours_up_to_now():
    start, end, hours, charges = _sept_inputs()
    now = start + dt.timedelta(days=10, minutes=30)                  # 10 days and a half hour in
    out = derived.summarise_period(hours, charges, start, end, now, OSLO)
    assert "period_not_over" in out["warnings"]
    assert out["hours_expected"] == 240 and out["hours_with_data"] == 240
    assert out["consumption_kwh"] == pytest.approx(SEPT["kwh"] / 3.0, abs=0.001)


def test_period_summary_warns_about_missing_hours_and_mismatched_charge_hours():
    start, end, hours, charges = _sept_inputs()
    out = derived.summarise_period(hours[:-3], charges, start, end, PERIOD_NOW, OSLO)
    assert "hours_missing:3" in out["warnings"]
    assert "charge_hours_differ_from_consumption_hours" in out["warnings"]


def test_period_summary_without_charges_gives_consumption_and_warns():
    start, end, hours, _ = _sept_inputs()
    out = derived.summarise_period(hours, None, start, end, PERIOD_NOW, OSLO)
    assert out["consumption_kwh"] == pytest.approx(SEPT["kwh"])
    assert "no_grid_rent_in_answer" in out["warnings"]
    for key in ("energy_gross", "grid_before_support", "norgespris_compensation",
                "house_cost_norgespris", "price_per_kwh_norgespris"):
        assert out[key] is None


def test_period_summary_falls_back_on_the_hourly_energy_sum_without_an_aggregate():
    start, end, hours, charges = _sept_inputs()
    charges["outer_total"] = None
    out = derived.summarise_period(hours, charges, start, end, PERIOD_NOW, OSLO)
    assert out["energy_gross"] == pytest.approx(HOURLY_ENERGY + 25.0)        # the hours plus the fixed price
    assert "fixed_monthly_price_not_in_energy_total" not in out["warnings"]


def test_period_summary_over_the_autumn_clock_change_counts_all_25_hours():
    start, end = derived.resolve_period("2026-10-25", "2026-10-26", OSLO)
    hours = _hourly(start, 25)                                       # 1.0 kr per hour: 25 in all
    charges = {"energy": hours, "outer_total": 25.0 + 1.0, "grid": {"total": 1.0, "compensation": 0.0},
               "fixed_total": 0.0}
    out = derived.summarise_period(hours, charges, start, end, dt.datetime(2026, 10, 26, 12, tzinfo=UTC), OSLO)
    assert out["hours_expected"] == out["hours_with_data"] == 25
    assert out["warnings"] == []


# --- hours Amperium has no data for -----------------------------------------------------------
def test_missing_hours_are_the_holes_in_the_series_not_the_newest_hours():
    start = dt.datetime(2026, 10, 31, 23, tzinfo=UTC)
    hours = _hourly(start, 24)                                    # 23:00 on 31 Oct to 22:00 on 1 Nov
    del hours[16:18]                                              # 15:00 and 16:00 UTC on 1 Nov are gone
    now = dt.datetime(2026, 11, 1, 22, 4, tzinfo=UTC)
    out = derived.missing_hours(hours, start, now)
    assert out == [dt.datetime(2026, 11, 1, 15, tzinfo=UTC), dt.datetime(2026, 11, 1, 16, tzinfo=UTC)]


def test_the_newest_two_hours_are_not_missing_yet():
    start = dt.datetime(2026, 11, 1, 0, tzinfo=UTC)
    hours = _hourly(start, 6)                                     # 00:00 to 05:00, then nothing
    assert derived.missing_hours(hours, start, dt.datetime(2026, 11, 1, 7, 30, tzinfo=UTC)) == []
    later = derived.missing_hours(hours, start, dt.datetime(2026, 11, 1, 10, 30, tzinfo=UTC))
    assert [h.hour for h in later] == [6, 7]                      # older than the 2 hours of grace now
    assert [h.hour for h in derived.missing_hours(hours, start, dt.datetime(2026, 11, 1, 10, 30, tzinfo=UTC), 0)] == [6, 7, 8, 9]


def test_hours_before_the_first_reading_and_before_the_month_are_not_missing():
    start = dt.datetime(2026, 11, 1, 0, tzinfo=UTC)
    early = _hourly(dt.datetime(2026, 10, 31, 20, tzinfo=UTC), 2)           # last month: ignored
    hours = early + _hourly(dt.datetime(2026, 11, 1, 6, tzinfo=UTC), 14)    # the site's data starts at 06:00
    now = dt.datetime(2026, 11, 1, 20, tzinfo=UTC)
    assert derived.missing_hours(hours, start, now) == []


def test_missing_hours_ignores_partial_future_and_duplicate_buckets_and_empty_input():
    start = dt.datetime(2026, 11, 1, 0, tzinfo=UTC)
    now = dt.datetime(2026, 11, 1, 12, 30, tzinfo=UTC)
    hours = _hourly(start, 13)                                    # the last one ends after now
    assert derived.missing_hours(hours + hours[:3], start, now) == []
    assert derived.missing_hours([], start, now) == []


def test_changed_hours_tells_what_appeared_and_what_was_filled():
    a, b, c = (dt.datetime(2026, 11, 1, h, tzinfo=UTC) for h in (15, 16, 17))
    assert derived.changed_hours(None, {a, b}) == ([a, b], [])                  # the first look
    assert derived.changed_hours({a, b}, {a, b}) == ([], [])
    assert derived.changed_hours({a, b}, {b, c}) == ([c], [a])
    assert derived.changed_hours({a, b}, set()) == ([], [a, b])
