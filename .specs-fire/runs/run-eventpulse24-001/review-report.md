# Code Review Report

**Run**: run-eventpulse24-001
**Intent**: project-scaffold
**Reviewed**: 2026-10-27
**Files Reviewed**: 12

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 1 | 0 |
| Security | 0 | 0 | 1 |
| Architecture | 0 | 0 | 1 |
| Testing | 0 | 0 | 1 |
| **Total** | **1** | **1** | **3** |

**Tests Status**: Passing

---

## Files Reviewed

- `docker-compose.yml` (created)
- `docker/postgres/init/01-schemas-and-roles.sh` (created)
- `.env.example` (created)
- `.gitignore` (created)
- `Makefile` (created)
- `scripts/doctor.sh` (created)
- `scripts/db-check.sh` (created)
- `docs/setup/ubuntu.md` (created)
- `docs/setup/macos.md` (created)
- `README.md` (created)
- `.specs-fire/intents/project-scaffold/brief.md` (modified)
- `.specs-fire/intents/project-scaffold/work-items/local-infra-and-setup-docs.md` (modified)

---

## Auto-Fixed Issues

### 1. [Code Quality] shellcheck SC2016: literal backticks inside single quotes

- **File**: `scripts/doctor.sh:111`
- **Description**: Replaced the backticks around `make env` with double quotes. The output text is the same and there is no behavior change. shellcheck is now clean.

```diff
- printf 'Note: no .env yet — run `make env` to create it from .env.example.\n'
+ printf 'Note: no .env yet — run "make env" to create it from .env.example.\n'
```

Fixed during testing; the port-ownership bug in `doctor.sh` was also fixed then (see test-report.md, "Issues Found").

---

## Applied Suggestions

### 1. [Code Quality] Warn that `.env` values must not contain `$`

- **File**: `.env.example:3`
- **Description**: The Makefile `-include`s `.env`, so make would expand a `$` inside a value (e.g. a generated password) and silently corrupt it.
- **Rationale**: Comment only; prevents a confusing failure.
- **Risk Level**: Low
- **Approved**: 2026-10-27 (user chose option 1)
- **Diff**:

```diff
  # .env is git-ignored. These are LOCAL-ONLY defaults — never reuse them anywhere else.
+ # Values must not contain `$`: the Makefile includes .env and make would expand it.
```

Re-verified after applying: `make help`, `docker compose config -q`, and `db-check` all pass.

---

## Skipped Suggestions

### 1. [Testing] Always clean up db-check probe tables (`trap`)

- **File**: `scripts/db-check.sh:66`
- **Description**: If interrupted, the `__db_check` probe tables remain until the next run (which drops them first).
- **Rationale**: Unconditional cleanup via `trap … EXIT INT TERM`.
- **Risk Level**: Low
- **Reason Skipped**: User chose to apply suggestion 1 only. Low value on reflection: the next run drops leftovers first, a failed check still reaches cleanup (no `set -e`), and CI uses a fresh container per run, so leftovers never carry over.

### 2. [Security] Local passwords passed as `docker exec -e PGPASSWORD=…`

- **File**: `scripts/db-check.sh:31`
- **Description**: Passwords are visible in the local process list while db-check runs.
- **Rationale**: Not a real risk. These are local-only dev defaults, ports bind to 127.0.0.1, and `.env.example` says never to reuse them. CI/prod use the platform secret store (constitution).
- **Risk Level**: Low
- **Reason Skipped**: No action warranted.

### 3. [Architecture] `vector` extension in `public` + runtime `search_path = <schema>, public`

- **File**: `docker/postgres/init/01-schemas-and-roles.sh:57`
- **Description**: Both runtime roles can resolve objects in `public`. CREATE on `public` is revoked (db-check proves it), so nothing else can appear there.
- **Rationale**: This is a placeholder; the per-connection `search_path` is the schema-router-spike's decision under AD-3.
- **Risk Level**: Low
- **Reason Skipped**: Deferred to `schema-router-spike` (its design doc must confirm or change it).

---

## Project Tooling Used

- **shellcheck** (`koalaman/shellcheck:stable`, `-s sh`): POSIX lint for all shell scripts
- **docker compose config**: compose file validation
- No Python/JS linters yet (backend and frontend skeletons come in later items)

---

## Standards Referenced

- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/tech-stack.md`
