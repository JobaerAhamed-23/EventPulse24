import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";

/**
 * Recording a dismissal, from the browser.
 *
 * **This is the only write path FR-25's swipe has.** The swipe is a client gesture, so
 * the write is a client write — but it goes through the same generated client as
 * everything else (AD-19), and it is the *server* that decides whether the dismissal
 * counted, whether the cluster completed, and what the prompt says.
 *
 * **The client does not compute the cluster.** The embedding cosine, the 24-hour
 * window, the three-distinct-events rule and the rage-dismiss guard are all server
 * facts. A client that counted dismissals itself would be answering "has this cluster
 * fired?" with a number the server never agreed to — and the prompt would appear for
 * the wrong reason, or not at all. So the client sends one event id and renders what
 * comes back.
 *
 * **The prompt's copy arrives on the response.** The title names a chip in the server's
 * vocabulary, and the description carries the server's own count. Neither is built
 * here, because a scraped title must never reach the user's screen (AD-9) — and the
 * chip label is the server's word for a bucket the frontend does not own.
 *
 * **A failed write is not a dismissal.** The card stays where it is and the swipe
 * springs back. A card that vanished without a recorded dismissal would be the client
 * claiming a fact the server refused to store — and the user's next digest would bring
 * the same event back with no explanation.
 */
export type DismissalOutcome = {
  /** Whether this dismissal counted toward the cluster. */
  readonly cluster_advanced: boolean;
  /** Whether the product should now ask. */
  readonly prompt_due: boolean;
  /** The prompt, when one is due. `null` otherwise. */
  readonly prompt: components["schemas"]["MutePromptOut"] | null;
};

/**
 * Record one dismissal.
 *
 * **`null` means the write failed.** The caller must not treat that as "dismissed, no
 * prompt" — it means nothing was recorded, and the card must stay put.
 */
export async function recordDismissal(eventId: string): Promise<DismissalOutcome | null> {
  try {
    const response = await api.POST("/api/personal/dismissals", {
      body: { event_id: eventId },
    });
    if (response.error || !response.data) return null;
    return {
      cluster_advanced: response.data.cluster_advanced,
      prompt_due: response.data.prompt_due,
      prompt: response.data.prompt ?? null,
    };
  } catch {
    return null;
  }
}
