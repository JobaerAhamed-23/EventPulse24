"""AD-3: every database call names its alias with shared.db.PERSONAL / CATALOG.

`default` silently means personal, so an alias-less transaction or a literal alias name is a
bug waiting for the second schema.
"""

import pytest

from tests.architecture.checkers import BACKEND_DIR, alias_violations, project_files


@pytest.mark.parametrize("path", project_files(), ids=lambda p: str(p.relative_to(BACKEND_DIR)))
def test_project_file_names_its_database_alias(path):
    assert alias_violations(path.read_text()) == []


@pytest.mark.parametrize(
    "source",
    [
        "with transaction.atomic():\n    pass\n",
        "with atomic():\n    pass\n",
        "@transaction.atomic\ndef f():\n    pass\n",
        "@atomic\ndef f():\n    pass\n",
        "transaction.on_commit(send)\n",
        'with transaction.atomic(using="personal"):\n    pass\n',
        'transaction.on_commit(send, using="catalog")\n',
        "with transaction.atomic(using=None):\n    pass\n",
        'Event.objects.using("catalog").all()\n',
        'cursor = connections["default"].cursor()\n',
        "from django.db import connection\n",
        'user.save(using="default")\n',
    ],
)
def test_forbidden_form_reported(source):
    assert len(alias_violations(source)) == 1


@pytest.mark.parametrize(
    "source",
    [
        "with transaction.atomic(using=CATALOG):\n    pass\n",
        "@transaction.atomic(using=PERSONAL)\ndef f():\n    pass\n",
        "transaction.on_commit(send, using=CATALOG)\n",
        "Event.objects.using(CATALOG).all()\n",
        "cursor = connections[CATALOG].cursor()\n",
        "for alias in connections:\n    connections[alias].close()\n",
        "from django.db import connections, transaction\n",
    ],
)
def test_explicit_alias_not_reported(source):
    assert alias_violations(source) == []
