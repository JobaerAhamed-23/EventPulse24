/**
 * The retention table `/privacy` publishes.
 *
 * **This is a mirror, not a source.** The fact lives in `backend/shared/retention.py`,
 * where `RetentionCategory` is enforced: Django system checks `eventpulse.E003/E004` fail
 * the build on any concrete model without a valid category, and
 * `backend/tests/identity/test_deletion_retention_walk.py` walks the registry. This file
 * exists only because the page is TypeScript and the registry is Python.
 *
 * **`backend/tests/shared/test_retention_published.py` pins the two together.** Add a
 * category, rename one, or change a window in `shared/retention.py`, and that test fails
 * until this file follows. A published retention window that drifts from the one the
 * database enforces is the single most serious thing a privacy policy can get wrong — it
 * is a factual claim about other people's data, made to them, in writing.
 *
 * ## Two of the PRD's nine categories are deliberately absent
 *
 * `EMAIL_DELIVERY_EVENTS` and `ANALYTICS_AGGREGATES` are declared in `RetentionCategory`
 * and **no model uses either**. PRD §10.2 publishes windows for both — 90 days for
 * "sent, opened, clicked", and indefinite retention for anonymised aggregates.
 *
 * **Neither is built.** `apps/delivery/email_api.py` records that the storage behind the
 * open-and-click metric "is not" there, and the codebase contains no analytics vendor of
 * any kind. Publishing those rows would describe a product that watches more than this
 * one does, so they are omitted and the omission is tested for.
 */

export type RetentionRow = {
  /** The `RetentionCategory` member this mirrors. */
  key: string;
  /** What a reader would call it. */
  label: string;
  /** What the category actually holds, in the reader's terms. */
  holds: string;
  /** How long it is kept. */
  window: string;
  /** What account deletion does to it. */
  onDelete: string;
};

export const RETENTION_ROWS: readonly RetentionRow[] = [
  {
    key: "account_content",
    label: "Things you made and saved",
    holds:
      "Your personal events, the public events you saved, your collections, your reminder plans, the digests we built for you, and any event reports you sent us.",
    window: "Kept while your account is open.",
    onDelete: "Deleted.",
  },
  {
    key: "preference_signals",
    label: "What we learned about your taste",
    holds:
      "Your interests, your digest and notification settings, your quiet hours, which events you dismissed or opened, and the sources and categories you muted.",
    window: "Kept for 12 months on a rolling basis, then purged.",
    onDelete: "Deleted.",
  },
  {
    key: "account_identity",
    label: "Your account and its credentials",
    holds:
      "Your email address and password hash, your calendar connection, a pending email change if you have one, password-reset tokens, and your sessions.",
    window: "Kept while your account is open. Encrypted at rest.",
    onDelete: "Deleted. A calendar connection is deleted when you disconnect it, too.",
  },
  {
    key: "billing_records",
    label: "Billing records",
    holds: "Your subscription record, if you have ever been a Pro subscriber.",
    window: "Kept for 7 years, because tax and accounting law requires it.",
    onDelete: "Kept. We are not allowed to delete these on request.",
  },
  {
    key: "audit_log",
    label: "Security and audit logs",
    holds:
      "Records that something happened — a sign-in, a settings change, a deletion — without the contents. These logs are built to carry no personal data.",
    window: "Kept for 24 months.",
    onDelete: "Kept, because they identify no one.",
  },
  {
    key: "source_registry",
    label: "The public event catalog",
    holds:
      "Events, venues, cities and the sources we collect them from. This is third-party information about public events. It is not about you.",
    window: "Kept while the event is current, plus 12 months, then archived.",
    onDelete: "Unaffected. It was never yours.",
  },
  {
    key: "tos_review_records",
    label: "Our own source paperwork",
    holds:
      "Our records of reviewing each source's terms before collecting from it. Ours, not yours.",
    window: "Kept for 7 years, for legal reasons.",
    onDelete: "Unaffected.",
  },
] as const;
