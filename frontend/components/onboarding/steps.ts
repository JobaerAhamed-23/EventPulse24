/**
 * The flow's shape, mirrored from the server.
 *
 * `shared/constants.py` holds the truth: `ONBOARDING_STEPS = ("calendar", "interests",
 * "digest")` and `ONBOARDING_STEP_COUNT = 3`. FR-1 caps the flow at three user-visible
 * steps, and the API's `current_step` is the 1-based position in that tuple — so the
 * frontend needs the same positions to know which step to draw.
 *
 * This is the one place the frontend states them. The *contents* of each step come from
 * the API (the interest chips, the stored digest preference); only the running order is
 * here, because the step endpoints identify a step by its position and nothing in the
 * response names the three in order.
 */

export const ONBOARDING_STEP_COUNT = 3;

export const CALENDAR_STEP = 1;
export const INTERESTS_STEP = 2;
export const DIGEST_STEP = 3;
