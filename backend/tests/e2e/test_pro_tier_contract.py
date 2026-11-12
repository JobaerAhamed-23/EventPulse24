"""The contract this intent added: every endpoint, by name, in the published document.

**Why this enumerates routes rather than comparing hashes.** The repo already has four
contract tests that assert "the generated client is in sync with the document", and every
one of them would stay green if a route were **deleted** — the client would simply be
regenerated without it, and both sides would agree about an API that had quietly lost a
feature. Naming the paths is what makes a disappearance fail.

**The verbs are part of the contract, not an accident of implementation.** `/api/exports`
is `POST` only; there is no `DELETE`, because an export expires on its own and a client that
could delete one could delete somebody's evidence. `/api/personal/collections/order` is
`PUT` and takes the whole ordering, so the server never observes a partially reordered list.
Each entry below is a statement about what the API offers *and* what it deliberately does
not.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
FRONTEND = REPO / "frontend"

#: The OpenAPI document the frontend's client is generated from.
OPENAPI = FRONTEND / "lib/api/openapi.json"

#: The generated TypeScript types.
SCHEMA = FRONTEND / "lib/api/schema.ts"

#: Every path this intent put on the contract, with the verbs it offers.
#:
#: **The absences are deliberate and are asserted below.** No `DELETE /api/exports/{id}`:
#: an export expires on its own, and a client that could delete one could destroy a user's
#: own copy of their data. No `POST /api/billing/subscription`: entitlement is granted by a
#: webhook and by nothing a browser can call.
INTENT_PATHS: dict[str, set[str]] = {
    # FR-48 — the paid path.
    "/api/billing/checkout": {"post"},
    "/api/billing/portal": {"post"},
    "/api/billing/subscription": {"get"},
    "/api/billing/account": {"get"},
    "/api/webhooks/billing": {"post"},
    # FR-49 — named collections.
    "/api/personal/collections": {"post", "get"},
    "/api/personal/collections/order": {"put"},
    "/api/personal/collections/{collection_id}": {"patch", "delete"},
    "/api/personal/collections/{collection_id}/events": {"get"},
    "/api/personal/collections/{collection_id}/events/{saved_event_id}": {"put", "delete"},
    # FR-52 — download my data.
    "/api/exports": {"post"},
    "/api/exports/{export_id}": {"get"},
    "/api/exports/{export_id}/{fmt}": {"get"},
}

#: The refusal codes this intent's gates answer with. Each is a 409 carrying
#: `{cap, upgrade_hint}` and no modal-shaped field — one inline prompt renders all four.
CAP_CODES = (
    "save_cap_reached",
    "calendar_cap_reached",
    "quiet_hours_pro_required",
    "collections_pro_required",
)


def _executable(name: str) -> str:
    """The full path to an executable, or a failure that says so (ruff S607)."""
    found = shutil.which(name)
    if found is None:
        pytest.fail(f"{name} is not on PATH")
    return found


def _document() -> dict:
    assert OPENAPI.exists(), f"{OPENAPI} is missing: run `make client`"
    return json.loads(OPENAPI.read_text())


class TestTheIntentsEndpointsAreOnTheContract:
    """Every path, by name. A route that vanishes fails here and nowhere else."""

    @pytest.mark.parametrize("path", sorted(INTENT_PATHS))
    def test_the_path_is_published(self, path):
        document = _document()

        assert path in document["paths"], (
            f"{path} is not in the published document. If it was renamed, the frontend's "
            "client no longer has it; if it was removed, the client was regenerated "
            "without it and every whole-document contract test still passed."
        )

    @pytest.mark.parametrize("path,verbs", sorted(INTENT_PATHS.items()))
    def test_the_path_offers_exactly_the_verbs_it_should(self, path, verbs):
        """**Both directions.** A missing verb is a lost feature; an extra one is a
        surface nobody designed — and on these paths, one that could destroy user data."""
        document = _document()
        published = {
            verb
            for verb in document["paths"].get(path, {})
            if verb in {"get", "post", "put", "patch", "delete"}
        }

        assert published == verbs, f"{path} offers {sorted(published)}, expected {sorted(verbs)}"

    def test_an_export_cannot_be_deleted_through_the_api(self):
        """An export expires on its own. A client that could delete one could destroy a
        user's own copy of their data before they collected it."""
        document = _document()

        for path in ("/api/exports/{export_id}", "/api/exports/{export_id}/{fmt}"):
            assert "delete" not in document["paths"].get(path, {})

    def test_entitlement_cannot_be_written_from_a_browser(self):
        """**The property the whole intent rests on.** Only the webhook grants Pro; the
        read-only endpoints are read-only on the contract, not merely by convention."""
        document = _document()

        for path in ("/api/billing/subscription", "/api/billing/account"):
            published = set(document["paths"].get(path, {}))
            assert published & {"post", "put", "patch", "delete"} == set()


class TestTheRefusalsAreOnTheContract:
    """The four caps answer with one shape, so one inline prompt renders all of them."""

    @pytest.mark.parametrize("code", CAP_CODES)
    def test_the_frontend_knows_this_cap_code(self, code):
        """`CAP_CODES` in `lib/cap-details.ts` is what turns a refusal into the prompt.
        A backend code the frontend has never heard of falls back to a generic error
        line — the refusal still happens, and the upgrade path silently disappears."""
        cap_details = (FRONTEND / "lib/cap-details.ts").read_text()

        assert f'"{code}"' in cap_details


class TestTheGeneratedClientIsInSync:
    def test_regenerating_the_client_changes_nothing(self):
        """**`make client` is the contract; this is the measurement.**

        The question is not "does git show a diff" but *"does regenerating change
        anything?"* If it does, the checked-in types are not what the generator produces
        and the frontend is reading shapes the API does not send. The file is restored
        afterwards, so the test leaves the tree exactly as it found it.
        """
        before = SCHEMA.read_text()

        result = subprocess.run(  # noqa: S603 - executable resolved via shutil.which
            [
                _executable("pnpm"),
                "exec",
                "openapi-typescript",
                "lib/api/openapi.json",
                "--output",
                "lib/api/schema.ts",
            ],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            after = SCHEMA.read_text()
            assert result.returncode == 0, result.stderr
            assert after == before, (
                "schema.ts is not what openapi-typescript produces from openapi.json. "
                "Run `make client` and commit the result."
            )
        finally:
            SCHEMA.write_text(before)

    @pytest.mark.parametrize("path", sorted(INTENT_PATHS))
    def test_the_client_carries_the_path(self, path):
        """The document and the client are two artefacts, and only one of them is what the
        frontend actually imports."""
        schema = SCHEMA.read_text()

        assert f'"{path}"' in schema, f"{path} is missing from the generated client"
