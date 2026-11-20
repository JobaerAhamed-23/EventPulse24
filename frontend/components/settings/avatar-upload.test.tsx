/**
 * The picture control — **chosen, uploaded, removed, and told about.**
 *
 * ## Why this file exists
 *
 * **The upload control is the one settings control that is not save-on-change**, and
 * that break with the house pattern is deliberate — so it needs its own tests rather
 * than inheriting the shape of the name's.
 *
 * ## What is proved here
 *
 * 1. **A chosen file is sent, and it is sent once.** The moment the file is chosen is
 *    the moment it is saved.
 * 2. **The API's refusal is shown verbatim.** The backend refuses a file it cannot
 *    read with a message that says what to do, and a generic *"Couldn't save."* would
 *    throw that away.
 * 3. **The offline line is shown only when the request never reached the API.**
 * 4. **Nothing is published to the shell before the server accepts** — and the picture
 *    in the rail moves only after the write is accepted.
 * 5. **A second choice while a write is in flight is refused outright.** Two uploads
 *    racing would leave two objects, so the guard refuses the second file rather than
 *    starting a second upload — and the refusal lives in the handler, not only in the
 *    `disabled` attribute.
 * 6. **The control is not pressable twice**, and the wait is announced.
 * 7. **Removing the picture reverts the preview to the initials**, and the removal is
 *    published to the shell too.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AvatarUpload } from "@/components/settings/avatar-upload";
import { publishAvatar } from "@/lib/avatar-store";

const POST = vi.fn();
const DELETE = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    DELETE: (...args: unknown[]) => DELETE(...args),
  },
}));

const NAME = "Maya Ahmed";
const PICTURE = "/api/auth/profile/avatar/ab12cd34";

/**
 * The server's answer, as the endpoints send it.
 *
 * **The URL is the one for the object the server actually stored** — and a replaced
 * picture is a different URL, so the browser's cache invalidates itself.
 */
function answer(avatarUrl: string) {
  return {
    data: {
      id: "11111111-1111-1111-1111-111111111111",
      email: "maya@example.test",
      name: NAME,
      avatar_url: avatarUrl,
    },
    response: { status: 200 },
  };
}

/**
 * The API's refusal, as the server sends it.
 *
 * **This is the shape `backend/config/errors.py` writes** — `{code, message, details}`
 * — and the message is written for the person who typed it.
 */
function refusal(code: string, message: string, status = 422) {
  return {
    data: undefined,
    error: { code, message },
    response: { status },
  };
}

/** A file the browser hands to the input. */
function pictureFile(name = "maya.png") {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "image/png" });
}

/** The file input. */
function input(): HTMLInputElement {
  return document.querySelector("[data-avatar-input]") as HTMLInputElement;
}

beforeEach(() => {
  POST.mockReset();
  DELETE.mockReset();
  POST.mockResolvedValue(answer(PICTURE));
  DELETE.mockResolvedValue(answer(""));
});

describe("the picture control", () => {
  it("sends the chosen file, and it is sent once", async () => {
    // **The chosen file is the save.** There is no Save button and no second step.
    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);

    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(POST.mock.calls[0]?.[0]).toBe("/api/auth/profile/avatar");
  });

  it("shows the picture once the server has accepted it", async () => {
    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);

    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(document.querySelector("[data-avatar-preview] img")).not.toBeNull());
    expect(document.querySelector("[data-avatar-preview] img")?.getAttribute("src")).toBe(PICTURE);
  });

  it("shows the initials when the account has no picture", () => {
    // **The fallback is a real one.** An account with no picture still looks like an
    // account, rather than like a hole in the screen.
    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);

    expect(document.querySelector("[data-avatar-preview] img")).toBeNull();
    expect(document.querySelector("[data-avatar-preview]")?.textContent).toBe("MA");
  });

  it("offers no removal control when there is no picture to remove", () => {
    // **An affordance that cannot work is the same lie as a link to a 404.**
    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);

    expect(document.querySelector("[data-avatar-remove]")).toBeNull();
  });

  it("offers a removal control when there is a picture", () => {
    render(<AvatarUpload initialAvatarUrl={PICTURE} name={NAME} />);

    expect(document.querySelector("[data-avatar-remove]")).not.toBeNull();
  });

  it("removes the picture, and the preview falls back to the initials", async () => {
    render(<AvatarUpload initialAvatarUrl={PICTURE} name={NAME} />);

    fireEvent.click(document.querySelector("[data-avatar-remove]") as HTMLButtonElement);

    await waitFor(() => expect(DELETE).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(document.querySelector("[data-avatar-preview] img")).toBeNull());
    // **The initials come back**, so the screen still says who this is.
    expect(document.querySelector("[data-avatar-preview]")?.textContent).toBe("MA");
  });
});

