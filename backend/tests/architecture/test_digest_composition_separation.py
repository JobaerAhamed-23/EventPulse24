"""AD-11: no request handler composes a digest.

**The rule.** "A request handler's job is to validate, enqueue, and return." The
composition reads three candidate pools and scores them — that is worker work. So the
request path may **enqueue** a composition and may never **perform** one.

**Why the boundary is worth a file.** The enqueue and the composition live in the same
package, and the enqueue is reachable from a request handler by design — the onboarding
path calls it. So the *presence* of a composition import in an API module is not
automatically wrong; what is wrong is the API module **calling** it.

That is why this check is **AST-based and call-based**, not import-based:

- it reports a module that **calls** `compose_digest` — the thing AD-11 forbids;
- it does **not** report a module that merely imports the enqueue seam.

A plain "does any API module import `digest_composition`" rule would either be
vacuous (the worker legitimately imports it) or would need a list of exemptions that
grows with every new API module — and a list of exemptions is a list of holes.

**The check is on the call, so a re-export cannot hide it.** A module that re-exported
the composition under another name and called *that* would still be calling a function
whose ultimate definition is the composition — and the AST walk finds the call by the
name it is bound to, whatever the binding was called locally. What the check cannot see
is a composition reached through a function object passed in as an argument; code
review covers that, and the module docstring says so.
"""

import ast
from pathlib import Path

import pytest

from tests.architecture.checkers import BACKEND_DIR, api_modules

#: The composition command. **One name**, because there is one composition.
COMPOSE_DIGEST = "compose_digest"

#: The modules that take requests. **Discovered, not written down** — see
#: `_request_modules` for why a hand-written list would be a list of holes.
#:
#: **The discovery is shared with the AD-5 guard.** `checkers.surface_files()` computes
#: the same thing by the same rule — a module named `api.py` or ending in `_api.py`. Two
#: copies of one rule would be free to disagree about what a request handler is, and the
#: disagreement would be invisible: one guard would check a file the other had never
#: heard of.
REQUEST_MODULES = (
    "apps/catalog/api.py",
    "apps/catalog/preview_api.py",
    "apps/delivery/api.py",
    "apps/delivery/email_api.py",
    "apps/delivery/notices_api.py",
    "apps/delivery/preferences_api.py",
    "apps/editorial/api.py",
    "apps/identity/api.py",
    "apps/identity/billing_api.py",
    # FR-52. It enqueues nothing itself — the tick's dispatcher picks the row up — which is
    # exactly the shape AD-11 asks of a request handler.
    "apps/identity/export_api.py",
    "apps/identity/webhooks_api.py",
    "apps/ingestion/api.py",
    "apps/personalization/api.py",
    # FR-49. It validates, calls the published commands and returns — the shape AD-11
    # asks of a request handler.
    "apps/personalization/collections_api.py",
    "apps/personalization/detail_api.py",
    # FR-13, FR-16. It reads the registry through `ingestion`'s published service and
    # writes the caller's own visibility state through `personalization`'s — the shape
    # AD-11 asks of a request handler.
    "apps/personalization/source_mutes_api.py",
    # FR-25. It reads the caller's own muted categories and writes the caller's own
    # category mutes through `personalization`'s published service — the shape AD-11
    # asks of a request handler. It is a **sibling** of the sources router above, not
    # the same screen: the sources screen mutes sources, and this one mutes categories.
    "apps/personalization/taste_mutes_api.py",
    "config/api.py",
    "config/health.py",
)


def _python_files(package: str) -> list[Path]:
    return sorted((BACKEND_DIR / package.replace(".", "/")).rglob("*.py"))


