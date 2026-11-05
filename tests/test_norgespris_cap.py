"""Norgespris with the invoice's ceiling (5 000 kWh a month) and Amperium's cut at about 4 000 kWh.

Amperium's hourly figures are right, but one long request stops adding compensation at about
4 000 kWh from the start of the request. The fake client below does the same. The truth is what
the invoice does: Norgespris for the first 5 000 kWh of the calendar month, hour by hour.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools
from zoneinfo import ZoneInfo

import pytest
from conftest import charges as charges_mod
from conftest import derived, period

OSLO = ZoneInfo("Europe/Oslo")
UTC = dt.timezone.utc
HOUR = dt.timedelta(hours=1)
AMPERIUM_CUTS_AT = 4000.0
NOW = dt.datetime(2026, 12, 1, 12, tzinfo=UTC)
JAN = dt.datetime(2026, 1, 1, tzinfo=OSLO).astimezone(UTC)
FEB = dt.datetime(2026, 2, 1, tzinfo=OSLO).astimezone(UTC)


def month_hours(start, end, kwh_base=9.5):
    """Hourly consumption and a compensation rate that differ from hour to hour (so a mistake in
    which hour is counted shows up)."""
    hours = []
    moment = start
    i = 0
    while moment < end:
        hours.append({
            "start": moment, "end": moment + HOUR,
            "import": kwh_base + (i % 5) * 0.5,
            "rate": 0.3 + ((i * 7) % 10) * 0.1,
        })
        moment += HOUR
        i += 1
    return hours


class FakeAmperium:
    """Answers like Amperium: the hourly compensation of a request stops at ~4 000 kWh from its start."""

    def __init__(self, hours):
        self.hours = hours
        self.calls: list[tuple[str, dt.datetime, dt.datetime]] = []

    def _inside(self, start, end):
        return [h for h in self.hours if start <= h["start"] < end]

    async def async_get_energy(self, site_id, start, end):
        self.calls.append(("energy", start, end))
        return [{"start": h["start"], "end": h["end"], "import": h["import"], "export": 0.0}
                for h in self._inside(start, end)]

    async def async_get_prices(self, site_id, start, end):
        return []                      # not recorded: these tests count energy and charges calls

    async def async_get_charges(self, site_id, start, end):
        self.calls.append(("charges", start, end))
        buckets, counted = [], 0.0
        for h in self._inside(start, end):
            frac = min(1.0, max(0.0, (AMPERIUM_CUTS_AT - counted) / h["import"]))
            counted += h["import"]
            buckets.append({
                "start": h["start"], "end": h["end"], "energy": 1.0, "tax": 0.2,
                "norgespris": h["import"] * h["rate"] * frac,
                "norgespris_kwh": h["import"] * frac,
            })
        return {
            "energy": buckets, "outer_total": 5000.0, "fixed_total": 0.0,
            "grid": {"total": 100.0, "compensation": 0.0, "capacity_amount": 500.0,
                     "capacity_avg_kw": 12.0},
        }


def truth(hours, first, last, cap=5000.0):
    """The invoice's Norgespris for the hours in [first, last): the first ``cap`` kWh of the month."""
    total, counted = 0.0, 0.0
    for h in hours:
        if h["start"] >= last:
            break
        frac = min(1.0, max(0.0, (cap - counted) / h["import"]))
        counted += h["import"]
        if h["start"] >= first:
            total += h["import"] * h["rate"] * frac
    return total


def run(coro):
    return asyncio.run(coro)


def fetch_month(fake, start, end):
    energy = run(fake.async_get_energy(1, start, end))
    whole = run(fake.async_get_charges(1, start, end))
    hourly = run(charges_mod.async_uncapped_hourly_charges(fake, 1, start, end, energy, whole, NOW))
    return energy, whole, hourly


def test_the_fake_shows_the_amperium_cut_a_long_request_is_too_low():
    hours = month_hours(JAN, FEB)                      # about 7 000 kWh
    fake = FakeAmperium(hours)
    whole = run(fake.async_get_charges(1, JAN, FEB))
    cut = sum(b["norgespris"] for b in whole["energy"])
    assert cut < truth(hours, JAN, FEB)                # a month over the cut is too low
    assert sum(b["norgespris_kwh"] for b in whole["energy"]) == pytest.approx(AMPERIUM_CUTS_AT)


