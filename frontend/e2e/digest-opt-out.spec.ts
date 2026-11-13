import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import { expect, test, type Page } from "@playwright/test";

import { seedAccount, signIn } from "./helpers";

/** `execFile`, promisified — the walkthrough runs the product's own compose command. */
const run = promisify(execFile);

/**
 * The backend's directory, **resolved from the working directory**.
 *
 * **Not from `import.meta.url`** — Playwright loads test files through its own
 * CommonJS loader, and `import.meta` is not available there. This is the same
 * constraint `e2e/helpers.ts` records for the seed file's path.
 */
const BACKEND_DIR = path.resolve(process.cwd(), "../backend");

/**
 * The walkthrough of FR-19's opt-out, driven through a real browser.
 *
 * **What this file is for.** The intent's verification is *"automated tests plus a real
 * browser walkthrough"* — and a browser answers two questions a unit test cannot: **is
 * the control findable**, and **does the user's actual brief change when they use it**.
 *
 * **So the walkthrough is deliberately not a re-run of the unit suite.** The unit suite
 * proves the component calls the right endpoint with the right body; this file proves a
 * person can *find* the control, and that the digest they receive afterwards is a
 * different digest.
 *
 * **It drives the real stack.** The frontend is a server-rendered page reading a real
 * preference row, the API is the real API, and the database is the real database — so
 * a mock would be asserting that the mock behaves, which is the one thing a mock is
 * guaranteed to do.
 *
 * **The state is read from the API, not from the DOM, for the "before" and "after".**
 * The DOM says what the control *shows*; the API says what the *server holds*. The
 * walkthrough asserts both, because the seam this intent closed is precisely the gap
 * between them — a control that shows "off" while the server holds "on" would pass a
 * DOM-only check and fail the product.
 */

/**
 * The control's accessible name — stable in both states, by design.
 *
 * **It says "the Pulse Digest", not "your Pulse Digest".** The visible text says
 * "Personal events *are in your* Pulse Digest", and the two differ deliberately: the
 * name names the thing being controlled, so it does not change with the state, and it
 * says "the" because the digest is the product's noun. **The name is spelled out here
 * rather than copied from the component, because a locator that guesses the name is a
 * locator that fails for a reason nobody will guess.**
 */
const CONTROL_NAME = "Personal events in the Pulse Digest";

/** The hook on the "you have no schedule" line. */
const NO_SCHEDULE = "[data-no-schedule]";

/** The stored preference, as the server holds it. */
type StoredPreference = {
  include_personal_events: boolean;
  delivery_time: string | null;
  timezone: string | null;
};

/**
 * The server's stored preference, read over the API.
 *
 * **Over the API, not from the database.** The browser has a session and the API speaks
 * its language; going to the database from a browser test would need a second connection
 * and would assert something about the database rather than about the product.
 *
 * **The endpoint is `/api/personal/onboarding`, not `/onboarding/state`** — the state
 * read is the same one the settings route uses, and it carries the digest preference.
 */
async function storedPreference(page: Page): Promise<StoredPreference> {
  const response = await page.request.get("/api/personal/onboarding");
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    digest?: {
      include_personal_events?: boolean;
      delivery_time?: string | null;
      timezone?: string | null;
    };
  };
  return {
    include_personal_events: body.digest?.include_personal_events ?? true,
    delivery_time: body.digest?.delivery_time ?? null,
    timezone: body.digest?.timezone ?? null,
  };
}

/**
 * The digest the server holds for this user, as the API serves it.
 *
 * **The three states are distinguished, because "no cards" means two different things.**
 * `not_composed` means the worker has not built today's digest; `empty` means it built
 * one with nothing in it. The walkthrough needs `composed` — a digest with cards — or
 * there is nothing to say about what is in it.
 */
