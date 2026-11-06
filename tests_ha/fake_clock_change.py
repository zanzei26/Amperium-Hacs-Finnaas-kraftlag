"""A stand-in for Amperium on 5 November 2026, when last month (October) holds the autumn clock change.

October 2026 has 745 hours: the night of 25 October is an hour longer. This is the case that a month
without a clock change (the September of ``fake_api``) cannot show. Everything is invented: 3 kWh in
every hour, and a spot price that depends on the hour of the day (so that some hours are under the
Norgespris of 0.50 and give a negative compensation).

It also copies what was seen in a real installation, so the integration's answer to it can be tested:
the first of the two 02:00-03:00 hours has no cost row, Amperium's compensation leaves out both of the
repeated hours, and the energy total of the month is ``kraft_deficit`` kr under what the hours and
prices add up to.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from fake_api import _CAPACITY_TIERS, UTC, FakeAmperium, hours_between, iso

NOW_CLOCK = dt.datetime(2026, 11, 5, 11, 30, tzinfo=UTC)          # 12:30 in Norway (winter time)
OCT_FIRST = dt.datetime(2026, 9, 30, 22, tzinfo=UTC)               # 1 Oct 00:00 Europe/Oslo
NOV_FIRST = dt.datetime(2026, 10, 31, 23, tzinfo=UTC)              # 1 Nov 00:00 Europe/Oslo
REPEATED_1 = dt.datetime(2026, 10, 25, 0, tzinfo=UTC)              # 02:00-03:00 summer time
REPEATED_2 = dt.datetime(2026, 10, 25, 1, tzinfo=UTC)              # 02:00-03:00 winter time
KWH = 3.0
SURCHARGE = 0.0392
FIXED = 25.0
GRID_AFTER = 120.0
GRID_COMPENSATION = 40.0


def spot_of(hour: dt.datetime) -> float:
    """Spot price ex VAT: 0.30 at midnight UTC up to 0.60 late in the day."""
    return 0.30 + 0.013 * hour.hour


def energy_amount(hour: dt.datetime) -> float:
    return KWH * (spot_of(hour) + SURCHARGE) * 1.25


def compensation(hour: dt.datetime) -> float:
    return KWH * (spot_of(hour) * 1.25 - 0.50)


class ClockChangeAmperium(FakeAmperium):
    """The fake API with October 2026 as last month."""

    def __init__(self) -> None:
        super().__init__()
        # How far under the hours and prices Amperium's energy total is for a window that holds the
        # repeated hour and hours after it (7.54 kr was seen).
        self.kraft_deficit = 7.54
        # Amperium's compensation leaves out both repeated hours, and the first has no cost row.
        self.amperium_drops_repeated_hours = True

    @staticmethod
    def hours_of(first: dt.datetime, last: dt.datetime) -> list[dt.datetime]:
        return [h for h in hours_between(first, last) if h + dt.timedelta(hours=1) <= NOW_CLOCK]

    # -- answers ---------------------------------------------------------------------------------
    def _oct_hours(self) -> list[dt.datetime]:
        return self.hours_of(NOV_FIRST, NOW_CLOCK)

    def _prices(self, query: dict[str, str]) -> list[dict[str, Any]]:
        start, end = self._window(query)
        if start >= NOW_CLOCK:                      # tomorrow's prices are not published yet
            return []
        return [
            {"startTime": iso(h), "endTime": iso(h + dt.timedelta(hours=1)),
             "spotPreliminary": spot_of(h), "spotOfficial": spot_of(h), "surcharge": SURCHARGE,
             "salesTaxPercentage": 25, "updatedOn": iso(NOW_CLOCK)}
            for h in hours_between(start, end)
        ]

    def _energy(self, query: dict[str, str]) -> list[dict[str, Any]]:
        start, end = self._window(query)
        return [{"from": iso(h), "to": iso(h + dt.timedelta(hours=1)),
                 "importedEnergy": KWH, "exportedEnergy": 0.0}
                for h in self.hours_of(start, end)]

    def _charges(self, query: dict[str, str]) -> dict[str, Any]:
        start, end = self._window(query)
        hours = self.hours_of(start, end)
        rows = []
        for h in hours:
            if self.amperium_drops_repeated_hours and h == REPEATED_1:
                continue                            # 24 cost rows for a day of 25 hours
            dropped = self.amperium_drops_repeated_hours and h == REPEATED_2
            amount = energy_amount(h)
            rows.append({
                "from": iso(h), "to": iso(h + dt.timedelta(hours=1)),
                "importedEnergyAmount": amount, "salesTaxAmount": amount * 0.2,
                "importedCompensationAmountNorgespris": 0.0 if dropped else compensation(h),
                "importedCompensationEnergyNorgespris": 0.0 if dropped else KWH,
            })
        total = sum(energy_amount(h) for h in hours) + FIXED          # Amperium's total holds every hour
        if REPEATED_2 in hours and hours[-1] > REPEATED_2:
            total -= self.kraft_deficit
        return {
            "energy": rows,
            "totalAmount": total + GRID_AFTER,
            "gridRent": {
                "totalAmount": GRID_AFTER, "compensationAmount": GRID_COMPENSATION,
                "capacityChargeAveragePower": 6.5,
                "capacityInterval": {"powerMin": 5, "powerMax": 10, "amount": 400},
                "importedEnergyDay": 50.0, "importedEnergyNight": 22.0,
                "energyChargeDayAmount": 22.0, "energyChargeNightAmount": 8.0,
                "electricityFeeAmount": 6.4, "enovaFeeAmount": 0.9,
                "membershipDiscountAmount": 0.0, "salesTaxAmount": 10.0,
            },
            "fixedCharges": {"totalAmount": FIXED},
            "capacityChargeIntervals": _CAPACITY_TIERS,
        }
