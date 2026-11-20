"""The `city_source` vocabulary gains `seed`, for the local dev seed's fictional city.

**This migration touches no rows.** `city_source` is a `CharField` with `choices`, and
Django does not enforce choices at the database level — the database column is a
varchar either way. So this is an `AlterField` that changes the *Python-side* vocabulary
and nothing else. The existing rows keep the sources they had: `geo`, `choice`,
`fallback` or `backfill`.

**Why the vocabulary needed a fifth value.** The four it had describe how a **reader's**
city arrives: a geo header, a pick, a gap, a backfill. The local dev seed writes a
*fictional* city — "Fixtureville" — for a walk-through, and that write is none of those
four things. It is the **server** choosing a city, which is the same situation as the
fallback: there is no reader to mislead, so the value is stored verbatim.

**The item this came from.** `stored-city-is-the-picked-city` ended the silent rewrite,
and the rule it wrote is *"the stored city is the picked city"* — which holds for a
reader, and says nothing about a seed that writes a city no reader could have picked.
Rather than bend the seed's city into a real one (which would leave its venues and its
accounts' city disagreeing, and empty the Browse surface the walk-through exists to
show), the seed says which kind of writer it is.

**The reverse restores the four-value vocabulary.** It does not touch any row either,
because none was touched in the forward direction.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("personalization", "0017_dismissal_mute_cost"),
    ]

    operations = [
        migrations.AlterField(
            model_name="digestpreference",
            name="city_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("geo", "Geo"),
                    ("choice", "Choice"),
                    ("fallback", "Fallback"),
                    ("backfill", "Backfill"),
                    ("seed", "Seed"),
                ],
                max_length=16,
                null=True,
            ),
        ),
    ]
