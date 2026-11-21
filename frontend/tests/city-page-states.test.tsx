/**
 * The city page's degradation — and what the collection status may add to it.
 *
 * **The city page has two questions, and they are not the same one.** FR-27's
 * threshold asks whether the city has enough events on record to deserve a page; the
 * provisioning status asks whether our *collection* of it is working. The threshold
 * decides whether the page shows a listing or the "coming soon" sparse state, and the
 * status **only ever adds a sentence to the sparse state** — it never removes the
 * "coming soon" copy, and it never turns a published city's listing into a sparse
 * state.
 *
 * **That asymmetry is the point of this file.** A published city is published, whatever
 * its collection is doing: a `live` city that is between seasons still has its listing
 * (FR-27's own answer), and a `collecting` city that somehow has enough events on
 * record is published and shows them. The status is a fact about *our work*, and our
 * work does not un-publish a city.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CityPage } from "@/components/city-page/city-page";
import type { CityPageOut } from "@/lib/city-page-read";

/** A published city with one event on its listing. */
function page(overrides: Partial<CityPageOut> = {}): CityPageOut {
  return {
    slug: "brooklyn",
    name: "Brooklyn",
    country_code: "US",
    region: "NY",
    is_published: true,
    event_count: 42,
    items: [
      {
        canonical_url: "https://brooklynartscouncil.org/events/calm",
        city: "Brooklyn",
        description: "A short, opinionated panel on building products that respect attention.",
        end_time_utc: null,
        event_version: 3,
        id: "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061",
        is_sold_out: false,
        score: 4,
        slug: "brooklyn-symphony",
        start_time_tz: "America/New_York",
        start_time_utc: "2026-11-07T23:00:00Z",
        status: "published",
        tags: ["nearby"],
        title: "Brooklyn Symphony open rehearsal",
        tz_review_pending: false,
        venue_name: "BAM Howard Gilman Opera House",
      },
    ],
    page: 1,
    page_size: 24,
    has_next: false,
    city_collection_status: "",
    ...overrides,
  };
}

function renderPage(overrides: Partial<CityPageOut> = {}) {
  return render(<CityPage page={page(overrides)} currentPage={1} />);
}

describe("a published city shows its listing", () => {
  it("shows the events", () => {
    renderPage();

    expect(document.querySelectorAll("[data-city-event]").length).toBeGreaterThan(0);
  });

  it("is not the sparse state", () => {
    renderPage();

    expect(document.querySelector("[data-city-coming-soon]")).toBeNull();
  });

  it("says nothing about the collection, whatever the status", () => {
    // **A published city is published.** The status is a fact about our collection,
    // and our collection's state does not un-publish a city that has earned a listing.
    renderPage({ city_collection_status: "collecting" });

    expect(document.querySelector("[data-city-coming-soon]")).toBeNull();
    expect(document.querySelector("[data-city-collecting]")).toBeNull();
    expect(document.querySelector("[data-city-no-sources]")).toBeNull();
  });
});

describe("the sparse state", () => {
  it("says the city is coming soon", () => {
    // **A sparse city is a real city whose page is not published yet.** It is a 200,
    // not a 404 — a URL that vanishes after ranking throws the ranking away.
    renderPage({ is_published: false, event_count: 2, items: [] });

    expect(document.querySelector("[data-city-coming-soon]")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: /Coming soon/ })).toBeTruthy();
  });

  it("keeps the coming-soon copy whatever the collection status", () => {
    // **The threshold's answer is the threshold's answer.** The status only *adds* a
    // sentence; it never removes the one that is true.
    for (const status of ["collecting", "yielded_nothing", "paused", "no_providers", "live", ""]) {
      const view = renderPage({
        is_published: false,
        event_count: 0,
        items: [],
        city_collection_status: status,
      });

      expect(document.querySelector("[data-city-coming-soon]")).toBeTruthy();
      expect(screen.getByRole("heading", { level: 2, name: /Coming soon/ })).toBeTruthy();
      view.unmount();
    }
  });

  it("adds the collecting sentence when we are collecting", () => {
    renderPage({
      is_published: false,
      event_count: 0,
      items: [],
      city_collection_status: "collecting",
    });

    expect(screen.getByText(/We're collecting events for Brooklyn/)).toBeTruthy();
    expect(document.querySelector("[data-city-collecting]")).toBeTruthy();
  });

  it("adds the no-sources sentence when we have no sources", () => {
    for (const status of ["yielded_nothing", "paused", "no_providers", "failed"]) {
      const view = renderPage({
        is_published: false,
        event_count: 0,
        items: [],
        city_collection_status: status,
      });

      expect(screen.getByText(/couldn't find any event sources for Brooklyn/)).toBeTruthy();
      expect(document.querySelector("[data-city-no-sources]")).toBeTruthy();
      view.unmount();
    }
  });

  it("says nothing extra when the collection is working", () => {
    // **A `live` city below the threshold has nothing to add.** Its collection is
    // working, and the threshold's "coming soon" is the whole of the truth.
    renderPage({ is_published: false, event_count: 0, items: [], city_collection_status: "live" });

    expect(document.querySelector("[data-city-collecting]")).toBeNull();
    expect(document.querySelector("[data-city-no-sources]")).toBeNull();
  });

  it("says nothing extra for a status nobody wrote", () => {
    // **An unknown status reaches the surface as silence, not as a guess.** A status
    // added to the backend must not turn into a sentence no one wrote.
    renderPage({
      is_published: false,
      event_count: 0,
      items: [],
      city_collection_status: "a_status_from_the_future",
    });

    expect(document.querySelector("[data-city-collecting]")).toBeNull();
    expect(document.querySelector("[data-city-no-sources]")).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: /Coming soon/ })).toBeTruthy();
  });
});

describe("the states do not collapse into one another", () => {
  it("the collecting sentence and the no-sources sentence are different sentences", () => {
    // **Two different facts about our coverage, and the page must not say one for the
    // other.** A collecting city *has* sources and is waiting; a no-sources city has
    // nothing to collect from.
    const collecting = renderPage({
      is_published: false,
      event_count: 0,
      items: [],
      city_collection_status: "collecting",
    });
    const collectingText = document.querySelector("[data-city-collecting]")?.textContent ?? "";
    collecting.unmount();

    renderPage({
      is_published: false,
      event_count: 0,
      items: [],
      city_collection_status: "yielded_nothing",
    });
    const noSourcesText = document.querySelector("[data-city-no-sources]")?.textContent ?? "";

    expect(collectingText).not.toBe(noSourcesText);
    expect(collectingText).not.toBe("");
    expect(noSourcesText).not.toBe("");
  });

  it("a city with no collection status is not the collecting state", () => {
    // **A city that was never provisioned has made no attempt to collect.** Saying we
    // are collecting for it would be a claim about work that was never started.
    renderPage({ is_published: false, event_count: 0, items: [], city_collection_status: "" });

    expect(document.querySelector("[data-city-collecting]")).toBeNull();
    expect(document.querySelector("[data-city-no-sources]")).toBeNull();
  });
});
