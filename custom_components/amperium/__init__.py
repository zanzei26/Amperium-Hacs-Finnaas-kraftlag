"""The Amperium integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .api import AmperiumAuthError, AmperiumError
from .const import CONF_SCHEME, CONF_SITE_ID, DOMAIN
from .coordinator import AmperiumCoordinator
from .derived import resolve_period
from .period import async_period_summary

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

AmperiumConfigEntry = ConfigEntry[AmperiumCoordinator]

SERVICE_PERIOD = "hent_periode"
SERVICE_PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required("fra"): cv.string,
        vol.Required("til"): cv.string,
        vol.Optional("entry_id"): cv.string,
    }
)


async def _async_handle_period(call: ServiceCall) -> ServiceResponse:
    """Cost and consumption for a free period, as response data."""
    hass = call.hass
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get("entry_id")
    if wanted:
        entries = [entry for entry in entries if entry.entry_id == wanted]
    if not entries:
        raise ServiceValidationError("Ingen Amperium-oppføring er lastet")
    if len(entries) > 1:
        raise ServiceValidationError("Flere Amperium-oppføringer: velg en med entry_id")
    entry = entries[0]
    tz = dt_util.DEFAULT_TIME_ZONE
    try:
        start, end = resolve_period(call.data["fra"], call.data["til"], tz)
    except ValueError as err:
        raise ServiceValidationError(str(err)) from err
    try:
        return await async_period_summary(
            entry.runtime_data.client,
            entry.data[CONF_SITE_ID],
            start,
            end,
            tz,
            entry.options.get(CONF_SCHEME),
        )
    except AmperiumAuthError as err:
        raise HomeAssistantError(f"Amperium: innloggingen er ikke gyldig ({err})") from err
    except AmperiumError as err:
        raise HomeAssistantError(f"Amperium: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: AmperiumConfigEntry) -> bool:
    """Set up Amperium from a config entry."""
    coordinator = AmperiumCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    if not hass.services.has_service(DOMAIN, SERVICE_PERIOD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_PERIOD,
            _async_handle_period,
            schema=SERVICE_PERIOD_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AmperiumConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        others = [
            other
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
        ]
        if not others:
            hass.services.async_remove(DOMAIN, SERVICE_PERIOD)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: AmperiumConfigEntry) -> None:
    """Reload the config entry when the options change.

    The entry is also updated whenever a refreshed token is stored; that must
    not restart the integration, so only a changed options dict reloads it.
    """
    if dict(entry.options) == entry.runtime_data.options_snapshot:
        return
    await hass.config_entries.async_reload(entry.entry_id)
