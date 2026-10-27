"""Local stand-in for ICS import: a small fixed calendar, the same for every feed."""

from datetime import UTC, datetime, timedelta

from ports.calendar import CalendarEntry, CalendarFeed, CalendarPort

_DAY = datetime(2026, 11, 2, tzinfo=UTC)

FAKE_ENTRIES = (
    CalendarEntry(
        uid="fake-standup@eventpulse24.local",
        title="Team stand-up",
        starts_at=_DAY + timedelta(hours=9),
        ends_at=_DAY + timedelta(hours=9, minutes=15),
        tz="Europe/London",
    ),
    CalendarEntry(
        uid="fake-dinner@eventpulse24.local",
        title="Dinner",
        starts_at=_DAY + timedelta(hours=18),
        ends_at=_DAY + timedelta(hours=20),
        tz="Asia/Dhaka",
    ),
)


class FakeCalendarAdapter(CalendarPort):
    def fetch_entries(self, feed: CalendarFeed) -> list[CalendarEntry]:
        return list(FAKE_ENTRIES)
