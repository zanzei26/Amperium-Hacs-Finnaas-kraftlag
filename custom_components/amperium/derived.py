"""Pure helpers that turn Amperium hourly buckets into sensor values.

No Home Assistant imports here, so the logic can be tested on its own.
All bucket timestamps are timezone-aware datetimes (UTC from the API); day
and month boundaries are evaluated in the timezone passed in (the user's
local time).
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def local_month_bounds(
    now_local: dt.datetime,
) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    """Return (start of previous month, start of this month, start of next)."""
    this_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_start = (this_start - dt.timedelta(days=1)).replace(day=1)
    next_start = (this_start + dt.timedelta(days=32)).replace(day=1)
    return prev_start, this_start, next_start


def complete_hours(buckets: list[dict[str, Any]], now: dt.datetime) -> list[dict[str, Any]]:
    """Sort buckets, drop duplicates, partial/future hours and misaligned ones."""
    seen: dict[dt.datetime, dict[str, Any]] = {}
    for bucket in buckets:
        start, end = bucket.get("start"), bucket.get("end")
        if not isinstance(start, dt.datetime) or not isinstance(end, dt.datetime):
            continue
        if end > now or start.minute or start.second or start.microsecond:
            continue
        seen[start] = bucket
    return [seen[k] for k in sorted(seen)]


def choose_power_now(
    local_kw: float | None,
    amperium_kw: float | None,
    live_kw: float | None = None,
) -> tuple[float | None, str | None]:
    """Pick the "power now" value and say where it came from.

    Order: the user's own Home Assistant power sensor, then Amperium's live feed,
    then Amperium's hourly value (``currentActivePowerImport``). A reading of 0.0
    counts as a reading. Returns (kW, source) with source "local_sensor",
    "amperium_live", "amperium" or None.
    """
    if local_kw is not None:
        return local_kw, "local_sensor"
    if live_kw is not None:
        return live_kw, "amperium_live"
    if amperium_kw is not None:
        return amperium_kw, "amperium"
    return None, None


class ChangeGate:
    """Say whether a value differs from the last one it was asked about.

    Used to skip state writes that would repeat what is already shown.
    """

    _UNSET = object()

    def __init__(self) -> None:
        """Start with nothing remembered, so the first value always counts as changed."""
        self._last: Any = self._UNSET

    def changed(self, value: Any) -> bool:
        """Remember ``value``; True unless it equals the previous one."""
        if self._last is not self._UNSET and value == self._last:
            return False
        self._last = value
        return True


def days_until(timestamp: Any, now: dt.datetime) -> float | None:
    """Days from ``now`` until an ISO-8601 timestamp (None if unknown/invalid)."""
    if not isinstance(timestamp, str):
        return None
    try:
        when = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (when - now).total_seconds() / 86400


def _parse_iso(value: Any) -> dt.datetime | None:
    """Parse an ISO-8601 timestamp into an aware datetime (naive counts as UTC)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.timezone.utc)


def current_price_bucket(buckets: Any, now: dt.datetime) -> dict[str, Any] | None:
    """The hourly price bucket that contains ``now``, or None.

    The buckets carry UTC start/end times and ``now`` is an aware datetime, so the
    comparison is between instants: the local day boundary and summer/winter time
    cannot shift it. A bucket runs from its start up to, but not including, its end.
    """
    for bucket in buckets or []:
        if not isinstance(bucket, dict):
            continue
        start, end = _parse_iso(bucket.get("start")), _parse_iso(bucket.get("end"))
        if start is not None and end is not None and start <= now < end:
            return bucket
    return None


def current_spot_price(
    official: Any, bucket: dict[str, Any] | None, preliminary: Any
) -> tuple[float | None, bool | None]:
    """The spot price to show as "now", and whether it is the official one.

    Order: the official price from /api/sites, then the price of the current hour in
    the hourly list (official, or preliminary until it is fixed), then the preliminary
    price from /api/sites. Amperium has no official price for the hours right after
    midnight, and the sensor must still show a price then.
    """
    if official is not None:
        return float(official), True
    if isinstance(bucket, dict) and bucket.get("spot") is not None:
        return float(bucket["spot"]), bool(bucket.get("official"))
    if preliminary is not None:
        return float(preliminary), False
    return None, None


