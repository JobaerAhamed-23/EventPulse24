#!/usr/bin/env python
"""Mutation probes for the source-visibility surface (run-eventpulse24-033, plan step 6).

Each probe applies one real bug to the implementation, runs the source-mute tests, and
checks that at least one test fails. A probe that passes the suite means the tests don't
prove that rule, and the implementation or the test has to change.

**The probes are the point of the design.** The two rules this feature rests on — a mute
*excludes* and a show-less *deprioritises but does not exclude* — are easy to implement
one way and easy to test the other way. A test that passed with the two swapped would
prove nothing. These probes apply exactly that swap, and several more.

Run from the repo root:
    uv run --directory backend python tests/personalization/mutation_probe_source_mutes.py
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

COMPOSITION = BACKEND / "apps/personalization/services/digest_composition.py"
BROWSE = BACKEND / "apps/personalization/services/browse_read.py"
MUTES = BACKEND / "apps/personalization/services/source_mutes.py"
RANKING = BACKEND / "domain/ranking.py"
REGISTRY = BACKEND / "apps/ingestion/services/source_registry_read.py"
API = BACKEND / "apps/personalization/source_mutes_api.py"

TEST_FILES = [
    "tests/personalization/test_source_mute_composition.py",
    "tests/personalization/test_source_mutes.py",
    "tests/personalization/test_source_mutes_api.py",
    "tests/ingestion/test_source_registry_read.py",
]

PROBES = [
    (
        "the mute filter is dropped (a muted source's events reach the digest)",
        COMPOSITION,
        "    eligible = [candidate for candidate in public_candidates "
        "if candidate.source_id not in muted]\n",
        "    eligible = list(public_candidates)\n",
    ),
    (
        "the mute filter is dropped in Browse (the two surfaces disagree)",
        BROWSE,
        "    eligible = [\n"
        "        candidate for candidate in candidates "
        "if candidate.source_id not in visibility.muted\n"
        "    ]\n",
        "    eligible = list(candidates)\n",
    ),
    (
        "the show-less penalty is dropped (a show-less source scores the same)",
        COMPOSITION,
        "    score = apply_show_less(score, show_less=show_less)\n",
        "",
    ),
    (
        "the show-less penalty is folded into the confidence pulse (the bucket moves too)",
        COMPOSITION,
        "    bucket = apply_hysteresis(\n"
        "        previous_bucket=None,\n"
        "        previous_score=None,\n"
        "        new_score=score,\n"
        "    )\n"
        "    # **The ordering comes from the score the preference applied to.**\n"
        "    score = apply_show_less(score, show_less=show_less)\n",
        "    score = apply_show_less(score, show_less=show_less)\n"
        "    bucket = apply_hysteresis(\n"
        "        previous_bucket=None,\n"
        "        previous_score=None,\n"
        "        new_score=score,\n"
        "    )\n",
    ),
    (
        "the show-less penalty is dropped in Browse",
        BROWSE,
        "        score = apply_show_less(\n"
        "            relevance_score(inputs),\n"
        "            show_less=candidate.source_id in visibility.show_less,\n"
        "        )\n",
        "        score = relevance_score(inputs)\n",
    ),
    (
        "the show-less penalty subtracts nothing (the rule is applied but is a no-op)",
        RANKING,
        "    return _clamp((score - SOURCE_SHOW_LESS_PENALTY).quantize(SCORE_PRECISION))\n",
        "    return _clamp(score.quantize(SCORE_PRECISION))\n",
    ),
    (
        "the penalty is applied inside the ranking formula (FR-22's weights move)",
        RANKING,
        "    if not show_less:\n"
        "        return score\n"
        "    return _clamp((score - SOURCE_SHOW_LESS_PENALTY).quantize(SCORE_PRECISION))\n",
        "    if not show_less:\n"
        "        return score\n"
        "    return _clamp(score.quantize(SCORE_PRECISION))\n",
    ),
    (
        "the default state is stored as a row instead of deleting it",
        MUTES,
        "    if state == STATE_DEFAULT:\n"
        "        return _restore_one(user_id=user_id, source_id=source_id, actor=actor, now=now)\n",
        "",
    ),
    (
        "the bulk reset is not scoped to the caller (it clears everybody's rows)",
        MUTES,
        "        deleted, _ = SourceMute.objects.using(PERSONAL)"
        ".filter(user_id=user_id).delete()\n",
        "        deleted, _ = SourceMute.objects.using(PERSONAL).all().delete()\n",
    ),
    (
        "the bulk reset forgets the show-less preferences",
        MUTES,
        "        deleted, _ = SourceMute.objects.using(PERSONAL)"
        ".filter(user_id=user_id).delete()\n",
        "        deleted, _ = (\n"
        "            SourceMute.objects.using(PERSONAL)\n"
        "            .filter(user_id=user_id, state=STATE_MUTE)\n"
        "            .delete()\n"
        "        )\n",
    ),
    (
        "the trust band uses exclusive bounds (0.50 lands in band 2, not band 3)",
        BACKEND / "domain/reliability.py",
        "    if score >= SOURCE_TRUST_BAND_5:\n"
        "        return SOURCE_TRUST_MAX\n"
        "    if score >= SOURCE_TRUST_BAND_4:\n"
        "        return 4\n"
        "    if score >= SOURCE_TRUST_BAND_3:\n"
        "        return 3\n"
        "    if score >= SOURCE_TRUST_BAND_2:\n"
        "        return 2\n",
        "    if score > SOURCE_TRUST_BAND_5:\n"
        "        return SOURCE_TRUST_MAX\n"
        "    if score > SOURCE_TRUST_BAND_4:\n"
        "        return 4\n"
        "    if score > SOURCE_TRUST_BAND_3:\n"
        "        return 3\n"
        "    if score > SOURCE_TRUST_BAND_2:\n"
        "        return 2\n",
    ),
    (
        "the registry drops the paused sources (transparency fails)",
        REGISTRY,
        "        is_paused=source.status == Source.Status.PAUSED,\n",
        "        is_paused=False,\n",
    ),
    (
        "the registry drops the empty groups (the screen's shape depends on the data)",
        REGISTRY,
        "    for badge in SOURCE_GROUP_ORDER:\n",
        "    for badge in [b for b in SOURCE_GROUP_ORDER if by_badge.get(b)]:\n",
    ),
    (
        "the list drops the muted sources (the screen stops being transparent)",
        API,
        "                        mute_state=states.get(source.id, STATE_DEFAULT),\n",
        "                        mute_state=STATE_DEFAULT,\n",
    ),
    (
        "the list reads another user's states (the scoping is broken)",
        API,
        "    states = read_source_states(user_id=user_id)\n",
        "    states = read_source_states(user_id=uuid4())\n",
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