async function digest(page: Page): Promise<{
  status: string;
  local_date: string;
  cards: { slot: string; event_kind: string; title: string | null }[];
}> {
  const response = await page.request.get("/api/personal/digest");
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    status?: string;
    local_date?: string;
    cards?: { slot?: string; event_kind?: string; title?: string | null }[];
  };
  return {
    status: body.status ?? "",
    local_date: body.local_date ?? "",
    cards: (body.cards ?? []).map((card) => ({
      slot: card.slot ?? "",
      event_kind: card.event_kind ?? "",
      title: card.title ?? null,
    })),
  };
}

/**
 * Compose the digest for a local date **N days ahead**, the way the worker would.
 *
 * **Why a day ahead, and not today.** The composition is **idempotent per local date**
 * — `_existing_digest` (`digest_composition.py:562`) is consulted at `:699-712`, so a
 * digest already composed for today is returned as it was, and a re-compose for today
 * would read back the first digest and prove nothing about the flag.
 *
 * **Why a *different* day for the "after".** The same idempotence applies to the day
 * after. **So the "before" is composed for one day and the "after" for another** —
 * each a date no digest exists for yet, each fresh. **Composing both on the same date
 * would return the first one unchanged, and the walkthrough would "prove" that the
 * opt-out changes nothing.**
 *
 * **It goes through the product's own service.** `compose_digest` is the command the
 * worker's task runs (`worker/tasks.py:481`) — the walkthrough is meant to show the
 * real path, not a test-only one.
 *
 * **The clock is passed explicitly**, because a day is a day in the user's own zone,
 * and the composition resolves the date from the zone. **The instant is 14:00 local**,
 * which is safely inside the day whatever the offset is.
 *
 * **The cards come back from the composition's own rows**, not from the read endpoint.
 * The read endpoint resolves "today" from the server's wall clock, and it would hand
 * back today's digest — the one this walkthrough is trying to *get past*.
 */
async function userIdFor(page: Page, account: { email: string }): Promise<string> {
  // **The user's id, from the API** — the browser's own session, the product's own
  // read. The `me` endpoint is on the identity router, so the path is `/api/auth/me`.
  const me = await page.request.get("/api/auth/me");
  expect(me.ok()).toBeTruthy();
  const body = (await me.json()) as { id?: string; email?: string };
  expect(body.email).toBe(account.email);
  return body.id as string;
}

async function composeFor(
  page: Page,
  account: { email: string },
  daysAhead: number,
): Promise<{
  local_date: string;
  personal_qualifying_count: number;
  cards: { slot: string; event_kind: string }[];
}> {
  return runCompose(await userIdFor(page, account), daysAhead);
}

/**
 * Run the composition for one user, for a local date N days ahead, and print its rows.
 *
 * **It shells out to the product's own service**, through `manage.py shell` — because
 * the composition is a service call with an explicit clock, and the service is not
 * reachable over HTTP (AD-11: no request handler composes a digest).
 *
 * **The clock is derived in the user's zone**, so the day is the user's day.
 */
async function runCompose(
  userId: string,
  daysAhead: number,
): Promise<{
  local_date: string;
  personal_qualifying_count: number;
  cards: { slot: string; event_kind: string }[];
}> {
  const script = [
    "import json",
    "from datetime import UTC, datetime, timedelta",
    "from uuid import UUID",
    "from zoneinfo import ZoneInfo",
    "from django.utils import timezone",
    "from shared.actor import Actor",
    "from apps.personalization.services.digest_composition import compose_digest",
    "from apps.personalization.models import DigestPreference",
    "uid = UUID('" + userId + "')",
    "pref = DigestPreference.objects.filter(user_id=uid).first()",
    "zone = pref.timezone if pref else 'UTC'",
    "local_today = timezone.now().astimezone(ZoneInfo(zone)).date()",
    "local_day = local_today + timedelta(days=" + daysAhead + ")",
    "# 14:00 local on that day, expressed as the instant the composition takes.",
    "now = datetime(local_day.year, local_day.month, local_day.day, 14, 0, tzinfo=ZoneInfo(zone)).astimezone(UTC)",
    "result = compose_digest(user_id=uid, actor=Actor.system('walkthrough'), now=now)",
    "print('@@RESULT@@' + json.dumps({",
    "    'local_date': result.local_date.isoformat(),",
    "    'personal_qualifying_count': result.personal_qualifying_count,",
    "    'cards': [{'slot': r.slot, 'event_kind': r.event_kind} for r in result.compositions],",
    "}))",
  ].join("\n");

  const { stdout } = await run("uv", ["run", "python", "manage.py", "shell", "-c", script], {
    cwd: BACKEND_DIR,
  });
  const marker = stdout.indexOf("@@RESULT@@");
  expect(marker).toBeGreaterThanOrEqual(0);
  return JSON.parse(stdout.slice(marker + "@@RESULT@@".length).trim()) as {
    local_date: string;
    personal_qualifying_count: number;
    cards: { slot: string; event_kind: string }[];
  };
}