def consumer_price(spot: Any, surcharge: Any, vat_percent: Any) -> float | None:
    """Price per kWh the consumer pays: (spot + surcharge) incl. VAT.

    The VAT percentage comes from the API (never hardcoded). A missing
    surcharge counts as 0; a missing spot price or VAT percentage gives None.
    Derived, not confirmed by Amperium.
    """
    if spot is None or vat_percent is None:
        return None
    try:
        return (float(spot) + float(surcharge or 0)) * (1 + float(vat_percent) / 100)
    except (TypeError, ValueError):
        return None


SIGNAL_STATES = {0: "none", 1: "poor", 2: "fair", 3: "good", 4: "excellent"}


def han_signal_state(signal: Any, online: Any) -> str | None:
    """Map the HAN module's cellular signal (0-4) and online flag to a state.

    Mirrors the official app: offline wins, then "no data" when the signal is
    missing, otherwise 0=none, 1=poor, 2=fair, 3=good, 4=excellent (the app's
    icon picker also treats a higher number as a stronger signal).
    """
    if online is False:
        return "offline"
    if signal is None:
        return "no_data"
    try:
        return SIGNAL_STATES.get(int(signal))
    except (TypeError, ValueError):
        return None


def _iso_z(value: dt.datetime) -> str:
    """Format an aware datetime as ISO-8601 UTC with a trailing Z."""
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def summarise_energy(
    buckets: list[dict[str, Any]],
    now: dt.datetime,
    tz: dt.tzinfo,
    day_start: int,
    day_end: int,
) -> dict[str, Any]:
    """Aggregate hourly consumption into the sensor values we expose.

    "Day" is local hours day_start <= hour < day_end, "night" is the rest.
    Weekends and holidays are not treated specially.
    """
    hours = complete_hours(buckets, now)
    if not hours:
        return {}
    now_local = now.astimezone(tz)
    prev_start, this_start, _ = local_month_bounds(now_local)
    yesterday = (now_local - dt.timedelta(days=1)).date()

    today = now_local.date()
    out: dict[str, Any] = {
        "energy_last_hour": hours[-1]["import"],
        # One entry per complete local hour today, for charts (e.g. ApexCharts).
        "consumption_today": [
            {
                "start": _iso_z(b["start"]),
                "end": _iso_z(b["end"]),
                "kwh": b["import"],
            }
            for b in hours
            if b["start"].astimezone(tz).date() == today
        ],
    }
    yesterday_sum = month_day = month_night = last_month = 0.0
    have_yesterday = have_month = have_last = False
    for bucket in hours:
        local = bucket["start"].astimezone(tz)
        value = bucket["import"]
        if local.date() == yesterday:
            yesterday_sum += value
            have_yesterday = True
        if (local.year, local.month) == (this_start.year, this_start.month):
            have_month = True
            if day_start <= local.hour < day_end:
                month_day += value
            else:
                month_night += value
        elif (local.year, local.month) == (prev_start.year, prev_start.month):
            last_month += value
            have_last = True
    if have_yesterday:
        out["energy_yesterday"] = yesterday_sum
    if have_month:
        out["energy_day_month"] = month_day
        out["energy_night_month"] = month_night
    if have_last:
        out["energy_last_month"] = last_month
    return out


def _capacity_threshold(
    best: dict[dt.date, dict[str, Any]], today: dt.date, count: int
) -> float:
    """What an hour today must exceed to raise the capacity average.

    Today's own peak counts once: if it is already among the top days, any
    hour above it raises the average; otherwise an hour must beat the
    ``count``-th highest peak of the other days.
    """
    today_kw = best[today]["kw"] if today in best else 0.0
    others = sorted((p["kw"] for d, p in best.items() if d != today), reverse=True)
    if len(others) < count:
        return today_kw
    return max(today_kw, others[count - 1])


