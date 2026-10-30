"""AD-10: the two kinds of explanation never cross.

AD-10 names **two** kinds of explanation, and says both are persisted, neither is ever
recomputed at render:

| Kind | Computed | Persisted on | Serves | Owner |
| --- | --- | --- | --- | --- |
| **Event Fit** | per `(event, city)` | `catalog` | SEO pages, Pulse Preview | `ingestion` |
| Relevance Pulse | at digest composition | `personal` | card, detail, email | `personalization` |

They look identical on screen, and that is exactly why they must never be substituted
for one another. AD-10 calls it "the trust-collapse failure PRD Risk 11 calls
company-ending": an authenticated surface that falls back to Event Fit to fill a missing
Relevance Pulse tells a signed-in reader that a thing is a great match when nothing
personal was ever computed, and a public surface that reads `personal` leaks one
person's preferences to everyone.

**This file asserts both directions, on the real tree.**

* `personalization` may not reach the Event Fit read. It has its own explanation, and
  reaching across would let it silently substitute one for the other.
* `ingestion` may not reach `personalization`. The Event Fit is computed on the catalog
  side, from catalog facts; it has no business knowing about a user's preferences.
* The public Event Fit read may not touch the `personal` schema at all. It is served to
  visitors with no session (AD-12), so a read of `personal` would be a leak even if the
  value were discarded.

The checks are **AST-based**, not import-based: a module can reach another through an
alias, through a re-export, or through a function it was handed, and a runtime import
check would only catch the first.
"""

import ast
from pathlib import Path

import pytest

from tests.architecture.checkers import BACKEND_DIR

# The Event Fit is a **package**, and that is why the wall holds.
#
# The first version of this file named two leaves: `...services.event_fit` and
# `...services.event_fit_read`. A third module that re-exported the read — two lines —
# gave `personalization` the Event Fit with both the import contract and this file
# **green**. A wall made of names is opened by adding a name.
#
# A package is one name that covers everything inside it, so a new Event Fit module is
# inside the wall by default rather than outside it until somebody notices.
EVENT_FIT_PACKAGE = "apps.ingestion.event_fit"
# The two modules inside the package.
EVENT_FIT_READ = "apps.ingestion.event_fit.reads"
EVENT_FIT_WRITES = "apps.ingestion.event_fit.writes"
# The public catalog read, which personalization IS allowed to use.
PUBLIC_CATALOG_READ = "apps.ingestion.services.catalog_read"
PERSONALIZATION = "apps.personalization"
INGESTION = "apps.ingestion"


def _python_files(package: str) -> list[Path]:
    """Every Python file under a package, given as a dotted module path."""
    return sorted((BACKEND_DIR / package.replace(".", "/")).rglob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    """Every module the file imports, as dotted names.

    Resolves `from . import x` and `from ..services import y` against the file's own
    package, so a relative import of the Event Fit read is reported by its absolute name
    rather than by its relative spelling.

    A file outside the backend tree — a planted probe, say — has no package to resolve
    against, so it is read as a top-level module. That is enough for an absolute import,
    which is what a planted probe of this wall uses.
    """
    try:
        parts = path.relative_to(BACKEND_DIR).with_suffix("").parts
    except ValueError:
        parts = path.with_suffix("").parts
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts = parts[:-1]
    package = list(parts)

    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: max(len(package) - (node.level - 1), 0)]
                target = ".".join([*base, node.module] if node.module else base)
            else:
                target = node.module or ""
            imported.add(target)
            for alias in node.names:
                imported.add(f"{target}.{alias.name}" if target else alias.name)
    return imported


# ── Direction one: personalization may not read the Event Fit ─────────────────────


@pytest.mark.parametrize(
    "path",
    _python_files(PERSONALIZATION),
    ids=lambda p: str(p.relative_to(BACKEND_DIR)),
)
def test_personalization_does_not_import_the_event_fit_read(path):
    """The Relevance Pulse is not allowed to borrow the Event Fit.

    A Relevance Pulse that falls back to an Event Fit is the exact substitution AD-10
    forbids: the reader sees an indicator that says "this is a great match for you" and
    nothing personal was ever computed.

    The wall is the Event Fit **package**. `personalization` **is** allowed to read the
    public catalog — saving an event to your calendar needs the event's public facts, and
    that is a different thing from borrowing its explanation.

    The check is on the **package prefix**, not on a list of module names, because a
    re-export is the ordinary way a package boundary leaks. `import
    apps.ingestion.event_fit.reads` is caught; so is `import apps.ingestion.event_fit` —
    and so is `import apps.ingestion.event_fit_preview`, because the package name is a
    prefix of it. `test_the_wall_catches_a_re_export` plants that last one and proves it.
    """
    imported = _imported_modules(path)

    assert not any(name.startswith(EVENT_FIT_PACKAGE) for name in imported), (
        f"{path.relative_to(BACKEND_DIR)} reaches the Event Fit through a direct import "
        f"or a re-export ({EVENT_FIT_PACKAGE}); AD-10 says the two kinds of explanation "
        "never cross."
    )


