"""Formats: the one implementation of each file format more than one consumer parses.

A format is not an adapter (it does no I/O) and not a domain rule (it has no identity
policy). It sits below `apps` and `adapters`, above `ports`, `domain` and `shared`.

The reason this layer exists is the **ICS parser**: the catalog pipeline parses ICS
sources, and the calendar adapter parses a user's ICS calendar. Two implementations
would be two places for the same bug, and they would drift. So there is one, here, and
the `single-ics-parser` import contract fails the build if any module outside
`formats.ics` imports the `icalendar` library.

**No Django, no database, no network.** A format is a pure function from bytes to
values. `tests/architecture/test_formats_pure.py` pins that.
"""
