// @vitest-environment node
/**
 * The collection-status vocabulary, held to the backend's.
 *
 * **The status crosses the boundary as a string, and the string is the backend's.**
 * `city_collection_status` is the `CityProvisioning.Status` value, carried verbatim
 * from the Django model to the browser. The frontend has no vocabulary of its own to
 * invent — it recognises the backend's, and it must recognise **exactly** the
 * backend's.
 *
 * **Two failure modes, and they are opposite.**
 *
 * - **A status the frontend does not know about** reaches the surface as silence. That
 *   is the *right* failure for an unknown status (a status nobody wrote a sentence for
 *   must not become a sentence somebody invented) — but it means a backend status
 *   added without a frontend line is a city whose state the surface cannot report.
 * - **A status the frontend recognises but the backend does not have** is worse. It is
 *   a sentence the frontend can say about a fact the backend cannot produce, and it
 *   will be wrong the day the backend's spelling changes — silently, because the
 *   string simply stops matching and the city falls back to the quiet state, which
 *   says "there is nothing on tonight" about a city that is in fact being collected.
 *
 * **So the frontend's set must equal the backend's set.** Not a subset, not a
 * superset. That is what this file holds, and it is asserted on the *source* of both
 * sides — the same house pattern as `tests/event-state.test.ts`.
 *
 * **And the frontend's set is read from the files that use it**, not from a
 * hand-written list in this test. A list written here would drift from the code the
 * first time somebody added a status and forgot to update the test; reading the
 * literals out of the components means this test fails the moment the code and the
 * backend disagree, which is the only moment it matters.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/**
 * The backend's `CityProvisioning.Status` choices, read from the Django model.
 *
 * **The class is named, because there are three `Status` choices classes in that
 * file** — `Source.Status`, `Event.Status` and `CityProvisioning.Status`. A regex
 * that took the first match would read the registry's and every assertion below would
 * be about the wrong thing.
 */
function backendStatuses(): string[] {
  const source = readFileSync(path.resolve(ROOT, "../backend/apps/ingestion/models.py"), "utf8");
  const provisioning = /class CityProvisioning\(UUIDv7Model\):([\s\S]*?)\n    class Meta:/.exec(
    source,
  );
  if (!provisioning) throw new Error("backend CityProvisioning model not found");

  const block = /class Status\(models\.TextChoices\):([\s\S]*?)\n\n/.exec(provisioning[1]);
  if (!block) throw new Error("backend CityProvisioning.Status choices not found");

  return [...block[1].matchAll(/^\s+([A-Z_]+)\s*=\s*"([^"]+)"/gm)].map((match) => match[2]);
}

/** A source file with its comments removed. */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/**
 * The statuses the frontend recognises, read from the components that use them.
 *
 * **The literals are gathered from `status === "..."` comparisons**, which is how the
 * components actually branch on the status. A status named in a comment or in a
 * string that is not a comparison would be picked up by a looser pattern and would
 * make this test pass on code that does not branch on it.
 */
function frontendStatuses(file: string): string[] {
  const source = withoutComments(readFileSync(path.resolve(ROOT, file), "utf8"));
  return [...new Set([...source.matchAll(/status\s*===\s*"([^"]+)"/g)].map((match) => match[1]))];
}

/** The two surfaces that read the status. */
const SURFACES = {
  browse: "app/browse/page.tsx",
  cityPage: "components/city-page/city-page.tsx",
};

describe("the backend's vocabulary", () => {
  it("is read, not assumed", () => {
    // **A guard that silently matched nothing would pass every assertion below.**
    const statuses = backendStatuses();

    expect(statuses.length).toBeGreaterThan(0);
    expect(statuses).toContain("collecting");
    expect(statuses).toContain("live");
    expect(statuses).toContain("no_providers");
    expect(statuses).toContain("yielded_nothing");
    expect(statuses).toContain("paused");
  });
});

describe("the frontend's vocabulary", () => {
  it("is read, not assumed", () => {
    // **The same guard on the other side.** If the regex stopped matching, every
    // "the frontend has no extras" assertion would pass vacuously.
    for (const file of Object.values(SURFACES)) {
      expect(frontendStatuses(file).length, file).toBeGreaterThan(0);
    }
  });

  it("recognises every status the backend has", () => {
    // **A backend status with no frontend line is a city whose state the surface
    // cannot report.** The surface would fall back to the quiet state — "there is
    // nothing on tonight" — about a city that is in fact still being collected.
    for (const [name, file] of Object.entries(SURFACES)) {
      const known = frontendStatuses(file);
      for (const status of backendStatuses()) {
        expect(known, `${name} is missing ${status}`).toContain(status);
      }
    }
  });

  it("recognises no status the backend does not have", () => {
    // **A frontend sentence about a fact the backend cannot produce is a sentence
    // waiting to be wrong.** The day the backend's spelling changes, the string
    // simply stops matching and the city falls back to the quiet state — silently.
    for (const [name, file] of Object.entries(SURFACES)) {
      const known = frontendStatuses(file);
      for (const status of known) {
        expect(backendStatuses(), `${name} knows ${status}, which the backend does not`).toContain(
          status,
        );
      }
    }
  });

  it("the two surfaces recognise the same vocabulary", () => {
    // **One vocabulary, two surfaces.** A status one surface knows and the other does
    // not is a city that reads one way on Browse and another way on its own page.
    const browse = frontendStatuses(SURFACES.browse).sort();
    const cityPage = frontendStatuses(SURFACES.cityPage).sort();

    expect(browse).toEqual(cityPage);
  });
});
