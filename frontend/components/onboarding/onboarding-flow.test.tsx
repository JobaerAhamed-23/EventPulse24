import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";

/**
 * The flow, and the rule that keeps the screen and the server agreeing.
 *
 * The step endpoints take no body: `POST /step` advances *the server's* step. The mockups
 * have a Back button and the server has no "go back", so the view can sit behind the
 * server — and when it does, Continue must move the view without moving the server.
 * Getting that wrong does not throw; it silently finishes a step the user never saw.
 */

const POST = vi.fn();
const PUT = vi.fn();
const GET = vi.fn();
const replace = vi.fn();
const refresh = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    PUT: (...args: unknown[]) => PUT(...args),
    GET: (...args: unknown[]) => GET(...args),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh }),
}));

const CHIPS = [
  { key: "tech_meetups", label: "Tech & meetups" },
  { key: "sports_fitness", label: "Sports & fitness" },
  { key: "arts_culture", label: "Arts & culture" },
  { key: "family_kids", label: "Family & kids" },
];

function state(step: number | null, extra: Record<string, unknown> = {}) {
  return {
    completed: step === null,
    current_step: step,
    step_name: null,
    interests: [],
    // The three fields the digest preference grew: the home city, how it was arrived
    // at, and the personal-events opt-out (which defaults to included).
    digest: {
      delivery_time: null,
      timezone: null,
      city: null,
      city_source: null,
      include_personal_events: true,
    },
    last_advanced_at: null,
    completed_at: null,
    ...extra,
  };
}

/** The API's answer to a step call: the new state. */
function stepped(step: number | null) {
  return { data: state(step), error: undefined };
}

function renderFlow(step: number, extra: Record<string, unknown> = {}) {
  return render(<OnboardingFlow state={state(step, extra)} chips={CHIPS} connection={null} />);
}

beforeEach(() => {
  POST.mockReset();
  PUT.mockReset();
  GET.mockReset();
  replace.mockReset();
  refresh.mockReset();
  GET.mockResolvedValue({ data: { items: [] }, error: undefined });
  PUT.mockResolvedValue({ data: {}, error: undefined });
});

const back = () => screen.getByRole("button", { name: "← Back" });
const continueButton = () => screen.getByRole("button", { name: /Continue|Open my brief/ });
const skipStep = () => screen.getByRole("button", { name: "Skip for now" });
const skipAll = () => screen.getByRole("button", { name: "Skip all" });

describe("resume", () => {
  it("opens on the step the server recorded, not step 1", async () => {
    // FR-1: "resumed at the same step on return within 7 days". The first paint is the
    // recorded step — a flow that opened at step 1 and then jumped would not be a resume.
    renderFlow(2);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "What kinds of things?",
    );
  });

  it("opens on step 3 when that is where the user got to", async () => {
    renderFlow(3);

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "When should we ping you?",
    );
  });

  it("shows the stored picks when returning to the interests step", async () => {
    renderFlow(2, { interests: ["tech_meetups"] });

    expect(screen.getByRole("button", { name: /Tech & meetups/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

describe("Back", () => {
  it("moves the screen and calls nothing", async () => {
    renderFlow(2);

    fireEvent.click(back());

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "Connect a calendar?",
    );
    expect(POST).not.toHaveBeenCalled();
    expect(PUT).not.toHaveBeenCalled();
  });

  it("is not offered on the first step", () => {
    renderFlow(1);

    expect(screen.queryByRole("button", { name: "← Back" })).toBeNull();
  });
});

describe("Continue", () => {
  it("advances the server when the screen is on the live step", async () => {
    POST.mockResolvedValue(stepped(2));
    renderFlow(1);

    fireEvent.click(continueButton());

    await vi.waitFor(() => {
      expect(POST).toHaveBeenCalledWith("/api/personal/onboarding/step");
    });
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "What kinds of things?",
    );
  });

  it("moves the screen only when revisiting a step the server has passed", async () => {
    // The server is on 2; the user went Back to 1. Advancing here would push the server
    // to 3 and the user would never see step 2 — a step finished without being answered.
    renderFlow(2);
    fireEvent.click(back());
    await screen.findByRole("heading", { level: 1, name: "Connect a calendar?" });

    fireEvent.click(continueButton());

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "What kinds of things?",
    );
    expect(POST).not.toHaveBeenCalled();
  });

  it("advances the server again once the screen catches up with it", async () => {
    POST.mockResolvedValue(stepped(3));
    renderFlow(2);
    fireEvent.click(back());
    await screen.findByRole("heading", { level: 1, name: "Connect a calendar?" });
    fireEvent.click(continueButton()); // view 1 → 2, no call
    await screen.findByRole("heading", { level: 1, name: "What kinds of things?" });

    fireEvent.click(continueButton()); // view === server, so this one calls

    await vi.waitFor(() => {
      expect(POST).toHaveBeenCalledWith("/api/personal/onboarding/step");
    });
  });

  it("finishes the onboarding from the last step", async () => {
    POST.mockResolvedValue(stepped(null));
    renderFlow(3);

    fireEvent.click(continueButton());

    await vi.waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/");
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("goes home when the onboarding was finished in another tab", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "onboarding_already_complete",
        message: "You've already finished setting things up.",
      },
    });
    renderFlow(2);

    fireEvent.click(continueButton());

    await vi.waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/");
    });
  });
});