def capacity_peaks(
    buckets: list[dict[str, Any]], now: dt.datetime, tz: dt.tzinfo, count: int = 3
) -> dict[str, Any]:
    """Estimate the capacity basis from hourly consumption.

    Finnas Kraftlag's tariff (2026): the tier is set by the average of the
    three highest hourly consumptions on three different days in the billing
    month. An hour's kWh equals its average kW. For each local day the
    highest hour is found, then the ``count`` highest of those day peaks are
    averaged. Amperium's own value (gridRent.capacityChargeAveragePower) stays
    the authority; this shows which hours are the peaks and what a new day
    must beat to enter the top three.
    """
    now_local = now.astimezone(tz)
    _, this_start, _ = local_month_bounds(now_local)
    best: dict[dt.date, dict[str, Any]] = {}
    for bucket in complete_hours(buckets, now):
        local = bucket["start"].astimezone(tz)
        if (local.year, local.month) != (this_start.year, this_start.month):
            continue
        day = local.date()
        current = best.get(day)
        if current is None or bucket["import"] > current["kw"]:
            best[day] = {
                "date": day.isoformat(),
                "hour_start": _iso_z(bucket["start"]),
                "kw": bucket["import"],
            }
    if not best:
        return {}
    ranked = sorted(best.values(), key=lambda p: p["kw"], reverse=True)[:count]
    return {
        "capacity_calc_kw": sum(p["kw"] for p in ranked) / len(ranked),
        # What a new day's peak must exceed to enter the top three (0 while
        # fewer than three days have data).
        "capacity_threshold_kw": _capacity_threshold(best, now_local.date(), count),
        "capacity_peaks": ranked,
        "capacity_peak_days": len(best),
    }


def summarise_charges(
    buckets: list[dict[str, Any]], now: dt.datetime, tz: dt.tzinfo
) -> dict[str, Any]:
    """Aggregate hourly charges: yesterday's cost and this month's support."""
    hours = complete_hours(buckets, now)
    if not hours:
        return {}
    now_local = now.astimezone(tz)
    prev_start, this_start, _ = local_month_bounds(now_local)
    yesterday = (now_local - dt.timedelta(days=1)).date()

    out: dict[str, Any] = {}
    cost = gross = tax = norgespris = 0.0
    last_gross = last_tax = last_norgespris = 0.0
    have_cost = have_month = have_last = False
    for bucket in hours:
        local = bucket["start"].astimezone(tz)
        if local.date() == yesterday:
            cost += bucket["energy"]
            have_cost = True
        if (local.year, local.month) == (this_start.year, this_start.month):
            gross += bucket["energy"]
            tax += bucket["tax"]
            norgespris += bucket["norgespris"]
            have_month = True
        elif (local.year, local.month) == (prev_start.year, prev_start.month):
            last_gross += bucket["energy"]
            last_tax += bucket["tax"]
            last_norgespris += bucket["norgespris"]
            have_last = True
    if have_cost:
        out["cost_yesterday"] = cost
    if have_month:
        out["energy_gross_month"] = gross
        out["vat_month"] = tax
        out["norgespris_month"] = norgespris
    if have_last:
        out["energy_gross_last_month"] = last_gross
        out["vat_last_month"] = last_tax
        out["norgespris_last_month"] = last_norgespris
    return out


