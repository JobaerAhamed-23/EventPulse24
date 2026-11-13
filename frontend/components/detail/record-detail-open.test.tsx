import { render, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RecordDetailOpen } from "@/components/detail/record-detail-open";

/**
 * FR-24's detail-open signal.
 *
 * The neighbour count is a union of savers and openers; nothing had ever written an
 * opener. These tests hold the three properties that made the work item `confirm` rather
 * than a one-liner: it fires, it fires **once**, and a failure is silent.
 */
const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

const EVENT_ID = "9f1c2b4e-0000-7000-8000-00000000abcd";

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue({ data: undefined });
});

describe("RecordDetailOpen", () => {
  it("records the open for the event it was given", async () => {
    render(<RecordDetailOpen eventId={EVENT_ID} />);

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/events/{event_id}/opened", {
        params: { path: { event_id: EVENT_ID } },
      }),
    );
  });

  it("renders nothing", () => {
    const { container } = render(<RecordDetailOpen eventId={EVENT_ID} />);

    expect(container.innerHTML).toBe("");
  });

  it("fires once under Strict Mode's double-invoked effect", async () => {
    // **Strict Mode is the whole point of the ref guard**, and a plain re-render cannot
    // see it: the effect's dependency list is `[eventId]`, so re-rendering with the same
    // id never re-runs it with or without the guard. A probe proved that — removing the
    // guard left the old version of this test green. Strict Mode mounts, unmounts and
    // remounts, which is what actually double-fires the effect.
    render(
      <StrictMode>
        <RecordDetailOpen eventId={EVENT_ID} />
      </StrictMode>,
    );

    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(POST).toHaveBeenCalledTimes(1);
  });

  it("does not re-fire on a re-render with the same event", async () => {
    const { rerender } = render(<RecordDetailOpen eventId={EVENT_ID} />);
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));

    rerender(<RecordDetailOpen eventId={EVENT_ID} />);
    rerender(<RecordDetailOpen eventId={EVENT_ID} />);

    expect(POST).toHaveBeenCalledTimes(1);
  });

  it("says nothing when the write is refused", async () => {
    POST.mockResolvedValue({ error: { code: "server_error", message: "nope" } });
    const { container } = render(<RecordDetailOpen eventId={EVENT_ID} />);

    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  /**
   * **What this test covers, and what it cannot.**
   *
   * It covers the reachable claim: a rejected write changes nothing on screen and does
   * not break the render. It does **not** prove the `.catch` is attached — a probe that
   * deleted it left this file green, and the reason is environmental: Vitest installs its
   * own `unhandledRejection` handler, so a `process.on("unhandledRejection", …)` listener
   * registered inside a test never fires. Verified with a throwaway spec that rejected a
   * bare promise and observed nothing.
   *
   * Stated rather than faked. The `.catch` matters in a browser, where an unhandled
   * rejection is a console error on every detail view, and that is where it would have to
   * be verified — the e2e work item is the place.
   */
  it("changes nothing on screen when the write is rejected", async () => {
    POST.mockRejectedValue(new Error("offline"));
    const { container } = render(<RecordDetailOpen eventId={EVENT_ID} />);

    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });
});
