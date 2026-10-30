import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ContactAvatar } from "../contact-avatar";

/**
 * Owner, 2026-10-30: the inbox shows the person's photo (Instagram /
 * Messenger). It comes from our BFF route, never a storage link; without one,
 * or if it fails to load, the initials.
 */
describe("ContactAvatar", () => {
  const ID = "11111111-1111-4111-8111-111111111111";

  it("shows the picture from the BFF route when there is one", () => {
    const { container } = render(<ContactAvatar conversationId={ID} hasAvatar initials="AN" className="size-10" />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe(`/api/lite/inbox/avatar/${ID}`);
    expect(img?.getAttribute("alt")).toBe("");
  });

  it("falls back to the initials without a picture or when it fails", () => {
    const none = render(<ContactAvatar conversationId={ID} initials="AN" className="size-10" />);
    expect(none.container.querySelector("img")).toBeNull();
    expect(none.container.textContent).toBe("AN");
    none.unmount();

    const broken = render(<ContactAvatar conversationId={ID} hasAvatar initials="AN" className="size-10" />);
    fireEvent.error(broken.container.querySelector("img")!);
    expect(broken.container.querySelector("img")).toBeNull();
    expect(broken.container.textContent).toBe("AN");
  });
});
