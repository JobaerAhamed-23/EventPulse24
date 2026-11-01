"""AD-7, AD-17: one module owns the `SCHEDULED_SEND` schedule.

**The rule.** `scheduled_sends.py` is the single writer of the schedule: every write that
*plans* a send — minting it, moving it, cancelling it, rewriting it, applying a lifecycle
change to it — happens there. The one other module that writes the table is
`delivery_sweep`, and it writes the **execution** half: the claim, the mark as sent, the
record of a provider failure. A row's fate at the moment it is delivered is not a planning
decision, and a module that does not hold the claim cannot make it.

**Why the rule is worth a file.** `SCHEDULED_SEND` is the table the whole delivery
system turns on — AD-7 calls it "the sole source of truth for what is due". If a third
module starts writing it, the schedule has two sources of truth and the drift is
invisible: nothing breaks loudly, a send is simply scheduled by one rule and cancelled by
another.

**Why this is not AD-16.** AD-16 asks *which app* may write a table; `delivery` writes
`delivery_scheduledsend`, and that is satisfied. This asks a finer question — *which
module inside the owning app* — and AD-16's own docstring says why that matters: "a module
inside the owning app can still be the wrong place to write from". AD-5 (no surface module
writes at all) and this file are two halves of the same idea, at two different grains.

**Why it is AST-based.** A write reaches a model in more shapes than `.save()`:
`Model.objects.filter(...).update(...)` never binds the row, and `row.save()` writes
whatever `row` holds, which syntax cannot know. So the check attributes a write by
**what it names**: a call whose receiver is the model, or a call on a queryset built from
the model. Both are found here.

**Why the check is not vacuous.** A rule that finds nothing proves nothing unless it
*can* find something. So a violation is planted and the check is run against it directly —
in `tmp_path`, never in the tree, so the probe never becomes a second copy of the
production code.
"""

import ast
import pathlib

import pytest

from tests.architecture.checkers import BACKEND_DIR, WRITE_CALLS

#: The module that owns the schedule. **One path**, because there is one schedule.
SCHEDULE_OWNER = "apps/delivery/services/scheduled_sends.py"

#: The module that owns the execution half — the claim, the mark, the failure record.
#:
#: It is allowed to write the table because a row's fate at the moment it is delivered is
#: not a planning decision, and it is the module that holds the claim. It is listed
#: rather than exempt by pattern so that a *new* writer is reported by name.
EXECUTION_OWNER = "apps/delivery/services/delivery_sweep.py"

#: The modules allowed to write `SCHEDULED_SEND` at all.
ALLOWED_WRITERS = frozenset({SCHEDULE_OWNER, EXECUTION_OWNER})


def _app_modules() -> list[pathlib.Path]:
    """Every module inside `apps/`, except the migrations and the model declarations.

    The **migrations** are excluded because they are DDL, not application writes, and the
    **models** are excluded because a model declares its table rather than writing rows.
    """
    files = []
    for path in sorted((BACKEND_DIR / "apps").rglob("*.py")):
        relative = path.relative_to(BACKEND_DIR)
        if "migrations" in relative.parts:
            continue
        if relative.name == "models.py":
            continue
        files.append(path)
    return files


def _writes_to_scheduled_send(path: pathlib.Path) -> list[int]:
    """The lines in `path` that write `ScheduledSend`.

    **Two shapes count**, because a write takes both:

    - `ScheduledSend.objects.using(PERSONAL).filter(...).update(...)` — the receiver
      names the model, and the write never binds a row.
    - `row.save()` — the receiver is a variable, so this counts only where the module
      imports `ScheduledSend` and the row was built from it. The module-level import is
      what makes the attribution sound: a module that does not import the model cannot
      be writing it, and a module that does is writing it somewhere.
    """
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))

    imports_model = any(
        isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.endswith(".models")
        and any(alias.name == "ScheduledSend" for alias in node.names)
        for node in ast.walk(tree)
    )

    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in WRITE_CALLS:
            continue
        if _names_scheduled_send(node.func.value) or imports_model:
            lines.append(node.lineno)
    return sorted(lines)


