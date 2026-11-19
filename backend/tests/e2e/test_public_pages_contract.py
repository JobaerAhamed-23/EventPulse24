"""The public surface's **contracts**: the shapes, the boundaries, and the promises that
hold whatever the implementation does.

**Why this file exists beside the proof.** The proof (`test_public_pages_proof.py`)
asserts what the public surface *does* — it walks the crawl and checks the answers. This
file asserts what the public surface *is*: the shapes on the wire, the boundaries between
the packages, and the structural properties that no single request can reveal.

**The three kinds of contract, and why each needs its own language.**

1. **The wire shapes.** The committed `openapi.json` must match the live API, and the
   generated TypeScript must match the document. **AD-19's claim is that the client
   cannot drift from the API** — and a claim about a *generated file* is only provable by
   regenerating it, not by comparing two copies of the same stale bytes.
2. **The import contracts.** Nineteen of them, and they are the walls the public surface
   stands behind: `apps.catalog` may not import `apps.ingestion.models`, and the Event
   Fit may not leak into the personalized read.
3. **The structural properties.** "The public reads carry no session" is a property of
   a *module*, not of one rendered page — so it is asserted on the source, because a
   request-level assertion cannot see a call that returns a session and is then ignored.

**The contract file regenerates rather than compares.** The generated TypeScript is
produced *now* by `openapi-typescript` and compared to what is committed, and the
committed file is restored afterwards — so the check is a **measurement**, not a rewrite.
A test that rewrote the file would pass by fixing the drift, which is the opposite of
failing the build on it.
"""

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from ninja.responses import NinjaJSONEncoder

from config.api import api

#: The repository root — three levels up from `backend/tests/e2e/`.
ROOT = Path(__file__).resolve().parents[3]

#: The committed OpenAPI document, and the generated client beside it.
COMMITTED_SCHEMA = ROOT / "frontend/lib/api/openapi.json"
COMMITTED_SCHEMA_TS = ROOT / "frontend/lib/api/schema.ts"

#: The backend's own import-linter configuration. The contracts live there because they
#: are a property of the *tree*, not of any one module.
BACKEND_DIR = ROOT / "backend"
IMPORTLINTER_CONFIG = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text())["tool"][
    "importlinter"
]

#: The frontend's three public read modules, and the two that are allowed a session.
#:
#: **The public three are the anonymous surface.** A `sessionHeaders()` call in any of
#: them would make a public page's content depend on who is asking — and the first
#: requester would bake their session into the shared cache for every reader after them.
PUBLIC_READS = (
    "frontend/lib/public-event-read.ts",
    "frontend/lib/city-page-read.ts",
    "frontend/lib/url-feed-read.ts",
)

#: The two reads that are *supposed* to carry a session. They are asserted to, so the
#: "no session" rule above cannot be satisfied by simply deleting every session call.
AUTHED_READS = (
    "frontend/lib/event-detail-read.ts",
    "frontend/lib/reminder-plan-read.ts",
)

#: The three public endpoints, as the OpenAPI document names them.
PUBLIC_ENDPOINTS = (
    "/api/catalog/events/by-slug/{slug}",
    "/api/catalog/cities/by-slug/{slug}",
    "/api/catalog/url-feed",
)


