# Hand-written (ingest-pipeline-and-lifecycle-design.md D8, D11, D12, D16; run-015 plan P3).
# Runs on the `catalog` alias as the owner role, like 0001.

from importlib import import_module

import django.core.serializers.json
from django.db import migrations, models

# Existing rows get their current start as the original. The update guard rejects any UPDATE of
# a superseded row, so it is switched off for this one statement, inside the migration's
# transaction (plan P3).
BACKFILL = """
ALTER TABLE catalog.ingestion_event DISABLE TRIGGER event_guard_update;
UPDATE catalog.ingestion_event SET original_start_utc = start_time_utc;
ALTER TABLE catalog.ingestion_event ENABLE TRIGGER event_guard_update;
"""

# 0001's rules, plus: a new Event's original start is its start, and it never changes (D11).
# Keep the lifecycle column list in step with apps.ingestion.models.Event.LIFECYCLE_FIELDS.
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


def _previous_guard() -> str:
    """0001's function, restored on a local rollback (migrations are forward-only otherwise)."""
    sql = import_module("apps.ingestion.migrations.0001_initial").TRIGGERS
    start = sql.index("CREATE FUNCTION catalog.guard_event_write()")
    end = sql.index("$$;", start) + len("$$;")
    return sql[start:end].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="original_start_utc",
            field=models.DateTimeField(null=True),
        ),
        migrations.RunSQL(BACKFILL, reverse_sql=migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="event",
            name="original_start_utc",
            field=models.DateTimeField(),
        ),
        migrations.RunSQL(GUARD_EVENT_WRITE, reverse_sql=_previous_guard()),
        migrations.AddField(
            model_name="extractedrecord",
            name="match_notes",
            field=models.JSONField(
                blank=True,
                default=dict,
                encoder=django.core.serializers.json.DjangoJSONEncoder,
            ),
        ),
        migrations.AddField(
            model_name="source",
            name="fetched_url",
            field=models.URLField(blank=True, max_length=2048),
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
                ],
                max_length=16,
            ),
        ),
    ]
