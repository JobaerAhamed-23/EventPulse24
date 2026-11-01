import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * One event's Reminder Plan, read on the server.
 *
 * **The plan's delivery times are the server's answer, not the client's arithmetic.**
 * `GET /api/reminders/{target_kind}/{target_id}` returns the stored slots and, beside
 * them, each slot's **post-Quiet-Hours** instant together with a flag saying whether
 * Quiet Hours moved it. The picker renders that; it never recomputes it.
 *
 * **Why this matters more than it looks.** Recomputing the shift in the browser would
 * mean a second implementation of the Quiet Hours window in TypeScript — where DST and
 * the midnight-crossing window would be rediscovered, and got wrong differently from the
 * server. The server already knows the answer for every slot; asking it is both
 * cheaper and the only way the two can agree.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and the plan of a signed-in user read anonymously is not their plan.
 */
export type ReminderPlanRead =
  { kind: "found"; plan: ReminderPlanOut } | { kind: "missing" } | { kind: "unavailable" };

export type ReminderPlanOut = components["schemas"]["ReminderPlanOut"];
export type ReminderSlotDeliveryOut = components["schemas"]["ReminderSlotDeliveryOut"];

/**
 * The signed-in user's plan for one target.
 *
 * **Two kinds of nothing, kept apart.** `missing` is the server's 404 — the target does
 * not exist, is not the caller's, or is of the other kind. `unavailable` is a failure to
 * answer: a thrown request, a 500, or no response body. They are different facts about
 * different things, and the page says different things about them.
 */
export async function readReminderPlan(
  targetKind: TargetKind,
  targetId: string,
): Promise<ReminderPlanRead> {
  try {
    const response = await api.GET("/api/reminders/{target_kind}/{target_id}", {
      params: { path: { target_kind: targetKind, target_id: targetId } },
      headers: await sessionHeaders(),
    });

    if (response.response.status === 404) return { kind: "missing" };
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", plan: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}

/**
 * The two kinds of record a plan can belong to.
 *
 * **The server's vocabulary, exactly** — `ReminderPlan.TargetKind`'s. The picker is
 * reached from a saved event, so it uses `saved_event`; a personal event's plan would
 * use `personal_event`.
 */
export type TargetKind = "personal_event" | "saved_event";

/**
 * The user's default reminder slots — the plan a "Reset to default" restores.
 *
 * **The default plan's slots, and nothing else.** The endpoint returns the whole
 * settings surface — the quiet window, the default slots, the digest schedule — and
 * this read keeps only the slots, because that is all the reset needs. The window and
 * the schedule are the settings screen's business.
 *
 * **The reset does not save.** It restores the chips so the user can look at them and
 * then press Save. A reset that saved on its own would write the plan without the user
 * asking for it.
 */
export async function readDefaultReminderSlots(): Promise<string[] | null> {
  try {
    const response = await api.GET("/api/settings/notifications", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return null;
    return response.data.default_reminder_slots;
  } catch {
    return null;
  }
}
