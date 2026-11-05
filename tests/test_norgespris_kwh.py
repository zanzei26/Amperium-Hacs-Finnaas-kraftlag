"""The kWh Amperium counts for the Norgespris compensation (``norgespris_kwh``), and the warning
when they are fewer than the consumption (a ceiling reached, or hours that do not count)."""
from __future__ import annotations

import asyncio
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from conftest import api, derived

OSLO = ZoneInfo("Europe/Oslo")
UTC = dt.timezone.utc
HOUR = dt.timedelta(hours=1)
NOW = dt.datetime(2026, 12, 1, tzinfo=UTC)


def hours(start: dt.datetime, count: int):
    return [start + i * HOUR for i in range(count)]


def energy(starts, kwh=2.0):
    return [{"start": s, "end": s + HOUR, "import": kwh} for s in starts]


def charges(starts, counted):
    """Charge buckets; ``counted`` is the norgespris_kwh of each hour (None = field missing)."""
    return {
        "energy": [
            {"start": s, "end": s + HOUR, "energy": 1.0, "tax": 0.2, "norgespris": 0.5,
             "norgespris_kwh": k}
            for s, k in zip(starts, counted, strict=True)
        ],
        "grid": {"total": 10.0, "compensation": 0.0},
        "outer_total": 20.0,
        "fixed_total": 0.0,
    }


START = dt.datetime(2026, 10, 1, 0, tzinfo=UTC)
TEN = hours(START, 10)


def summary(cons, chg, start=START, end=None):
    end = end or start + 10 * HOUR
    return derived.summarise_period(cons, chg, start, end, NOW, OSLO)


def test_the_counted_kwh_are_summed_and_nothing_is_warned_when_all_consumption_counts():
    out = summary(energy(TEN), charges(TEN, [2.0] * 10))
    assert out["norgespris_kwh"] == pytest.approx(20.0)
    assert "norgespris_kwh_below_consumption" not in out["warnings"]


def test_fewer_counted_kwh_than_consumption_is_flagged_with_the_number():
    counted = [2.0] * 6 + [0.0] * 4              # a ceiling reached after six hours
    out = summary(energy(TEN), charges(TEN, counted))
    assert out["norgespris_kwh"] == pytest.approx(12.0)
    assert "norgespris_kwh_below_consumption" in out["warnings"]


def test_a_small_difference_is_rounding_not_a_warning():
    counted = [2.0] * 9 + [1.7]                  # 0.3 kWh short
    out = summary(energy(TEN), charges(TEN, counted))
    assert "norgespris_kwh_below_consumption" not in out["warnings"]


def test_no_counted_kwh_at_all_means_no_norgespris_and_no_warning():
    out = summary(energy(TEN), charges(TEN, [0.0] * 10))
    assert out["norgespris_kwh"] == 0.0
    assert "norgespris_kwh_below_consumption" not in out["warnings"]


def test_a_missing_field_is_none_and_not_a_zero_that_would_look_like_a_ceiling():
    out = summary(energy(TEN), charges(TEN, [None] * 10))
    assert out["norgespris_kwh"] is None
    assert "norgespris_kwh_below_consumption" not in out["warnings"]


def test_without_cost_rows_there_is_nothing_to_report():
    out = summary(energy(TEN), {"energy": [], "grid": {"total": 1.0, "compensation": 0.0}})
    assert out["norgespris_kwh"] is None


def test_the_hour_without_a_cost_row_on_the_autumn_day_is_not_a_false_warning():
    """25 October 2026 had 25 consumption hours and 24 cost rows. The counted kWh are compared
    with the consumption of the hours that have a cost row, so that hour does not make a warning."""
    start = dt.datetime(2026, 10, 24, 22, tzinfo=UTC)               # 25 Oct 00:00 local
    day = hours(start, 25)
    with_cost = day[:2] + day[3:]                                      # the first 02:00 hour is missing
    out = derived.summarise_period(
        energy(day), charges(with_cost, [2.0] * 24), start, start + 25 * HOUR, NOW, OSLO
    )
    assert out["hours_with_data"] == 25
    assert out["norgespris_kwh"] == pytest.approx(48.0)
    assert "charge_hours_differ_from_consumption_hours" in out["warnings"]
    assert "norgespris_kwh_below_consumption" not in out["warnings"]


def test_the_api_client_reads_the_kwh_field_and_keeps_missing_apart_from_zero():
    raw = {
        "energy": [
            {"from": "2026-10-01T00:00:00Z", "to": "2026-10-01T01:00:00Z",
             "importedEnergyAmount": 1.0, "salesTaxAmount": 0.2,
             "importedCompensationAmountNorgespris": 0.5,
             "importedCompensationEnergyNorgespris": 1.75},
            {"from": "2026-10-01T01:00:00Z", "to": "2026-10-01T02:00:00Z",
             "importedEnergyAmount": 1.0, "salesTaxAmount": 0.2,
             "importedCompensationAmountNorgespris": 0.5},
        ],
        "totalAmount": 1.0,
    }

    class Client(api.AmperiumClient):
        async def _request(self, *args, **kwargs):
            return 200, raw

    out = asyncio.run(Client(None, "a", "r").async_get_charges(1, START, START + 2 * HOUR))
    assert [b["norgespris_kwh"] for b in out["energy"]] == [1.75, None]
