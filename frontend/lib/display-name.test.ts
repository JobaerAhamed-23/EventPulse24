/**
 * The display-name rule — **the stored name if there is one, the address otherwise.**
 *
 * **This file exists because the rule used to live in fifteen places.** Each copy was
 * the same five lines, and the rule had to grow a half when the account gained a name.
 * A rule with two branches that is pasted fifteen times is a rule that can differ from
 * itself in fifteen places, silently.
 *
 * **The fallback is pinned to the old copies' behaviour, not to "something sensible".**
 * The work item is explicit that this is the point: **no existing screen changes
 * appearance** for anyone who has not set a name. Not "close enough" — *the same
 * function*. So the cases below are the old function's cases, written down.
 */
import { describe, expect, it } from "vitest";

import { displayName } from "@/lib/display-name";

describe("a user with a stored name", () => {
  it("is called by that name", () => {
    expect(displayName({ name: "Maya Ahmed", email: "maya@example.test" })).toBe("Maya Ahmed");
  });

  it("is called by that name verbatim, not trimmed and not re-cased", () => {
    // **A person's name is theirs.** The display rule for the *email* exists because an
    // address has no capitals — not because names should be capitalised. So a name
    // stored as "maya ahmed" stays "maya ahmed", and one stored as "MAYA" stays
    // "MAYA".
    expect(displayName({ name: "maya ahmed", email: "maya@example.test" })).toBe("maya ahmed");
    expect(displayName({ name: "MAYA AHMED", email: "maya@example.test" })).toBe("MAYA AHMED");
  });

  it("is not trimmed either", () => {
    // **The "verbatim" claim covers the whitespace, not only the capitals.** A helper
    // that trimmed would show "Maya Ahmed" for a name stored as "  Maya Ahmed  " —
    // which is *nicer*, and is exactly why it is a change of behaviour rather than a
    // detail. **The backend trims on write, so a stored name is already trimmed** —
    // and the frontend's job is to show what the account holds, not to tidy it.
    expect(displayName({ name: "  Maya Ahmed  ", email: "maya@example.test" })).toBe(
      "  Maya Ahmed  ",
    );
  });

  it("is shown even when it is only whitespace", () => {
    // **The emptiness check is `name === ""`, not a trim.** So a name that is all
    // spaces is shown as all spaces — a blank rail.
    //
    // **This is deliberate, and it is safe because the backend cannot write it.** The
    // name command trims the value and stores `""` for a whitespace-only input, so
    // `""` is the *only* empty state the account can hold. **The frontend's rule is
    // "the stored name if there is one"**, and "there is one" means "it is not the
    // empty string" — the backend owns the question of what counts as empty.
    expect(displayName({ name: "   ", email: "maya@example.test" })).toBe("   ");
  });

  it("does not split the stored name on separators", () => {
    // **The email rule splits on `.`, `_` and `-`. The stored name must not be run
    // through that rule** — a name is not an address.
    expect(displayName({ name: "van der Berg", email: "maya@example.test" })).toBe("van der Berg");
    expect(displayName({ name: "Mary-Jane", email: "maya@example.test" })).toBe("Mary-Jane");
  });

  it("wins over the email, whatever the email is", () => {
    expect(displayName({ name: "Maya Ahmed", email: "someone.else@other.test" })).toBe(
      "Maya Ahmed",
    );
  });
});

describe("a user with no stored name", () => {
  it("is called by the email's local part, capitalised", () => {
    // **The old rule, exactly.** `maya.ahmed@example.test` → `"Maya Ahmed"`.
    expect(displayName({ name: "", email: "maya.ahmed@example.test" })).toBe("Maya Ahmed");
  });

  it("is called by the whole local part when it has no separators", () => {
    expect(displayName({ name: "", email: "maya@example.test" })).toBe("Maya");
  });

  it("splits on a dot", () => {
    expect(displayName({ name: "", email: "maya.ahmed@example.test" })).toBe("Maya Ahmed");
  });

  it("splits on an underscore", () => {
    expect(displayName({ name: "", email: "maya_ahmed@example.test" })).toBe("Maya Ahmed");
  });

  it("splits on a hyphen", () => {
    expect(displayName({ name: "", email: "maya-ahmed@example.test" })).toBe("Maya Ahmed");
  });

  it("splits on a mix of them", () => {
    expect(displayName({ name: "", email: "maya.ahmed_solo-joint@example.test" })).toBe(
      "Maya Ahmed Solo Joint",
    );
  });

  it("collapses a run of separators into one break", () => {
    // **The old rule split on a run, not on each separator** — `maya..ahmed` is
    // "Maya Ahmed", not "Maya  Ahmed".
    expect(displayName({ name: "", email: "maya..ahmed@example.test" })).toBe("Maya Ahmed");
  });

  it("falls back to the whole email when the local part is empty", () => {
    // **There is nothing else to call somebody by.** The old copies returned the email
    // itself, and so does this.
    expect(displayName({ name: "", email: "@example.test" })).toBe("@example.test");
  });

  it("falls back to the whole email when the local part is only separators", () => {
    expect(displayName({ name: "", email: "...@example.test" })).toBe("...@example.test");
  });

  it("capitalises only the first letter of each word", () => {
    // **The old rule did not lower-case the rest.** `McDonald` stays `McDonald`.
    expect(displayName({ name: "", email: "mcDonald.vanDerBerg@example.test" })).toBe(
      "McDonald VanDerBerg",
    );
  });
});
