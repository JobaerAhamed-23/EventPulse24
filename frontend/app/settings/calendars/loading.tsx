/**
 * The Calendar sync route's skeleton.
 *
 * **A skeleton, not a spinner** — the product has exactly one transition (`.fade-in`), and
 * `styles/motion.test.ts` fails the suite on any other animation.
 */
export default function SettingsCalendarsLoading() {
  return (
    <div data-settings-skeleton>
      <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-3 h-4 w-30 rounded-subtle bg-surface-subtle" />

      <div className="mt-8 flex max-w-(--layout-container-reading) flex-col gap-3">
        <div className="h-16 rounded-card bg-surface-subtle" />
        <div className="h-16 rounded-card bg-surface-subtle" />
      </div>
    </div>
  );
}
