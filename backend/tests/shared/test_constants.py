"""Shared constants match the spine and load without Django."""

import os
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from shared.constants import (
    CONFLICT_MIN_OVERLAP,
    DEFAULT_REMINDER_PLAN,
    EXTRACTION_CONFIDENCE_PUBLISH,
    EXTRACTION_CONFIDENCE_REJECT,
    REMINDER_SLOT_OFFSET,
    SEND_KEY_SEPARATOR,
    TZ_INFERENCE_CONFIDENCE_DIGEST,
    ReminderSlot,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_confidence_gates_match_spine():
    assert EXTRACTION_CONFIDENCE_REJECT == Decimal("0.5")
    assert EXTRACTION_CONFIDENCE_PUBLISH == Decimal("0.7")
    assert TZ_INFERENCE_CONFIDENCE_DIGEST == Decimal("0.7")


def test_default_reminder_plan_is_one_day_plus_one_hour():
    assert DEFAULT_REMINDER_PLAN == (ReminderSlot.ONE_DAY, ReminderSlot.ONE_HOUR)
    assert [str(slot) for slot in DEFAULT_REMINDER_PLAN] == ["1d", "1hr"]


def test_every_slot_has_an_offset():
    assert REMINDER_SLOT_OFFSET == {
        ReminderSlot.FIVE_DAYS: timedelta(days=5),
        ReminderSlot.TWO_DAYS: timedelta(days=2),
        ReminderSlot.ONE_DAY: timedelta(days=1),
        ReminderSlot.ONE_HOUR: timedelta(hours=1),
    }


def test_conflict_overlap_and_send_key_separator():
    assert CONFLICT_MIN_OVERLAP == timedelta(minutes=15)
    assert SEND_KEY_SEPARATOR == ":"


def test_constants_and_ids_import_without_django():
    code = (
        "import sys, shared.constants, shared.ids\n"
        "leaked = [m for m in sys.modules if m == 'django' or m.startswith('django.')]\n"
        "sys.exit('loaded Django: ' + ', '.join(leaked[:5]) if leaked else 0)\n"
    )
    env = {key: value for key, value in os.environ.items() if key != "DJANGO_SETTINGS_MODULE"}

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
