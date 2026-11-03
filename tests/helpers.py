"""Helpers and sample data shared by more than one test file."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from conftest import api, derived

UTC = dt.timezone.utc
COMP = 118.45260713  # the subsidy (compensation) of an invented three-day period


OSLO = ZoneInfo("Europe/Oslo")


def _sub(history=None):
    return api.LiveSubscription(
        details={"server": "mq.example.test", "port": 5671, "useSsl": True, "virtualHost": "vh",
                 "username": "user-secret", "password": "pw-secret", "queueName": "queue-secret",
                 "exchangeName": "exchange-secret"},
        import_observations=history or [],
    )


DETAILS = {"server": "mq.example.test", "port": 5671, "useSsl": True, "virtualHost": "vh",
           "username": "u", "password": "p", "queueName": "q", "exchangeName": "x"}


# --- last month, free periods and the landlord's average price (October 2026) -----------------
def _hourly(start, count, *, kwh=1.0, energy=1.0, tax=0.2, norgespris=0.5):
    """Hourly buckets carrying both the consumption and the charges fields."""
    out = []
    for i in range(count):
        first = start + dt.timedelta(hours=i)
        out.append({"start": first, "end": first + dt.timedelta(hours=1), "import": kwh,
                    "export": 0.0, "energy": energy, "tax": tax, "norgespris": norgespris})
    return out


PERIOD_NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


# An INVENTED invoice for September 2026, line by line. Every figure here is made up; only the way
# the lines relate to each other (Kraft holds the fixed monthly price, VAT is 20 % of the gross
# amount, the grid rent has no fixed charge, Norgespris is deducted) follows a real invoice.
KRAFT_LINES = {"kraftpris": 3110.40, "paslag": 84.10, "fast_manedspris": 25.00, "oss_modul": 0.0}
INVOICE = {"kraft": 3219.50, "nettleie": 1342.65, "norgespris": 2236.80, "kwh": 1788.520, "kraft_mva": 643.90, "total": 2325.35}


# From the API for the same month: the grid rent after subsidy. The subsidy deducted in the grid rent is
# DERIVED from the invoice's nettleie 1342.65 - (-112.40); it is not read from the API.
SEPT = {"energy": INVOICE["kraft"], "grid_after": -112.40, "compensation": 1342.65 + 112.40,
        "norgespris": INVOICE["norgespris"], "kwh": INVOICE["kwh"]}


# September as hourly data, built from the invoice figures above.
HOURLY_ENERGY = KRAFT_LINES["kraftpris"] + KRAFT_LINES["paslag"]       # spot price and surcharge per hour
HOURLY_VAT = INVOICE["kraft_mva"] - 5.00                                # the API's hourly VAT (638.90)


def _sept_inputs():
    start, end = derived.resolve_period("2026-09-01", "2026-10-01", OSLO)
    hours = _hourly(start, 720, kwh=SEPT["kwh"] / 720, energy=HOURLY_ENERGY / 720, tax=HOURLY_VAT / 720,
                    norgespris=SEPT["norgespris"] / 720)
    charges = {
        "energy": hours,
        # Amperium's total holds the hours AND the kraft's fixed monthly price (25) plus the grid rent after subsidy.
        "outer_total": SEPT["energy"] + SEPT["grid_after"],
        "grid": {"total": SEPT["grid_after"], "compensation": SEPT["compensation"],
                 "capacity_amount": 400.0, "capacity_avg_kw": 8.17},
        "fixed_total": 25.0,
    }
    return start, end, hours, charges
