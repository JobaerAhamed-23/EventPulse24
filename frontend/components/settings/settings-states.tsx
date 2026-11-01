import Link from "next/link";

/**
 * The settings routes' one failure: **the API could not answer.**
 *
 * **There is no "missing" here.** The notification settings are a **singleton** — the
 * user's own — and the endpoint creates them on first read. There is no target that
 * might not exist and no target that might belong to somebody else, so the only
 * failure left is a failure to answer.
 *
 * **The copy carries its own instruction**, and the action matches it: one link home,
 * and nothing else. There is no retry on a screen whose retry would hit the same API.
 */
export function SettingsStates() {
  return (
    <div className="max-w-(--layout-container-reading)" data-settings-unavailable>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        Couldn&apos;t load your settings.
      </h1>
      <p className="mt-4 text-ink-secondary [font:var(--type-scale-body-md)]">
        Your settings are safe. This is on our side.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block rounded-control bg-accent-terracotta px-6 py-3 text-ink-inverse [font:var(--type-scale-meta-md)]"
      >
        Back to Pulse Digest
      </Link>
    </div>
  );
}