def summarise_grid(
    resp: dict[str, Any] | None, suffix: str = ""
) -> dict[str, Any]:
    """Turn the charges response's grid/fixed/capacity parts into sensor values.

    ``suffix`` is "" for this month and "_last_month" for the previous one.
    """
    if not resp or not resp.get("grid"):
        return {}
    grid = resp["grid"]
    out: dict[str, Any] = {
        f"grid_total{suffix}": grid["total"],
        f"grid_compensation{suffix}": grid["compensation"],
        f"fixed_total{suffix}": resp.get("fixed_total"),
        f"capacity_avg_kw{suffix}": grid["capacity_avg_kw"],
        f"capacity_amount{suffix}": grid["capacity_amount"],
        f"grid_breakdown{suffix}": {
            "capacity_charge": grid["capacity_amount"],
            "energy_day": grid["energy_day"],
            "energy_night": grid["energy_night"],
            "electricity_fee": grid["electricity_fee"],
            "enova_fee": grid["enova_fee"],
            "membership_discount": grid["membership_discount"],
            "subsidy_applied": subsidy_applied(grid["compensation"]),
            "vat_included": grid["sales_tax"],
        },
    }
    out.update(_capacity_tier(grid, resp.get("capacity_intervals") or [], suffix))
    out[f"grid_energy_day_kwh{suffix}"] = grid.get("energy_day_kwh")
    out[f"grid_energy_night_kwh{suffix}"] = grid.get("energy_night_kwh")
    if suffix == "_last_month":
        # Month-level figures for the previous month come from this response;
        # /api/sites only reports the current month.
        outer, total = resp.get("outer_total"), grid["total"]
        out["cost_last_month"] = outer
        out["cost_grid_rent_last_month"] = total
        out["cost_energy_last_month"] = (
            outer - total if outer is not None and total is not None else None
        )
    return out


def _capacity_tier(
    grid: dict[str, Any], intervals: list[dict[str, Any]], suffix: str
) -> dict[str, Any]:
    """Describe the current capacity tier and the distance to the next one."""
    avg, tier_min, tier_max = (
        grid["capacity_avg_kw"], grid["capacity_min_kw"], grid["capacity_max_kw"]
    )
    ordered = sorted(
        (i for i in intervals if i.get("min") is not None), key=lambda i: i["min"]
    )
    next_tier = None
    for index, tier in enumerate(ordered):
        if tier["min"] == tier_min and index + 1 < len(ordered):
            next_tier = ordered[index + 1]
            break
    headroom = None
    if avg is not None and tier_max is not None:
        headroom = tier_max - avg
    return {
        f"capacity_headroom_kw{suffix}": headroom,
        f"capacity_details{suffix}": {
            "tier_from_kw": tier_min,
            "tier_to_kw": tier_max,
            "tier_amount": grid["capacity_amount"],
            "next_tier_from_kw": next_tier["min"] if next_tier else None,
            "next_tier_amount": next_tier["amount"] if next_tier else None,
            "extra_cost_next_tier": (
                next_tier["amount"] - grid["capacity_amount"]
                if next_tier
                and next_tier["amount"] is not None
                and grid["capacity_amount"] is not None
                else None
            ),
            "tiers": [
                {"from_kw": t["min"], "to_kw": t["max"], "amount": t["amount"]}
                for t in ordered
            ],
        },
    }


def subsidy_applied(compensation: Any) -> float | None:
    """The straumstotte applied in the grid rent, as a positive amount.

    Amperium has been seen to report it as a positive number; an earlier
    reading suggested a negative one. It is always a deduction, so the sign
    is ignored: the magnitude is what counts.
    """
    if compensation is None:
        return None
    return abs(float(compensation))


def add_amounts(*values: Any) -> float | None:
    """Sum amounts; None if any of them is missing."""
    if any(v is None for v in values):
        return None
    return sum(float(v) for v in values)


def gross_grid_rent(grid_total: Any, compensation: Any) -> float | None:
    """Grid rent (incl. capacity charge) BEFORE straumstotte.

    gridRent.totalAmount is after the subsidy, so the subsidy is added back:
    gross = total + |compensation| (sign-independent, see subsidy_applied).
    """
    if grid_total is None or compensation is None:
        return None
    return float(grid_total) + abs(float(compensation))


