"""The consumption-weighted spot price of a period, and what lies above the Norgespris ceiling.

The invoice's "Kraftpris" is the spot price incl. VAT (not the surcharge) weighted by the hourly
consumption: the sum of (kWh in the hour x spot price of the hour) divided by the sum of kWh.
Norgespris is then that price minus 0.50. This module computes the same from Amperium's hourly
prices and hourly consumption. No Home Assistant is needed, so it can be tested on its own.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from .charges import NORGESPRIS_CAP_KWH, cap_shares
from .derived import _parse_iso, complete_hours, vat_with_fixed_price

MAX_LISTED_HOURS = 48
# A difference between Amperium's Kraft and the one rebuilt from the prices over this (kr) is a warning.
KRAFT_DEVIATION_WARNING = 1.0


def price_index(prices: list[dict[str, Any]]) -> dict[dt.datetime, dict[str, float]]:
    """Hourly price buckets by their start, keeping only those with a usable spot price and VAT."""
    index: dict[dt.datetime, dict[str, float]] = {}
    for bucket in prices or []:
        start = _parse_iso(bucket.get("start"))
        spot, vat = bucket.get("spot"), bucket.get("vat_percent")
        if start is None or not isinstance(spot, (int, float)) or not isinstance(vat, (int, float)):
            continue
        surcharge = bucket.get("surcharge")
        index[start] = {
            "spot": float(spot),
            "vat": float(vat),
            "surcharge": float(surcharge) if isinstance(surcharge, (int, float)) else 0.0,
        }
    return index


def weighted_spot(
    energy: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
) -> dict[str, Any]:
    """Consumption-weighted spot price over the hours of [start, end) that have a price.

    ``spotsnitt`` is incl. VAT and without the surcharge (the invoice's Kraftpris). ``borspris``
    is the same without VAT, ``paslag`` the surcharge incl. VAT, and ``inkl_paslag`` the sum of
    ``spotsnitt`` and ``paslag`` (what the consumer pays per kWh for the power). An hour with
    consumption and no price is counted in ``manglende_timer`` and left out of the average,
    nothing is made up for it. ``sum_spot_inkl_mva`` and ``sum_paslag_inkl_mva`` are the amounts
    in kr, so a period's Kraft can be compared hour for hour.
    """
    index = price_index(prices)
    kwh = spot_ex = spot_incl = paslag_incl = vat_sum = 0.0
    priced = zero_price = 0
    missing: list[str] = []
    missing_count = 0
    for bucket in complete_hours(energy, now):
        if not start <= bucket["start"] < end:
            continue
        price = index.get(bucket["start"])
        if price is None:
            missing_count += 1
            if len(missing) < MAX_LISTED_HOURS:
                missing.append(bucket["start"].astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
            continue
        factor = 1 + price["vat"] / 100
        weight = bucket["import"]
        kwh += weight
        spot_ex += weight * price["spot"]
        spot_incl += weight * price["spot"] * factor
        paslag_incl += weight * price["surcharge"] * factor
        vat_sum += weight * (price["spot"] + price["surcharge"]) * (factor - 1)
        priced += 1
        if price["spot"] == 0:
            zero_price += 1
    have = kwh > 0
    return {
        "spotsnitt": spot_incl / kwh if have else None,
        "borspris": spot_ex / kwh if have else None,
        "paslag": paslag_incl / kwh if have else None,
        "inkl_paslag": (spot_incl + paslag_incl) / kwh if have else None,
        "kwh": kwh,
        "timer": priced,
        "manglende_timer": missing_count,
        "manglende_timer_liste": missing,
        "timer_med_pris_null": zero_price,
        "sum_spot_inkl_mva": spot_incl,
        "sum_paslag_inkl_mva": paslag_incl,
        "sum_mva": vat_sum,
    }


def cap_split(
    energy: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    now: dt.datetime,
    tz: dt.tzinfo,
    cap_kwh: float = NORGESPRIS_CAP_KWH,
) -> dict[str, Any]:
    """The consumption under and over the month's Norgespris ceiling, and the price of what is over.

    ``energy`` must hold the consumption from the 1st of the month. ``norgespris_kwh`` is the
    consumption under the ceiling (the first 5 000 kWh in the order the hours came) and
    ``over_tak_kwh`` the rest. ``spotsnitt_over_tak`` is the weighted price per kWh of the part
    above the ceiling incl. surcharge and VAT (what that power costs, with no Norgespris), and
    ``spotsnitt_over_tak_uten_paslag`` the same without the surcharge. They are None when nothing
    is above the ceiling. ``over_tak_uten_pris_kwh`` is the part above it in hours with no price.
    """
    index = price_index(prices)
    within = over = 0.0
    priced_kwh = spot_incl = paslag_incl = 0.0
    unpriced = 0.0
    for start, (frac, kwh) in cap_shares(energy, now, tz, cap_kwh).items():
        within += kwh * frac
        above = kwh * (1 - frac)
        if above <= 0:
            continue
        over += above
        price = index.get(start)
        if price is None:
            unpriced += above
            continue
        factor = 1 + price["vat"] / 100
        priced_kwh += above
        spot_incl += above * price["spot"] * factor
        paslag_incl += above * price["surcharge"] * factor
    have = priced_kwh > 0
    return {
        "norgespris_kwh": within,
        "over_tak_kwh": over,
        "spotsnitt_over_tak": (spot_incl + paslag_incl) / priced_kwh if have else None,
        "spotsnitt_over_tak_uten_paslag": spot_incl / priced_kwh if have else None,
        "over_tak_uten_pris_kwh": unpriced,
    }


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def expected_hours(start: dt.datetime, end: dt.datetime, now: dt.datetime) -> int:
    """The whole hours of [start, end) that have passed (the same count ``summarise_period`` uses)."""
    cutoff = min(end, now.replace(minute=0, second=0, microsecond=0))
    return max(0, round((cutoff - start).total_seconds() / 3600))


def kraft_from_prices(
    energy: list[dict[str, Any]],
    prices: list[dict[str, Any]] | None,
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
    fixed: float | None,
) -> tuple[float, float] | None:
    """Kraft and its VAT rebuilt from the hourly prices, or None when that cannot be trusted.

    Kraft is the sum over the hours of kWh x (spot + surcharge) incl. VAT, plus the fixed monthly
    price. It is only returned when every hour of the period has consumption AND a price, so
    nothing is made up and nothing is left out. It equals Amperium's own Kraft (which matched the
    invoices) to the øre in the seven months tried, except October 2026, where Amperium's answer
    for a request that crosses the clock change (25 October) came out about 7.5 kr too low.
    """
    if prices is None or fixed is None:     # without the fixed price the sum would miss it
        return None
    avg = weighted_spot(energy, prices, start, end, now)
    # "timer" counts the hours that have both consumption and a price, so it is only equal to the
    # hours that have passed when none lacks either.
    if avg["kwh"] <= 0 or avg["timer"] != expected_hours(start, end, now):
        return None
    gross = avg["sum_spot_inkl_mva"] + avg["sum_paslag_inkl_mva"]
    kraft = gross + fixed
    return kraft, vat_with_fixed_price(avg["sum_mva"], gross, fixed)


def period_price_fields(
    energy: list[dict[str, Any]],
    prices: list[dict[str, Any]] | None,
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
    energy_gross: float | None,
    fixed: float | None,
) -> tuple[dict[str, Any], list[str]]:
    """The fields ``hent_periode`` adds from the hourly prices, and the warnings that go with them.

    ``kraft_fra_priser`` is Kraft rebuilt from the prices: the sum of kWh x (spot + surcharge) incl.
    VAT over the hours, plus the fixed monthly price. ``kraft_avvik_fra_priser`` is Amperium's
    ``energy_gross`` minus that, so a difference between the two sources shows up as a number.
    Prices that could not be fetched give empty fields and the warning ``priser_ikke_hentet``.
    """
    empty = {
        "spotsnitt": None, "borspris": None, "spot_inkl_paslag": None, "spot_kwh": None,
        "spot_timer": None, "spot_manglende_timer": None, "spot_timer_med_pris_null": None,
        "kraft_fra_priser": None, "kraft_avvik_fra_priser": None,
    }
    if prices is None:
        return empty, ["priser_ikke_hentet"]
    avg = weighted_spot(energy, prices, start, end, now)
    kraft = None
    if avg["kwh"] > 0:
        kraft = avg["sum_spot_inkl_mva"] + avg["sum_paslag_inkl_mva"] + (fixed or 0.0)
    deviation = None if kraft is None or energy_gross is None else energy_gross - kraft
    fields = {
        "spotsnitt": _round(avg["spotsnitt"], 4),
        "borspris": _round(avg["borspris"], 4),
        "spot_inkl_paslag": _round(avg["inkl_paslag"], 4),
        "spot_kwh": _round(avg["kwh"], 3),
        "spot_timer": avg["timer"],
        "spot_manglende_timer": avg["manglende_timer"],
        "spot_timer_med_pris_null": avg["timer_med_pris_null"],
        "kraft_fra_priser": _round(kraft, 2),
        "kraft_avvik_fra_priser": _round(deviation, 2),
    }
    warnings: list[str] = []
    if avg["manglende_timer"]:
        warnings.append(f"priser_mangler:{avg['manglende_timer']}")
    elif deviation is not None and abs(deviation) > KRAFT_DEVIATION_WARNING:
        warnings.append("kraft_avviker_fra_priser")
    return fields, warnings
