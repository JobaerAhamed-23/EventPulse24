/**
 * The failure line for a settings save — **the API's words when the API spoke**.
 *
 * **The rule the whole frontend follows**: the API's errors are read for display,
 * verbatim (`lib/api-errors.ts`). The API writes its messages for the user — the
 * quiet-hours refusal says *"A quiet window needs a start and an end that differ."* —
 * and a frontend that replaces that with its own generic sentence is throwing away the
 * one line that says what to fix. The backend's own test calls that message *"a
 * readable message"*, and a message nobody reads is not one.
 *
 * **So there are two cases, and they are different.**
 *
 * - **The API answered with an error** — the request reached the server and the server
 *   said no. Its message is shown **as it arrived**. This is the `invalid_quiet_hours_window`
 *   case, and it is the one a generic failure line cannot replace.
 * - **The API never answered** — the request threw, the network dropped, the device
 *   went offline. The API said nothing, so there is nothing to quote, and the route's
 *   own failure line is shown instead.
 *
 * **The route's own line is the fallback, not the answer.** That is why the routes
 * carry two: the reminders route's *"Couldn't save. We'll try again on your next
 * change."* and the quiet-hours and delivery-time routes' shorter *"Couldn't save."*
 * The second one is the **offline** case — and it is honest there, because nothing was
 * refused.
 */
import { readApiError } from "@/lib/api-errors";

/**
 * The line to show after a failed save.
 *
 * @param error The API's error body, when it sent one — the `error` member of an
 *   openapi-fetch response. `null` when the request never reached the API.
 * @param offline The route's own failure line, shown when the API said nothing.
 */
export function saveFailureMessage(error: unknown, offline: string): string {
  if (error === null || error === undefined) {
    return offline;
  }
  // `readApiError` returns the API's own message when the body is the project's error
  // shape, and the offline fallback when it is not. **The API's shape is what makes the
  // difference**, so the body is checked before the message is taken.
  const failure = readApiError(error);
  return failure.code === null ? offline : failure.message;
}