describe("Skip for now", () => {
  it("skips the live step through the API", async () => {
    POST.mockResolvedValue(stepped(2));
    renderFlow(1);

    fireEvent.click(skipStep());

    await vi.waitFor(() => {
      expect(POST).toHaveBeenCalledWith("/api/personal/onboarding/step/skip");
    });
  });

  it("calls nothing when the screen is behind the server", async () => {
    // Skipping here would skip the *live* step, which is not the one on screen.
    renderFlow(2);
    fireEvent.click(back());
    await screen.findByRole("heading", { level: 1, name: "Connect a calendar?" });

    fireEvent.click(skipStep());

    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(
      "What kinds of things?",
    );
    expect(POST).not.toHaveBeenCalled();
  });
});

describe("Skip all", () => {
  it.each([1, 2, 3])("finishes the whole flow from step %i", async (step) => {
    POST.mockResolvedValue({ data: state(null), error: undefined });
    renderFlow(step);

    fireEvent.click(skipAll());

    await vi.waitFor(() => {
      expect(POST).toHaveBeenCalledWith("/api/personal/onboarding/skip-all");
    });
    expect(replace).toHaveBeenCalledWith("/");
  });
});

describe("a request that never reaches the API", () => {
  // openapi-fetch rethrows a failed `fetch`, so a dropped connection is a *throw*, not a
  // returned error. Uncaught, it would leave the footer's buttons disabled for good.
  it("says so, and leaves the step usable", async () => {
    POST.mockRejectedValue(new TypeError("Failed to fetch"));
    renderFlow(1);

    fireEvent.click(continueButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach Pulse. Try again.");
    expect(continueButton()).toBeEnabled();
  });

  it("does not move the step on", async () => {
    POST.mockRejectedValue(new TypeError("Failed to fetch"));
    renderFlow(1);

    fireEvent.click(continueButton());

    await screen.findByRole("alert");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Connect a calendar?");
  });

  it("recovers a failed skip-all", async () => {
    POST.mockRejectedValue(new TypeError("Failed to fetch"));
    renderFlow(2);

    fireEvent.click(skipAll());

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach Pulse. Try again.");
    expect(skipAll()).toBeEnabled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("recovers a failed save, and keeps the picks", async () => {
    PUT.mockRejectedValue(new TypeError("Failed to fetch"));
    renderFlow(2);

    fireEvent.click(screen.getByRole("button", { name: /Tech & meetups/ }));
    fireEvent.click(continueButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach Pulse. Try again.");
    expect(POST).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Tech & meetups/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

describe("saving", () => {
  it("sends the interest keys, then advances", async () => {
    POST.mockResolvedValue(stepped(3));
    renderFlow(2);

    fireEvent.click(screen.getByRole("button", { name: /Tech & meetups/ }));
    fireEvent.click(continueButton());

    // The save comes first and the advance follows it, so waiting on the advance proves
    // the order as well as the bodies.
    await vi.waitFor(() => {
      expect(POST).toHaveBeenCalledWith("/api/personal/onboarding/step");
    });
    expect(PUT).toHaveBeenCalledWith("/api/personal/onboarding/interests", {
      body: { chip_keys: ["tech_meetups"] },
    });
  });

  it("sends an empty list when nothing is picked", async () => {
    POST.mockResolvedValue(stepped(3));
    renderFlow(2);

    fireEvent.click(continueButton());

    await vi.waitFor(() => {
      expect(PUT).toHaveBeenCalledWith("/api/personal/onboarding/interests", {
        body: { chip_keys: [] },
      });
    });
  });

  it("sends the delivery time and zone from the digest step", async () => {
    POST.mockResolvedValue(stepped(null));
    renderFlow(3);

    fireEvent.change(screen.getByLabelText("Pulse Digest delivery time"), {
      target: { value: "07:30" },
    });
    fireEvent.change(screen.getByLabelText("Timezone"), {
      target: { value: "America/New_York" },
    });
    fireEvent.click(continueButton());

    await vi.waitFor(() => {
      expect(PUT).toHaveBeenCalledWith("/api/personal/onboarding/digest-preference", {
        body: { delivery_time: "07:30", timezone: "America/New_York" },
      });
    });
  });

  it("does not advance when the save is refused", async () => {
    PUT.mockResolvedValue({
      data: undefined,
      error: { code: "too_many_interests", message: "You can pick up to three interests." },
    });
    renderFlow(2);

    fireEvent.click(continueButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You can pick up to three interests.",
    );
    expect(POST).not.toHaveBeenCalled();
  });
});
