import { api } from "@/lib/backend-client";

/**
 * Setting and clearing a category mute, from the browser.
 *
 * **The prompt's accept path writes a mute here.** The "Show me less" button is the
 * product's own question being answered, and the answer is a row on the server — not a
 * local flag. A mute that only existed in the browser would be gone on the next
 * navigation, and the user would have been told their next digest would change.
 *
 * **The duration set is the server's.** `7`, `30`, `90`, or `null` for "until I change
 * it" — the same closed set `FR25_MUTE_DURATIONS_DAYS` names, and the server answers
 * anything else with a 422. The client does not widen it.
 */
export type MuteDurationDays = 7 | 30 | 90 | null;

/**
 * Set one category mute.
 *
 * **`false` means the write failed.** The caller must not treat that as "muted" — the
 * mute did not happen, and the screen must not say it did.
 */
export async function setCategoryMute(
  categoryKey: string,
  durationDays: MuteDurationDays,
): Promise<boolean> {
  try {
    const response = await api.PUT("/api/settings/taste/mutes", {
      body: { category_key: categoryKey, duration_days: durationDays },
    });
    return !response.error && response.data !== undefined;
  } catch {
    return false;
  }
}

/**
 * Clear one category mute.
 *
 * **`false` means the write failed**, for the same reason the setter's `false` does.
 */
export async function clearCategoryMute(categoryKey: string): Promise<boolean> {
  try {
    const response = await api.DELETE("/api/settings/taste/mutes/{category_key}", {
      params: { path: { category_key: categoryKey } },
    });
    return !response.error && response.data !== undefined;
  } catch {
    return false;
  }
}
