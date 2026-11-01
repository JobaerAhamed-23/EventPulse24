/**
 * The Reminder Picker's loading skeleton.
 *
 * **The picker's own shape.** A heading block, a meta line and four chip skeletons —
 * the shape the screen will have when it arrives, so the wait is a shape rather than a
 * blank page.
 *
 * **The Detail Screen's fade, not the digest's pulse.** `EXPERIENCE.md` §12 describes
 * the Detail Screen's skeleton as "one full-width header block + one meta row + 3 chip
 * skeletons. Same fade animation", and the fade — `motion.fadeIn`, the product's single
 * transition — is what a *shape* uses. The digest's `skeleton-pulse` keyframe is a
 * *waiting* animation on a surface that waits, and a reminder plan does not wait; it is
 * being fetched and then it is here.
 */
export default function ReminderPickerLoading() {
  return (
    <div className="max-w-(--layout-container-reading)" data-reminder-skeleton>
      <h1 className="text-ink-primary [font:var(--type-scale-headline-lg)]">
        When should we remind you?
      </h1>
      <div className="mt-4 h-4 w-1/2 rounded-card bg-surface-elevated" />
      <div className="mt-8 flex flex-wrap gap-2">
        <div className="h-12 w-16 rounded-control bg-surface-elevated" />
        <div className="h-12 w-16 rounded-control bg-surface-elevated" />
        <div className="h-12 w-16 rounded-control bg-surface-elevated" />
        <div className="h-12 w-16 rounded-control bg-surface-elevated" />
      </div>
      <div className="mt-8 flex gap-3">
        <div className="h-12 w-30 rounded-control bg-surface-elevated" />
        <div className="h-12 w-20 rounded-control bg-surface-elevated" />
      </div>
    </div>
  );
}
