import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PersonalEventForm } from "@/components/sheets/personal-event-form";

/**
 * The create/edit form (FR-18, AD-6).
 *
 * The properties that matter: the timezone is a **required** field, and the body the
 * form posts carries the UTC instant the browser computed from the local date, time and
 * zone — because the backend stores the instant and never reinterprets a wall-clock
 * time in the zone.
 */

type SubmittedBody = {
  name: string;
  start_time_utc: string;
  start_time_tz: string;
  end_time_utc: string | null;
  location: string | null;
  notes: string | null;
};

function renderForm(overrides: Partial<React.ComponentProps<typeof PersonalEventForm>> = {}): {
  onSubmit: ReturnType<typeof vi.fn>;
} {
  const onSubmit = vi.fn();
  render(
    <PersonalEventForm
      open
      mode="create"
      initial={{
        name: "",
        date: "2026-11-06",
        time: "19:30",
        timezone: "America/New_York",
        endDate: "",
        endTime: "",
        location: "",
        notes: "",
      }}
      onClose={() => {}}
      onSubmit={onSubmit}
      {...overrides}
    />,
  );
  return { onSubmit };
}

/** The body of the last submit call. */
function bodyOf(onSubmit: ReturnType<typeof vi.fn>): SubmittedBody {
  const call = onSubmit.mock.calls.at(-1);
  if (!call) throw new Error("the form was not submitted");
  return call[0] as SubmittedBody;
}

describe("PersonalEventForm", () => {
  it("gives each form on the page its own field ids, so every label finds its own input", () => {
    // The sidenav, the bottom-tab bar, the header's quick-add and the list each mount a
    // form. With fixed ids, the open form's "Name" label pointed at a closed form's input.
    const { container } = render(
      <>
        <PersonalEventForm open mode="create" onClose={() => {}} onSubmit={vi.fn()} />
        <PersonalEventForm open mode="create" onClose={() => {}} onSubmit={vi.fn()} />
      </>,
    );

    const ids = [...container.querySelectorAll("[id]")].map((element) => element.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const label of container.querySelectorAll("label[for]")) {
      const control = (label as HTMLLabelElement).control;
      expect(control, label.textContent ?? "").not.toBeNull();
      expect(label.closest("form")).toBe(control?.closest("form"));
    }
  });

  it("renders the create heading and a close button", () => {
    renderForm();

    expect(screen.getByRole("heading", { name: "Add personal event" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("renders the edit heading in edit mode", () => {
    renderForm({ mode: "edit" });

    expect(screen.getByRole("heading", { name: "Edit personal event" })).toBeInTheDocument();
  });

  describe("the required timezone", () => {
    it("refuses to submit without one", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "Dinner",
          date: "2026-11-06",
          time: "19:30",
          timezone: "",
          endDate: "",
          endTime: "",
          location: "",
          notes: "",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText("Pick a timezone.")).toBeInTheDocument();
    });

    it("marks the field as required", () => {
      renderForm();

      const field = screen.getByLabelText(/Timezone/);
      expect(field).toHaveAttribute("aria-invalid", "false");
      // The "required" marker is a visible word, not only an attribute.
      expect(screen.getAllByText("required").length).toBeGreaterThan(0);
    });

    it("offers only zones the backend accepts", () => {
      renderForm();

      const options = screen
        .getByLabelText(/Timezone/)
        .querySelectorAll("option")
        .values();
      const zones = [...options].map((option) => option.value).filter(Boolean);
      expect(zones).toContain("America/New_York");
      expect(zones).toContain("UTC");
      for (const zone of zones) {
        expect(zone === "UTC" || /^[A-Za-z]+\/[A-Za-z_]+$/.test(zone)).toBe(true);
      }
    });

    it("labels each zone with its city", () => {
      renderForm();

      expect(
        screen.getByRole("option", { name: "America/New_York — New York" }),
      ).toBeInTheDocument();
    });
  });

  describe("the other required fields", () => {
    it("refuses to submit without a name", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "   ",
          date: "2026-11-06",
          time: "19:30",
          timezone: "America/New_York",
          endDate: "",
          endTime: "",
          location: "",
          notes: "",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText("Give the event a name.")).toBeInTheDocument();
    });

    it("refuses to submit without a date", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "Dinner",
          date: "",
          time: "19:30",
          timezone: "America/New_York",
          endDate: "",
          endTime: "",
          location: "",
          notes: "",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText("Pick a date.")).toBeInTheDocument();
    });

    it("refuses to submit without a start time", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "Dinner",
          date: "2026-11-06",
          time: "",
          timezone: "America/New_York",
          endDate: "",
          endTime: "",
          location: "",
          notes: "",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText("Pick a start time.")).toBeInTheDocument();
    });
  });

  describe("the posted body", () => {
    it("carries the UTC instant the zone implies, and the zone itself", () => {
      const { onSubmit } = renderForm();

      fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Dinner" } });
      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(bodyOf(onSubmit)).toMatchObject({
        name: "Dinner",
        // 19:30 in New York on 6 November is EST (UTC−5): half past midnight the next day.
        start_time_utc: "2026-11-07T00:30:00Z",
        start_time_tz: "America/New_York",
        end_time_utc: null,
        location: null,
        notes: null,
      });
    });

    it("converts a summer time by the summer offset", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "Dinner",
          date: "2026-07-06",
          time: "19:30",
          timezone: "America/New_York",
          endDate: "",
          endTime: "",
          location: "",
          notes: "",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      // 19:30 in New York on 6 July is EDT (UTC−4).
      expect(bodyOf(onSubmit).start_time_utc).toBe("2026-07-06T23:30:00Z");
    });

    it("converts the end time too, and it may be on another day", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "Dinner",
          date: "2026-11-06",
          time: "19:30",
          timezone: "America/New_York",
          endDate: "2026-11-07",
          endTime: "01:30",
          location: "",
          notes: "",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(bodyOf(onSubmit).end_time_utc).toBe("2026-11-07T06:30:00Z");
    });

    it("refuses an end time without an end date", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "Dinner",
          date: "2026-11-06",
          time: "19:30",
          timezone: "America/New_York",
          endDate: "",
          endTime: "21:00",
          location: "",
          notes: "",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText("Give both an end date and an end time.")).toBeInTheDocument();
    });

    it("sends the location and notes, trimmed, or null", () => {
      const { onSubmit } = renderForm({
        initial: {
          name: "  Dinner  ",
          date: "2026-11-06",
          time: "19:30",
          timezone: "America/New_York",
          endDate: "",
          endTime: "",
          location: "  Brooklyn  ",
          notes: "  Book the corner table  ",
        },
      });

      fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));

      expect(bodyOf(onSubmit)).toMatchObject({
        name: "Dinner",
        location: "Brooklyn",
        notes: "Book the corner table",
      });
    });
  });

  describe("the pre-highlighted start time", () => {
    it("is not marked by default", () => {
      renderForm();

      expect(
        screen.queryByText("This is the time that overlaps. Shift it to fix it."),
      ).not.toBeInTheDocument();
    });

    it("is marked when the form was opened from the conflict prompt", () => {
      renderForm({ highlightStartTime: true });

      expect(
        screen.getByText("This is the time that overlaps. Shift it to fix it."),
      ).toBeInTheDocument();
    });
  });

  it("closes without saving when the close button is used", () => {
    const onClose = vi.fn();
    renderForm({ onClose });

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
