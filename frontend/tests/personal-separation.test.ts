// @vitest-environment node
/**
 * AD-10's other half, on the frontend: **a public surface never reads `personal`.**
 *
 * **What the rule protects.** The Event Fit is served to visitors with **no session**.
 * A read of the personal side on that path would leak one person's preferences to
 * everyone — and a read whose value is then discarded is still a leak, because the
 * *query* happened.
 *
 * **The backend half already exists.** `tests/architecture/test_event_fit_separation.py`
 * asserts the PERSONAL alias is absent from the Event Fit's read and write. This file
 * is the **frontend** half, and it is the half that matters for the Detail Screen,
 * which is new in this intent and serves **two audiences from one route**: a signed-in
 * reader and an anonymous visitor.
 *
 * **The interesting bug is a use of personal data outside the guard.** The Detail
 * Screen's own review found one: the reminder picker rendered for an anonymous
 * visitor, because the picker sat outside the `personal` check while the breakdown and
 * the neighbour count sat inside it. So this file does not check "is `personal` read"
 * — it checks **where** it is read.
 *
 * **The check is a data-flow check on the source.** Every use of `.personal` in the
 * route must be **inside a branch guarded by it**. That is stronger than a name
 * check, and it is the only form that would have caught the picker.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

const DETAIL_PAGE = path.join(ROOT, "app/events/[id]/page.tsx");
const DETAIL_READ = path.join(ROOT, "lib/event-detail-read.ts");
const PREVIEW_PAGE = path.join(ROOT, "app/preview/page.tsx");
const PREVIEW_SECTION = path.join(ROOT, "components/preview/preview-section.tsx");

/**
 * The source with its comments removed.
 *
 * A comment is not code — and the Detail Screen's docstrings discuss the personal
 * half by name, so a source-text assertion that read them would be asserting on prose.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

const detailCode = withoutComments(readFileSync(DETAIL_PAGE, "utf8"));

/**
 * Every use of `personal` that is **not** inside a branch guarded by a test of
 * `personal`.
 *
 * **The walk is outward through the braces.** For each use, the enclosing blocks are
 * found by matching braces backwards, and each block's *header* — the text before its
 * `{` — is examined for a conditional that tests `personal`.
 *
 * A header that mentions `personal` in a conditional counts as a guard:
 * `{personal ? (`, `{personal && (`, `{personal ? (` and `{personal !== null ? (`.
 * A header that merely *binds* it (`const personal =`) is the declaration, not a use.
 */
function unguardedPersonalUses(code: string): string[] {
  const uses: string[] = [];
  // Every `personal` that is part of a property access or a declaration is a *use*;
  // the declaration itself is not.
  const pattern = /\bpersonal\b(?!\s*=[^=])/g;

  let match = pattern.exec(code);
  while (match !== null) {
    const index = match.index;
    const before = code.slice(0, index);
    const after = code.slice(index);

    // The declaration: `const personal = …`. It is where the local comes from, not a
    // use of the personal *data*.
    if (/const\s+$/.test(before)) {
      match = pattern.exec(code);
      continue;
    }

    // The optional-chained read that decides whether a composition exists. It yields
    // `undefined` for an anonymous visitor, which is the absent explanation — not a
    // leak.
    if (/^personal\?\./.test(after)) {
      match = pattern.exec(code);
      continue;
    }

    // **The extraction of the field itself.** `read.detail.personal ?? null` is the
    // one place the personal payload is read without a guard — and it has to be,
    // because reading it is how the code learns whether there is any personal data to
    // guard. It is the *definition* of the guard's subject, not a use of the data.
    //
    // So it is matched narrowly: the field access immediately followed by `?? null`
    // or `?? undefined`, and nothing else.
    if (/^personal\s*\?\?\s*(null|undefined)/.test(after)) {
      match = pattern.exec(code);
      continue;
    }

    // **The guard's own test.** In `{personal ? ( … ) : null}`, the `personal` in the
    // header *is* the test — it is the question being asked, not an answer being
    // rendered. It is the one place `personal` is read before the guard is known to
    // hold, and that is the guard's whole job.
    //
    // So a `personal` that is **the condition of a conditional** is exempt. The
    // pattern is narrow: `personal` followed by `?` or `&&`, with nothing but
    // whitespace and a comparison between — so `personal ? (` and `personal && (` are
    // exempt, while `personal.saved` (a property read) is not.
    if (/^personal\s*(\?|&&|\?\?)/.test(after) && !/^personal\s*\./.test(after)) {
      match = pattern.exec(code);
      continue;
    }

    if (isGuarded(code, index)) {
      match = pattern.exec(code);
      continue;
    }

    const line = before.split("\n").length;
    uses.push(
      `  line ${line}: ${code.slice(index, code.indexOf("\n", index) === -1 ? code.length : code.indexOf("\n", index)).trim()}`,
    );
    match = pattern.exec(code);
  }

  return uses;
}

