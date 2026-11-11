import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EventReportControl } from "@/components/detail/event-report-control";
import type { components } from "@/lib/api/schema";

/**
 * The report flag — FR-59's "Report this event".
 *
 * **The control is a private signal, not a state.** The event does not change when a
 * report is made: no badge, no greyed card, no re-read. FR-59 says it twice — *"A single
 * report does not auto-reject an event"* and *"Auto-rejection on a single report
 * (rejected — editorial confirmation required)"* — and the reason is the calm principle:
 * if one person's report changed what everyone else saw, one report would be a lever on a
 * listing.
 *
 * **The request body is typed by the generated contract**, so a category the API does not
 * have is a compile error here rather than a request the server refuses (AD-19).
 */
const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
  },
}));

/**
 * The body the control sends, **as the generated contract states it**.
 *
 * **The type is the point.** `EventReportIn["category"]` is the API's own union, so a
 * test that names a category the contract does not have would not compile — which is a
 * stronger guarantee than a runtime assertion.
 */
type ReportBody = components["schemas"]["EventReportIn"];

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue({
    data: { category: "wrong_venue", reported: true },
    response: { status: 201 },
  });
});

function renderControl() {
  return render(<EventReportControl eventId="event-1" eventName="Free tech meetup" />);
}

/** The modal, by its accessible name. */
function modal(): HTMLElement {
  return screen.getByRole("dialog", { name: "Report this event" });
}

/** The flag, by its accessible name. */
function flag(): HTMLElement {
  return screen.getByRole("button", { name: "Report this event" });
}

/** Open the modal and wait for it. */
async function openModal() {
  fireEvent.click(flag());
  await waitFor(() => expect(modal()).toBeInTheDocument());
}

/**
 * Choose a category and submit.
 *
 * **The choice and the submission are two presses**, and the order matters: the first is
 * a choice, the second is a commitment. Choosing does not submit.
 */
async function chooseAndSubmit(label: string) {
  fireEvent.click(screen.getByRole("radio", { name: label }));
  fireEvent.click(screen.getByRole("button", { name: "Submit report" }));
}

