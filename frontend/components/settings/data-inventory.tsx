import Link from "next/link";

import { RETENTION_ROWS } from "@/lib/retention-categories";

/**
 * **"What we store"** — PRD §10.2's data inventory, on `Settings → Privacy`.
 *
 * > **User-visible data inventory:** Settings → Privacy → "What we store" displays the
 * > categories and current retention windows in plain language.
 *
 * That requirement has been in §10.2 since the PRD was written and had no surface until
 * now. This route's own header comment has listed it among the commitments the page does
 * not keep since `run-eventpulse24-048`.
 *
 * ## It reads the registry; it does not restate it
 *
 * Every row comes from `RETENTION_ROWS`, which mirrors `backend/shared/retention.py` and
 * is pinned to it by `backend/tests/shared/test_retention_published.py`. **No retention
 * window is written as a literal on this surface.**
 *
 * That is the whole reason to build it this way. A hand-written inventory would be a
 * third copy of these windows — after the database and the public policy — free to drift
 * from both, on the one screen where a user goes specifically to find out what is true.
 * Reading the shared table means the schema, `/privacy` and this page cannot disagree
 * without a test failing.
 *
 * ## Two categories are missing on purpose
 *
 * §10.2 published nine; seven are real. `EMAIL_DELIVERY_EVENTS` and
 * `ANALYTICS_AGGREGATES` are declared in the registry and used by no model — there is no
 * open-and-click store and no analytics vendor — so **Amendment A-27 withdrew both from
 * §10.2**. They are absent here for the same reason they are absent from `/privacy`: a
 * page that listed them would be telling a user we watch something we do not.
 */
export function DataInventory() {
  return (
    <section aria-labelledby="what-we-store">
      <h2
        id="what-we-store"
        className="text-ink-primary [font:var(--type-scale-headline-md)]"
      >
        What we store
      </h2>
      <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
        Every table in our database is tagged with a retention rule, and the application
        refuses to start if one is untagged. This list is built from those same rules, so
        it describes what actually happens rather than what we intend.
      </p>

      <ul className="mt-6 flex flex-col gap-6">
        {RETENTION_ROWS.map((row) => (
          <li key={row.key} data-retention-row={row.key}>
            <h3 className="text-ink-primary [font:var(--type-scale-body-md)] font-semibold">
              {row.label}
            </h3>
            <p className="mt-1 text-ink-secondary [font:var(--type-scale-body-sm)]">
              {row.holds}
            </p>
            <p className="mt-1 text-ink-muted [font:var(--type-scale-meta-md)]">
              {row.window} <span aria-hidden="true">·</span> If you delete your account:{" "}
              {row.onDelete.toLowerCase()}
            </p>
          </li>
        ))}
      </ul>

      <p className="mt-6 text-ink-muted [font:var(--type-scale-meta-md)]">
        The full{" "}
        <Link href="/privacy" className="underline underline-offset-4">
          Privacy Policy
        </Link>{" "}
        explains who else sees any of this. You can{" "}
        <Link href="/settings/account" className="underline underline-offset-4">
          export everything we hold
        </Link>{" "}
        at any time.
      </p>
    </section>
  );
}
