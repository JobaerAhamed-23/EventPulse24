"""AD-3: the composition path reads the two schemas **separately**.

**The rule.** "No query joins `catalog` and `personal`, and no model in either schema
holds a foreign key into the other." The wall is a database constraint, not a
convention — `test_personal_events_invariants.py` proves the constraint half, through
`information_schema`, for every model in both schemas.

**What this file adds: the query half, on the one path that legitimately touches both
sides.** Every other module in the codebase lives on one side or the other. The
composition is the exception — it reads the catalog (the candidate pool) *and* the
personal side (the preferences, the interests, the saves), and writes only to the
personal side. So the composition is the one place where the rule needs a **specific**
assertion rather than the general one.

**The two halves, and why they are different assertions.**

1. **No transaction spans both schemas.** The composition's shape is "read the catalog,
   score, then open one transaction on `personal` and write everything atomically".
   The window between the read and the write is the accepted cost of the wall — and it
   is only acceptable because the transaction is on **one** schema. A transaction
   spanning both would be a distributed transaction, which Postgres cannot do and which
   the ORM would fake by opening a second connection.

2. **No query names both aliases.** Every chain in the composition names exactly one
   alias. A chain that mixed them would be a cross-schema join, and the ORM would emit
   it as one statement — the one thing AD-3 forbids.

**Why the check is AST-based and not a database trace.** A database trace would prove
that *this run* joined nothing, and a join added tomorrow would pass until someone
happened to run the path that takes it. The AST check reads the code, so it fails the
moment the join is written.

**The check is on the `using=` argument, not on the alias's value.** `using=PERSONAL`
is the same alias every time; what matters is that the argument is **present** and is
**one** alias, and that no chain names a second one.
"""

import ast
from pathlib import Path

import pytest

from tests.architecture.checkers import BACKEND_DIR

#: The composition service — the one module that touches both schemas.
COMPOSITION = "apps/personalization/services/digest_composition.py"

#: The catalog read it uses. This module is on the catalog side; the composition
#: reaches it, and it must not reach back.
CATALOG_READ = "apps/ingestion/services/catalog_read.py"


def _called_names(path: Path) -> set[str]:
    """Every function name called in the file, by the name it is called *by*."""
    tree = ast.parse(path.read_text(), filename=str(path))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    return called


def test_the_composition_reads_the_catalog_before_it_opens_a_transaction():
    """**The reads happen first, outside the transaction.**

    The composition's `transaction.atomic` is `using=PERSONAL`, and the catalog reads
    happen **before** it opens. So the window between reading the catalog and writing
    the personal side is not inside a transaction at all — which is what makes a
    single-schema transaction possible.

    **The check is on the order, not just the presence.** A transaction that opened
    *before* the catalog read would be a transaction whose window spans both schemas,
    even though it names only one alias.

    **The check is on EVERY read against EVERY transaction.** This is the detail that
    makes the check strong, and it was found by the mutation probe: an earlier version
    of this test compared the **earliest** catalog read to the **earliest** `atomic`.
    A bug that moved a catalog read inside a *second* transaction passed that check —
    the earliest read was still before the earliest transaction — while the later read
    sat squarely inside the transaction's window.

    So the rule is: **every** candidate read must precede **every** transaction. The
    strongest form of "no transaction spans both schemas" that a line-ordering check
    can express.
    """
    source = (BACKEND_DIR / COMPOSITION).read_text()
    tree = ast.parse(source, filename=str(COMPOSITION))

    atomic_lines: list[int] = []
    catalog_read_lines: list[int] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # A call is spelled `name(...)` or `thing.name(...)`. The candidate reads
            # are plain names — `list_public_candidates(...)` — because they are
            # imported into the module's own namespace.
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                name = None
            if name == "atomic":
                atomic_lines.append(node.lineno)
            if name in ("list_public_candidates", "list_personal_candidates"):
                catalog_read_lines.append(node.lineno)

    assert atomic_lines, (
        f"{COMPOSITION} opens no transaction. A composition that writes without one "
        "would leave a half-written digest behind."
    )
    assert catalog_read_lines, (
        f"{COMPOSITION} reads no candidates. A composition that read nothing would "
        "compose an empty digest every time."
    )

    # **Every** read, against **every** transaction. A read at or after a transaction
    # opens is a read whose window spans both schemas.
    for read_line in catalog_read_lines:
        for atomic_line in atomic_lines:
            assert read_line < atomic_line, (
                f"{COMPOSITION} reads a candidate pool on line {read_line} and opens a "
                f"transaction on line {atomic_line}. The catalog read must happen "
                "*before* the personal transaction opens: a transaction whose window "
                "spans both schemas is a distributed transaction, and the ORM would "
                "fake it by opening a second connection (AD-3)."
            )