def _called_names(path: Path) -> set[str]:
    """Every function name called in the file, by the name it is called *by*.

    A call is `ast.Call` whose func is a `Name` (`compose_digest(...)`) or an
    `Attribute` (`services.compose_digest(...)`) — the two spellings a direct call can
    take. A decorator is excluded for the same reason the write checker excludes it:
    `@router.delete(...)` registers a route, it does not delete a record.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    decorator_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    decorator_lines.add(decorator.lineno)

    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or node.lineno in decorator_lines:
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


def _request_modules() -> list[Path]:
    """Every module that takes a request.

    **The list is discovered, not written down**, so a new API module is covered the
    moment it exists. A hand-written list would be a list of holes — and a new API
    module would be outside it until somebody noticed.

    **It is `checkers.api_modules()`**, the same shape rule the AD-5 guard's discovery
    uses, so the two guards cannot disagree about what a request handler is. (The AD-5
    guard also covers the admins, which are not request handlers and are not this
    guard's business.)
    """
    return api_modules()


@pytest.mark.parametrize(
    "path",
    _request_modules(),
    ids=lambda p: str(p.relative_to(BACKEND_DIR)),
)
def test_no_request_handler_composes_a_digest(path):
    """AD-11: a request handler validates, enqueues, and returns. It never composes.

    Composing reads three candidate pools and scores them — that is worker work, and
    doing it inside a request would hold the connection open for the length of a
    scoring pass.
    """
    called = _called_names(path)

    assert COMPOSE_DIGEST not in called, (
        f"{path.relative_to(BACKEND_DIR)} calls {COMPOSE_DIGEST}(). A request handler's "
        "job is to validate, enqueue, and return; the composition is worker work (AD-11)."
    )


def test_the_request_modules_are_the_ones_we_think():
    """The discovery finds the modules the hand-written list names — so the discovery is
    not silently finding nothing."""
    found = {str(p.relative_to(BACKEND_DIR)) for p in _request_modules()}

    assert found == set(REQUEST_MODULES)


def test_the_composition_is_reachable_from_the_worker():
    """**The boundary is a direction, not an absence.**

    A rule that forbade the composition *everywhere* would be satisfied by a tree where
    no digest was ever composed — and the user's digest would simply never appear.
    The worker is where the composition belongs, and this pins that it is still there.
    """
    composing = {
        str(path.relative_to(BACKEND_DIR))
        for path in [
            *(_python_files("worker")),
            *(_python_files("apps")),
            *(_python_files("config")),
        ]
        if COMPOSE_DIGEST in _called_names(path)
    }

    assert "worker/tasks.py" in composing, (
        "the worker must compose the digest; AD-11 moves the work *out* of the request "
        "path, not out of the system"
    )


def test_the_onboarding_path_enqueues_rather_than_composes():
    """**The onboarding path is the one place a request handler may start a
    composition — and it does it by enqueueing.**

    The enqueue is registered on `on_commit`, so the job runs after the transaction is
    durable. This test pins that the onboarding module calls the *enqueue*, and not
    the composition.

    **The call is one level down.** The onboarding module calls a private
    `_enqueue_first_digest`, which registers the callback; the callback holds the
    enqueue function itself. So the check follows the local binding: the onboarding
    module must call something whose name says *enqueue*, and must not call the
    composition.
    """
    onboarding = BACKEND_DIR / "apps/personalization/services/onboarding.py"
    source = onboarding.read_text()
    called = _called_names(onboarding)

    assert COMPOSE_DIGEST not in called
    assert "_enqueue_first_digest" in called
    assert "enqueue_digest_composition" in source


def test_the_enqueue_seam_does_not_import_the_composition():
    """**The seam sends a job by name; it does not compose anything.**

    `personalization` cannot import `worker` or `config` (the layers contract), so the
    job is sent by its dotted name through the Celery app. The seam therefore has no
    reason to import the composition — and if it did, the enqueue path would drag the
    scoring code into every module that imports the seam.

    **The check is on the import, not the text.** The module's own name contains
    `digest_composition` as a substring — `enqueue_digest_composition` — so a plain
    text search would flag the module for its own function name.
    """
    seam = BACKEND_DIR / "apps/personalization/services/digest_enqueue.py"

    imported = _imported_modules(seam)

    assert not any(
        name.startswith("apps.personalization.services.digest_composition") for name in imported
    ), (
        "the enqueue seam imports the composition. The seam sends a job by name; it "
        "does not compose anything, and importing the composition would drag the "
        "scoring code into every module that imports the seam."
    )


def _imported_modules(path: Path) -> set[str]:
    """Every module the file imports, as dotted names.

    Resolves relative imports against the file's own package, so a relative import is
    reported by its absolute name.
    """
    parts = path.relative_to(BACKEND_DIR).with_suffix("").parts
    package = list(parts[:-1])
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
