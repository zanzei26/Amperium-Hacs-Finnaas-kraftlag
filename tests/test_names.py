"""The names of the sensors and of the actions: they follow the invoice, and the three
translation files say the same things (checked without Home Assistant)."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parent.parent / "custom_components" / "amperium"
FILES = {
    "strings": PKG / "strings.json",
    "nb": PKG / "translations" / "nb.json",
    "en": PKG / "translations" / "en.json",
}

# Words from before 0.14.0 that the invoice does not use. A name with one of them is a regression.
OLD_WORDS = ("fastledd", "netto kostnad", "energikostnad", "uten fastledd", "inkl. fastledd", "din ordning")


def _load(name: str) -> dict:
    return json.loads(FILES[name].read_text(encoding="utf-8"))


def _names(data: dict) -> dict[tuple[str, str], str]:
    return {
        (platform, key): entity["name"]
        for platform, entities in data["entity"].items()
        for key, entity in entities.items()
    }


def _renamed_keys() -> frozenset[str]:
    """RENAMED_KEYS in naming.py, read from the source (the module needs Home Assistant)."""
    tree = ast.parse((PKG / "naming.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "RENAMED_KEYS" for t in node.targets
        ):
            call = node.value
            assert isinstance(call, ast.Call)
            return frozenset(ast.literal_eval(call.args[0]))
    raise AssertionError("RENAMED_KEYS not found in naming.py")


def test_the_three_files_name_the_same_entities_and_actions():
    nb, en, strings = _load("nb"), _load("en"), _load("strings")
    assert set(_names(nb)) == set(_names(en)) == set(_names(strings))
    assert set(nb["services"]) == set(en["services"]) == set(strings["services"])
    for service in nb["services"]:
        assert set(nb["services"][service].get("fields", {})) == set(
            en["services"][service].get("fields", {})
        )


def test_english_names_are_the_same_in_strings_and_en():
    assert _names(_load("strings")) == _names(_load("en"))


def test_every_action_in_services_yaml_is_described_in_the_translations():
    text = (PKG / "services.yaml").read_text(encoding="utf-8")
    actions = set(re.findall(r"^([a-z_]+):\s*$", text, flags=re.MULTILINE))
    assert actions == set(_load("nb")["services"])


def test_no_name_uses_a_word_the_invoice_does_not_use():
    for platform_key, name in _names(_load("nb")).items():
        lowered = name.lower()
        for word in OLD_WORDS:
            assert word not in lowered, f"{platform_key}: «{name}» contains «{word}»"


def test_the_renamed_keys_are_all_sensors_that_exist():
    sensors = {key for platform, key in _names(_load("nb")) if platform == "sensor"}
    assert _renamed_keys() <= sensors


def test_names_are_unique_within_the_integration():
    names = list(_names(_load("nb")).values())
    assert len(names) == len(set(names))


@pytest.mark.parametrize(
    ("key", "name"),
    [
        ("cost_energy", "Kraft denne måneden"),
        ("cost_energy_last_month", "Kraft forrige måned"),
        ("fixed_month", "Fast månedspris denne måneden"),
        ("grid_gross_month", "Nettleie før straumstøtte denne måneden"),
        ("cost_grid_rent", "Nettleie etter straumstøtte denne måneden"),
        ("subsidy_applied_month", "Straumstøtte denne måneden"),
        ("norgespris_month", "Norgespris denne måneden"),
        ("net_cost_last_month", "Totalt forrige måned"),
        ("net_norgespris_month", "Totalt denne måneden med Norgespris"),
        ("net_subsidy_month", "Totalt denne måneden med straumstøtte"),
    ],
)
def test_the_main_names_are_the_words_of_the_invoice(key, name):
    assert _names(_load("nb"))[("sensor", key)] == name


def test_the_live_feed_is_marked_experimental_wherever_the_user_meets_it():
    nb = _load("nb")
    names = _names(nb)
    assert "eksperimentell" in names[("sensor", "amperium_live_power")].lower()
    assert "eksperimentell" in names[("sensor", "amperium_live_status")].lower()
    assert "eksperimentell" in nb["options"]["step"]["init"]["data"]["has_dobbe"].lower()