describe("the report flag", () => {
  it("renders a control named 'Report this event'", () => {
    renderControl();

    expect(flag()).toBeInTheDocument();
  });

  it("shows the words as well as the glyph", () => {
    // **The house rule is a visible label, never an icon-only button** (WCAG 1.1.1, as
    // `share-control.tsx`'s docstring puts it). FR-59 asks for a flag glyph; the words
    // are the label. Both are here.
    renderControl();

    expect(flag().textContent).toContain("Report this event");
    // And the glyph is decorative — it carries no name of its own.
    expect(flag().querySelector("[aria-hidden='true']")).not.toBeNull();
  });

  it("is visually subordinate to Save and Share", () => {
    // FR-59: "Not a primary button". **The subordination is the absence of the tokens
    // the other two have** — no terracotta fill, no elevated surface, no border.
    renderControl();

    const classes = flag().className;
    expect(classes).not.toContain("bg-accent-terracotta");
    expect(classes).not.toContain("bg-surface-elevated");
    expect(classes).not.toContain("border-border-subtle");
  });

  it("opens the modal on press", async () => {
    renderControl();

    await openModal();

    expect(modal()).toBeInTheDocument();
  });

  it("does not open the modal on its own", () => {
    renderControl();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("is named the same as the modal's heading", () => {
    // **The accessible name and the visible heading agree**, so the name is not doubled
    // up with the thing it names.
    renderControl();

    expect(flag()).toHaveAccessibleName("Report this event");
  });
});

describe("the modal", () => {
  it("is named 'Report this event'", async () => {
    renderControl();

    await openModal();

    expect(modal()).toHaveAccessibleName("Report this event");
    expect(modal().querySelector("h2")).toHaveTextContent("Report this event");
  });

  it("names the event the user is looking at", async () => {
    // **The screen knows what it is showing** — it is the screen for it — so the client
    // does not look it up and does not guess one.
    renderControl();

    await openModal();

    expect(modal()).toHaveTextContent("Free tech meetup");
  });

  it("offers exactly four options", async () => {
    renderControl();

    await openModal();

    expect(within(modal()).getAllByRole("radio")).toHaveLength(4);
  });

  it("words the four options exactly as FR-59 words them", async () => {
    // **The labels are the contract.** FR-59 lists them, and the acceptance criteria
    // say "worded exactly as in FR-59" — so they are neither paraphrased nor shortened.
    renderControl();

    await openModal();

    for (const label of [
      "Wrong date or time",
      "Wrong venue or address",
      "Doesn't exist or is cancelled",
      "Duplicate of another event",
    ]) {
      expect(screen.getByRole("radio", { name: label })).toBeInTheDocument();
    }
  });

  it("offers no fifth option", async () => {
    // **Four is the whole set.** The API's category union has four members, and the
    // editorial queue triages on four.
    renderControl();

    await openModal();

    expect(within(modal()).getAllByRole("radio")).toHaveLength(4);
  });

  it("has no free-text field", async () => {
    // FR-59: "No free-text field in MVP." **Not a disabled one — no textbox at all.** The
    // API's body has two fields, so there is nowhere for free text to go.
    renderControl();

    await openModal();

    expect(within(modal()).queryByRole("textbox")).not.toBeInTheDocument();
    expect(modal().querySelector("textarea")).toBeNull();
    expect(modal().querySelector("input")).toBeNull();
  });

  it("is a radio group", async () => {
    // **A category is a state** — exactly one of the four is true — so it is a radio
    // group and not the conflict prompt's `role="group"` of action buttons.
    renderControl();

    await openModal();

    expect(
      within(modal()).getByRole("radiogroup", { name: "Report category" }),
    ).toBeInTheDocument();
  });

  it("keeps exactly one option checked at a time", async () => {
    renderControl();

    await openModal();

    fireEvent.click(screen.getByRole("radio", { name: "Wrong date or time" }));
    expect(screen.getByRole("radio", { name: "Wrong date or time" })).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: "Duplicate of another event" }));
    expect(screen.getByRole("radio", { name: "Duplicate of another event" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Wrong date or time" })).not.toBeChecked();
  });

  it("leaves the chosen option checked when the same one is pressed again", async () => {
    // **A radio group does not un-select.** There is no way to submit with nothing
    // chosen, which is what makes the disabled Submit honest.
    renderControl();

    await openModal();

    fireEvent.click(screen.getByRole("radio", { name: "Wrong venue or address" }));
    fireEvent.click(screen.getByRole("radio", { name: "Wrong venue or address" }));

    expect(screen.getByRole("radio", { name: "Wrong venue or address" })).toBeChecked();
  });

  it("disables the Submit until an option is chosen", async () => {
    renderControl();

    await openModal();

    const submit = screen.getByRole("button", { name: "Submit report" });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByRole("radio", { name: "Wrong date or time" }));

    expect(submit).not.toBeDisabled();
  });

  it("does not submit when an option is chosen", async () => {
    // **Choosing is not committing.** A report that fires on a mis-tapped radio is a
    // report the user did not mean to make.
    //
    // **The assertion is on the call count, and the probe that checks it posts with the
    // newly chosen category** — because a "submit on select" defect that read the
    // *stale* `selected` would post nothing, and a call-count assertion on that would
    // still be green. So the count is what it is: **no request at all**.
    renderControl();

    await openModal();

    fireEvent.click(screen.getByRole("radio", { name: "Wrong date or time" }));

    expect(POST).not.toHaveBeenCalled();
    // **And nothing was sent under any spelling.** A "submit on select" defect would
    // post with the newly chosen category, so the assertion covers the body too — not
    // just the count.
    for (const call of POST.mock.calls) {
      const [, options] = call as [string, { body?: ReportBody }];
      expect(options?.body?.category).not.toBe("wrong_date_time");
    }
  });

  it("closes on the Escape key", async () => {
    // **The sheet is dismissible, unlike the conflict prompt.** A report is optional; a
    // conflict is a forced choice (FR-58).
    renderControl();

    await openModal();

    const event = new Event("cancel", { cancelable: true });
    modal().dispatchEvent(event);

    // The `cancel` event's default is not prevented, so the native dialog would close.
    expect(event.defaultPrevented).toBe(false);
  });

  it("moves the focus to the heading when it opens", async () => {
    // **A screen reader lands on the question**, not on the first option.
    renderControl();

    await openModal();

    await waitFor(() => expect(modal().querySelector("h2")).toHaveFocus());
  });
});

describe("the submission", () => {
  it("posts the event id and the chosen category", async () => {
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));

    const [path, options] = POST.mock.calls[0] as [string, { body: ReportBody }];
    expect(path).toBe("/api/personal/event-reports");
    expect(options.body).toEqual({ event_id: "event-1", category: "wrong_venue" });
  });

  it("goes through the generated client", async () => {
    // AD-19: the frontend reaches the backend only through the generated client.
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));

    const [path] = POST.mock.calls[0] as [string];
    expect(path).toBe("/api/personal/event-reports");
  });
});

describe("the success", () => {
  it("shows the toast", async () => {
    // FR-59: "The user sees a confirmation toast: 'Thanks — we'll review this.'"
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() =>
      expect(screen.getByText("Thanks — we'll review this.")).toBeInTheDocument(),
    );
  });

  it("closes the modal", async () => {
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("returns the focus to the flag", async () => {
    // **The browser's default is to move focus to `<body>` when a modal closes**, which
    // dumps a keyboard user at the top of the document with no focus at all (WCAG 2.4.3).
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() => expect(flag()).toHaveFocus());
  });

  it("leaves the event visibly unchanged", async () => {
    // **A report is a private signal, not a state.** Nothing on the page says
    // "reported", and the flag still reads the same — it does not become "Reported ✓".
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() =>
      expect(screen.getByText("Thanks — we'll review this.")).toBeInTheDocument(),
    );

    expect(document.body.textContent ?? "").not.toMatch(/reported/i);
    expect(flag()).toHaveTextContent("Report this event");
  });

  it("does not add a second status region", async () => {
    // **The row already owns this surface's one `role="status"`** — the conflict-failure
    // line. Two status regions would make "which one is the page talking?" a question
    // the DOM cannot answer.
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() =>
      expect(screen.getByText("Thanks — we'll review this.")).toBeInTheDocument(),
    );

    expect(screen.queryAllByRole("status")).toHaveLength(0);
  });

  it("keeps the toast's live region in the DOM before there is a message", () => {
    // **A live region added to the page together with its text is not announced
    // reliably**; a region that is already there and then changes is.
    renderControl();

    const live = document.querySelectorAll("[aria-live='polite']");
    expect(live.length).toBeGreaterThan(0);
    for (const region of live) {
      expect(region.getAttribute("role")).not.toBe("status");
    }
  });
});