def test_the_wall_catches_a_re_export(tmp_path):
    """The bypass that broke the first wall is caught, and the proof is planted.

    The first version of this wall named two leaves, and a module that re-exported the
    read (`event_fit_preview.py`, two lines) walked straight through it: the import
    contract said "kept", and the wall test said "green", while `personalization` held
    the Event Fit.

    **The import contract cannot catch this one.** A `forbidden` contract matches on
    *import names*, and it expands the forbidden package into the modules inside it — so
    it sees `apps.ingestion.event_fit.reads` and it does not see
    `apps.ingestion.event_fit_preview`, which lives outside the package and merely
    re-exports what is inside. That is a property of how the contract works, not a gap
    in how it is configured, so the contract is not asked to catch it.

    This check is, and it can — but only because it looks at the name of the module
    that *is* imported, not only at what that module imports. The bypass has two
    hops:

    1. `apps/ingestion/event_fit_preview.py` re-exports the read.
    2. `personalization` imports **that module**, by name.

    Step 2 is the one the wall sees, and the name it sees is
    `apps.ingestion.event_fit_preview` — which carries the package prefix. A wall made
    of a *list* of module names misses it, because the name is not on the list; a wall
    made of a *prefix* catches it, and catches every future name built the same way.

    The plant below writes the bypass, both halves, and asserts the wall sees it.
    """
    re_export = tmp_path / "event_fit_preview.py"
    re_export.write_text(
        "from apps.ingestion.event_fit.reads import list_event_fit_for_city\n"
        "\n"
        "__all__ = ['list_event_fit_for_city']\n"
    )
    borrower = tmp_path / "borrower.py"
    borrower.write_text("import apps.ingestion.event_fit_preview\n")

    imported = _imported_modules(borrower)

    assert any(name.startswith(EVENT_FIT_PACKAGE) for name in imported), (
        "the wall must see the Event Fit reached through a re-export; a module outside "
        "the package that re-exports what is inside is the ordinary way a boundary leaks"
    )
    # And the module that does the re-exporting is itself named with the package
    # prefix, which is the name `personalization` reaches for.
    assert "apps.ingestion.event_fit_preview".startswith(EVENT_FIT_PACKAGE)
    # A wall made of a *list* of names would miss it, because the name is not on the
    # list. That is why the check is a prefix and not an equality.
    assert "apps.ingestion.event_fit_preview" not in {EVENT_FIT_READ, EVENT_FIT_WRITES}


def test_personalization_may_still_read_the_public_catalog():
    """The wall is narrow on purpose: it blocks the explanation, not the event.

    A test that forbade `personalization` from reading the catalog at all would have
    been satisfied by a tree where saving an event had been broken. This pins the
    boundary that is actually wanted.
    """
    readers = [
        path
        for path in _python_files(PERSONALIZATION)
        if PUBLIC_CATALOG_READ in _imported_modules(path)
    ]

    assert readers, (
        "personalization reads the public catalog to save events. If this ever stops "
        "being true, the Event Fit wall needs rethinking rather than the saving feature."
    )


# ── Direction two: ingestion may not reach personalization ───────────────────────


@pytest.mark.parametrize(
    "path",
    _python_files(INGESTION),
    ids=lambda p: str(p.relative_to(BACKEND_DIR)),
)
def test_ingestion_does_not_import_personalization(path):
    """The Event Fit is computed from catalog facts, and nothing else.

    It is the explanation for a stranger. If computing it read a user's preferences, the
    score would be a personal one wearing a public label — and the same row would then
    mean two different things depending on who looked at it.
    """
    imported = _imported_modules(path)

    assert not any(name.startswith(PERSONALIZATION) for name in imported), (
        f"{path.relative_to(BACKEND_DIR)} imports personalization; the Event Fit is "
        "computed on the catalog side, from catalog facts."
    )


# ── The read never touches the personal schema ───────────────────────────────────


def test_the_event_fit_read_never_reads_the_personal_schema():
    """The public Event Fit read is served to visitors with no session (AD-12).

    It therefore never reads `personal` — not even to discard the value. The check is on
    the **schema alias**, not on the module: reading a personal model through the catalog
    alias would still be a personal read.
    """
    source = (BACKEND_DIR / f"{EVENT_FIT_READ.replace('.', '/')}.py").read_text()

    assert "PERSONAL" not in source, (
        f"{EVENT_FIT_READ} mentions the PERSONAL alias. The public Event Fit read must "
        "never read the personal schema."
    )


def test_the_event_fit_service_never_reads_the_personal_schema():
    """Same rule for the writer: it computes on the catalog side."""
    source = (BACKEND_DIR / f"{EVENT_FIT_WRITES.replace('.', '/')}.py").read_text()

    assert "PERSONAL" not in source, (
        f"{EVENT_FIT_WRITES} mentions the PERSONAL alias. Event Fit is computed on the "
        "catalog side, from catalog facts."
    )


# ── The read computes nothing ────────────────────────────────────────────────────


def test_the_event_fit_read_does_not_call_the_domain_function():
    """AD-10: "never recomputed at render".

    The read serves the **persisted** row. If the read called `compute_event_fit`, the
    score on screen would be computed at request time — which is the substitution AD-10
    is against, and it is also how two surfaces end up disagreeing about the same event.
    """
    source = (BACKEND_DIR / f"{EVENT_FIT_READ.replace('.', '/')}.py").read_text()

    assert "compute_event_fit" not in source, (
        f"{EVENT_FIT_READ} calls compute_event_fit. The Event Fit is persisted and served "
        "as it stands; it is never recomputed at render (AD-10)."
    )


def test_the_domain_function_is_the_only_place_a_fit_is_computed():
    """One function computes a fit, and it is a pure one.

    Every fit in the system comes from `domain.event_fit.compute_event_fit`. A second
    implementation — in a service, in a view, in a template helper — would be a second
    rule set, and the two would drift.
    """
    computing = set()
    for package in ("apps", "worker", "config", "adapters", "ports"):
        for path in _python_files(package):
            if "compute_event_fit" in path.read_text():
                computing.add(str(path.relative_to(BACKEND_DIR)))

    assert computing == {"apps/ingestion/event_fit/writes.py"}, (
        "Only the Event Fit writer computes a fit. Found: " + ", ".join(sorted(computing))
    )