def gross_grid_from_net(
    grid_after: Any, compensation: Any, fallback_total: Any = None
) -> float | None:
    """This month's grid rent BEFORE subsidy, built on the figure shown as "after".

    "After" comes from /api/sites (every poll) and the subsidy from the charges
    response (hourly). Adding the subsidy to the very figure that is shown as
    "after" makes "before - subsidy = after" hold exactly, whatever the age of
    the two sources. ``fallback_total`` (the charges response's own total) is
    used only while /api/sites has no figure. Last month has no /api/sites
    figure and keeps using ``gross_grid_rent``.
    """
    if grid_after is None:
        grid_after = fallback_total
    if grid_after is None or compensation is None:
        return None
    return float(grid_after) + subsidy_applied(compensation)


def gross_total_from_net(total_after: Any, compensation: Any) -> float | None:
    """This month's total BEFORE subsidy.

    = total after subsidy (/api/sites) + subsidy, so that
    "total before - subsidy = total after" holds exactly. The kraft's fixed monthly
    price is already inside the total (it is part of the energy amount), so it is
    not added again.
    """
    if compensation is None:
        return None
    return add_amounts(total_after, subsidy_applied(compensation))


def net_with_subsidy(site_total: Any) -> float | None:
    """Total cost for a customer on the regular subsidy.

    /api/sites totalAmount (energy + grid rent) is already after straumstotte
    and already holds the kraft's fixed monthly price (inside the energy amount),
    so it is the answer as it stands.
    """
    return None if site_total is None else float(site_total)


def net_with_norgespris(site_total: Any, subsidy: Any, norgespris: Any) -> float | None:
    """Total cost for a Norgespris customer.

    Start from the after-subsidy total (the kraft's fixed monthly price is already
    in it), add the straumstotte back (it does not apply on Norgespris) and
    subtract the Norgespris compensation.
    """
    if None in (site_total, subsidy, norgespris):
        return None
    return float(site_total) + float(subsidy) - float(norgespris)


def compensation_for_scheme(scheme: Any, norgespris: Any, subsidy: Any) -> float | None:
    """Return the compensation amount for the chosen scheme (None if unset)."""
    if scheme == "norgespris":
        value = norgespris
    elif scheme == "subsidy":
        value = subsidy
    else:
        return None
    return None if value is None else float(value)


def net_for_scheme(scheme: Any, site_total: Any, subsidy: Any, norgespris: Any) -> float | None:
    """Total cost for the scheme the customer has chosen."""
    if scheme == "norgespris":
        return net_with_norgespris(site_total, subsidy, norgespris)
    if scheme == "subsidy":
        return net_with_subsidy(site_total)
    return None


def house_cost(
    scheme: Any, energy_gross: Any, grid_after: Any, compensation: Any, norgespris: Any
) -> float | None:
    """The house's electricity cost for a period.

    ``energy_gross`` is the invoice's Kraft, which holds the fixed monthly price, so
    that price is in the result once. This is the number a landlord divides by the
    kWh to get an average price:
    - Norgespris: energy + grid rent BEFORE straumstotte (it does not apply on
      Norgespris, so the subsidy is added back) - the Norgespris compensation.
    - regular subsidy: energy + grid rent after straumstotte.
    ``grid_after`` is the grid rent after subsidy (gridRent.totalAmount) and
    ``compensation`` the subsidy applied against it (the sign is ignored).
    """
    if scheme == "norgespris":
        if None in (energy_gross, grid_after, compensation, norgespris):
            return None
        return (
            float(energy_gross)
            + float(grid_after)
            + subsidy_applied(compensation)
            - float(norgespris)
        )
    if scheme == "subsidy":
        return add_amounts(energy_gross, grid_after)
    return None


def price_per_kwh(cost: Any, kwh: Any) -> float | None:
    """Average price per kWh (None without a cost or with no consumption)."""
    if cost is None or kwh is None:
        return None
    try:
        if float(kwh) <= 0:
            return None
        return float(cost) / float(kwh)
    except (TypeError, ValueError):
        return None


