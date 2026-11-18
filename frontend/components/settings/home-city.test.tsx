/**
 * `Component.Settings.HomeCity` — the control a shipped link already promised.
 *
 * Browse's hero and its empty state both offer "Change city" and send the reader to
 * `/settings/account`, which had no city control at all. So the one route the product
 * gives for fixing an empty Browse arrived at a page that could not fix it.
 *
 * What is pinned here: the city is **shown**, it is **changeable**, the schedule rides
 * along unchanged (the server takes `delivery_time` and `timezone` or refuses), the
 * server's answer wins over the client's guess, a refusal puts the old city back, and a
 * user with no city is offered a placeholder that is never submitted.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { HomeCity, citySourceNote } from "@/components/settings/home-city";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

const CHOICES = ["Dhaka", "Fixtureville", "Montgomery"];

function answer(city: string | null, city_source: string | null = "choice") {
  return { data: { digest: { city, city_source } }, error: null };
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockResolvedValue(answer("Dhaka"));
});

function renderControl(city: string | null = "Montgomery", source: string | null = "choice") {
  render(
    <HomeCity
      initialCity={city}
      initialCitySource={source}
      choices={CHOICES}
      deliveryTime="09:00:00"
      timezone="Asia/Dhaka"
    />,
  );
  return screen.getByRole("combobox", { name: "City" });
}

it("shows the stored city", () => {
  expect(renderControl("Montgomery")).toHaveValue("Montgomery");
});

it("offers every city the catalog can serve", () => {
  renderControl();

  const offered = screen.getAllByRole("option").map((option) => option.textContent);
  expect(offered).toEqual(CHOICES);
});

it("saves the chosen city", async () => {
  const select = renderControl("Montgomery");

  fireEvent.change(select, { target: { value: "Dhaka" } });

  await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
  expect(PUT.mock.calls[0][1].body.city).toBe("Dhaka");
});

it("sends the schedule back unchanged, because the server requires both", async () => {
  // A wall clock without its zone is not a schedule: the endpoint takes all three or
  // refuses, and this control owns none of the schedule.
  fireEvent.change(renderControl(), { target: { value: "Dhaka" } });

  await waitFor(() => expect(PUT).toHaveBeenCalled());
  expect(PUT.mock.calls[0][1].body).toEqual({
    city: "Dhaka",
    delivery_time: "09:00:00",
    timezone: "Asia/Dhaka",
  });
});

it("takes the server's city over the one it sent", async () => {
  // The server replaces a city it cannot serve with a fallback, so what it stored is not
  // always what was asked for — and the control must show what is true.
  PUT.mockResolvedValue(answer("Fixtureville", "fallback"));
  const select = renderControl("Montgomery");

  fireEvent.change(select, { target: { value: "Dhaka" } });

  await waitFor(() => expect(select).toHaveValue("Fixtureville"));
  expect(screen.getByText(/We don't have your city yet/)).toBeInTheDocument();
});

it("puts the old city back when the save is refused", async () => {
  PUT.mockResolvedValue({ data: null, error: { code: "nope", message: "No." } });
  const select = renderControl("Montgomery");

  fireEvent.change(select, { target: { value: "Dhaka" } });

  await waitFor(() => expect(screen.getByText("No.")).toBeInTheDocument());
  expect(select).toHaveValue("Montgomery");
});

it("puts the old city back when the request never lands", async () => {
  PUT.mockRejectedValue(new Error("offline"));
  const select = renderControl("Montgomery");

  fireEvent.change(select, { target: { value: "Dhaka" } });

  await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
  expect(select).toHaveValue("Montgomery");
});

it("offers a placeholder when the user has no city, and never submits it", async () => {
  const select = renderControl(null, null);

  expect(select).toHaveValue("");
  expect(screen.getByRole("option", { name: "Choose a city" })).toBeInTheDocument();

  // Selecting the placeholder is not a request this endpoint could carry out: a null
  // city means "leave it alone", so there is no way to say "no city" here.
  fireEvent.change(select, { target: { value: "" } });
  expect(PUT).not.toHaveBeenCalled();
});

it("keeps showing a stored city the catalog no longer serves", () => {
  // A select whose value is missing from its options renders blank, which would read as
  // "you have no city" to someone who has one.
  const select = renderControl("Atlantis");

  expect(select).toHaveValue("Atlantis");
  expect(screen.getByRole("option", { name: "Atlantis" })).toBeInTheDocument();
});

it("says when the city was guessed rather than chosen", () => {
  expect(citySourceNote("Dhaka", "geo")).toMatch(/Guessed from your connection/);
  expect(citySourceNote("Dhaka", "choice")).toBe(
    "Browse and your Pulse Digest both use this city.",
  );
  expect(citySourceNote(null, null)).toBe("Browse and your Pulse Digest both use this city.");
});
