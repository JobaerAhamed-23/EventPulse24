import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BrandMark } from "@/components/brand-mark";
import { BrandTopbar } from "@/components/brand-topbar";
import { PreAuthFooter } from "@/components/pre-auth/pre-auth-footer";
import { Sidenav } from "@/components/shell/sidenav";

// The sidenav marks the active route from the pathname, so it needs one.
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

// The sidenav mounts the personal-events panel, which is not what this test is about.
vi.mock("@/components/personal-events-panel", () => ({
  PersonalEventsPanel: () => null,
}));

/**
 * The one-logo rule.
 *
 * **The product used to show three different marks.** The pre-auth topbar drew the
 * brand from a PNG; the authed topbar and the sidenav rail drew a `◉` glyph; and the
 * pre-auth footer drew a terracotta dot. Three surfaces, three marks, one product —
 * and a reader on `/signin` and a reader on `/` were looking at different pictures of
 * the same company.
 *
 * **Now they cannot drift.** Every surface renders `BrandMark`, and `BrandMark` has
 * one `src`. This test is what holds that: it asserts that the four brand surfaces
 * all point at the same image, and that the asset on disk is the canonical one.
 */

const CANONICAL_SRC = "/brand/eventpulse24-logo-ecg.png";

/**
 * The source image of every image in a rendered fragment.
 *
 * **`next/image` rewrites the `src` into its optimizer URL** —
 * `/_next/image?url=%2Fbrand%2Feventpulse24-logo-ecg.png&w=96&q=75` — so the canonical
 * path is URL-encoded inside it. Decoding it gives back the path that was asked for.
 */
function imageSrcs(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("img")).map((img) => {
    const src = img.getAttribute("src") ?? "";
    const encoded = src.match(/[?&]url=([^&]+)/)?.[1];
    return encoded ? decodeURIComponent(encoded) : src;
  });
}

describe("the brand mark", () => {
  it("is one image, and every brand surface shows that one image", () => {
    const topbar = render(<BrandTopbar />).container;
    const footer = render(<PreAuthFooter />).container;
    const sidenav = render(
      <Sidenav name="Ada Lovelace" email="ada@example.com" avatarUrl="" />,
    ).container;

    // Each of the three surfaces above carries exactly one image — the mark.
    expect(imageSrcs(topbar)).toHaveLength(1);
    expect(imageSrcs(footer)).toHaveLength(1);
    expect(imageSrcs(sidenav)).toHaveLength(1);

    // And they are the same image. This is the assertion that would have failed
    // before the unification: the topbar's PNG, the footer's dot and the rail's
    // glyph were three different marks.
    expect(imageSrcs(topbar)[0]).toContain(CANONICAL_SRC);
    expect(imageSrcs(footer)[0]).toContain(CANONICAL_SRC);
    expect(imageSrcs(sidenav)[0]).toContain(CANONICAL_SRC);
  });

  it("leaves no CSS-drawn or text-drawn brand mark behind", () => {
    const surfaces = [
      render(<BrandTopbar />).container,
      render(<PreAuthFooter />).container,
      render(<Sidenav name="Ada Lovelace" email="ada@example.com" avatarUrl="" />).container,
    ];

    for (const surface of surfaces) {
      // The `◉` glyph that stood in for the logo on the authed surfaces.
      expect(surface.textContent).not.toContain("◉");
      // The terracotta dot that stood in for it in the footer.
      expect(surface.querySelector(".rounded-full.bg-accent-terracotta")).toBeNull();
    }
  });

  it("renders the mark at the size it is asked for", () => {
    const { container } = render(<BrandMark size={28} />);

    const logo = container.querySelector("img");
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("width", "28");
    expect(logo).toHaveAttribute("height", "28");
  });

  it("gives the mark an empty alt, because the wordmark beside it carries the name", () => {
    const { container } = render(<BrandMark />);

    expect(container.querySelector("img")).toHaveAttribute("alt", "");
  });

  /**
   * The asset on disk has to be the canonical logo.
   *
   * The file in `public/brand/` is what the browser fetches, and it is a copy of
   * `docs/EventPulse24-logo.png` in the repository root — the original. **A copy is
   * only as good as the copy:** if the two drift apart, the product serves a logo
   * nobody chose, and nothing else in the codebase would notice. This compares their
   * bytes.
   */
  it("serves the canonical logo, byte for byte", async () => {
    const { readFile } = await import("node:fs/promises");
    const { join } = await import("node:path");

    const repoRoot = join(process.cwd(), "..");
    const [served, canonical] = await Promise.all([
      readFile(join(process.cwd(), "public", "brand", "eventpulse24-logo-ecg.png")),
      readFile(join(repoRoot, "docs", "EventPulse24-logo.png")),
    ]);

    expect(served.equals(canonical)).toBe(true);
  });

  /**
   * The share card has to be the size it says it is.
   *
   * **The metadata declares 1200×630, and the card must match.** The square logo is
   * 1282×1288 — pointing a share card at it means the card is cropped or letterboxed
   * by whichever platform renders it. The PNG's real dimensions are read from its
   * IHDR chunk here, so the assertion is against the file on disk rather than against
   * what the code hopes.
   */
  it("serves a share card whose real dimensions match the declared ones", async () => {
    const { readFile } = await import("node:fs/promises");
    const { join } = await import("node:path");

    const png = await readFile(join(process.cwd(), "public", "brand", "eventpulse24-og.png"));

    // IHDR is the first chunk: 8-byte signature, then length+type, then the data.
    const width = png.readUInt32BE(16);
    const height = png.readUInt32BE(20);

    expect(width).toBe(1200);
    expect(height).toBe(630);
  });
});