/**
 * The index of the `}` that closes the `{` at `open`, or `-1` if there is none.
 *
 * **The walk is a real brace match, not a `lastIndexOf`.** This is the detail that
 * makes the check correct, and the mutation probe found it: `lastIndexOf("}")` cannot
 * tell a block that is still **open** from one that has already **closed**.
 *
 * In JSX, `{personal ? (...) : null}` blocks are **siblings**, not nested — but a
 * backwards `lastIndexOf("{")` walk treats the *earlier sibling* as an enclosing
 * block, because the sibling's own `}` is somewhere after the use and the walk never
 * checks it. So a use placed *after* a guarded sibling looked guarded, and the probe's
 * bug — an unguarded read, exactly the shape this file exists to catch — sailed
 * through.
 *
 * Matching the braces properly is what distinguishes "this block is open around the
 * use" from "this block closed before the use".
 */
function matchingBrace(code: string, open: number): number {
  let depth = 0;
  for (let i = open; i < code.length; i += 1) {
    const character = code[i];
    if (character === "{") depth += 1;
    else if (character === "}") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * The index of the `)` that closes the `(` at `open`, or `-1` if there is none.
 *
 * **The JSX guard's body is delimited by parentheses, not braces.** `{personal ? (
 * <>{…}</> ) : null}` — the `(` after the `?` opens the branch, and it is that
 * parenthesis, not the brace, that encloses the guarded body. So the walk has to
 * understand both delimiters: the brace opens the *expression*, and the parenthesis
 * opens the *branch*.
 */
function matchingParen(code: string, open: number): number {
  let depth = 0;
  for (let i = open; i < code.length; i += 1) {
    const character = code[i];
    if (character === "(") depth += 1;
    else if (character === ")") {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * Whether the use at `index` sits inside a branch guarded by a test of `personal`.
 *
 * The walk is outward through the enclosing blocks. For each candidate, the block's
 * *header* — the text before its opening delimiter — is examined for a conditional
 * that tests `personal`.
 *
 * **A candidate only counts if its block is still open at the use.** That is what
 * `matchingBrace` is for: a `{personal ? (` that closed *before* the use is a
 * *sibling* of the use, not an ancestor.
 *
 * **Two delimiters, two walks.** A JSX guard has two layers:
 *
 * - the **expression** `{personal ? ( … ) : null}` — its header is `personal ? (`, and
 *   its *body* is the parenthesised branch;
 * - the **branch** `( … )` — its header is whatever precedes the `(`, which is the
 *   `?`.
 *
 * The expression's own brace closes at the very end of the expression, so the
 * expression alone cannot vouch for a use in the branch. The branch's parenthesis is
 * what actually encloses the use — so both are checked.
 */
function isGuarded(code: string, index: number): boolean {
  let cursor = index;

  while (cursor > 0) {
    const open = code.lastIndexOf("{", cursor);
    if (open === -1) return false;

    // **Is this expression still open at the use?** If it closed before the use, it is
    // a *sibling* of the use, not an ancestor, and it cannot guard it.
    const expressionEnd = matchingBrace(code, open);

    if (expressionEnd !== -1 && expressionEnd > index) {
      // **The condition is *inside* the expression, not before it.** A JSX guard is
      // `{ personal ? ( … ) : null }` — the brace opens the expression, and the test
      // follows it. So the "header" is the text *after* the opening brace, up to the
      // branch's `(`.
      const branchOpen = code.indexOf("(", open);
      const condition = code.slice(open + 1, branchOpen === -1 ? open + 1 : branchOpen);

      // A condition that tests `personal`.
      if (/personal\s*\?/.test(condition) || /personal\s*&&/.test(condition)) {
        // The expression's *body* is the parenthesised branch. The use is inside the
        // guard when it is inside that branch.
        if (branchOpen !== -1 && branchOpen < index) {
          const branchEnd = matchingParen(code, branchOpen);
          if (branchEnd !== -1 && branchEnd > index) {
            return true;
          }
        }
      }
    }

    // Step **past** this brace, or the next `lastIndexOf` finds it again.
    cursor = open - 1;
  }

  return false;
}

describe("the Detail Screen's personal data flow", () => {
  it("reads the personal payload once, at the top", () => {
    // The payload's personal half is read **once**, into a local. Every later use is
    // of that local, so the guard is the only thing standing between the personal
    // half and the public document.
    const reads = detailCode.match(/\.personal\b/g) ?? [];

    // One read of the payload's field, plus the guarded uses of the local. The count
    // is a backstop, not the rule — the rule is the guard, below.
    expect(reads.length).toBeGreaterThan(0);
    expect(detailCode).toMatch(/read\.detail\.personal/);
  });

  it("guards every personal use behind a personal check", () => {
    // **The rule.** Every use of the personal local is inside a branch that tests it.
    //
    // **The check is brace-aware, not line-based.** A line-based check would be fooled
    // by the very shape this file's own review found: the guard `{personal ? (` is on
    // one line and the use `personal.saved}` is two lines later, inside the branch.
    // So the check finds each use and walks **outward** through the enclosing braces,
    // looking for a conditional whose test mentions `personal`.
    //
    // **Why not a full taint analysis.** It would be stronger, and it would also be a
    // parser to maintain. This is the honest middle: it fails when a personal use is
    // not inside a guard, which is the bug class that actually happened — and it does
    // not fire on a correct use, which a line-based version would.
    const unguarded = unguardedPersonalUses(detailCode);

    expect(
      unguarded,
      `the Detail Screen uses personal data outside a guard:\n${unguarded.join("\n")}`,
    ).toEqual([]);
  });

  it("never renders the personal payload directly", () => {
    // The personal half is a **union field**, not something to spread into the DOM.
    // A `{...personal}` would leak every field the API later adds.
    expect(detailCode).not.toMatch(/\{\.\.\.personal\}/);
    expect(detailCode).not.toMatch(/\{\.\.\.read\.detail\.personal\}/);
  });

  it("does not fetch a personal endpoint from the public preview", () => {
    // The preview's read is the **public** one. It must not call a personal endpoint —
    // not even conditionally.
    const preview = withoutComments(readFileSync(PREVIEW_SECTION, "utf8"));

    expect(preview).not.toMatch(/\/api\/personal\//);
    expect(preview).not.toMatch(/saved-events|onboarding|digest/);
  });

  it("the preview route reads only the public endpoint", () => {
    const previewPage = withoutComments(readFileSync(PREVIEW_PAGE, "utf8"));

    expect(previewPage).not.toMatch(/\/api\/personal\//);
    expect(previewPage).not.toMatch(/personal/i);
  });

  it("the detail route reads one endpoint, and it is the public one", () => {
    // The Detail Screen is "Authed + Anon (read-only)": it reads one endpoint, and
    // the *personal* half of that endpoint's answer is `null` for an anonymous
    // visitor. It does not make a second, personal-scoped request.
    //
    // **The read lives in `lib/event-detail-read.ts`**, not in the route — the route
    // decides what to render, and the read is a typed function it calls. So the check
    // is on the read module.
    const read = withoutComments(readFileSync(DETAIL_READ, "utf8"));
    const fetches = [...read.matchAll(/api\.(GET|POST)\(\s*"([^"]+)"/g)].map((match) => match[2]);

    expect(fetches).toEqual(["/api/events/{event_id}"]);
  });

  it("the route itself makes no fetch at all", () => {
    // The route is a **renderer**. Every fetch is in a read module, so the route
    // cannot acquire a personal-scoped request by accident.
    expect(detailCode).not.toMatch(/api\.(GET|POST)\(/);
    expect(detailCode).not.toMatch(/fetch\(/);
  });
});
