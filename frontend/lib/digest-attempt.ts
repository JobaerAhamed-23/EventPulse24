import { cookies } from "next/headers";

/**
 * How many consecutive digest reads have failed.
 *
 * **§5's error pattern is stateful.** The first failure says "Couldn't reach Pulse. Try
 * again."; the **second consecutive** one says "Refresh page." — because by then the
 * failure is probably not in the one request, and re-running one request would just fail
 * again.
 *
 * **The count has to survive a reload, so it lives in a cookie.** A client-side counter
 * cannot survive one, and the retry *is* a navigation: it re-runs the server's read, so
 * the server has to know how many times it has already failed.
 *
 * **The cookie is only written on a failure.** A successful read clears it, so the count
 * is *consecutive* failures rather than a lifetime tally — a user who fails once on
 * Monday and succeeds on Tuesday has not failed twice in a row, and on Tuesday's next
 * failure they should see "Try again." again, not "Refresh page.".
 *
 * **This is the server's own business.** The client never reads the cookie; it renders
 * the label the server chose. A client that counted for itself would be a second source
 * of truth for the same fact.
 */
export const ATTEMPT_COOKIE = "pulse-digest-attempt";

/** How long the failure count lives. A day is long enough to survive a reload. */
const ATTEMPT_MAX_AGE = 60 * 60 * 24;

/**
 * The attempt count the server knows about.
 *
 * **A malformed cookie is zero, not a crash.** The cookie is user-writable, so its
 * contents are untrusted input: anything that is not a positive integer is "no failures
 * yet".
 */
export function attemptFromCookie(value: string | undefined): number {
  if (!value) return 0;
  const attempt = Number(value);
  return Number.isFinite(attempt) && attempt > 0 ? Math.floor(attempt) : 0;
}

/** The attempt count for this request, read from the visitor's cookie. */
export async function readAttempt(): Promise<number> {
  const store = await cookies();
  return attemptFromCookie(store.get(ATTEMPT_COOKIE)?.value);
}

/**
 * Record a digest failure, and return **how many failures came before this one**.
 *
 * **The return value is the count of *prior* failures, not the new total.** The error
 * state's rule is "the second *consecutive* failure says 'Refresh page.'", so the
 * component asks "how many failures have already happened?" — and the answer is 0 on
 * the first failure and 1 on the second. The cookie then holds the *total*, so the next
 * request knows how many there have been.
 *
 * Returning the new total instead would make the first failure render "Refresh page." —
 * which is the bug this shape exists to prevent.
 */
export async function recordFailure(): Promise<number> {
  const store = await cookies();
  const prior = readAttemptOf(store);
  store.set(ATTEMPT_COOKIE, String(prior + 1), {
    maxAge: ATTEMPT_MAX_AGE,
    path: "/",
    sameSite: "lax",
  });
  return prior;
}

/**
 * Forget the failure count, because the read succeeded.
 *
 * **A success resets the run.** "Consecutive" means consecutive: one good read breaks
 * the streak, and the next failure is a first failure again.
 */
export async function clearAttempt(): Promise<void> {
  const store = await cookies();
  store.delete(ATTEMPT_COOKIE);
}

/** The attempt count already in the store, without touching the request twice. */
function readAttemptOf(store: Awaited<ReturnType<typeof cookies>>): number {
  return attemptFromCookie(store.get(ATTEMPT_COOKIE)?.value);
}