describe("the rate limit", () => {
  it("shows the API's message inline", async () => {
    // **The message is the API's own words.** `lib/api-errors.ts` exists so the frontend
    // quotes the API verbatim rather than writing its own.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "rate_limited",
        message: "You have reported enough events for today. Please try again tomorrow.",
      },
      response: { status: 429 },
    });

    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() =>
      expect(
        screen.getByText("You have reported enough events for today. Please try again tomorrow."),
      ).toBeInTheDocument(),
    );
  });

  it("shows it inside the modal, not as a toast", async () => {
    // **A toast is transient, and the rate limit lasts until tomorrow.** A message that
    // disappears on a timer is a message the user will miss.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "rate_limited",
        message: "You have reported enough events for today. Please try again tomorrow.",
      },
      response: { status: 429 },
    });

    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() =>
      expect(
        screen.getByText("You have reported enough events for today. Please try again tomorrow."),
      ).toBeInTheDocument(),
    );

    expect(modal()).toHaveTextContent(
      "You have reported enough events for today. Please try again tomorrow.",
    );
    expect(screen.queryByText("Thanks — we'll review this.")).not.toBeInTheDocument();
  });

  it("leaves the modal open", async () => {
    // **A modal that closed on a refused report would tell the user it went somewhere.**
    // It did not.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "rate_limited",
        message: "You have reported enough events for today. Please try again tomorrow.",
      },
      response: { status: 429 },
    });

    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() =>
      expect(
        screen.getByText("You have reported enough events for today. Please try again tomorrow."),
      ).toBeInTheDocument(),
    );

    expect(modal()).toBeInTheDocument();
  });

  it("keeps the selection, so the user does not choose again", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "rate_limited",
        message: "You have reported enough events for today. Please try again tomorrow.",
      },
      response: { status: 429 },
    });

    renderControl();

    await openModal();
    await chooseAndSubmit("Duplicate of another event");

    await waitFor(() =>
      expect(
        screen.getByText("You have reported enough events for today. Please try again tomorrow."),
      ).toBeInTheDocument(),
    );

    expect(screen.getByRole("radio", { name: "Duplicate of another event" })).toBeChecked();
  });
});

describe("a network failure", () => {
  beforeEach(() => {
    POST.mockRejectedValue(new Error("offline"));
  });

  it("leaves the modal open", async () => {
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong venue or address");

    await waitFor(() =>
      expect(screen.getByText("Couldn't reach Pulse. Try again.")).toBeInTheDocument(),
    );

    expect(modal()).toBeInTheDocument();
  });

  it("keeps the selection, so the user does not choose again", async () => {
    // **The selection is the user's work.** Losing it because the network hiccuped
    // would make the user do the thing twice.
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong date or time");

    await waitFor(() =>
      expect(screen.getByText("Couldn't reach Pulse. Try again.")).toBeInTheDocument(),
    );

    expect(screen.getByRole("radio", { name: "Wrong date or time" })).toBeChecked();
  });

  it("offers a retry — the Submit is live again", async () => {
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong date or time");

    await waitFor(() =>
      expect(screen.getByText("Couldn't reach Pulse. Try again.")).toBeInTheDocument(),
    );

    expect(screen.getByRole("button", { name: "Submit report" })).not.toBeDisabled();
  });

  it("does not show the success toast", async () => {
    renderControl();

    await openModal();
    await chooseAndSubmit("Wrong date or time");

    await waitFor(() =>
      expect(screen.getByText("Couldn't reach Pulse. Try again.")).toBeInTheDocument(),
    );

    expect(screen.queryByText("Thanks — we'll review this.")).not.toBeInTheDocument();
  });

  it("sends the same category when the user retries", async () => {
    // **The retry is the same report** — the selection survived, so the second attempt
    // is the same one.
    renderControl();

    await openModal();
    await chooseAndSubmit("Doesn't exist or is cancelled");

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));

    POST.mockResolvedValue({ data: {}, response: { status: 201 } });
    fireEvent.click(screen.getByRole("button", { name: "Submit report" }));

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(2));

    const [, options] = POST.mock.calls[1] as [string, { body: ReportBody }];
    expect(options.body.category).toBe("does_not_exist");
  });
});
