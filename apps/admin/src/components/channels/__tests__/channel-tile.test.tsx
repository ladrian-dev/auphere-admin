import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChannelTile } from "../channel-tile";
import { AVAILABILITY_LABEL, canStart } from "../labels";

describe("channel catalog (spec 035, R1)", () => {
  it("only available and beta channels can start", () => {
    expect(canStart("available")).toBe(true);
    expect(canStart("beta")).toBe(true);
    expect(canStart("pending")).toBe(false);
    expect(canStart("coming_soon")).toBe(false);
    expect(AVAILABILITY_LABEL.coming_soon).toBe("Próximamente");
  });

  it("a startable tile is a link to step 2", () => {
    render(
      <ChannelTile
        entry={{ key: "whatsapp", name: "WhatsApp", description: "d", availability: "available", note: null }}
        href="/tenants/t1/channels/new/whatsapp"
      />,
    );
    expect(screen.getByRole("link", { name: /WhatsApp/ })).toHaveAttribute("href", "/tenants/t1/channels/new/whatsapp");
  });

  it("a coming-soon tile says so and leads nowhere", () => {
    render(
      <ChannelTile
        entry={{ key: "threads", name: "Threads", description: "d", availability: "coming_soon", note: null }}
        href="/tenants/t1/channels/new/threads"
      />,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Próximamente")).toBeInTheDocument();
  });
});