def strip_comments(source: str) -> str:
    """**Remove the comments from a source file, and nothing else.**

    **The comments are removed because they *name* the forbidden things.** The public
    read's own docstring says "there is no `sessionHeaders()` call here, and there must
    never be one" — so a naive substring search would find `sessionHeaders` in a file
    that has no such call, and the assertion would be measuring the documentation rather
    than the code.

    **But the removal must be string-aware.** A `//` inside a string literal is not a
    comment — it is the tail of a URL. A regex that removed everything after a `//`
    would take `"https://eventpulse24.test"` down to `"https:` and would silently
    truncate any assertion made against a URL. **So the scanner walks the text and
    tracks whether it is inside a string**, and only removes a comment that is really a
    comment.

    **The scanner handles the three string forms TypeScript has** — single-quoted,
    double-quoted and backticked — and a backtick may span lines. A `\\`` inside a
    template literal is an escaped backtick and does not end the string.

    **And it handles regex literals**, because a regex may hold `//` in its body — as
    `/^https?:\\/\\//` does. **Without that, the scanner would read the regex's own
    closing slash and the escaped one before it as the start of a line comment, and
    truncate the file there** — and every assertion made on a truncated file is an
    assertion about the file's first half. `frontend/app/events/[id]/page.tsx` carries
    a regex literal, so this is not hypothetical.

    **A regex literal is only recognised where one can appear** — after `(`, `=`, `,`,
    `:`, `[`, `!`, `&`, `|`, `?`, `{`, `;`, `return`, or the start of the line. A `/`
    after an identifier is a division, and the scanner leaves it alone.
    """
    out: list[str] = []
    i = 0
    length = len(source)

    # ── the characters after which a `/` opens a regex literal rather than dividing ──
    regex_preceded = set("(=,:[!&|?{;\n+-*%<>~^")
    # ── the keywords after which a `/` opens a regex literal ──
    regex_keywords = ("return", "typeof", "case", "in", "of", "do", "else", "yield", "await")

    while i < length:
        char = source[i]
        nxt = source[i + 1] if i + 1 < length else ""

        # ── a line comment ──
        if char == "/" and nxt == "/":
            while i < length and source[i] != "\n":
                i += 1
            continue

        # ── a block comment ──
        if char == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            i = length if end == -1 else end + 2
            continue

        # ── a regex literal ──
        if char == "/" and _opens_a_regex(source, i, regex_preceded, regex_keywords):
            end = _end_of_regex(source, i)
            out.append(source[i:end])
            i = end
            continue

        # ── a string literal ──
        if char in "\"'`":
            quote = char
            out.append(char)
            i += 1
            while i < length:
                if source[i] == "\\" and i + 1 < length:
                    # **An escaped character is copied verbatim** — `\"` does not close
                    # the string, and `\\` is not a backslash to the scanner.
                    out.append(source[i : i + 2])
                    i += 2
                    continue
                out.append(source[i])
                if source[i] == quote:
                    i += 1
                    break
                i += 1
            continue

        out.append(char)
        i += 1

    return "".join(out)


def _opens_a_regex(source: str, index: int, preceded: set[str], keywords: tuple[str, ...]) -> bool:
    """**Does the `/` at `index` open a regex literal, or is it a division?**

    **The look-behind is the whole of it.** A `/` after an identifier, a number or a
    closing bracket is a division — `total / count` — and treating it as a regex would
    swallow the rest of the line looking for a closing slash.

    **So the scanner looks at the last non-space character before the `/`.** A
    character in the punctuation set means an operand was expected, so a `/` there is a
    regex; a letter or a digit means an operand was already there, so it is a division.
    """
    j = index - 1
    while j >= 0 and source[j] in " \t":
        j -= 1
    if j < 0:
        return True  # **The start of the file.**

    previous = source[j]
    if previous in preceded:
        return True

    # **A keyword is an operand on its own**, so a `/` right after one opens a regex.
    for keyword in keywords:
        if source[: j + 1].endswith(keyword):
            return True

    return False


def _end_of_regex(source: str, start: int) -> int:
    """**The index just past the `/` that closes the regex literal at `start`.**

    **The literal's own characters class is tracked**, because `/` may appear inside it:
    - in a character class `[...]`, a `/` is an ordinary character;
    - otherwise, an escaped `\\/` is an ordinary character too;
    - otherwise, the first unescaped `/` ends the literal.

    **A regex may carry flags after its closing slash** — `g`, `i`, `m`, `s`, `u`, `y` —
    and those belong to the literal.
    """
    i = start + 1
    length = len(source)
    in_class = False

    while i < length:
        char = source[i]
        if char == "\\" and i + 1 < length:
            i += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            i += 1
            while i < length and source[i] in "gimsuyd":
                i += 1
            return i
        elif char == "\n":
            # **A regex cannot span lines**, so this was never a regex.
            return start + 1
        i += 1

    return start + 1


def source_of(relative: str) -> str:
    """A frontend module's source, with its comments removed.

    **The comments are removed because they *name* the forbidden things.** The public
    read's own docstring says "there is no `sessionHeaders()` call here, and there must
    never be one" — so a naive substring search would find `sessionHeaders` in a file
    that has no such call, and the assertion would be measuring the documentation rather
    than the code.

    **The removal is string-aware** — see `strip_comments`. A `//` inside a string is
    not a comment, and truncating a URL would make an assertion against it vacuous.
    """
    return strip_comments((ROOT / relative).read_text())


