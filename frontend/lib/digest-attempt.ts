/**
 * How many consecutive digest reads have failed.
 *
 * **§5's error pattern is stateful.** The first failure says "Couldn't reach Pulse. Try
 * again."; the **second consecutive** one says "Refresh page." — because by then the
 * failure is probably not in the one request, and re-running one request would just fail
 * again.
 *
 * **The count lives in the URL, not in a cookie.** The retry *is* a navigation: the first
 * failure's "Try again" link goes to `/?retry=1`, so a render that carries `retry` is the
 * second attempt in a row, and a failure there is the second consecutive failure. The
 * page cannot keep the count in a cookie: a Server Component render may read cookies but
 * not write them (Next allows that only in a Server Action or Route Handler), and the
 * cookie version threw on every render of `/`.
 *
 * **A fresh visit is a first attempt.** Opening `/` without `retry` starts the count over,
 * which is what "consecutive" asks for: the user's own navigation breaks the run.
 *
 * **This is the server's own business.** The client never counts; it renders the label
 * the server chose.
 */
export const RETRY_PARAM = "retry";

/**
 * The number of failures **before** this render: 0 on a fresh visit, 1 on the retry.
 *
 * **The value is untrusted input.** Anyone can type a query string, so anything that is
 * not a single positive integer — missing, empty, junk, or a repeated `?retry=a&retry=b`
 * that arrives as an array — is "no failures yet".
 */
export function attemptFromQuery(value: string | string[] | undefined): number {
  if (typeof value !== "string" || value === "") return 0;
  const attempt = Number(value);
  return Number.isFinite(attempt) && attempt > 0 ? Math.floor(attempt) : 0;
}
