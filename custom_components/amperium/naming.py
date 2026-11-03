"""Names that follow the invoice, and the move of old entity ids to them (0.14.0).

An entity id is fixed when the entity is first created, so an installation made before 0.14.0
keeps ids like ``..._energikostnad_brutto_denne_maneden`` although the entity is now called
"Kraft denne måneden". The action ``amperium.oppdater_navn`` gives those entities the id Home
Assistant would give them on a new installation. It only shows the plan unless it is told to do
it, because anything that mentions the old ids (templates, automations, dashboards) has to be
updated at the same time.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

# The translation keys of the entities whose name changed in 0.14.0 (see translations/nb.json).
RENAMED_KEYS = frozenset(
    {
        "cost_energy", "cost_energy_last_month", "energy_gross_month", "cost_yesterday",
        "fixed_month", "fixed_last_month", "vat_month",
        "grid_gross_month", "grid_gross_last_month", "cost_grid_rent", "cost_grid_rent_last_month",
        "subsidy_applied_month", "subsidy_applied_last_month",
        "norgespris_month", "norgespris_last_month", "compensation_month",
        "net_cost_last_month", "net_cost_month", "net_norgespris_month", "net_subsidy_month",
        "gross_total_month", "cost_total", "cost_last_month",
        "avg_price_month", "avg_price_last_month",
        "amperium_live_power", "amperium_live_status",
    }
)

STATUS_RENAME = "bytte"            # planned
STATUS_DONE = "byttet"
STATUS_SAME = "uendret"            # already has the new id
STATUS_TAKEN = "finnes_allerede"   # another entity has the new id
STATUS_OWN_NAME = "eget_navn"      # the user named it, so it is left alone
STATUS_FAILED = "feilet"


def plan_renames(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, Any]]:
    """What each renamed entity of the entry would be called, and what would happen to it.

    ``nokkel`` is the sensor's key (the part of its unique id after the entry id), which says
    which sensor an old entity id belongs to without guessing from the id.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    taken = {e.entity_id for e in ent_reg.entities.values()} | set(hass.states.async_entity_ids())
    prefix = f"{entry.entry_id}_"
    rows: list[dict[str, Any]] = []
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        unique_id = entity.unique_id or ""
        key = unique_id[len(prefix):] if unique_id.startswith(prefix) else ""
        if key not in RENAMED_KEYS:
            continue
        device = dev_reg.async_get(entity.device_id) if entity.device_id else None
        device_name = (device.name_by_user or device.name) if device else ""
        # The same rule Home Assistant uses for a new entity: device name + entity name.
        wanted = f"{entity.domain}.{slugify(f'{device_name} {entity.original_name or ''}'.strip())}"
        row: dict[str, Any] = {"nokkel": key, "fra": entity.entity_id, "til": wanted}
        if entity.name:
            row["status"] = STATUS_OWN_NAME
        elif wanted == entity.entity_id:
            row["status"] = STATUS_SAME
        elif wanted in taken:
            row["status"] = STATUS_TAKEN
        else:
            row["status"] = STATUS_RENAME
            taken.add(wanted)  # two entities must not be planned onto the same id
        rows.append(row)
    return sorted(rows, key=lambda r: r["fra"])


def apply_renames(hass: HomeAssistant, rows: list[dict[str, Any]]) -> None:
    """Carry out the planned renames; each row gets its outcome in ``status``."""
    ent_reg = er.async_get(hass)
    for row in rows:
        if row["status"] != STATUS_RENAME:
            continue
        try:
            ent_reg.async_update_entity(row["fra"], new_entity_id=row["til"])
        except ValueError as err:  # for example an id that became taken a moment ago
            row["status"] = STATUS_FAILED
            row["feil"] = str(err)
            continue
        row["status"] = STATUS_DONE
    done = sum(1 for row in rows if row["status"] == STATUS_DONE)
    _LOGGER.warning(
        "amperium.oppdater_navn: %d entity id(s) changed. Templates, automations and dashboards "
        "that mention the old ids must use the new ones",
        done,
    )