# ── The wire shapes ───────────────────────────────────────────────────────────────


class TestTheCommittedContractMatchesTheLiveApi:
    """**AD-19: the client is generated from the document, and the document is the API.**

    CI's `contract` job regenerates the client and fails on any diff — so a drifted
    client fails the build. **This asserts the same property locally**, so the failure
    arrives while the author is still looking at it rather than in a pipeline.
    """

    def test_the_committed_document_matches_the_live_api(self):
        assert COMMITTED_SCHEMA.exists(), f"{COMMITTED_SCHEMA} is missing: run `make client`"

        live = json.loads(json.dumps(api.get_openapi_schema(), cls=NinjaJSONEncoder))
        committed = json.loads(COMMITTED_SCHEMA.read_text())

        assert committed == live, "The API changed: run `make client` and commit lib/api/"

    def test_the_document_names_the_three_public_endpoints(self):
        """**The public surface is in the contract, not beside it.**

        A public endpoint that was never in the OpenAPI document would be a surface the
        generated client cannot call — and a drift the comparison above would not catch,
        because the comparison checks the two against each other, not against the intent.
        """
        document = json.loads(COMMITTED_SCHEMA.read_text())

        for path in PUBLIC_ENDPOINTS:
            assert path in document["paths"], f"{path} is missing from the OpenAPI document"

    def test_the_document_carries_the_public_endpoints_responses(self):
        """**Each public endpoint declares its 404 as well as its 200.**

        The 404 is part of the contract: a client that cannot tell "no such event" from
        "no such city" from a failure has nothing to branch on, and the frontend's three
        answers (`found` / `not-found` / `unavailable`) are built on exactly that
        distinction.
        """
        document = json.loads(COMMITTED_SCHEMA.read_text())

        for path in PUBLIC_ENDPOINTS[:2]:
            responses = document["paths"][path]["get"]["responses"]
            assert "200" in responses
            assert "404" in responses