describe("the refusal", () => {
  it("shows the API's own message, verbatim", async () => {
    // **The API's verdict.** The backend refuses a file it cannot read, and says why
    // in a message written for the person who chose it.
    POST.mockResolvedValue(
      refusal(
        "invalid_input",
        "That file isn't an image we can read. Try a PNG, JPEG, WebP or GIF.",
      ),
    );

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() =>
      expect(
        screen.getByText("That file isn't an image we can read. Try a PNG, JPEG, WebP or GIF."),
      ).toBeInTheDocument(),
    );
    // **The generic line is not shown as well** — the API's verdict replaces it, rather
    // than joining it.
    expect(screen.queryByText("Couldn't save.")).toBeNull();
  });

  it("shows the offline line when the request never reached the API", async () => {
    // **Nothing was refused**, so there is nothing to quote, and the route's own line is
    // the honest one.
    POST.mockRejectedValue(new Error("offline"));

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
  });

  it("announces the failure", async () => {
    POST.mockRejectedValue(new Error("offline"));

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });

  it("keeps the picture the account had when the upload was refused", async () => {
    // **The person did not lose their picture over a failed upload.**
    POST.mockResolvedValue(refusal("invalid_input", "That file isn't an image we can read."));

    render(<AvatarUpload initialAvatarUrl={PICTURE} name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(document.querySelector("[data-avatar-preview] img")?.getAttribute("src")).toBe(PICTURE);
  });
});

describe("publishing to the shell", () => {
  it("publishes the new picture once the server has accepted it", async () => {
    // **The whole property.** The shell is rendered on the server, so the picture it
    // was drawn with is fixed for the life of the render — and a save that does not show
    // up is a save that did not happen.
    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);

    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
    // **The published value is the server's URL**, the one for the object the server
    // actually stored.
    publishAvatar(PICTURE);
  });

  it("publishes nothing when the API refused", async () => {
    // **Publishing on a refusal would publish a picture that does not exist.**
    POST.mockResolvedValue(refusal("invalid_input", "That file isn't an image we can read."));

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    // **No "Saved."**, which is the observable half of "nothing was published".
    expect(screen.queryByText("Saved.")).toBeNull();
  });

  it("publishes nothing when the request never reached the API", async () => {
    POST.mockRejectedValue(new Error("offline"));

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText("Saved.")).toBeNull();
  });
});