/**
 * Give the sign-in throttle its allowance back.
 *
 * **The throttle is real, and it is doing its job.** `AUTH_THROTTLE_SIGN_IN_IP` is ten
 * an hour per IP and `AUTH_THROTTLE_SIGN_IN_ACCOUNT` is five an hour per account
 * (`shared/constants.py:466-468`) — and a walkthrough that signs in once per test burns
 * the account's five on its second run. **A walkthrough that fails on its second run,
 * for a reason that has nothing to do with what it is walking through, is a walkthrough
 * that cannot be repeated.**
 *
 * **So the setup gives the allowance back**, through the product's own
 * `reset_sign_in_throttle` — the same function `make seed-browse` calls, and the same
 * one the password-reset flow calls. **It is not a backdoor around the throttle; it is
 * the throttle's own reset.**
 */
async function resetSignInThrottle(emails: string[]): Promise<void> {
  const script = [
    "from apps.identity.services.throttle import reset_sign_in_throttle",
    "reset_sign_in_throttle(ip_address='127.0.0.1', emails=" +
      JSON.stringify(emails) +
      ")",
  ].join("\n");
  await run("uv", ["run", "python", "manage.py", "shell", "-c", script], { cwd: BACKEND_DIR });
}

/**
 * Put the seeded account back to "personal events are in the digest".
 *
 * **The walkthrough starts from a known state.** The seeded account's flag is a stored
 * fact, and the walkthrough's own last run left it off — **so a second run of the
 * walkthrough would start from a different place than the first**, and the "the control
 * renders the server's answer" assertion would be asserting against a flag the
 * walkthrough had set itself.
 */
async function resetOptOut(): Promise<void> {
  const script = [
    "from django.contrib.auth import get_user_model",
    "from apps.personalization.models import DigestPreference",
    "u = get_user_model().objects.get(email='free@browse.example.test')",
    "p = DigestPreference.objects.filter(user_id=u.pk).first()",
    "if p is not None:",
    "    p.include_personal_events = True",
    "    p.save(update_fields=['include_personal_events'])",
  ].join("\n");
  await run("uv", ["run", "python", "manage.py", "shell", "-c", script], { cwd: BACKEND_DIR });
}

/**
 * Wait for a save to finish, and fail loudly if it did not.
 *
 * **The button moves before the save lands.** The control flips its state *optimistically*
 * — `setIncluded(next)` fires before the PUT is even sent (`digest-personal-events.tsx:237`)
 * — so a test that waits for `aria-pressed` to change is waiting for the **guess**, not
 * for the **save**. **Reading the server right after that would race the request.**
 *
 * **So the walkthrough waits for the save's own signal.** `SaveFeedback` renders
 * `[data-saved]` — *"Saved."* — only once the server's answer has replaced the guess
 * (`digest-personal-events.tsx:253-254`), and renders `[data-save-failed]` if the save
 * was refused. **Waiting for one of those two is waiting for the round trip.**
 *
 * **And it asserts the save succeeded**, rather than waiting for a timeout and moving
 * on — a walkthrough that quietly skipped a failed save would report a control that
 * works when it did not.
 */
async function waitForSave(page: Page): Promise<void> {
  const saved = page.locator("[data-saved]");
  const failed = page.locator("[data-save-failed]");
  await expect(saved.or(failed).first()).toBeVisible();
  await expect(saved).toBeVisible();
  await expect(failed).toHaveCount(0);
}