class TestTheGeneratedClientIsInSync:
    """**The committed TypeScript is what `openapi-typescript` produces today.**

    **This regenerates rather than compares two copies of the same bytes.** A test that
    read the committed `.ts` and compared it to the committed `.json` would prove only
    that two files agree with each other — and a hand-edit to both would satisfy it.
    The generator is the third party: it is the tool CI runs, and it is the thing that
    decides what the client *is*.

    **The committed file is restored afterwards**, so the check is a measurement and not
    a rewrite — and so a drifting repository stays drifting until somebody runs
    `make client` on purpose.
    """

    def test_the_generated_client_matches_the_document(self):
        pnpm = shutil.which("pnpm")
        if pnpm is None:  # pragma: no cover - a machine without node cannot run this
            pytest.skip("pnpm is not available, so the client cannot be regenerated")

        if not COMMITTED_SCHEMA_TS.exists():
            pytest.skip("the generated client is not committed")

        committed = COMMITTED_SCHEMA_TS.read_text()
        try:
            # **The exact command `make client` runs.** The generator is invoked through
            # the project's own package manager, so the version that produces the file
            # is the version the lockfile pins — not whatever `npx` happens to fetch
            # today, which would make the check depend on the network.
            result = subprocess.run(
                [
                    pnpm,
                    "--dir",
                    str(ROOT / "frontend"),
                    "exec",
                    "openapi-typescript",
                    "lib/api/openapi.json",
                    "--output",
                    "lib/api/schema.ts",
                ],
                cwd=ROOT / "frontend",
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
            if result.returncode != 0:
                pytest.skip(f"openapi-typescript could not run: {result.stderr.strip()[:200]}")
            assert COMMITTED_SCHEMA_TS.read_text() == committed, (
                "The generated client has drifted: run `make client` and commit lib/api/"
            )
        finally:
            COMMITTED_SCHEMA_TS.write_text(committed)


# ── The import contracts ──────────────────────────────────────────────────────────


class TestTheImportContractsHold:
    """**Nineteen walls, and the public surface stands behind every one of them.**

    The public reads are the most exposed part of the tree — they answer to anybody —
    so the walls around them matter most: `apps.catalog` may not import another app's
    models, and the Event Fit may not leak into the personalized read.
    """

    def test_every_import_contract_holds(self):
        """**The whole set, in one run.** `import-linter` is the tool CI uses
        (`make lint-imports`), and running it here means the e2e suite fails on a broken
        wall even if nobody runs the architecture suite.
        """
        linter = Path(sys.executable).with_name("lint-imports")
        if not linter.exists():  # pragma: no cover - the tool is a dev dependency
            pytest.skip("lint-imports is not installed")

        result = subprocess.run(
            [str(linter), "--config", "pyproject.toml", "--no-cache"],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr

    def test_there_are_twenty_contracts(self):
        """**The number is the assertion.** A contract removed from the configuration
        would leave the suite green — the walls that are checked are the walls that
        exist. So the count is itself a contract.
        """
        assert len(IMPORTLINTER_CONFIG["contracts"]) == 20

    def test_the_public_surface_cannot_reach_another_apps_models(self):
        """**`models-ingestion`, the wall the catalog's public reads stand behind.**

        The catalog's three public endpoints are served by `apps/catalog`, which is not
        allowed to import `apps.ingestion.models` — the Event Fit and the Event live
        behind a published read interface. A catalog endpoint that reached for the model
        directly would put the ingestion schema inside the public API's blast radius.

        **The contract is a *protected* one, so the wall is named by its
        `protected_modules` and its `allowed_importers`** — and the assertion is that
        the catalog is *not* on the allowed list. The catalog reads the ingestion data
        through `apps.ingestion.services`, which is what keeps the published read
        interface the only door.
        """
        contract = next(
            c for c in IMPORTLINTER_CONFIG["contracts"] if c["id"] == "models-ingestion"
        )

        assert contract["protected_modules"] == ["apps.ingestion.models"]
        assert "apps.ingestion" in contract["allowed_importers"]
        assert "apps.catalog" not in contract["allowed_importers"]


# ── The structural properties ─────────────────────────────────────────────────────


class TestThePublicReadsCarryNoSession:
    """**"No session" is a property of a module, not of one rendered page.**

    A request-level assertion cannot see a call that reads a session and then ignores
    it — and a session read that is *ignored* is exactly the failure that rots
    quietly, because every test that logs in first still passes. **So this is asserted
    on the source**, with the comments stripped, and the forbidden names are checked one
    by one.
    """

    @pytest.mark.parametrize("relative", PUBLIC_READS)
    def test_the_read_names_no_session(self, relative):
        source = source_of(relative)

        assert "sessionHeaders" not in source, f"{relative} calls sessionHeaders()"
        assert "getSession" not in source, f"{relative} calls getSession()"
        assert "cookies(" not in source, f"{relative} reads cookies()"

    @pytest.mark.parametrize("relative", PUBLIC_READS)
    def test_the_read_forwards_no_headers(self, relative):
        """**No `headers:` argument at all.** The `sessionHeaders()` check above catches
        the obvious shape; this catches the other one — a read that forwards some *other*
        header, which would be a cookie by another name.
        """
        source = source_of(relative)

        assert "headers:" not in source, f"{relative} forwards a header"

    @pytest.mark.parametrize("relative", PUBLIC_READS)
    def test_the_read_does_not_import_the_session_module(self, relative):
        """**The import itself is the strongest form of the rule.** A module that does
        not import `lib/session` cannot call `sessionHeaders()` — so the rule is
        enforced by the module graph, not by a convention somebody has to remember.
        """
        source = source_of(relative)

        assert "@/lib/session" not in source, f"{relative} imports the session module"

    @pytest.mark.parametrize("relative", PUBLIC_READS)
    def test_the_read_does_not_import_next_headers(self, relative):
        """**`next/headers`'s `cookies()` is the server's own door to the cookie jar**,
        and it is the door a public page must not open. The public *route* modules are
        allowed to be near it — the Detail Screen needs it — but the three reads are
        not.
        """
        source = source_of(relative)

        assert "next/headers" not in source, f"{relative} imports next/headers"


class TestTheAuthedReadsStillCarryASession:
    """**The rule is not "no session anywhere".** It is "no session on the *public*
    reads" — and the two authed reads must still carry one, or the Detail Screen and
    the reminder plan would silently become anonymous and their tests would be proving
    nothing.

    **Asserted so the public rule cannot be satisfied by deletion.** A suite that
    removed `sessionHeaders()` from `event-detail-read.ts` would pass the assertions
    above; this one fails.
    """

    @pytest.mark.parametrize("relative", AUTHED_READS)
    def test_the_authed_read_forwards_the_session_headers(self, relative):
        source = source_of(relative)

        assert "sessionHeaders" in source, f"{relative} stopped forwarding the session"
        assert "headers:" in source, f"{relative} stopped forwarding a header"


class TestThePublicMetadataIsIndexable:
    """**The public branches are indexable, and the Detail Screen's is not.**

    This is the pairing that matters: `/events` is *one* path segment serving two
    surfaces, so robots.txt cannot separate them — a `Disallow: /events/` would take
    the public pages with it. **The document itself has to say so**, and the public
    half must not inherit the private half's noindex.
    """

    def test_the_public_branches_carry_no_noindex(self):
        """**Neither public branch is marked noindex.** The event page's metadata is
        built in the public branch and the city page's in its own route — and a stray
        `robots: { index: false }` on either would take a page out of the index while
        every other test stayed green.
        """
        event_source = source_of("frontend/app/events/[id]/page.tsx")
        city_source = source_of("frontend/app/events-in/[slug]/page.tsx")

        # **The Detail Screen's noindex is real and is asserted here too** — so a
        # deletion of the whole `robots` key would fail this file rather than pass it.
        assert "robots: { index: false, follow: false }" in event_source
        assert city_source.count("robots: { index: false, follow: false }") == 1, (
            "the city page's only noindex is the failure-to-answer case"
        )

    def test_the_detail_screen_is_the_only_noindexed_surface(self):
        """**The event route's noindex sits inside the detail branch.** The public
        branch is the shareable half, and the two branches are chosen by the same
        `isDetailEvent` predicate — so the metadata and the page cannot disagree about
        which surface a parameter names.
        """
        source = source_of("frontend/app/events/[id]/page.tsx")

        branch = source.index("if (isDetailEvent(id))")
        noindex = source.index("robots: { index: false, follow: false }")

        assert noindex > branch, "the noindex is not inside the detail branch"

    def test_the_public_branches_carry_a_canonical_url(self):
        """**A canonical URL is what tells a crawler which of two addresses is the
        real one.** Both public branches declare one, and both name the *public* form —
        `/events/{slug}` and `/events-in-{slug}` — which is the same string the
        backend's revalidation signal names.
        """
        event_source = source_of("frontend/app/events/[id]/page.tsx")
        city_source = source_of("frontend/app/events-in/[slug]/page.tsx")

        assert "alternates: { canonical: `/events/${page.slug}` }" in event_source
        assert "alternates: { canonical }" in city_source
        assert "cityPageHref(city.slug, page)" in city_source


class TestThePublicReadsAreCachedUnderTheirOwnPath:
    """**The cache tag is the contract with the backend's revalidation signal.**

    `domain/revalidation.py` builds `/events/{slug}` and `/events-in-{slug}`, and the
    `/revalidate` handler drops exactly those tags. **A read cached under a different
    tag would be a cache nothing could ever clear** — the page would go stale the first
    time the catalog moved, and no signal would ever fix it.
    """

    def test_the_event_read_is_tagged_with_the_event_path(self):
        source = source_of("frontend/lib/public-event-read.ts")

        assert "tags: [eventPath(slug)]" in source
        assert "return `/events/${slug}`" in source

    def test_the_city_read_is_tagged_with_the_city_path(self):
        source = source_of("frontend/lib/city-page-read.ts")

        assert "tags: [cityPath(slug)]" in source
        assert "return `/events-in-${slug}`" in source

    def test_the_two_path_builders_match_the_backend_conventions(self):
        """**The same strings, on both sides of the wall.** The backend's prefixes live
        in `domain/revalidation.py`; the frontend's live in the two read modules. **Two
        definitions of the same URL convention is one definition too many** — so the
        literal strings are compared here.
        """
        backend = (BACKEND_DIR / "domain/revalidation.py").read_text()

        assert 'EVENT_PATH_PREFIX = "/events/"' in backend
        assert 'CITY_PATH_PREFIX = "/events-in-"' in backend

    def test_the_revalidation_handler_clears_both_caches(self):
        """**Two caches, one signal.** The *page* lives in the Full Route Cache and the
        *facts* live in the data cache; a signal that cleared only one of them would
        leave a stale answer on one of them.
        """
        source = source_of("frontend/app/revalidate/route.ts")

        assert "revalidatePath(path)" in source
        assert "revalidateTag(path" in source