def test_a_month_over_the_ceiling_gets_exactly_the_first_5000_kwh():
    hours = month_hours(JAN, FEB)
    fake = FakeAmperium(hours)
    energy, _, hourly = fetch_month(fake, JAN, FEB)
    capped = charges_mod.apply_cap(hourly, energy, NOW, OSLO)
    assert sum(b["norgespris"] for b in capped) == pytest.approx(truth(hours, JAN, FEB))
    assert sum(b["norgespris_kwh"] for b in capped) == pytest.approx(5000.0)


def test_a_month_between_amperiums_cut_and_the_ceiling_is_not_cut_at_all():
    """Like December and February: under 5 000 kWh, but over what Amperium counts in one request."""
    end = JAN + dt.timedelta(days=18)                   # about 4 500 kWh
    hours = month_hours(JAN, end)
    fake = FakeAmperium(hours)
    energy, whole, hourly = fetch_month(fake, JAN, end)
    uncut = sum(h["import"] * h["rate"] for h in hours)
    assert sum(b["norgespris"] for b in whole["energy"]) < uncut      # one request is too low
    capped = charges_mod.apply_cap(hourly, energy, NOW, OSLO)
    assert 4000 < sum(h["import"] for h in hours) < 5000
    assert sum(b["norgespris"] for b in capped) == pytest.approx(uncut)


def test_a_small_month_needs_no_extra_requests():
    end = JAN + dt.timedelta(days=5)
    fake = FakeAmperium(month_hours(JAN, end))
    fetch_month(fake, JAN, end)
    assert [c[0] for c in fake.calls] == ["energy", "charges"]


def test_a_long_month_is_asked_for_in_pieces_that_are_each_well_under_the_cut():
    fake = FakeAmperium(month_hours(JAN, FEB))
    fetch_month(fake, JAN, FEB)
    pieces = [c for c in fake.calls[2:] if c[0] == "charges"]       # after energy and the whole
    assert len(pieces) >= 3
    assert pieces[0][1] == JAN and pieces[-1][2] == FEB
    assert all(a[2] == b[1] for a, b in itertools.pairwise(pieces))   # no gaps
    for _, a, b in pieces:
        kwh = sum(h["import"] for h in fake.hours if a <= h["start"] < b)
        assert kwh <= charges_mod.SAFE_REQUEST_KWH + 20


def test_the_hour_that_crosses_the_ceiling_gets_the_share_under_it_and_later_hours_none():
    start = JAN
    energy = [{"start": start + i * HOUR, "end": start + (i + 1) * HOUR, "import": 2000.0}
              for i in range(4)]
    chg = [{"start": e["start"], "end": e["end"], "norgespris": 10.0, "norgespris_kwh": 2000.0}
           for e in energy]
    out = charges_mod.apply_cap(chg, energy, NOW, OSLO)
    assert [round(b["norgespris"], 6) for b in out] == [10.0, 10.0, 5.0, 0.0]      # 2000+2000+1000
    assert [b["norgespris_cap_frac"] for b in out] == [1.0, 1.0, 0.5, 0.0]
    assert out[2]["norgespris_kwh"] == pytest.approx(1000.0)


def test_the_ceiling_starts_over_on_the_first_of_the_next_month():
    jan_last = FEB - HOUR
    energy = [
        {"start": jan_last, "end": FEB, "import": 6000.0},
        {"start": FEB, "end": FEB + HOUR, "import": 100.0},
    ]
    chg = [{"start": e["start"], "end": e["end"], "norgespris": 5.0, "norgespris_kwh": e["import"]}
           for e in energy]
    out = charges_mod.apply_cap(chg, energy, NOW, OSLO)
    assert out[0]["norgespris_cap_frac"] == pytest.approx(5000 / 6000)
    assert out[1]["norgespris_cap_frac"] == 1.0                                # a new month


