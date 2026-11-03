import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ChannelWizard } from "../channel-picker";

describe("ChannelWizard: conectar otro", () => {
  it("WhatsApp pide otro número; Instagram y Messenger, otra cuenta", () => {
    render(
      <LocaleProvider locale="es">
        <ChannelWizard
          step={0}
          connected={{ whatsapp: 1, instagram: 1, messenger: 1 }}
          available={["instagram", "messenger"]}
          onConnect={vi.fn()}
        />
      </LocaleProvider>,
    );
    const card = (name: RegExp) => within(screen.getByRole("button", { name }));
    expect(card(/WhatsApp/).getByText("Conectar otro número")).toBeVisible();
    expect(card(/Instagram/).getByText("Conectar otra cuenta")).toBeVisible();
    expect(card(/Messenger/).getByText("Conectar otra cuenta")).toBeVisible();
  });
});