def vat_with_fixed_price(vat: Any, energy: Any, fixed: Any) -> float | None:
    """VAT on the energy amount, including the VAT inside the fixed monthly price.

    ``vat`` and ``energy`` are the hourly VAT and gross energy sums; the fixed
    monthly price (kraft) is not in those hours but is part of the invoice's Kraft,
    with VAT at the same share of the gross amount (20 % of the gross at 25 % MVA).
    Without a fixed price or a share to derive it from, the hourly VAT is returned.
    """
    if vat is None:
        return None
    if fixed is None or not energy:
        return float(vat)
    return float(vat) + float(fixed) * float(vat) / float(energy)


MAX_PERIOD_DAYS = 100


def _period_edge(value: Any, tz: dt.tzinfo) -> tuple[dt.datetime, bool]:
    """One end of a period as an aware datetime, and whether it was a plain date."""
    if isinstance(value, dt.datetime):
        return (value if value.tzinfo else value.replace(tzinfo=tz)), False
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min, tzinfo=tz), True
    if isinstance(value, str):
        text = value.strip()
        try:
            if len(text) == 10:
                return dt.datetime.combine(dt.date.fromisoformat(text), dt.time.min, tzinfo=tz), True
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as err:
            raise ValueError(f"Cannot read '{value}' as a date or time (use 2026-09-01)") from err
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)), False
    raise ValueError(f"Cannot read {value!r} as a date or time")


def resolve_period(fra: Any, til: Any, tz: dt.tzinfo) -> tuple[dt.datetime, dt.datetime]:
    """Turn the two ends of a period into UTC instants [start, end).

    ``fra`` is included and ``til`` is NOT, so periods can follow each other without
    overlap: 2026-09-01 to 2026-10-01 is all of September. Plain dates mean 00:00
    local time on that date. A date and time (or an ISO string with a time) is
    taken exactly. Raises ValueError for unreadable input, an end that is not after
    the start, or a period longer than MAX_PERIOD_DAYS.
    """
    start, _ = _period_edge(fra, tz)
    end, _ = _period_edge(til, tz)
    if end <= start:
        raise ValueError("The period must end after it starts (the end date is not included)")
    if (end - start) > dt.timedelta(days=MAX_PERIOD_DAYS):
        raise ValueError(f"The period can be at most {MAX_PERIOD_DAYS} days")
    return start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)


def _r(value: Any, digits: int) -> float | None:
    """Round a number, pass None through."""
    return None if value is None else round(float(value), digits)


