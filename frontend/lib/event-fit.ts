/**
 * The Event Fit's range, mirrored from the server.
 *
 * `shared/constants.py` holds the truth (`EVENT_FIT_SCORE_MIN`, `EVENT_FIT_SCORE_MAX`).
 * The frontend needs the maximum to draw the right number of dots and to say "4 of 5", so
 * it is stated here once rather than typed as a literal beside each use.
 */

export const EVENT_FIT_MIN = 1;
export const EVENT_FIT_MAX = 5;

/** The score, clamped to the range the server promises, so a bad value cannot draw six dots. */
export function clampEventFit(score: number): number {
  if (!Number.isFinite(score)) return EVENT_FIT_MIN;
  return Math.max(EVENT_FIT_MIN, Math.min(EVENT_FIT_MAX, Math.round(score)));
}
