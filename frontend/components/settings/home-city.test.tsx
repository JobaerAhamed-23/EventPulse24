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
 *
 * **And the two strings per city are the point.** The catalog's `label` is what a reader
 * reads and its `value` is what a preference holds — "Portland, Oregon" and "Portland,
 * OR" — so the option shows one and submits the other. A control that showed the value
 * would offer two cities called "Atlanta, Georgia" and "Tbilisi, Georgia" without
 * telling them apart, and one that submitted the label would store a string the server
 * does not hold.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { HomeCity, citySourceNote } from "@/components/settings/home-city";
import type { CityChoice } from "@/lib/home-city-read";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/**
 * The catalog's choices, in the shape the endpoint returns.
 *
 * **`Montgomery` has the same label and value**, which the catalog's own rows never do —
 * it is here because a stored city with no label of its own is exactly this shape.
 */
const CHOICES: CityChoice[] = [
  { value: "Chattogram, Bangladesh", label: "Chattogram, Bangladesh" },
  { value: "Dhaka", label: "Dhaka, Bangladesh" },
  { value: "Portland, OR", label: "Portland, Oregon" },
];

function answer(city: string | null, city_source: string | null = "choice") {
  return { data: { digest: { city, city_source } }, error: null };
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockResolvedValue(answer("Dhaka"));
});

function renderControl(city: string | null = "Dhaka", source: string | null = "choice") {
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
  expect(renderControl("Dhaka")).toHaveValue("Dhaka");
});

it("offers every city the catalog holds", () => {
  renderControl();

  const offered = screen.getAllByRole("option").map((option) => option.textContent);
  expect(offered).toEqual(CHOICES.map((choice) => choice.label));
});

it("shows the label, not the value, for a city whose two forms differ", () => {
  // **The reader reads "Portland, Oregon"; the server stores "Portland, OR".** A control
  // that showed the value would offer two "…, Georgia" entries and tell the reader
  // nothing about which is which.
  renderControl();

  expect(screen.getByRole("option", { name: "Portland, Oregon" })).toHaveValue("Portland, OR");
});

it("saves the chosen city's value, not its label", async () => {
  // **The label is for the reader and the value is for the server.** The PUT carries the
  // catalog's own string, because that is the string `DigestPreference.city` holds.
  const select = renderControl("Dhaka");

  fireEvent.change(select, { target: { value: "Portland, OR" } });

  await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
  expect(PUT.mock.calls[0][1].body.city).toBe("Portland, OR");
});

it("sends the schedule back unchanged, because the server requires both", async () => {
  // A wall clock without its zone is not a schedule: the endpoint takes all three or
  // refuses, and this control owns none of the schedule.
  fireEvent.change(renderControl(), { target: { value: "Portland, OR" } });

  await waitFor(() => expect(PUT).toHaveBeenCalled());
  expect(PUT.mock.calls[0][1].body).toEqual({
    city: "Portland, OR",
    delivery_time: "09:00:00",
    timezone: "Asia/Dhaka",
  });
});

it("takes the server's city over the one it sent", async () => {
  // The server replaces a city it cannot serve with a fallback, so what it stored is not
  // always what was asked for — and the control must show what is true.
  PUT.mockResolvedValue(answer("Fixtureville", "fallback"));
  const select = renderControl("Dhaka");

  fireEvent.change(select, { target: { value: "Portland, OR" } });

  await waitFor(() => expect(select).toHaveValue("Fixtureville"));
  expect(screen.getByText(/We don't have your city yet/)).toBeInTheDocument();
});

it("puts the old city back when the save is refused", async () => {
  PUT.mockResolvedValue({ data: null, error: { code: "nope", message: "No." } });
  const select = renderControl("Dhaka");

  fireEvent.change(select, { target: { value: "Portland, OR" } });

  await waitFor(() => expect(screen.getByText("No.")).toBeInTheDocument());
  expect(select).toHaveValue("Dhaka");
});

it("puts the old city back when the request never lands", async () => {
  PUT.mockRejectedValue(new Error("offline"));
  const select = renderControl("Dhaka");

  fireEvent.change(select, { target: { value: "Portland, OR" } });

  await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
  expect(select).toHaveValue("Dhaka");
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

it("keeps showing a stored city the catalog no longer offers", () => {
  // A select whose value is missing from its options renders blank, which would read as
  // "you have no city" to someone who has one.
  const select = renderControl("Atlantis");

  expect(select).toHaveValue("Atlantis");
  expect(screen.getByRole("option", { name: "Atlantis" })).toBeInTheDocument();
});

it("shows a stored city the catalog no longer offers as its own label", () => {
  // **There is nothing better to show.** The catalog's disambiguating form for a city it
  // does not hold is unknown, and inventing one would be a fabrication — so the stored
  // string is the label.
  renderControl("Atlantis");

  expect(screen.getByRole("option", { name: "Atlantis" })).toHaveValue("Atlantis");
});

it("does not offer a stored city the catalog still holds twice", () => {
  // **The stored city is matched by its value.** A duplicate option would show the same
  // city twice and leave the reader wondering which one is theirs.
  renderControl("Portland, OR");

  const options = screen.getAllByRole("option").map((option) => option.textContent);
  expect(options.filter((text) => text === "Portland, Oregon")).toHaveLength(1);
});

it("picks a city the catalog holds and nothing has been collected for, and keeps it", async () => {
  // **The headline.** The catalog is a map of the world, not a mirror of what we happen
  // to have: a reader in a city with no ingested events may pick it, and the pick is
  // kept. **Against the old control — whose options were the preview's list of cities
  // with events — this city would not have been offered at all.**
  const select = renderControl(null, null);

  fireEvent.change(select, { target: { value: "Portland, OR" } });

  await waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
  expect(PUT.mock.calls[0][1].body.city).toBe("Portland, OR");

  // **And the server's answer puts it back**, so the control shows what is true.
  PUT.mockResolvedValue(answer("Portland, OR"));
  fireEvent.change(select, { target: { value: "Portland, OR" } });
  await waitFor(() => expect(select).toHaveValue("Portland, OR"));
});

it("says when the city was guessed rather than chosen", () => {
  expect(citySourceNote("Dhaka", "geo")).toMatch(/Guessed from your connection/);
  expect(citySourceNote("Dhaka", "choice")).toBe(
    "Browse and your Pulse Digest both use this city.",
  );
  expect(citySourceNote(null, null)).toBe("Browse and your Pulse Digest both use this city.");
});

it("still labels a fallback city honestly", () => {
  // **The fallback is still live** — only a *chosen* city outside the catalog is refused.
  // A geo guess and a backfill still fall back, and their accounts still carry one.
  expect(citySourceNote("Fixtureville", "fallback")).toMatch(/We don't have your city yet/);
});