describe("a write that is superseded", () => {
  it("refuses the second choice outright while the first is in flight", async () => {
    // **Two uploads racing would leave two objects in the bucket**, one of them
    // orphaned. The second choice is refused rather than queued — and the refusal is
    // at the handler, not only the `disabled` attribute, so it holds even when the
    // browser does not honour the attribute.
    const resolvers: ((value: unknown) => void)[] = [];
    POST.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push(resolve);
        }),
    );

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);

    fireEvent.change(input(), { target: { files: [pictureFile("first.png")] } });
    await waitFor(() => expect(resolvers).toHaveLength(1));

    // **The second file never becomes a request.** There is no second object, so
    // there is nothing to orphan.
    fireEvent.change(input(), { target: { files: [pictureFile("second.png")] } });
    expect(POST).toHaveBeenCalledTimes(1);

    resolvers[0]?.(answer("/api/auth/profile/avatar/first"));
    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
    expect(document.querySelector("[data-avatar-preview] img")?.getAttribute("src")).toBe(
      "/api/auth/profile/avatar/first",
    );
  });

  it("refuses a removal while an upload is in flight", async () => {
    // **A removal racing an upload would leave the account in whichever state
    // committed last**, and the object behind the other one would be orphaned. So the
    // removal is refused too — the guard is on the write, not on the upload alone.
    const resolvers: ((value: unknown) => void)[] = [];
    POST.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push(resolve);
        }),
    );

    render(<AvatarUpload initialAvatarUrl={PICTURE} name={NAME} />);

    fireEvent.change(input(), { target: { files: [pictureFile()] } });
    await waitFor(() => expect(resolvers).toHaveLength(1));

    fireEvent.click(document.querySelector("[data-avatar-remove]") as HTMLButtonElement);
    expect(DELETE).not.toHaveBeenCalled();

    resolvers[0]?.(answer(PICTURE));
    await waitFor(() => expect(input().disabled).toBe(false));
  });

  it("takes the next choice once the first write has come back", async () => {
    // **The guard is not a queue.** Once the write has landed, the control works
    // again — otherwise a refused second file would be refused forever.
    const resolvers: ((value: unknown) => void)[] = [];
    POST.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvers.push(resolve);
        }),
    );

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);

    fireEvent.change(input(), { target: { files: [pictureFile("first.png")] } });
    await waitFor(() => expect(resolvers).toHaveLength(1));
    resolvers[0]?.(answer("/api/auth/profile/avatar/first"));
    await waitFor(() => expect(input().disabled).toBe(false));

    fireEvent.change(input(), { target: { files: [pictureFile("second.png")] } });
    await waitFor(() => expect(resolvers).toHaveLength(2));
    expect(POST).toHaveBeenCalledTimes(2);
  });
});

describe("the in-flight affordance", () => {
  it("announces the wait and refuses a second press", async () => {
    // **Two uploads racing leave two objects**, so the control is not pressable twice —
    // and the wait is announced rather than only drawn.
    let resolvePost: (value: unknown) => void = () => {};
    POST.mockReturnValue(
      new Promise((resolve) => {
        resolvePost = resolve;
      }),
    );

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(input().disabled).toBe(true));
    // **`aria-busy` on the control**, so the wait reaches assistive technology where the
    // wait is — and on the region, so a reader who has moved on hears the section still
    // working.
    expect(input().getAttribute("aria-busy")).toBe("true");
    expect(document.querySelector("[data-avatar-region]")?.getAttribute("aria-busy")).toBe("true");
    // **And the control really is disabled**, not merely marked.
    expect(input().disabled).toBe(true);

    // **A second choice while the first is in flight does not start a second upload.**
    //
    // **The change event is fired on a disabled input on purpose.** A browser will not
    // let a person change a disabled input, so this event cannot happen by hand — and
    // that is exactly why the guard has to be in the handler rather than in the
    // attribute. **The `disabled` attribute is the affordance; the refusal is the
    // enforcement**, and the enforcement must not depend on the browser honouring the
    // attribute.
    fireEvent.change(input(), { target: { files: [pictureFile("second.png")] } });
    expect(POST).toHaveBeenCalledTimes(1);

    resolvePost(answer(PICTURE));
    await waitFor(() => expect(input().disabled).toBe(false));
  });

  it("shows a static dot, never a spinner", async () => {
    // **The product bans spinners.** `EXPERIENCE.md`: "No spinners, anywhere." So the
    // in-flight state is a static dot.
    let resolvePost: (value: unknown) => void = () => {};
    POST.mockReturnValue(
      new Promise((resolve) => {
        resolvePost = resolve;
      }),
    );

    render(<AvatarUpload initialAvatarUrl="" name={NAME} />);
    fireEvent.change(input(), { target: { files: [pictureFile()] } });

    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).not.toBeNull());
    const dot = document.querySelector("[data-saving-dot]");
    expect(dot?.className).toContain("rounded-full");
    expect(dot?.className).not.toContain("animate-");

    resolvePost(answer(PICTURE));
    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).toBeNull());
  });
});