/**
 * Clear the digests already composed for the days this walkthrough composes for.
 *
 * **The composition is idempotent per local date** — `_existing_digest`
 * (`digest_composition.py:562`) is consulted at `:699-712`, and when a digest exists
 * for that date the composition returns **the rows it persisted then**, not the rows it
 * would compose now. **So a digest left behind by an earlier run would be handed back
 * verbatim**, and the walkthrough would assert against a stale answer while believing
 * it had composed a fresh one.
 *
 * **This is the trap the "before" and "after" have to be on different days to avoid** —
 * and a different day is not enough on its own, because a *previous run of the
 * walkthrough* may have already composed for that day too.
 *
 * **So the walkthrough clears the days it is about to compose for.** It is the
 * walkthrough's own scratch space, on an account it seeded, and it deletes nothing the
 * product's users created.
 */
async function resetDigests(userId: string, daysAhead: number): Promise<void> {
  const script = [
    "from datetime import timedelta",
    "from uuid import UUID",
    "from zoneinfo import ZoneInfo",
    "from django.utils import timezone",
    "from apps.personalization.models import DigestPreference, PulseDigest",
    "uid = UUID('" + userId + "')",
    "pref = DigestPreference.objects.filter(user_id=uid).first()",
    "zone = pref.timezone if pref else 'UTC'",
    "local_today = timezone.now().astimezone(ZoneInfo(zone)).date()",
    "local_day = local_today + timedelta(days=" + daysAhead + ")",
    "PulseDigest.objects.filter(user_id=uid, local_date=local_day).delete()",
  ].join("\n");
  await run("uv", ["run", "python", "manage.py", "shell", "-c", script], { cwd: BACKEND_DIR });
}

/**
 * Put a personal event on the user's agenda, **inside the window the digest for
 * `daysAhead` reads**.
 *
 * **The window is `[now, now + 48h]`** — `RANKING_PERSONAL_EVENT_WINDOW`, read at
 * `digest_candidates.py:191` — and `now` is the *composition's* clock, not the wall
 * clock. **So an event that qualifies for today's digest does not qualify for
 * tomorrow's**: a composition for tomorrow at 14:00 local reads
 * `[tomorrow 14:00, tomorrow+48h]`, and an event that started six hours ago is not in
 * it.
 *
 * **So the walkthrough creates its own event, at the right place** — two hours into the
 * day it is composing for, which is inside the window and nowhere near its edge. **It
 * is the user's own agenda row, through the model's own service-level writer**, and it
 * replaces any event a previous run left behind so the walkthrough is repeatable.
 */
async function createPersonalEvent(userId: string, daysAhead: number): Promise<void> {
  const script = [
    "from datetime import UTC, datetime, timedelta",
    "from uuid import UUID",
    "from zoneinfo import ZoneInfo",
    "from django.utils import timezone",
    "from apps.personalization.models import DigestPreference, PersonalEvent",
    "uid = UUID('" + userId + "')",
    "pref = DigestPreference.objects.filter(user_id=uid).first()",
    "zone = pref.timezone if pref else 'UTC'",
    "local_today = timezone.now().astimezone(ZoneInfo(zone)).date()",
    "local_day = local_today + timedelta(days=" + daysAhead + ")",
    "# Two hours into the day, which is what the composition's window opens on.",
    "start = datetime(local_day.year, local_day.month, local_day.day, 16, 0, tzinfo=ZoneInfo(zone)).astimezone(UTC)",
    "PersonalEvent.objects.filter(user_id=uid, name='Walkthrough dinner').delete()",
    "PersonalEvent.objects.create(",
    "    user_id=uid,",
    "    name='Walkthrough dinner',",
    "    start_utc=start,",
    "    end_utc=start + timedelta(hours=3),",
    "    start_time_tz=zone,",
    "    location='Home',",
    "    source='user_created',",
    ")",
  ].join("\n");
  await run("uv", ["run", "python", "manage.py", "shell", "-c", script], { cwd: BACKEND_DIR });
}

