# Hand-written (event-rejection-state-design.md D1, D2, D10).
# Runs on the `catalog` alias as the owner role, like 0001 and 0002.

from django.db import migrations, models

# 0002's rules, plus one: entering or leaving `rejected` needs `event_version + 1` (D2).
#
# **Why this is a boundary rule and not a lifecycle column.** The obvious move is to add
# `publication_status` to `Event.LIFECYCLE_FIELDS` and the column list below. It is wrong:
# ingestion already moves events `in_review -> published` *silently* on every re-resolution
# (`IncomingEvent.gating()`, run-015 plan P1), and that transition would suddenly demand a
# version bump and emit a state change to every saver of every event coming out of
# timezone review. So the rule fires only on the `rejected` boundary, which no ingestion
# path crosses — only `apps.ingestion.services.editorial_state` does.
#
# The bump is what makes a reject reach saved users at all: it is the version the
# `delisted` EventStateChange carries through the AD-17 outbox.
GUARD_EVENT_WRITE = """
CREATE OR REPLACE FUNCTION catalog.guard_event_write() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.event_version <> 1 OR NEW.status = 'superseded' THEN
      RAISE EXCEPTION 'a new Event starts at event_version 1 and is not superseded'
        USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.original_start_utc IS DISTINCT FROM NEW.start_time_utc THEN
      RAISE EXCEPTION 'a new Event''s original_start_utc is its start_time_utc'
        USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'superseded' THEN
    RAISE EXCEPTION 'superseded Event % is terminal', OLD.id USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.original_start_utc IS DISTINCT FROM OLD.original_start_utc THEN
    RAISE EXCEPTION 'original_start_utc of Event % never changes', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.event_version NOT IN (OLD.event_version, OLD.event_version + 1) THEN
    RAISE EXCEPTION 'event_version may only stay or rise by 1 (% -> %)',
      OLD.event_version, NEW.event_version USING ERRCODE = 'restrict_violation';
  END IF;
  IF (OLD.publication_status = 'rejected') IS DISTINCT FROM (NEW.publication_status = 'rejected')
     AND NEW.event_version <> OLD.event_version + 1 THEN
    RAISE EXCEPTION 'entering or leaving rejected needs event_version + 1 on Event %', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.event_version = OLD.event_version AND (
       NEW.start_time_utc IS DISTINCT FROM OLD.start_time_utc
    OR NEW.end_time_utc IS DISTINCT FROM OLD.end_time_utc
    OR NEW.start_time_tz IS DISTINCT FROM OLD.start_time_tz
    OR NEW.status IS DISTINCT FROM OLD.status
    OR NEW.is_sold_out IS DISTINCT FROM OLD.is_sold_out
    OR NEW.venue_id IS DISTINCT FROM OLD.venue_id
    OR NEW.superseded_by_id IS DISTINCT FROM OLD.superseded_by_id) THEN
    RAISE EXCEPTION 'a lifecycle change to Event % needs event_version + 1', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END
$$;
"""

# 0002's body verbatim, so a reverse lands exactly where 0002 left it.
PREVIOUS_GUARD_EVENT_WRITE = """
CREATE OR REPLACE FUNCTION catalog.guard_event_write() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.event_version <> 1 OR NEW.status = 'superseded' THEN
      RAISE EXCEPTION 'a new Event starts at event_version 1 and is not superseded'
        USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.original_start_utc IS DISTINCT FROM NEW.start_time_utc THEN
      RAISE EXCEPTION 'a new Event''s original_start_utc is its start_time_utc'
        USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'superseded' THEN
    RAISE EXCEPTION 'superseded Event % is terminal', OLD.id USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.original_start_utc IS DISTINCT FROM OLD.original_start_utc THEN
    RAISE EXCEPTION 'original_start_utc of Event % never changes', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.event_version NOT IN (OLD.event_version, OLD.event_version + 1) THEN
    RAISE EXCEPTION 'event_version may only stay or rise by 1 (% -> %)',
      OLD.event_version, NEW.event_version USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.event_version = OLD.event_version AND (
       NEW.start_time_utc IS DISTINCT FROM OLD.start_time_utc
    OR NEW.end_time_utc IS DISTINCT FROM OLD.end_time_utc
    OR NEW.start_time_tz IS DISTINCT FROM OLD.start_time_tz
    OR NEW.status IS DISTINCT FROM OLD.status
    OR NEW.is_sold_out IS DISTINCT FROM OLD.is_sold_out
    OR NEW.venue_id IS DISTINCT FROM OLD.venue_id
    OR NEW.superseded_by_id IS DISTINCT FROM OLD.superseded_by_id) THEN
    RAISE EXCEPTION 'a lifecycle change to Event % needs event_version + 1', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0008_reviewitem"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="publication_status",
            field=models.CharField(
                choices=[
                    ("published", "Published"),
                    ("in_review", "In Review"),
                    ("rejected", "Rejected"),
                ],
                default="published",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="eventstatechange",
            name="kind",
            field=models.CharField(
                choices=[
                    ("time_moved", "Time Moved"),
                    ("postponed", "Postponed"),
                    ("cancelled", "Cancelled"),
                    ("reinstated", "Reinstated"),
                    ("sold_out", "Sold Out"),
                    ("detail_changed", "Detail Changed"),
                    ("superseded", "Superseded"),
                    ("delisted", "Delisted"),
                    ("relisted", "Relisted"),
                ],
                max_length=16,
            ),
        ),
        migrations.RunSQL(GUARD_EVENT_WRITE, reverse_sql=PREVIOUS_GUARD_EVENT_WRITE),
    ]
