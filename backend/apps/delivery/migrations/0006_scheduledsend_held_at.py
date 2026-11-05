"""AD-17's propagation hold: a nullable `held_at` on `ScheduledSend`.

**Additive, nullable, no default, no backfill.** The sweep claims from this table
continuously, so the migration must not rewrite it: adding a nullable column with no
default is a catalogue-only change in PostgreSQL and takes no table lock worth the name.

Every existing row is correctly `held_at = NULL` — nothing was ever held before this
column existed.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("delivery", "0005_scheduledsend_slot_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledsend",
            name="held_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
