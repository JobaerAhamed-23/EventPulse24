---
id: duplicate-file-cleanup
title: Clear 1,323 filesystem conflict copies out of the tree
intent: traceability-reconciliation
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-12
run_id: run-eventpulse24-028
completed_at: 2026-11-12T05:04:48.728Z
---

# Work Item: Clear 1,323 filesystem conflict copies out of the tree

## Description

`backend/` and `frontend/` hold **1,323** files matching `* 2.*` — filesystem conflict
copies produced by a syncing file system, not by anything in this repo. None are tracked:
`git ls-files | grep -c " 2\."` returns **0**, and `git status --short` lists them as `??`.

They are not merely untidy. `apps/personalization/migrations/0013_eventreport 2.py` sits in
a Django `migrations/` directory, which the migration loader walks by listing the directory.
A filename containing a space is not an importable module name. This has not broken a run
yet; it is a loaded gun.

**The deletion is trivial. The proof that each file is safe to delete is the work.** Nothing
is tracked, so there is no git history to recover from if a copy turns out to hold the only
version of something.

## Acceptance Criteria

- [ ] Every `* 2.*` file is classified before anything is deleted, into exactly one of:
      **identical** to its original (byte-for-byte), **stale** (original is a strict superset
      or newer and the copy introduces nothing), or **divergent** (contains content found
      nowhere else).
- [ ] The classification is produced by a script, not by eye, and the script is kept in the
      scratchpad or `scripts/` — not committed as repo tooling unless it earns its place.
- [ ] **Any file classified divergent stops the item and is reported, not deleted.** A
      divergent copy means real work was done in the wrong file and would be destroyed.
- [ ] Identical and stale copies are deleted. `find backend frontend -name "* 2.*"` returns
      nothing, excluding `node_modules/` and `.next/`.
- [ ] The duplicates under `.specs-fire/runs/run-eventpulse24-027/` (`run 2.md`,
      `walkthrough 2.md`, `review-report 2.md`, `test-report 2.md`) are handled by the same
      rule — they are FIRE's own records and a divergent one matters more, not less.
- [ ] `.gitignore` gains a rule matching this pattern so the copies never enter history.
- [ ] `python manage.py makemigrations --check --dry-run` and the backend test suite pass
      after the deletion, proving no import resolved through a duplicate.
- [ ] The frontend typechecks and builds after the deletion.

## Technical Notes

Medium, not low — the rating is deliberate. Under the `balanced` autonomy bias a `low`
rating would make this **autopilot**, and a 1,323-file untracked deletion should not run
without a checkpoint.

Check `.puku-cli/worktrees/` too: the survey found `backend/adapters` and `backend/ports`
mirrored under `.puku-cli/worktrees/agent-a943cb93/`. Decide whether that worktree is live
before touching anything inside it — it is out of scope for deletion unless it is confirmed
dead, and it should not be counted in the 1,323.

Watch for a duplicate that is **newer** than its original. That inverts the stale case and
means the sync wrote the real edit into the copy. Treat it as divergent and stop.