def test_an_unknown_norgespris_stays_unknown_and_an_hour_without_consumption_is_left_alone():
    energy = [{"start": JAN, "end": JAN + HOUR, "import": 6000.0}]
    chg = [
        {"start": JAN, "end": JAN + HOUR, "norgespris": None, "norgespris_kwh": None},
        {"start": JAN + HOUR, "end": JAN + 2 * HOUR, "norgespris": 7.0, "norgespris_kwh": 1.0},
    ]
    out = charges_mod.apply_cap(chg, energy, NOW, OSLO)
    assert out[0]["norgespris"] is None and out[0]["norgespris_kwh"] is None
    assert out[1]["norgespris"] == 7.0 and "norgespris_cap_frac" not in out[1]


def test_unknown_norgespris_is_left_out_of_the_month_and_warned_about_in_a_period():
    start = JAN + 24 * HOUR
    hours = month_hours(start, start + 6 * HOUR)
    fake = FakeAmperium(hours)
    whole = run(fake.async_get_charges(1, start, start + 6 * HOUR))
    unknown = charges_mod.unknown_norgespris(whole["energy"])
    month = derived.summarise_charges(unknown, dt.datetime(2026, 1, 3, tzinfo=UTC), OSLO)
    assert "norgespris_month" not in month and month["energy_gross_month"] == pytest.approx(6.0)
    out = derived.summarise_period(
        run(fake.async_get_energy(1, start, start + 6 * HOUR)), {**whole, "energy": unknown},
        start, start + 6 * HOUR, NOW, OSLO,
    )
    assert "norgespris_unknown" in out["warnings"]
    assert out["norgespris_compensation"] is None and out["house_cost_norgespris"] is None


def test_a_period_in_the_middle_of_the_month_gets_the_ceiling_counted_from_the_first():
    """12 January to 1 February: the ceiling is reached inside it, so the later hours get nothing."""
    hours = month_hours(JAN, FEB)
    fake = FakeAmperium(hours)
    start = dt.datetime(2026, 1, 12, tzinfo=OSLO).astimezone(UTC)
    out = run(period.async_period_summary(fake, 1, start, FEB, OSLO, "norgespris", now=NOW))
    assert out["norgespris_compensation"] == pytest.approx(truth(hours, start, FEB), abs=0.005)
    assert "norgespris_cap_reached" in out["warnings"]
    assert 0 < out["norgespris_kwh"] < out["consumption_kwh"]
    assert "norgespris_kwh_below_consumption" in out["warnings"]


def test_a_period_after_the_ceiling_has_no_norgespris_at_all():
    hours = month_hours(JAN, FEB)
    fake = FakeAmperium(hours)
    start = dt.datetime(2026, 1, 30, tzinfo=OSLO).astimezone(UTC)
    out = run(period.async_period_summary(fake, 1, start, FEB, OSLO, now=NOW))
    assert out["norgespris_compensation"] == pytest.approx(0.0, abs=1e-9)


def test_a_whole_month_period_equals_the_month_and_asks_nothing_extra_when_small():
    end = JAN + dt.timedelta(days=5)
    hours = month_hours(JAN, end)
    fake = FakeAmperium(hours)
    out = run(period.async_period_summary(fake, 1, JAN, end, OSLO, now=NOW))
    assert out["norgespris_compensation"] == pytest.approx(truth(hours, JAN, end), abs=0.005)
    assert "norgespris_cap_reached" not in out["warnings"]
    assert [c[0] for c in fake.calls] == ["energy", "charges"]


def test_a_period_that_starts_late_in_a_small_month_reads_the_month_before_it_for_the_count():
    hours = month_hours(JAN, JAN + dt.timedelta(days=10))
    fake = FakeAmperium(hours)
    start = JAN + dt.timedelta(days=4)
    end = JAN + dt.timedelta(days=6)
    run(period.async_period_summary(fake, 1, start, end, OSLO, now=NOW))
    energy_calls = [c for c in fake.calls if c[0] == "energy"]
    assert (JAN, start) in [(c[1], c[2]) for c in energy_calls]       # the 1st up to the period
