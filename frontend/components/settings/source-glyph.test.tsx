/**
 * `Component.Source.Glyph` — the monogram tile on each row of the Sources screen.
 *
 * It exists because a long single column of names is the hardest kind of list to scan.
 * What is asserted here is the naming rule (which has edge cases a render cannot show
 * well), the badge tint, and the fact that it stays silent for a screen reader — the
 * name is right beside it, and announcing its abbreviation first would be noise.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceGlyph, monogram } from "@/components/settings/source-glyph";

describe("the monogram", () => {
  it("takes the initial of each of the first two words", () => {
    expect(monogram("Barbican Centre")).toBe("Bc");
    expect(monogram("Stone Theatre")).toBe("St");
  });

  it("takes the first two letters of a single-word name", () => {
    expect(monogram("Songkick")).toBe("So");
  });

  it("ignores the words after the second", () => {
    expect(monogram("New York City Ballet")).toBe("Ny");
  });

  it("survives the names that would otherwise throw", () => {
    // A registry is not a curated list — a name can arrive padded, empty, or one
    // character long, and a glyph that crashed would take the whole screen with it.
    expect(monogram("  Spaced   Out  ")).toBe("So");
    expect(monogram("X")).toBe("X");
    expect(monogram("")).toBe("?");
    expect(monogram("   ")).toBe("?");
  });
});

describe("the tile", () => {
  it("is silent, because the name is beside it", () => {
    render(<SourceGlyph name="Barbican Centre" badge="official" />);

    // No accessible name of its own, and hidden from the tree: announcing "Bc" before
    // "Barbican Centre" is reading an abbreviation of the next thing.
    expect(screen.queryByText("Bc")).toHaveAttribute("aria-hidden", "true");
  });

  it("carries its badge, so the tint is assertable without reading a colour", () => {
    const { container } = render(<SourceGlyph name="Nights Out" badge="community" />);

    expect(container.querySelector("[data-source-glyph='community']")).not.toBeNull();
  });

  it("renders an unfamiliar badge rather than guessing a colour for it", () => {
    // A badge type added server-side should look unfamiliar, not miscoloured — and it
    // must certainly not crash the registry screen.
    const { container } = render(<SourceGlyph name="Something New" badge="syndicated" />);

    const tile = container.querySelector("[data-source-glyph='syndicated']");
    expect(tile).not.toBeNull();
    expect(tile?.textContent).toBe("Sn");
  });
});