test.describe("FR-19: the personal-events opt-out, in a browser", () => {
  test.beforeEach(async () => {
    // **The allowance back, before every test.** Each test signs in, and each sign-in
    // counts against the throttle.
    await resetSignInThrottle([
      "free@browse.example.test",
      "nosched-walkthrough@example.test",
    ]);
    // **And the flag back to "in".**
    await resetOptOut();
  });

  test("the control is findable, saves, and changes what the digest holds", async ({ page }) => {
    const account = await seedAccount("free");
    await signIn(page, account);

    // --- 1. The control is FINDABLE ------------------------------------------------
    //
    // **The link is on the quiet-hours page, because there is no settings index.** So
    // "findable" is tested the way a user finds it: by following the link, not by
    // typing the URL. A test that went straight to `/settings/digest` would pass
    // whether the link existed at all — and this intent exists because a control with
    // no path to it is not a control.
    await page.goto("/settings/quiet-hours");
    const link = page.getByRole("link", { name: "What's in your Pulse Digest" });
    await expect(link).toBeVisible();
    await link.click();
    await page.waitForURL(/\/settings\/digest/);

    // --- 2. The control's INITIAL state --------------------------------------------
    //
    // **It reads the server's answer.** The seeded account has never touched the
    // setting, so the server says "included" and the control must say so too.
    const control = page.getByRole("button", { name: CONTROL_NAME });
    await expect(control).toBeVisible();
    await expect(control).toHaveAttribute("aria-pressed", "true");
    await expect(control).toHaveText("Personal events are in your Pulse Digest");

    // **And the server agrees with what the control shows.** This is the seam, read
    // from both sides.
    const before = await storedPreference(page);
    expect(before.include_personal_events).toBe(true);

    // --- 3. The save SUCCEEDS --------------------------------------------------------
    await control.click();
    // **And the save finished** — the button moves optimistically, so waiting for
    // `aria-pressed` alone would race the request.
    await waitForSave(page);
    await expect(control).toHaveAttribute("aria-pressed", "false");
    await expect(control).toHaveText("Personal events are not in your Pulse Digest");

    // **The server took it.** The control moving is not the proof; the server holding
    // the new value is.
    const after = await storedPreference(page);
    expect(after.include_personal_events).toBe(false);

    // **And the schedule was not disturbed.** The endpoint has no "change one field"
    // mode, so the toggle sends the schedule back — and a save that moved the delivery
    // time would be a bug the walkthrough should catch.
    expect(after.delivery_time).toBe(before.delivery_time);
    expect(after.timezone).toBe(before.timezone);

    // --- 4. The control ROUND-TRIPS --------------------------------------------------
    //
    // **A second visit proves it persisted.** A control that shows the right value
    // because the client remembered it — rather than because the server still holds it
    // — would pass everything above and fail the product.
    await page.reload();
    await expect(page.getByRole("button", { name: CONTROL_NAME })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    // --- 5. Opting back IN -----------------------------------------------------------
    //
    // **The control is not write-once.** The second save takes the *update* branch of
    // the write path, which the first save never reached.
    await page.getByRole("button", { name: CONTROL_NAME }).click();
    await waitForSave(page);
    await expect(page.getByRole("button", { name: CONTROL_NAME })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    const restored = await storedPreference(page);
    expect(restored.include_personal_events).toBe(true);
  });

  test("the digest the user receives changes: the personal event leaves Slot 1", async ({
    page,
  }) => {
    const account = await seedAccount("free");
    await signIn(page, account);
    const userId = await userIdFor(page, account);

    // --- The BEFORE -------------------------------------------------------------------
    //
    // **The digest for tomorrow holds the personal event in Slot 1.** The walkthrough
    // needs one, or "the digest changed" would be vacuous — and it needs it *in the
    // digest*, not merely qualifying, because a qualifying event that lost the slot to
    // a public one would prove nothing about the opt-out.
    //
    // **Tomorrow, and not today.** The composition is idempotent per local date, so
    // today's digest is whatever it already was. **Tomorrow's has not been composed
    // yet**, so this composes it fresh and reads the result.
    //
    // **And the event is placed for that day**, not for wall-clock now — the window is
    // `[now, now + 48h]` measured from the *composition's* clock, so an event that
    // qualifies today does not qualify tomorrow.
    await createPersonalEvent(userId, 1);
    await resetDigests(userId, 1);
    const before = await composeFor(page, account, 1);
    expect(before.cards.length).toBeGreaterThan(0);
    expect(before.cards[0].event_kind).toBe("personal");
    expect(before.personal_qualifying_count).toBe(1);

    // --- The user opts out, in the browser ---------------------------------------------
    await page.goto("/settings/digest");
    const control = page.getByRole("button", { name: CONTROL_NAME });
    await expect(control).toHaveAttribute("aria-pressed", "true");
    await control.click();
    await waitForSave(page);
    await expect(control).toHaveAttribute("aria-pressed", "false");

    // **The server took it** — the control moving is not the proof.
    const after = await storedPreference(page);
    expect(after.include_personal_events).toBe(false);

    // --- The AFTER ---------------------------------------------------------------------
    //
    // **The day after tomorrow**, because tomorrow's digest now exists and the
    // composition is idempotent — composing tomorrow again would return it unchanged
    // and the walkthrough would "prove" that the opt-out changes nothing.
    //
    // **And the event is placed for that day too** — the same reason, and the same
    // helper. **The walkthrough deletes the previous day's event**, so the two digests
    // are not reading the same row.
    await createPersonalEvent(userId, 2);
    await resetDigests(userId, 2);
    const tomorrow = await composeFor(page, account, 2);
    expect(tomorrow.cards.length).toBeGreaterThan(0);

    // **Slot 1 is no longer the personal event.**
    expect(tomorrow.cards[0].event_kind).not.toBe("personal");
    // **And the personal event is gone from the whole digest**, not just demoted.
    expect(tomorrow.cards.every((card) => card.event_kind === "public")).toBe(true);
    // **And the product does not know about it** — the count is suppressed, so an
    // opted-out event is not the reason the user keeps receiving a Ping.
    expect(tomorrow.personal_qualifying_count).toBe(0);

    // **And the two digests are different days** — the guard against the idempotence
    // trap above, stated as an assertion so a future edit that puts both on the same
    // day fails here rather than passing vacuously.
    expect(tomorrow.local_date).not.toBe(before.local_date);
  });

  test("a user with no schedule is told what to do, not given a control that fails", async ({
    page,
  }) => {
    // **The account is one the walkthrough created**, and it is a real one — a user who
    // completed onboarding by *advancing* through the steps without ever sending the
    // digest preference.
    //
    // **That state is reachable, and it is the state this test is about.** `skip_all`
    // and "skip the digest step" both write a default `DigestPreference`; `advance_step`
    // past the last step does **not** — it sets `completed_at` and nothing else. So a
    // user who presses Continue three times, with the client never having sent the
    // digest `PUT`, finishes onboarding with `delivery_time = None`.
    //
    // **The reviewer account cannot be used here**, and the reason is worth recording:
    // it has not completed onboarding at all, so `homeRoute` redirects it to
    // `/onboarding` and the settings screen is never reached. The half-onboarded user
    // is redirected away; the *completed but schedule-less* user is the one who sees
    // this control.
    const account = {
      key: "walkthrough-no-schedule",
      email: "nosched-walkthrough@example.test",
      password: "walkthrough-local",
      plan: "free",
    };
    await signIn(page, account);

    await page.goto("/settings/digest");
    const control = page.getByRole("button", { name: CONTROL_NAME });
    await expect(control).toBeVisible();

    // **The control is disabled** — a control that can only fail is worse than one that
    // is honestly unavailable.
    await expect(control).toBeDisabled();

    // **And it says why, in words a user can act on.**
    await expect(page.locator(NO_SCHEDULE)).toHaveText("Set your delivery time first.");
  });
});
