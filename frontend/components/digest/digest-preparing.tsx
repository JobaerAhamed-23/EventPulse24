/**
 * The digest has not been composed yet.
 *
 * **This is not the empty state, and it must never be the empty state.** The empty
 * state's copy — "No qualifying events in {city}." — is a **claim about the world**: it
 * says there is nothing for you. If the digest has not been composed, the page does not
 * know that; it knows only that the question has not been asked yet. Showing "your week
 * is quiet" before the answer would be a lie, and one the user cannot detect.
 *
 * **So this state says only what is true.** The digest is being prepared. It makes no
 * claim about the world, offers no recovery, and shows no CTA — the same calm the
 * placeholder home had, for the same reason.
 *
 * **The API distinguishes the two.** `DigestOut.status` is `not_composed` when the
 * digest has not been composed and `empty` when it was composed and nothing qualified.
 * Both answer 200; the difference is in the body, and the page keeps them apart.
 */
export function DigestPreparing() {
  return (
    <div className="max-w-(--layout-container-reading)">
      <article className="fade-in rounded-card border border-border-subtle bg-surface-elevated p-6">
        <h2 className="text-ink-primary [font:var(--type-scale-headline-md)]">
          Your Pulse is being prepared.
        </h2>
        <p className="mt-2 text-ink-secondary [font:var(--type-scale-body-md)]">
          It is put together each morning, from what is on your calendar and what is happening
          nearby. Come back a little later today.
        </p>
      </article>
    </div>
  );
}
