"""Tests that pin the settings other behaviour depends on."""
from __future__ import annotations

from conftest import const


def test_down_means_15_minutes_by_default():
    assert const.LIVE_DOWN_AFTER_SECONDS == 900
    assert const.LIVE_DOWN_AFTER_SECONDS > const.LIVE_MAX_AGE_SECONDS            # unknown comes first


def test_han_status_is_read_every_5_minutes_and_the_main_poll_is_unchanged():
    assert const.HAN_STATUS_INTERVAL == 300
    assert const.DEFAULT_SCAN_INTERVAL == 900


def test_the_missing_hours_settings():
    assert const.MISSING_HOURS_GRACE == 2 and const.MISSING_HOURS_LISTED == 48
