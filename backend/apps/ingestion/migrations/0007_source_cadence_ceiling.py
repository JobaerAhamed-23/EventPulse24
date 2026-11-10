"""FR-53: a source's cadence may not exceed its tier's ceiling, and existing rows are brought
within it by this migration rather than by hand.

**The order matters, and it is not cosmetic.** `AddConstraint` on a check constraint
*validates the existing rows* — PostgreSQL refuses to add a constraint that existing data
violates. So the clamping runs first and the constraint is added second. Reversed, the
migration would fail on exactly the rows it is meant to fix.

**The clamp, not a refusal.** A migration cannot refuse: the rows exist, and the schema
must end up legal. A source whose cadence is above its tier's ceiling is brought *down* to
the ceiling — never up, and never touched if it is already legal.

**The reverse does not restore the clamped values.** It cannot: it does not know them. The
reverse drops the constraint and leaves the clamped cadences as they are, which is stated
here because a reverse migration that silently loses data is worse than one that says what
it does.
"""

from django.db import migrations, models

import shared.constants


def clamp_source_cadences(apps, schema_editor):
    """Bring every source's cadence within its tier's ceiling (FR-53).

    **The tier is derived, exactly as the application derives it** — from the acquisition
    method, via the same rule. The migration does not import the application's
    `cadence_ceiling`, because a migration must keep working when that function changes:
    a migration that imports live application code is a migration whose behaviour depends on
    the day it is run. So the rule is restated here, against the same constants, and the
    constants are what tie the two together.
    """
    Source = apps.get_model("ingestion", "Source")
    high = shared.constants.HIGH_PRIORITY_METHODS
    high_max = shared.constants.HIGH_PRIORITY_CADENCE_MAX
    low_max = shared.constants.LOW_PRIORITY_CADENCE_MAX

    clamped = 0
    for source in Source.objects.all().iterator():
        ceiling = high_max if source.acquisition_method in high else low_max
        if source.ingestion_cadence > ceiling:
            Source.objects.filter(pk=source.pk).update(ingestion_cadence=ceiling)
            clamped += 1
    if clamped:
        print(f"FR-53: clamped {clamped} source cadence(s) to their tier's ceiling.")


def unconstraint_source_cadences(apps, schema_editor):
    """Drop the ceiling constraint. **The clamped cadences stay clamped.**

    The reverse cannot restore the original values — it does not know them, and guessing
    would be worse than leaving them. The clamped cadence is a legal cadence under the tier
    it is in, so the schema remains valid without the constraint.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("ingestion", "0006_revalidationrequest"),
    ]

    operations = [
        migrations.RunPython(clamp_source_cadences, unconstraint_source_cadences),
        migrations.AddConstraint(
            model_name="source",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("acquisition_method__in", shared.constants.HIGH_PRIORITY_METHODS),
                        ("ingestion_cadence__lte", shared.constants.HIGH_PRIORITY_CADENCE_MAX),
                    )
                    | (
                        ~models.Q(
                            ("acquisition_method__in", shared.constants.HIGH_PRIORITY_METHODS)
                        )
                        & models.Q(
                            ("ingestion_cadence__lte", shared.constants.LOW_PRIORITY_CADENCE_MAX)
                        )
                    )
                ),
                name="source_cadence_within_priority_ceiling_ck",
            ),
        ),
    ]
