import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ChannelOut } from "@/lib/backend";

import { WhatsAppNumbers } from "../whatsapp-numbers";

const updateChannelRoleAction = vi.fn();

vi.mock("../actions", () => ({
  updateChannelRoleAction: (...args: unknown[]) =>
    updateChannelRoleAction(...args),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function makeChannel(o: Partial<ChannelOut> = {}): ChannelOut {
  return {
    id: "ch_1",
    type: "whatsapp",
    provider: "meta",
    provider_identifier: "+584249018017",
    config: { phone_number_id: "PNID-1", verified_name: "Muna Restaurante" },
    status: "active",
    created_at: "2026-07-31T16:44:32Z",
    updated_at: "2026-07-31T16:44:32Z",
    ...o,
  };
}

beforeEach(() => {
  updateChannelRoleAction.mockReset();
  updateChannelRoleAction.mockResolvedValue({ ok: true, data: makeChannel() });
});

// The Select and Dialog render into portals that survive a bare re-render, so
// a test that opened a listbox would otherwise leave its options in the
// document and the next `getByRole("option", …)` would query the stale tree.
afterEach(cleanup);

describe("WhatsAppNumbers — what is shown", () => {
  it("renders nothing when the tenant has no WhatsApp channel", () => {
    const { container } = render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[
          makeChannel({
            id: "ch_web",
            type: "web",
            provider: "web_widget",
            provider_identifier: "web_widget:tnt_1",
          }),
        ]}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("lists only WhatsApp numbers, never the web channels", () => {
    render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[
          makeChannel(),
          makeChannel({
            id: "ch_web",
            type: "web",
            provider: "qa_playground",
            provider_identifier: "qa_playground:tnt_1",
          }),
        ]}
      />,
    );
    expect(screen.getByText("+584249018017")).toBeInTheDocument();
    expect(screen.queryByText(/qa_playground/)).not.toBeInTheDocument();
  });

  it("shows a retired number without controls", () => {
    render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[
          makeChannel({
            status: "disconnected",
            provider_identifier: "disconnected:45166e02:+34672138367",
          }),
        ]}
      />,
    );
    // The bookkeeping prefix is stripped — the operator sees the number.
    expect(screen.getByText("+34672138367")).toBeInTheDocument();
    expect(screen.getByText("Desconectado")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});

describe("WhatsAppNumbers — the unassigned-role warning", () => {
  const two = [
    makeChannel({ id: "ch_a", provider_identifier: "+584249018017" }),
    makeChannel({ id: "ch_b", provider_identifier: "+584240000001" }),
  ];

  it("warns when two numbers are live and none is the notifications line", () => {
    render(<WhatsAppNumbers tenantId="tnt_1" channels={two} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      /rechazar en vez de salir por el número equivocado/,
    );
  });

  it("drops the warning once one of them claims the role", () => {
    render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[
          makeChannel({
            id: "ch_a",
            config: { role: "notifications" },
          }),
          makeChannel({ id: "ch_b", provider_identifier: "+584240000001" }),
        ]}
      />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not warn on a single number — that setup needs no assignment", () => {
    render(<WhatsAppNumbers tenantId="tnt_1" channels={[makeChannel()]} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ignores a disconnected sibling when deciding whether to warn", () => {
    render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[
          makeChannel({ id: "ch_a" }),
          makeChannel({
            id: "ch_dead",
            status: "disconnected",
            provider_identifier: "disconnected:x:+56900000000",
          }),
        ]}
      />,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("WhatsAppNumbers — assigning a role", () => {
  it("sends the chosen role for that channel", async () => {
    const user = userEvent.setup();
    render(<WhatsAppNumbers tenantId="tnt_1" channels={[makeChannel()]} />);

    await user.click(screen.getByRole("combobox", { name: /\+584249018017/ }));
    await user.click(
      await screen.findByRole("option", { name: "Línea de notificaciones" }),
    );

    expect(updateChannelRoleAction).toHaveBeenCalledWith("tnt_1", "ch_1", {
      role: "notifications",
    });
  });

  it("clears the role with an explicit null, not by omission", async () => {
    const user = userEvent.setup();
    render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[makeChannel({ config: { role: "agent" } })]}
      />,
    );

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "Sin asignar" }));

    expect(updateChannelRoleAction).toHaveBeenCalledWith("tnt_1", "ch_1", {
      role: null,
    });
  });
});

describe("WhatsAppNumbers — silencing the agent", () => {
  it("asks for confirmation before muting a line", async () => {
    const user = userEvent.setup();
    render(<WhatsAppNumbers tenantId="tnt_1" channels={[makeChannel()]} />);

    await user.click(screen.getByRole("button", { name: "Silenciar agente" }));
    // Nothing sent yet — muting stops replies to real people.
    expect(updateChannelRoleAction).not.toHaveBeenCalled();

    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText(/los mensajes que lleguen se guardan/i),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Silenciar" }));

    expect(updateChannelRoleAction).toHaveBeenCalledWith("tnt_1", "ch_1", {
      agent_enabled: false,
    });
  });

  it("cancelling leaves the line untouched", async () => {
    const user = userEvent.setup();
    render(<WhatsAppNumbers tenantId="tnt_1" channels={[makeChannel()]} />);

    await user.click(screen.getByRole("button", { name: "Silenciar agente" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Cancelar",
      }),
    );
    expect(updateChannelRoleAction).not.toHaveBeenCalled();
  });

  it("re-enables without a confirmation — turning the agent back on is safe", async () => {
    const user = userEvent.setup();
    render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[makeChannel({ config: { agent_enabled: false } })]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Activar agente" }));

    expect(updateChannelRoleAction).toHaveBeenCalledWith("tnt_1", "ch_1", {
      agent_enabled: true,
    });
  });

  it("treats an absent flag as enabled — every channel in prod predates it", () => {
    render(
      <WhatsAppNumbers
        tenantId="tnt_1"
        channels={[makeChannel({ config: {} })]}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Silenciar agente" }),
    ).toBeInTheDocument();
  });
});
