import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChannelKindSelector } from "../channel-selector";

describe("ChannelKindSelector", () => {
  it("renders the current value", () => {
    render(<ChannelKindSelector value="web" onChange={() => {}} />);
    const select = screen.getByRole("combobox");
    expect((select as HTMLSelectElement).value).toBe("web");
  });

  it("offers web and whatsapp options at minimum", () => {
    render(<ChannelKindSelector value="web" onChange={() => {}} />);
    expect(screen.getByRole("option", { name: /Web/ })).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /WhatsApp/ }),
    ).toBeInTheDocument();
  });

  it("fires onChange when the operator picks a different channel", async () => {
    const onChange = vi.fn();
    render(<ChannelKindSelector value="web" onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "whatsapp");
    expect(onChange).toHaveBeenCalledWith("whatsapp");
  });
});
