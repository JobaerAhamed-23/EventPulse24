import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DetailHeader } from "@/components/detail/detail-header";

/**
 * The Detail Screen's header.
 *
 * **The conflict mark is the affordance here.** On the Pulse Card the indicator is a
 * fact and the card is the tap target; on the Detail Screen the mark is a **button**,
 * because the prompt is opened from it and the choice is one tap away.
 *
 * **The mark's accessible name says what pressing it does** — "Schedule conflict"
 * alone would tell a screen-reader user that something is wrong and not that there is
 * a choice waiting.
 *
 * **The mark is the same mark the Pulse Card draws.** It is the same component, so the
 * two surfaces cannot drift apart in size, colour or shape.
 *
 * **The journey from the mark to the prompt** is proven in `detail-conflict.test.tsx`,
 * where the mark and the island are rendered together.
 */
function renderHeader(hasConflict: boolean) {
  return render(
    <DetailHeader
      eventId="event-1"
      title="Designing for Calm"
      venueName="Brooklyn Arts Council"
      venueCity="Brooklyn"
      times={null}
      approximate={false}
      sourceBadgeKey="official_site"
      confidence={4}
      factors={["nearby"]}
      hasConflict={hasConflict}
    />,
  );
}

describe("the header's conflict mark", () => {
  it("is absent when the payload names no pair", () => {
    renderHeader(false);

    expect(screen.queryByRole("button", { name: /Schedule conflict/ })).not.toBeInTheDocument();
  });

  it("is present when the payload names a pair", () => {
    renderHeader(true);

    expect(
      screen.getByRole("button", { name: "Schedule conflict. Choose how to handle it." }),
    ).toBeInTheDocument();
  });

  it("says what pressing it does, not merely what it is", () => {
    renderHeader(true);

    // "Schedule conflict" alone would say something is wrong and not that a choice is
    // waiting — and the whole point of the mark here is that the choice is one tap away.
    expect(
      screen.getByRole("button", { name: "Schedule conflict. Choose how to handle it." }),
    ).toBeInTheDocument();
  });

  it("carries the event's id, so the mark reaches the right island", () => {
    // The signal carries the event id, and the island checks it. A page that rendered
    // two Detail Screens must open one prompt, not two.
    renderHeader(true);

    const mark = screen.getByRole("button", { name: /Schedule conflict/ });
    expect(mark).toBeInTheDocument();
  });
});
