/**
 * The Taste route's skeleton.
 *
 * **A skeleton, not a spinner** — the product has exactly one transition (`.fade-in`), and
 * `styles/motion.test.ts` fails the suite on any other animation.
 *
 * **The rows are the skeleton, not a card.** A muted-category row is a name with a
 * duration under it and a one-tap button beside it, so the placeholder is a short bar
 * where the name would be and a longer one where the button would be — the shape of the
 * thing that is coming, so the page does not jump when it arrives.
 *
 * **Every width is a step on the spacing scale, or an exact size in brackets.** The
 * scale is `0 1 2 3 4 6 8 12 16 20 30`, and `styles/tokens.css` resets Tailwind's
 * spacing multiplier — so a width written as `w-30` is a step, while a width that
 * is not on the scale generates no CSS at all.
 */
export default function SettingsTasteLoading() {
  return (
    <div data-settings-skeleton>
      <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
      <div className="mt-3 h-4 w-20 rounded-subtle bg-surface-subtle" />

      <div className="mt-8 flex max-w-(--layout-container-reading) flex-col gap-3">
        {[0, 1, 2].map((row) => (
          <div key={row} className="flex items-center justify-between gap-3">
            <div className="flex flex-col gap-2">
              <div className="h-4 w-30 rounded-subtle bg-surface-subtle" />
              <div className="h-3 w-20 rounded-subtle bg-surface-subtle" />
            </div>
            <div className="h-[44px] w-30 rounded-control bg-surface-subtle" />
          </div>
        ))}
      </div>
    </div>
  );
}