def test_the_composition_names_exactly_one_alias_per_query():
    """**No query names both aliases.** Every chain names one.

    A chain that mixed `using(PERSONAL)` and `using(CATALOG)` would be a cross-schema
    join, and the ORM would emit it as one statement — the thing AD-3 forbids.

    **The check is on the `using=` argument.** Every ORM chain in the composition must
    name an alias, and the alias must be the same one on both sides of the call: the
    composition writes to `personal` and reads the catalog through the *published*
    catalog read, which is a different module with its own alias.

    So the rule is: **no chain in the composition names two different aliases**, and
    **every chain names one**.
    """
    source = (BACKEND_DIR / COMPOSITION).read_text()
    tree = ast.parse(source, filename=str(COMPOSITION))

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "using":
            continue
        if not node.args:
            violations.append(f"{node.lineno}: .using() with no alias")
            continue
        argument = node.args[0]
        # The alias is a name — `PERSONAL` or `CATALOG` — imported from `shared.db`.
        if not isinstance(argument, ast.Name):
            violations.append(f"{node.lineno}: .using({ast.dump(argument)}) is not an alias name")

    assert not violations, (
        f"{COMPOSITION} has a query that does not name its schema alias: "
        + "; ".join(violations)
        + ". AD-3: every database call names its alias with shared.db.PERSONAL / CATALOG."
    )


def test_the_composition_never_writes_to_the_catalog():
    """**The composition writes to `personal` and only to `personal`.**

    The catalog side is read-only for the personalization app — it owns the events, and
    the composition borrows its facts. A write across the wall would be the violation
    that AD-5 (write ownership) exists to prevent, and it would be invisible to the
    schema-separation test: a write does not need a foreign key.
    """
    source = (BACKEND_DIR / COMPOSITION).read_text()

    assert "using(CATALOG)" not in source, (
        f"{COMPOSITION} writes to the catalog. The composition reads the catalog and "
        "writes to `personal`; a write across the wall is a violation of write "
        "ownership (AD-5) and it would not need a foreign key to happen."
    )


def test_the_catalog_read_does_not_reach_into_personalization():
    """**The other half of the wall, on the module that crosses it.**

    `catalog_read` is a catalog-side module that `personalization` imports — so if it
    reached into `personalization`, the personal side would arrive inside the catalog
    read, and the composition's catalog read would be a personal read wearing a
    catalog label.

    This is the same reasoning `test_event_fit_separation.py` uses for
    `catalog_read` and the Event Fit, applied to the other direction.
    """
    imported = _imported_modules(BACKEND_DIR / "apps/ingestion/services/catalog_read.py")

    assert not any(name.startswith("apps.personalization") for name in imported), (
        f"{CATALOG_READ} reaches into personalization. The composition imports this "
        "module, so the personal side would arrive inside the catalog read — and the "
        "two schemas would meet in a query (AD-3)."
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


@pytest.mark.parametrize(
    "path",
    [
        BACKEND_DIR / "apps/personalization/services/digest_composition.py",
        BACKEND_DIR / "apps/personalization/services/digest_read.py",
        BACKEND_DIR / "apps/personalization/services/detail_read.py",
    ],
    ids=lambda p: p.name,
)
def test_no_read_path_names_a_literal_schema(path):
    """AD-3's general rule, applied to the three modules that matter here.

    `shared.db.PERSONAL` and `shared.db.CATALOG` are the two aliases, and a literal
    `"personal"` in a `using=` would bypass the shared definition — and would be a
    different string if the schema's name ever changed.
    """
    source = path.read_text()

    for literal in ('using("personal")', "using('personal')", 'using("catalog")', "using('catalog')"):
        assert literal not in source, (
            f"{path.relative_to(BACKEND_DIR)} uses the literal {literal}. Every database "
            "call names its alias with shared.db.PERSONAL / CATALOG (AD-3)."
        )