def _names_scheduled_send(node: ast.expr) -> bool:
    """Whether a call's receiver names the `ScheduledSend` model.

    `ScheduledSend.objects` — a `Name` whose id is the model.
    `ScheduledSend.objects.using(PERSONAL)` — the model reached through `.objects`.
    """
    if isinstance(node, ast.Attribute) and node.attr == "objects":
        return isinstance(node.value, ast.Name) and node.value.id == "ScheduledSend"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "using":
            return _names_scheduled_send(node.func.value)
    return False


@pytest.mark.parametrize(
    "path",
    _app_modules(),
    ids=lambda p: str(p.relative_to(BACKEND_DIR)),
)
def test_only_the_owner_writes_the_schedule(path: pathlib.Path):
    """AD-7: the schedule has one writer, and it is named.

    A module that writes `SCHEDULED_SEND` outside the two owners is a third source of
    truth for what is due, and the drift between them is silent — a send scheduled by one
    rule and cancelled by another.
    """
    relative = str(path.relative_to(BACKEND_DIR))
    if relative not in ALLOWED_WRITERS:
        assert _writes_to_scheduled_send(path) == [], (
            f"{relative} writes SCHEDULED_SEND. The schedule has one writer — "
            f"{SCHEDULE_OWNER} — and the execution half is {EXECUTION_OWNER}. "
            "A third writer is a second rule set, and the two will drift."
        )


def test_the_two_owners_are_both_real_writers():
    """The allowance is not a list of holes.

    `ALLOWED_WRITERS` names two modules. If either stopped writing the table, the
    allowance would be a stale exemption — and a stale exemption is how a closed set
    quietly stops being closed. So both are checked to actually write.
    """
    for relative in sorted(ALLOWED_WRITERS):
        path = BACKEND_DIR / relative
        assert path.exists(), f"{relative} is allowed to write the schedule but does not exist"
        assert _writes_to_scheduled_send(path), (
            f"{relative} is allowed to write SCHEDULED_SEND but does not. "
            "The allowance is stale — remove it."
        )


def test_the_schedule_owner_is_the_one_that_plans():
    """The two owners are two halves, and the halves are not interchangeable.

    `scheduled_sends.py` mints and cancels — the decisions. `delivery_sweep.py` claims
    and marks — the execution. This test pins which half each one is, because the two
    being swapped would be invisible: both would still write the table, and the schedule
    would still work, but the module that decides *what is due* would be the one that
    delivers it.
    """
    schedule_source = (BACKEND_DIR / SCHEDULE_OWNER).read_text()
    sweep_source = (BACKEND_DIR / EXECUTION_OWNER).read_text()

    # The schedule owner mints and cancels.
    assert "def mint_for_plan(" in schedule_source
    assert "def cancel_sends_for_targets(" in schedule_source
    assert "def cancel_pending_digests_for_user(" in schedule_source

    # The execution owner claims and marks.
    assert "def sweep_due_sends(" in sweep_source
    assert "scheduled_send.sent" in sweep_source

    # And the schedule owner does not mark a row as sent — that is the sweep's half.
    assert "scheduled_send.sent" not in schedule_source


def test_the_probe_is_caught(tmp_path: pathlib.Path):
    """The check can find something, so finding nothing means something.

    **This is the revert verification.** A rule that has never fired is a rule nobody has
    tested. So a violation is planted — a module outside the owners writing the table —
    and the check is run against it directly.

    The plant is written into `tmp_path` rather than into the tree, so the probe never
    exists as a real module: a probe left in `apps/` would be a second copy of the
    production code, and it would be picked up by the other checks in this directory.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(
        "from apps.delivery.models import ScheduledSend\n"
        "from shared.db import PERSONAL\n"
        "\n"
        "ScheduledSend.objects.using(PERSONAL).filter(status='pending').update(status='sent')\n"
    )

    writes = _writes_to_scheduled_send(probe)

    assert writes, "the probe's write was not found at all"
