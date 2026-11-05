"""Summer/winter time: a day with 25 hours (autumn) and a day with 23 hours (spring).

The functions count instants (UTC buckets) and group by the local date, so a day that is not
24 hours long needs no special case. These tests build whole days in Europe/Oslo around both
changes and run the real functions on them, so a change that assumes 24 hours a day shows up.
The days are the ones in 2026/2027: the clocks go back on 25 October 2026 and forward on
28 March 2027.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from conftest import derived

OSLO = ZoneInfo("Europe/Oslo")
UTC = dt.timezone.utc
HOUR = dt.timedelta(hours=1)


def local(year, month, day, hour=0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, tzinfo=OSLO)


def instants(start_local: dt.datetime, end_local: dt.datetime) -> list[dt.datetime]:
    """Every whole hour in [start, end), as UTC instants."""
    out = []
    moment = start_local.astimezone(UTC)
    stop = end_local.astimezone(UTC)
    while moment < stop:
        out.append(moment)
        moment += HOUR
    return out


def energy_buckets(start_local, end_local, kwh=lambda local_hour: 1.0):
    return [
        {"start": s, "end": s + HOUR, "import": kwh(s.astimezone(OSLO).hour)}
        for s in instants(start_local, end_local)
    ]


def charge_buckets(start_local, end_local, price=0.5):
    return [
        {"start": s, "end": s + HOUR, "energy": price, "tax": price / 5, "norgespris": 0.1}
        for s in instants(start_local, end_local)
    ]


AUTUMN = (local(2026, 10, 25), local(2026, 10, 26), 25)   # the clocks go back: 25 hours
SPRING = (local(2027, 3, 28), local(2027, 3, 29), 23)     # the clocks go forward: 23 hours
LONG_RANGE = {
    "autumn": (local(2026, 10, 1), local(2026, 11, 1), 745),   # 31 days + 1 hour
    "spring": (local(2027, 3, 1), local(2027, 4, 1), 743),     # 31 days - 1 hour
}


@pytest.mark.parametrize(("start", "end", "hours"), [AUTUMN, SPRING], ids=["autumn", "spring"])
def test_the_day_has_the_number_of_hours_it_really_has(start, end, hours):
    assert len(instants(start, end)) == hours


@pytest.mark.parametrize(("start", "end", "hours"), [AUTUMN, SPRING], ids=["autumn", "spring"])
def test_a_period_over_the_day_expects_and_finds_every_hour(start, end, hours):
    now = local(2026, 12, 1) if start.year == 2026 else local(2027, 5, 1)
    energy = energy_buckets(start, end)
    charges = {
        "energy": charge_buckets(start, end),
        "grid": {"total": 100.0, "compensation": 0.0},
        "outer_total": 200.0,
        "fixed_total": 25.0,
    }
    out = derived.summarise_period(
        energy, charges, start.astimezone(UTC), end.astimezone(UTC), now.astimezone(UTC), OSLO
    )
    assert out["hours_expected"] == hours
    assert out["hours_with_data"] == hours
    assert out["consumption_kwh"] == pytest.approx(hours)
    assert out["energy_gross_hourly_sum"] == pytest.approx(0.5 * hours)
    assert "charge_hours_differ_from_consumption_hours" not in out["warnings"]
    assert not any(w.startswith("hours_missing") for w in out["warnings"])


@pytest.mark.parametrize(("start", "end", "hours"), list(LONG_RANGE.values()), ids=list(LONG_RANGE))
def test_a_whole_month_with_the_change_has_no_missing_or_extra_hours(start, end, hours):
    now = (end + dt.timedelta(hours=2)).astimezone(UTC)     # two hours of grace after the last hour
    energy = energy_buckets(start, end)
    out = derived.summarise_period(
        energy, {"energy": charge_buckets(start, end)}, start.astimezone(UTC),
        end.astimezone(UTC), now, OSLO,
    )
    assert out["hours_expected"] == out["hours_with_data"] == hours
    assert derived.missing_hours(energy, start.astimezone(UTC), now) == []


def test_amperium_giving_one_cost_hour_too_few_is_flagged_not_hidden():
    """What the real answer for 25 October 2026 looked like: 25 consumption hours, 24 cost hours."""
    start, end, _ = AUTUMN
    charges = charge_buckets(start, end)
    del charges[2]                       # the first 02:00-03:00 hour has no cost row
    out = derived.summarise_period(
        energy_buckets(start, end), {"energy": charges},
        start.astimezone(UTC), end.astimezone(UTC), local(2026, 12, 1).astimezone(UTC), OSLO,
    )
    assert out["hours_with_data"] == 25
    assert out["energy_gross_hourly_sum"] == pytest.approx(0.5 * 24)   # nothing is made up
    assert "charge_hours_differ_from_consumption_hours" in out["warnings"]


@pytest.mark.parametrize(("start", "end", "hours"), [AUTUMN, SPRING], ids=["autumn", "spring"])
def test_yesterday_is_the_whole_local_day_whatever_its_length(start, end, hours):
    now = (end + dt.timedelta(hours=12)).astimezone(UTC)     # noon the day after
    out = derived.summarise_energy(energy_buckets(start, end), now, OSLO, 6, 22)
    assert out["energy_yesterday"] == pytest.approx(hours)


@pytest.mark.parametrize(("start", "end", "hours"), [AUTUMN, SPRING], ids=["autumn", "spring"])
def test_the_cost_of_yesterday_is_the_whole_local_day_whatever_its_length(start, end, hours):
    now = (end + dt.timedelta(hours=12)).astimezone(UTC)
    out = derived.summarise_charges(charge_buckets(start, end), now, OSLO)
    assert out["cost_yesterday"] == pytest.approx(0.5 * hours)


@pytest.mark.parametrize(
    ("start", "end", "hours", "night_hours"),
    [(*AUTUMN, 9), (*SPRING, 7)],     # day is 06-22 = 16 clock hours; the rest is night
    ids=["autumn", "spring"],
)
def test_day_and_night_split_follows_the_clock_on_the_changing_day(start, end, hours, night_hours):
    """In autumn the 02-03 hour happens twice (both are night); in spring it does not happen."""
    now = (end + dt.timedelta(hours=12)).astimezone(UTC)
    out = derived.summarise_energy(energy_buckets(start, end), now, OSLO, 6, 22)
    assert out["energy_day_month"] == pytest.approx(16)
    assert out["energy_night_month"] == pytest.approx(night_hours)
    assert out["energy_day_month"] + out["energy_night_month"] == pytest.approx(hours)


@pytest.mark.parametrize(("start", "end", "_hours"), [AUTUMN, SPRING], ids=["autumn", "spring"])
def test_the_changing_day_counts_once_as_a_day_for_the_capacity_peaks(start, end, _hours):
    """The day's peak is its highest hour, so the repeated hour does not count the day twice."""
    peak_hour = 2 if start.month == 10 else 12      # the repeated 02:00 hour in autumn
    energy = energy_buckets(start, end, kwh=lambda h: 9.0 if h == peak_hour else 1.0)
    now = (end + dt.timedelta(hours=12)).astimezone(UTC)
    out = derived.capacity_peaks(energy, now, OSLO)
    assert out["capacity_peak_days"] == 1
    assert [p["kw"] for p in out["capacity_peaks"]] == [9.0]


@pytest.mark.parametrize(("start", "end", "hours"), [AUTUMN, SPRING], ids=["autumn", "spring"])
def test_hourly_statistics_has_one_row_per_hour_and_the_sum_is_whole(start, end, hours):
    now = (end + dt.timedelta(hours=12)).astimezone(UTC)
    rows = derived.build_hourly_statistics(energy_buckets(start, end), "import", 0.0, now)
    assert len(rows) == hours
    assert rows[-1]["sum"] == pytest.approx(hours)
    assert [r["start"] for r in rows] == sorted({r["start"] for r in rows})   # no repeats