def summarise_period(
    energy: list[dict[str, Any]],
    charges: dict[str, Any] | None,
    start: dt.datetime,
    end: dt.datetime,
    now: dt.datetime,
    tz: dt.tzinfo,
) -> dict[str, Any]:
    """Cost and consumption for one free period [start, end), for a landlord's accounts.

    ``energy`` are hourly consumption buckets and ``charges`` is the answer from
    ``async_get_charges`` for the same window. The grid rent and the energy total
    are the aggregates Amperium gives for the window; the Norgespris compensation
    can only be summed from the hourly buckets. The energy total is the invoice's
    Kraft: spot price and surcharge per hour plus the kraft's fixed monthly price
    (``fixed_monthly_price``), which is part of it and not an extra. Amounts in kr,
    energy in kWh. ``warnings`` lists anything that makes the numbers less reliable.
    """
    charges = charges or {}
    warnings: list[str] = []
    cutoff = min(end, now.replace(minute=0, second=0, microsecond=0))
    expected = max(0, round((cutoff - start).total_seconds() / 3600))

    hours = [b for b in complete_hours(energy, now) if start <= b["start"] < end]
    kwh = sum(b["import"] for b in hours)
    charge_hours = [
        b for b in complete_hours(charges.get("energy") or [], now) if start <= b["start"] < end
    ]
    hourly_energy = sum(b["energy"] for b in charge_hours) if charge_hours else None
    vat_hourly = sum(b["tax"] for b in charge_hours) if charge_hours else None
    norgespris = sum(b["norgespris"] for b in charge_hours) if charge_hours else None

    grid = charges.get("grid") or {}
    grid_after = grid.get("total")
    compensation = grid.get("compensation")
    outer_total = charges.get("outer_total")
    fixed = charges.get("fixed_total")
    capacity = grid.get("capacity_amount")
    subsidy = subsidy_applied(compensation)
    grid_before = gross_grid_rent(grid_after, compensation)
    if outer_total is not None and grid_after is not None:
        energy_gross = float(outer_total) - float(grid_after)
    elif hourly_energy is not None and fixed is not None:
        energy_gross = hourly_energy + float(fixed)
    else:
        energy_gross = hourly_energy
    vat = vat_with_fixed_price(vat_hourly, hourly_energy, fixed)

    cost_norgespris = house_cost("norgespris", energy_gross, grid_after, compensation, norgespris)
    cost_subsidy = house_cost("subsidy", energy_gross, grid_after, compensation, norgespris)

    if end > now:
        warnings.append("period_not_over")
    if len(hours) < expected:
        warnings.append(f"hours_missing:{expected - len(hours)}")
    if len(charge_hours) != len(hours):
        warnings.append("charge_hours_differ_from_consumption_hours")
    if not grid:
        warnings.append("no_grid_rent_in_answer")
    if fixed is None:
        warnings.append("fixed_monthly_price_missing")
    elif (
        outer_total is not None
        and grid_after is not None
        and hourly_energy is not None
        and len(hours) == expected
        and len(charge_hours) == len(hours)
        and abs((energy_gross - hourly_energy) - float(fixed)) > 1.0
    ):
        # The total is expected to be the hours plus the fixed monthly price.
        warnings.append("fixed_monthly_price_not_in_energy_total")
    local_first = start.astimezone(tz)
    local_last = (end - dt.timedelta(seconds=1)).astimezone(tz)
    if (local_first.year, local_first.month) != (local_last.year, local_last.month):
        warnings.append("period_spans_months")

    return {
        "from": local_first.isoformat(),
        "to": end.astimezone(tz).isoformat(),
        "hours_expected": expected,
        "hours_with_data": len(hours),
        "consumption_kwh": _r(kwh, 3),
        "energy_gross": _r(energy_gross, 2),
        "energy_gross_hourly_sum": _r(hourly_energy, 2),
        "vat_on_energy": _r(vat, 2),
        "grid_before_support": _r(grid_before, 2),
        "subsidy_applied": _r(subsidy if compensation is not None else None, 2),
        "grid_after_support": _r(grid_after, 2),
        "capacity_charge": _r(capacity, 2),
        "capacity_basis_kw": _r(grid.get("capacity_avg_kw"), 3),
        "grid_before_support_excl_capacity": _r(
            None if grid_before is None or capacity is None else grid_before - float(capacity), 2
        ),
        "fixed_monthly_price": _r(fixed, 2),
        "norgespris_compensation": _r(norgespris, 2),
        "house_cost_norgespris": _r(cost_norgespris, 2),
        "house_cost_subsidy": _r(cost_subsidy, 2),
        "price_per_kwh_norgespris": _r(price_per_kwh(cost_norgespris, kwh), 4),
        "price_per_kwh_subsidy": _r(price_per_kwh(cost_subsidy, kwh), 4),
        "warnings": warnings,
    }


def compensation_difference(norgespris: Any, subsidy: Any) -> float | None:
    """How much more Norgespris compensates than the regular subsidy."""
    if norgespris is None or subsidy is None:
        return None
    return float(norgespris) - float(subsidy)


def build_hourly_statistics(
    buckets: list[dict[str, Any]], key: str, base_sum: float, now: dt.datetime
) -> list[dict[str, Any]]:
    """Turn hourly buckets into cumulative statistics rows.

    Each row's sum continues from base_sum (the sum of the last row that was
    stored before the first bucket), so re-importing an overlapping window
    keeps the chain consistent.
    """
    rows = []
    running = base_sum
    for bucket in complete_hours(buckets, now):
        running += bucket[key]
        rows.append({"start": bucket["start"], "state": running, "sum": running})
    return rows
