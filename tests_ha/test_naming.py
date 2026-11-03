"""Names after the invoice (0.14.0), and the action amperium.oppdater_navn that moves the ids of
an installation made before to the ones a new installation gets."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from ha_helpers import entity_id, make_entry, setup_entry
from homeassistant.helpers import entity_registry as er

from custom_components.amperium import naming
from custom_components.amperium.amqp_feed import AmperiumLiveFeed
from custom_components.amperium.const import DOMAIN

PREFIX = "sensor.amperium_testveien_1_"


@pytest.fixture(autouse=True)
def _norwegian(hass):
    """Entity ids are made from the names in Home Assistant's language; the invoice is Norwegian."""
    hass.config.language = "nb"

# Invented ids of the kind an installation from before 0.14.0 has (one per old naming).
OLD = {
    "cost_energy": PREFIX + "energikostnad_brutto_denne_maneden",
    "fixed_month": PREFIX + "fastledd_denne_maneden",
    "net_cost_last_month": PREFIX + "netto_kostnad_forrige_maned_din_ordning_inkl_fastledd",
}
NEW = {
    "cost_energy": PREFIX + "kraft_denne_maneden",
    "fixed_month": PREFIX + "fast_manedspris_denne_maneden",
    "net_cost_last_month": PREFIX + "totalt_forrige_maned",
}


async def call(hass, data=None):
    return await hass.services.async_call(
        DOMAIN, "oppdater_navn", data or {}, blocking=True, return_response=True
    )


def _register_old_ids(hass, entry) -> None:
    """Entities as an old installation has them: the unique id is the same, the entity id older."""
    registry = er.async_get(hass)
    for key, old in OLD.items():
        registry.async_get_or_create(
            "sensor", DOMAIN, f"{entry.entry_id}_{key}", config_entry=entry,
            suggested_object_id=old.split(".", 1)[1],
        )


async def _old_installation(hass):
    entry = make_entry()
    entry.add_to_hass(hass)
    _register_old_ids(hass, entry)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_new_installation_gets_ids_from_the_invoice_names(hass, api):
    entry = await setup_entry(hass, make_entry())
    for key, wanted in NEW.items():
        assert entity_id(hass, entry, key) == wanted
        assert hass.states.get(wanted) is not None
    assert entity_id(hass, entry, "energy_month") == PREFIX + "forbruk_denne_maneden"


async def test_on_a_new_installation_there_is_nothing_to_change(hass, api):
    # With the live feed on, so that the two live sensors are there too.
    async def never_started(self):
        return None

    with patch.object(AmperiumLiveFeed, "run", never_started):
        entry = await setup_entry(hass, make_entry(dobbe=True))
    out = await call(hass)
    assert out["antall_bytte"] == 0
    listed = {row["fra"] for row in out["endringer"]}
    for key in ("cost_energy", "amperium_live_power", "amperium_live_status"):
        assert entity_id(hass, entry, key) in listed
    assert {row["status"] for row in out["endringer"]} == {naming.STATUS_SAME}
    assert all(row["fra"] == row["til"] for row in out["endringer"])


async def test_an_old_installation_keeps_its_ids_and_the_action_only_shows_the_plan(hass, api):
    entry = await _old_installation(hass)
    for key, old in OLD.items():
        assert entity_id(hass, entry, key) == old        # the platform does not rename by itself
    out = await call(hass)                                # no arguments: only show
    assert out["kun_vis"] is True
    assert out["antall_bytte"] == len(OLD)
    plan = {row["fra"]: (row["til"], row["status"], row["nokkel"]) for row in out["endringer"]}
    for key, old in OLD.items():
        assert plan[old] == (NEW[key], naming.STATUS_RENAME, key)   # nokkel: which sensor it is
    # Nothing was touched.
    for key, old in OLD.items():
        assert entity_id(hass, entry, key) == old
        assert hass.states.get(old) is not None
        assert hass.states.get(NEW[key]) is None


async def test_the_action_moves_the_ids_when_asked_and_keeps_state_and_unique_id(hass, api):
    entry = await _old_installation(hass)
    registry = er.async_get(hass)
    before = {key: hass.states.get(old).state for key, old in OLD.items()}
    out = await call(hass, {"kun_vis": False})
    await hass.async_block_till_done()
    assert out["kun_vis"] is False
    done = {row["fra"]: row["status"] for row in out["endringer"] if row["fra"] in OLD.values()}
    assert set(done.values()) == {naming.STATUS_DONE}
    for key, old in OLD.items():
        assert entity_id(hass, entry, key) == NEW[key]
        assert hass.states.get(old) is None               # the old id is gone
        assert hass.states.get(NEW[key]).state == before[key]  # same value under the new id
        entity = registry.async_get(NEW[key])
        assert entity.unique_id == f"{entry.entry_id}_{key}"   # statistics and history follow this


async def test_running_the_action_again_changes_nothing(hass, api):
    await _old_installation(hass)
    await call(hass, {"kun_vis": False})
    await hass.async_block_till_done()
    out = await call(hass, {"kun_vis": False})
    assert out["antall_bytte"] == 0
    assert {row["status"] for row in out["endringer"]} == {naming.STATUS_SAME}


async def test_an_id_that_another_entity_has_is_not_taken_over(hass, api):
    entry = await _old_installation(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", "someone_else", "x", suggested_object_id=NEW["cost_energy"].split(".", 1)[1]
    )
    out = await call(hass, {"kun_vis": False})
    await hass.async_block_till_done()
    status = {row["fra"]: row["status"] for row in out["endringer"]}
    assert status[OLD["cost_energy"]] == naming.STATUS_TAKEN
    assert entity_id(hass, entry, "cost_energy") == OLD["cost_energy"]    # left as it was
    assert status[OLD["fixed_month"]] == naming.STATUS_DONE               # the others still move
    assert entity_id(hass, entry, "fixed_month") == NEW["fixed_month"]


async def test_a_sensor_the_user_has_named_is_left_alone(hass, api):
    entry = await _old_installation(hass)
    registry = er.async_get(hass)
    registry.async_update_entity(OLD["fixed_month"], name="Min egen fastpris")
    await hass.async_block_till_done()
    out = await call(hass, {"kun_vis": False})
    await hass.async_block_till_done()
    status = {row["fra"]: row["status"] for row in out["endringer"]}
    assert status[OLD["fixed_month"]] == naming.STATUS_OWN_NAME
    assert entity_id(hass, entry, "fixed_month") == OLD["fixed_month"]
    assert registry.async_get(OLD["fixed_month"]).name == "Min egen fastpris"


async def test_only_the_renamed_sensors_are_in_the_plan(hass, api):
    entry = await _old_installation(hass)
    out = await call(hass)
    listed = {row["fra"] for row in out["endringer"]}
    assert entity_id(hass, entry, "energy_month") not in listed       # its name did not change
    assert entity_id(hass, entry, "han_online", "binary_sensor") not in listed


async def test_the_action_names_the_warning_in_the_log(hass, api, caplog):
    await _old_installation(hass)
    await call(hass, {"kun_vis": False})
    assert "amperium.oppdater_navn: 3 entity id(s) changed" in caplog.text
