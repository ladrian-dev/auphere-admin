import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type {
  AuphereOwnerChannelOut,
  OwnerPhoneIndexOut,
} from "@/lib/backend";

import { OwnersTable } from "../owners-table";

function makeOwner(o: Partial<OwnerPhoneIndexOut> = {}): OwnerPhoneIndexOut {
  return {
    phone_e164: "+56911111111",
    tenant_id: "tnt_1",
    user_label: "Luis",
    active: true,
    added_at: "2026-05-24T12:00:00Z",
    auphere_channel_id: null,
    confirmed_at: "2026-05-24T12:00:00Z",
    ...o,
  };
}

function makeChannel(
  o: Partial<AuphereOwnerChannelOut> = {},
): AuphereOwnerChannelOut {
  return {
    id: "ch_1",
    phone_e164: "+56999000001",
    display_name: "Auphere CL",
    country_code: "CL",
    provider: "ycloud",
    provider_phone_id: null,
    active: true,
    is_default: false,
    has_webhook_secret: false,
    created_at: "2026-05-24T10:00:00Z",
    updated_at: "2026-05-24T10:00:00Z",
    ...o,
  };
}

describe("OwnersTable — empty state", () => {
  it("renders the empty placeholder when there are no owners", () => {
    const update = vi.fn();
    const deregister = vi.fn();
    render(
      <OwnersTable
        tenantId="tnt_1"
        owners={[]}
        channels={[]}
        updateAction={update as never}
        deregisterAction={deregister as never}
      />,
    );
    expect(screen.getByText(/Sin dueños registrados/i)).toBeInTheDocument();
  });
});

describe("OwnersTable — render", () => {
  it("renders one row per owner with phone, label, status", () => {
    render(
      <OwnersTable
        tenantId="tnt_1"
        owners={[
          makeOwner({ phone_e164: "+56911111111", user_label: "Luis" }),
          makeOwner({
            phone_e164: "+56922222222",
            user_label: "Carla",
            active: false,
          }),
        ]}
        channels={[]}
        updateAction={vi.fn() as never}
        deregisterAction={vi.fn() as never}
      />,
    );
    expect(screen.getByText("+56911111111")).toBeInTheDocument();
    expect(screen.getByText("+56922222222")).toBeInTheDocument();
    expect(screen.getByText("Luis")).toBeInTheDocument();
    expect(screen.getByText("Carla")).toBeInTheDocument();
    const inactiveRow = screen.getByTestId("owner-row-+56922222222");
    expect(within(inactiveRow).getByText("Inactivo")).toBeInTheDocument();
  });

  it("renders the row when owner has no channel pin", () => {
    // The Select content lives in a portal that doesn't render unless
    // opened — we just verify the row + its select trigger are
    // present. The "Default del provider" item is covered by the
    // channels listing tests in app/(dashboard)/auphere/channels.
    render(
      <OwnersTable
        tenantId="tnt_1"
        owners={[makeOwner({ auphere_channel_id: null })]}
        channels={[makeChannel({ is_default: true })]}
        updateAction={vi.fn() as never}
        deregisterAction={vi.fn() as never}
      />,
    );
    const row = screen.getByTestId("owner-row-+56911111111");
    expect(within(row).getByRole("combobox")).toBeInTheDocument();
  });
});

describe("OwnersTable — actions", () => {
  it("calls deregisterAction with confirm prompt", async () => {
    const deregister = vi.fn(async () => ({ ok: true as const, data: null }));
    const update = vi.fn();
    vi.stubGlobal("confirm", () => true);
    render(
      <OwnersTable
        tenantId="tnt_1"
        owners={[makeOwner()]}
        channels={[]}
        updateAction={update as never}
        deregisterAction={deregister as never}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Desregistrar/i }),
    );
    expect(deregister).toHaveBeenCalledWith("tnt_1", "+56911111111");
    vi.unstubAllGlobals();
  });

  it("calls updateAction({active:false}) on Desactivar", async () => {
    const update = vi.fn(async () => ({
      ok: true as const,
      data: makeOwner({ active: false }),
    }));
    render(
      <OwnersTable
        tenantId="tnt_1"
        owners={[makeOwner({ active: true })]}
        channels={[]}
        updateAction={update as never}
        deregisterAction={vi.fn() as never}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Desactivar/i }));
    expect(update).toHaveBeenCalledWith("tnt_1", "+56911111111", {
      active: false,
    });
  });
});
