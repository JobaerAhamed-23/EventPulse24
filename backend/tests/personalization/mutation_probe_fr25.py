#!/usr/bin/env python
"""Mutation probes for FR-25 — the "less like this" loop (run-eventpulse24-034, step 15).

Each probe applies one real bug to the implementation, runs the FR-25 tests, and checks
that at least one test fails. A probe that passes the suite means the tests don't prove
that rule, and the implementation or the test has to change.

**The probes are the point of the design.** FR-25's rules are the ones a future
refactor is most likely to break *quietly* — a threshold that drifts, a guard that
stops guarding, a filter that becomes a penalty, an expiry that stops expiring. Every
one of those changes the product's behaviour without raising an error, so the only thing
that catches them is a test that fails when they change.

**The rules each probe attacks:**

- the cluster needs three *distinct* events, not three swipes;
- the cosine threshold is 0.70, and *every* comparison must clear it;
- the window is 24 hours, measured on the span of the fresh dismissals;
- the decay halves at 60 days and expires at 180;
- the rage guard stops the third dismissal inside five seconds from counting;
- the serendipity slot is immune to clustering;
- the prompt fires *once* per cluster, and the counter resets;
- the mute *excludes* — it is a filter on the candidate set, not a score term;
- an expired mute excludes nothing;
- a chip-less event is never muted;
- another user's mute does not affect this user;
- the mute is scoped to its caller;
- the provider's vectors are paired to the texts *by index*, whatever order they
  arrive in — a vector attached to the wrong event is a wrong cluster;
- the embedding call writes a cost row, and the cost is the token count times the
  provider's price — a row of zero is a lie the dashboard would report.

Run from the repo root:
    uv run --directory backend python tests/personalization/mutation_probe_fr25.py
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

DISMISSALS = BACKEND / "apps/personalization/services/dismissals.py"
TASTE = BACKEND / "apps/personalization/services/taste_mutes.py"
COMPOSITION = BACKEND / "apps/personalization/services/digest_composition.py"
BROWSE = BACKEND / "apps/personalization/services/browse_read.py"
API = BACKEND / "apps/personalization/taste_mutes_api.py"
DISMISSAL_API = BACKEND / "apps/personalization/api.py"
VOYAGE = BACKEND / "adapters/llm/voyage.py"

TEST_FILES = [
    "tests/personalization/test_dismissal_clustering.py",
    "tests/personalization/test_category_mutes.py",
    "tests/personalization/test_category_mute_composition.py",
    "tests/personalization/test_taste_mutes_api.py",
    "tests/personalization/test_dismissals_api.py",
    "tests/adapters/test_voyage_embedding.py",
]


PROBES = [
    # ------------------------------------------------------------------ cluster
    (
        "the cluster needs only two events (the third is not required)",
        DISMISSALS,
        "    return evidence >= Decimal(FR25_CLUSTER_MIN_EVENTS)\n",
        "    return evidence >= Decimal(2)\n",
    ),
    (
        "the cosine threshold is lowered (dissimilar events cluster)",
        DISMISSALS,
        "        if similarity < FR25_CLUSTER_COSINE_THRESHOLD:\n            return False\n",
        '        if similarity < Decimal("0.10"):\n            return False\n',
    ),
    (
        "the cosine is checked against *any* pair, not each one",
        DISMISSALS,
        "        if similarity < FR25_CLUSTER_COSINE_THRESHOLD:\n            return False\n"
        "        evidence += _decayed_weight(dismissed_at=other.dismissed_at, now=now)\n",
        "        evidence += _decayed_weight(dismissed_at=other.dismissed_at, now=now)\n",
    ),
    (
        "the window is dropped (a dismissal from last week joins the cluster)",
        DISMISSALS,
        "        if span > timedelta(hours=FR25_CLUSTER_WINDOW_HOURS):\n            return False\n",
        "        if False:\n            return False\n",
    ),
    (
        "the decay is ignored (an old dismissal counts for a whole one)",
        DISMISSALS,
        "        evidence += _decayed_weight(dismissed_at=other.dismissed_at, now=now)\n",
        "        evidence += Decimal(1)\n",
    ),
    (
        "the decay never expires (a 200-day-old dismissal still counts)",
        DISMISSALS,
        "    cutoff = now - timedelta(days=FR25_DECAY_EXPIRE_DAYS)\n",
        "    cutoff = now - timedelta(days=10000)\n",
    ),
    (
        "the serendipity slot is not immune (a discovery card joins the cluster)",
        DISMISSALS,
        "        .exclude(slot=SERENDIPITY_SLOT)\n",
        "",
    ),
    (
        "a dismissal with no vector is treated as comparable (the cluster forms anyway)",
        DISMISSALS,
        "        if other_vector is None:\n            return False\n",
        "",
    ),
    # -------------------------------------------------------------- rage guard
    (
        "the rage guard is dropped (three rapid swipes count as a cluster)",
        DISMISSALS,
        "    advanced = not _is_rage_dismissal(user_id=user_id, now=now)\n",
        "    advanced = True\n",
    ),
    (
        "the rage guard's window is widened (a slow flick still counts as a rage flick)",
        DISMISSALS,
        "    window_start = now - timedelta(seconds=FR25_RAGE_GUARD_SECONDS)\n",
        "    window_start = now - timedelta(seconds=600)\n",
    ),
    # ------------------------------------------------------------------ prompt
    (
        "the prompt fires again for the same cluster (the counter does not reset)",
        DISMISSALS,
        "            EventDismissal.objects.using(PERSONAL).filter(\n"
        "                user_id=user_id, event_id__in=[row.event_id for row in candidates]\n"
        "            ).update(cluster_advanced=False)\n",
        "",
    ),
    (
        "the prompt's copy is built from the event's title (AD-9's leak)",
        DISMISSALS,
        "    label = CHIP_LABELS.get(category_key, category_key)\n",
        "    label = str(candidates[0].event_id)\n",
    ),
    (
        "the generic prompt is given a category (a mute on nothing)",
        DISMISSALS,
        "    if category_key is None:\n"
        "        return ClusterPrompt(\n"
        "            title=PROMPT_TITLE_GENERIC.format(), description=description, "
        "category_key=None\n"
        "        )\n",
        "    if category_key is None:\n"
        "        return ClusterPrompt(\n"
        '            title=PROMPT_TITLE_EXPLICIT.format(label="arts & culture"), '
        'description=description, category_key="arts_culture"\n'
        "        )\n",
    ),
    (
        "the dismissal is not scoped to its caller",
        DISMISSALS,
        "        .filter(\n            user_id=user_id,\n            cluster_advanced=True,\n",
        "        .filter(\n            cluster_advanced=True,\n",
    ),
    # ------------------------------------------------------------------- mutes
    (
        "the category mute is dropped from the digest (the filter is gone)",
        COMPOSITION,
        "        and not is_muted_by_category(chip_keys=candidate.chip_keys, "
        "muted_keys=muted_categories)\n",
        "",
    ),
    (
        "the category mute is dropped from Browse (the two surfaces disagree)",
        BROWSE,
        "        and not is_muted_by_category(chip_keys=candidate.chip_keys, "
        "muted_keys=muted_categories)\n",
        "",
    ),
    (
        "the mute is a penalty, not a filter (muted events are still shown)",
        TASTE,
        "    if not muted_keys:\n        return False\n"
        "    return bool(set(chip_keys) & muted_keys)\n",
        "    return False\n",
    ),
    (
        "an event with no chips is muted (the product decides what it is)",
        TASTE,
        "    if not muted_keys:\n        return False\n"
        "    return bool(set(chip_keys) & muted_keys)\n",
        "    if not muted_keys:\n        return True\n"
        "    return bool(set(chip_keys) & muted_keys)\n",
    ),
    (
        "an expired mute is still applied (it never lifts)",
        TASTE,
        "        if expires_at is None or expires_at > now\n",
        "        if True\n",
    ),
    (
        "the mute's expiry is computed from its creation, not from now",
        TASTE,
        "    expires_at = None if duration_days is None else now + timedelta(days=duration_days)\n",
        "    expires_at = None if duration_days is None else now + timedelta(days=1)\n",
    ),
    (
        "an unknown duration is accepted (the closed set is open)",
        TASTE,
        "    if duration_days not in FR25_MUTE_DURATIONS_DAYS:\n",
        "    if False:\n",
    ),
    (
        "the bulk reset is not scoped to the caller",
        TASTE,
        "        deleted, _ = CategoryMute.objects.using(PERSONAL)"
        ".filter(user_id=user_id).delete()\n",
        "        deleted, _ = CategoryMute.objects.using(PERSONAL).all().delete()\n",
    ),
    # ---------------------------------------------------------------------- api
    (
        "the list endpoint reads another user's mutes (the scoping is broken)",
        API,
        "    mutes = read_active_mutes(user_id=request.user.pk, now=timezone.now())\n",
        "    mutes = read_active_mutes(user_id=uuid4(), now=timezone.now())\n",
    ),
    (
        "the list endpoint drops the server's labels (it sends the raw key)",
        API,
        "                label=mute.label,\n",
        "                label=mute.category_key,\n",
    ),
    (
        "the unmute endpoint does not delete the row (it only reports success)",
        API,
        "    result = clear_category_mute(\n"
        "            user_id=request.user.pk,\n"
        "            category_key=category_key,\n"
        "            actor=_actor(request),\n"
        "            now=timezone.now(),\n"
        "        )\n",
        "    result = set_category_mute(\n"
        "            user_id=request.user.pk,\n"
        "            category_key=category_key,\n"
        "            duration_days=None,\n"
        "            actor=_actor(request),\n"
        "            now=timezone.now(),\n"
        "        )\n",
    ),
    (
        "the dismissal endpoint reports the prompt as due whatever the server said",
        DISMISSAL_API,
        "        prompt_due=result.prompt_due,\n",
        "        prompt_due=True,\n",
    ),
    # ------------------------------------------------------------------ adapter
    (
        "the provider's vectors are not re-ordered (a vector is paired with the wrong text)",
        VOYAGE,
        '        pairs = sorted(vectors, key=lambda item: item.get("index", 0))\n',
        "        pairs = list(vectors)\n",
    ),
    (
        "the wrong number of vectors is accepted (a pairing is silently dropped)",
        VOYAGE,
        "        if not isinstance(vectors, list) or len(vectors) != len(texts):\n",
        "        if not isinstance(vectors, list):\n",
    ),
    (
        "a vector of the wrong size is accepted (the cosine compares nothing)",
        VOYAGE,
        "            if not isinstance(embedding, list) or len(embedding) != dimensions:\n",
        "            if not isinstance(embedding, list):\n",
    ),
    (
        "the cost is not written to the cost row (the dashboard reports a free call)",
        VOYAGE,
        "        write_cost_row(\n"
        '            kind="embedding",\n'
        "            model=FR25_EMBEDDING_MODEL,\n"
        "            input_tokens=input_tokens,\n"
        "            output_tokens=0,\n"
        "            cost_micros=cost_micros,\n"
        "            call_count=len(texts),\n"
        "        )\n",
        "        pass\n",
    ),
    (
        "the cost is computed as zero (the row says the call was free)",
        VOYAGE,
        "        return (input_tokens * price_per_million_micros) // 1_000_000\n",
        "        return 0\n",
    ),
    (
        "the batch limit is not enforced (the request body is unbounded)",
        VOYAGE,
        "        if len(texts) > VOYAGE_MAX_BATCH:\n",
        "        if False:\n",
    ),
    (
        "a missing key is treated as a free embedding (the row lies about the cost)",
        VOYAGE,
        "        if not api_key:\n",
        "        if False:\n",
    ),
    (
        "the input type is a query (the vectors are in the wrong part of the space)",
        VOYAGE,
        'VOYAGE_INPUT_TYPE = "document"\n',
        'VOYAGE_INPUT_TYPE = "query"\n',
    ),
    (
        "the dimension is not requested (the truncation is applied by slicing)",
        VOYAGE,
        '                        "output_dimension": dimensions,\n',
        "",
    ),
]


def run_tests(test_files: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_files, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    failures = []
    for description, path, original, mutated in PROBES:
        source = path.read_text()
        if original not in source:
            failures.append(f"PROBE DID NOT APPLY: {description}")
            print(f"SKIP  {description} (pattern not found)")
            continue

        path.write_text(source.replace(original, mutated, 1))
        try:
            code, output = run_tests(TEST_FILES)
        finally:
            path.write_text(source)

        if code == 0:
            failures.append(f"NOT CAUGHT: {description}")
            print(f"FAIL  {description} -- the suite still passed")
        else:
            last = output.strip().splitlines()[-1] if output.strip() else ""
            print(f"OK    {description} -- caught ({last})")

    print()
    if failures:
        for failure in failures:
            print(failure)
        return 1
    print(f"All {len(PROBES)} probes were caught by the suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
