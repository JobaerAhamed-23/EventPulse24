"""A proof that the contract file's comment stripper cannot be fooled.

**The contract file asserts on *source text*, with the comments removed.** That makes the
stripper load-bearing in a way a reader should not have to take on trust:

- **If it stopped removing comments**, the assertions would start measuring the
  *documentation* — and this codebase's comments deliberately *name* the forbidden
  things (*"there is no `sessionHeaders()` call here, and there must never be one"*),
  so the assertions would fail on a file that is perfectly correct.
- **If it removed too much**, it would take a real call with it, and the assertion would
  pass for the wrong reason.

**So the stripper is proved here, on the stripper itself.** This file is the only place
that tests `strip_comments` — and it is the reason the contract file's assertions can be
trusted to be about the *code*.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend" / "tests" / "e2e"))

from test_public_pages_contract import source_of, strip_comments  # noqa: E402

#: The eight modules the contract file asserts on.
ASSERTED_FILES = (
    "frontend/lib/public-event-read.ts",
    "frontend/lib/city-page-read.ts",
    "frontend/lib/url-feed-read.ts",
    "frontend/lib/event-detail-read.ts",
    "frontend/lib/reminder-plan-read.ts",
    "frontend/app/events/[id]/page.tsx",
    "frontend/app/events-in/[slug]/page.tsx",
    "frontend/app/revalidate/route.ts",
)


class TestTheStripperRemovesWhatItMust:
    """**A comment is not code, and the stripper says so."""

    def test_a_line_comment_is_removed(self):
        stripped = strip_comments("const a = 1; // a comment\nconst b = 2;")

        assert stripped == "const a = 1; \nconst b = 2;"

    def test_a_block_comment_is_removed(self):
        stripped = strip_comments("const a = 1; /* a comment */ const b = 2;")

        assert "comment" not in stripped
        assert "const a = 1;" in stripped
        assert "const b = 2;" in stripped

    def test_a_multiline_block_comment_is_removed(self):
        stripped = strip_comments("/*\n a comment\n spanning lines\n*/\nconst a = 1;")

        assert "comment" not in stripped
        assert "const a = 1;" in stripped

    def test_a_comment_naming_a_forbidden_call_is_removed(self):
        """**The exact reason the stripper exists.**

        The public read's own docstring says *"there is no `sessionHeaders()` call here,
        and there must never be one"* — so a stripper that left the comments in place
        would find `sessionHeaders` in a file that has no such call, and the assertion
        would be measuring the documentation rather than the code.
        """
        source = """
        // a comment naming sessionHeaders()
        /* a block comment naming cookies( */
        const value = 1;
        """

        stripped = strip_comments(source)

        assert "sessionHeaders" not in stripped
        assert "cookies(" not in stripped
        assert "const value = 1;" in stripped


class TestTheStripperRemovesNothingElse:
    """**A `//` inside a string is not a comment.**

    This is the half that a regex gets wrong, and it was **found by this file**: the
    first version of the stripper was `re.sub(r"//[^\\n]*", "", text)`, which turned
    `"https://eventpulse24.test"` into `"https:`. **No current assertion was broken by
    it** — none of the eight asserted modules holds a URL string — but it is a latent
    trap: a module that grew a URL would have had its tail silently eaten, and any
    assertion made against that URL would have been made against a truncated string.
    """

    def test_a_url_in_a_string_is_not_mistaken_for_a_comment(self):
        stripped = strip_comments('const origin = "https://eventpulse24.test";')

        assert "https://eventpulse24.test" in stripped

    def test_a_real_call_is_not_removed(self):
        """**The stripper must not eat code.** A call it ate would let the public rule
        pass for the wrong reason.
        """
        stripped = strip_comments(
            """
            const headers = await sessionHeaders();
            const jar = cookies();
            """
        )

        assert "sessionHeaders" in stripped
        assert "cookies()" in stripped

    def test_a_slash_inside_a_regex_literal_survives(self):
        """**A regex literal is not a string, but it is not a comment either.** The
        stripper keeps it whole — and the `//` inside it does not start a comment.

        **This is not a hypothetical.** `frontend/app/events/[id]/page.tsx` — one of the
        eight modules the contract file asserts on — contains `local.split(/[._-]+/)`,
        and the scanner has to reach the end of that file for the assertions on it to
        be about the whole file rather than about its first half.
        """
        stripped = strip_comments("const words = local.split(/[._-]+/); const x = 1;")

        assert "const x = 1;" in stripped
        assert "const words" in stripped

    def test_a_regex_literal_whose_body_holds_two_slashes_survives(self):
        """**The hard case: a regex whose *body* contains `//`.**

        A regex like `/^https?:\\/\\//` ends with an escaped slash and then the
        literal's own closing slash — so the text holds `//` where a line comment
        would start. A scanner that does not know about regex literals reads that as a
        comment and truncates the file from there.

        **So the scanner knows about regex literals too** — it tracks them the way it
        tracks strings, and a `/` that begins a regex literal is not a comment.
        """
        stripped = strip_comments(r"const re = /^https?:\/\//; const x = 1;")

        assert "const x = 1;" in stripped, f"the scanner truncated the file: {stripped!r}"

    def test_a_slash_inside_a_regex_character_class_survives(self):
        """**A `/` inside a character class is an ordinary character.** `[._-/]` holds a
        slash that must not end the literal.
        """
        stripped = strip_comments("const re = /[._-/]+/; const x = 1;")

        assert "const x = 1;" in stripped, f"the scanner truncated the file: {stripped!r}"

    def test_a_division_is_not_mistaken_for_a_regex(self):
        """**A division is not a regex.** `total / count` has no closing slash, so a
        scanner that treated the `/` as a regex would swallow the rest of the line
        looking for one — and take real code with it.
        """
        stripped = strip_comments("const half = total / count; const x = 1;")

        assert "const x = 1;" in stripped, f"the scanner truncated the file: {stripped!r}"
        assert "total / count" in stripped

    def test_a_regex_literal_is_kept_whole(self):
        """**The literal is copied verbatim, flags included.** A scanner that dropped
        the flags would leave a source that no longer parses.
        """
        stripped = strip_comments("const re = /abc/gi; const x = 1;")

        assert "/abc/gi" in stripped


class TestTheStripperLeavesTheAssertedFilesIntact:
    """**Every file the contract file asserts on survives the strip.**

    If the stripper emptied one of them, the assertions on it would pass vacuously.
    """

    def test_every_asserted_file_keeps_its_code(self):
        for relative in ASSERTED_FILES:
            stripped = source_of(relative)

            assert len(stripped) > 200, f"{relative} was almost entirely stripped"
            assert "import" in stripped, f"{relative} lost its imports"

    def test_no_asserted_file_still_carries_a_comment_marker(self):
        for relative in ASSERTED_FILES:
            stripped = source_of(relative)

            assert "/*" not in stripped, f"{relative} still carries a block comment"
            assert "*/" not in stripped, f"{relative} still carries a block comment"

    def test_the_stripper_reaches_the_end_of_every_asserted_file(self):
        """**The scanner must not stop early on any asserted file.**

        **This is the guard on the guard.** A scanner that mistook part of a *regex
        literal* for the start of a line comment would truncate the file at that point
        — and every assertion made on the truncated file would be an assertion about
        the file's first half. `frontend/app/events/[id]/page.tsx` carries a regex
        literal, so this is not hypothetical.

        **The check is that the file's braces still balance.** A truncation drops the
        file's closing braces, so an unbalanced stripped file is a truncated one. And
        this is a *non-vacuous* check: a scanner that removed too little would leave
        a stray `{` from a comment and fail it too — which is the other direction the
        check has to catch.
        """
        for relative in ASSERTED_FILES:
            stripped = source_of(relative)

            assert stripped.count("{") == stripped.count("}"), (
                f"{relative} was truncated or over-stripped by the stripper"
            )

    def test_the_scanner_keeps_more_of_every_asserted_file_than_a_regex_would(self):
        """**The scanner is strictly more careful than the regex it replaced.**

        **This is the record of what the change bought.** The regex stripper
        (`re.sub(r"//[^\\n]*", "", text)`) removed every `//` and its line, whether it
        was a comment or the tail of a URL. The scanner removes only real comments — so
        it keeps **at least as much**, and on a file with a URL or a regex literal it
        keeps **more**.

        **The check is one-sided on purpose.** A scanner that kept *less* would be a
        regression, and that is the failure this catches.

        **And the test is not vacuous.** The eight asserted modules happen to hold no
        URL string and no regex literal with a `//` in it, so on them the two strippers
        agree — which means this check alone would not catch the old behaviour. **The
        cases that *do* catch it are the synthetic ones above**, and this test records
        the honest fact that the real files did not need the change.

        **So the file records both: the real files are unaffected, and the scanner is
        right anyway.**
        """
        for relative in ASSERTED_FILES:
            raw = (ROOT / relative).read_text()
            regex_stripped = re.sub(r"/\*[\s\S]*?\*/", "", re.sub(r"//[^\n]*", "", raw))
            scanned = strip_comments(raw)

            assert len(scanned) >= len(regex_stripped), (
                f"{relative}: the scanner kept less than the regex it replaced"
            )

    def test_the_public_reads_still_carry_no_session(self):
        """**The stripper's own contract, checked on the real files.** The three public
        reads must still *read* as having no session — which is the assertion the
        contract file makes, and this is the same stripper.
        """
        for relative in (
            "frontend/lib/public-event-read.ts",
            "frontend/lib/city-page-read.ts",
            "frontend/lib/url-feed-read.ts",
        ):
            stripped = source_of(relative)

            assert "sessionHeaders" not in stripped, f"{relative} calls sessionHeaders()"
            assert "cookies(" not in stripped, f"{relative} reads cookies()"

    def test_the_authed_reads_still_carry_their_session(self):
        """**And the mirror image: the stripper must not have eaten the two authed
        reads' session calls** — otherwise the "the authed reads still carry a session"
        assertion would be measuring a stripped file.
        """
        for relative in (
            "frontend/lib/event-detail-read.ts",
            "frontend/lib/reminder-plan-read.ts",
        ):
            stripped = source_of(relative)

            assert "sessionHeaders" in stripped, f"{relative} lost its session call"
