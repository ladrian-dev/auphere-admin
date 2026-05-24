import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import type { TakeoverContext } from "@/lib/backend";

// The hook opens a real EventSource which jsdom doesn't expose by default.
// We mock it to a noop so render tests focus on the panel surface.
vi.mock("../use-conversation-stream", () => ({
  useConversationStream: vi.fn(),
}));

const toggleAction = vi.fn();
const sendAction = vi.fn();
vi.mock("../../actions", () => ({
  toggleConversationAgentAction: (
    ...args: Parameters<typeof toggleAction>
  ) => toggleAction(...args),
  operatorSendMessageAction: (
    ...args: Parameters<typeof sendAction>
  ) => sendAction(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { TakeoverPanel } from "../takeover-panel";

const baseProps = {
  tenantId: "tnt-1",
  conversationId: "conv-1",
  agentActiveVersion: 3,
  takeoverContext: null as TakeoverContext | null,
};

beforeEach(() => {
  toggleAction.mockReset();
  sendAction.mockReset();
});

describe("TakeoverPanel — agent active state", () => {
  it("shows the 'Tomar control' button and hides the composer", () => {
    render(<TakeoverPanel {...baseProps} agentActive={true} />);
    expect(
      screen.getByRole("button", { name: /tomar control/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/responder como operador/i),
    ).not.toBeInTheDocument();
  });

  it("does not render the takeover banner when no takeover_context", () => {
    render(<TakeoverPanel {...baseProps} agentActive={true} />);
    expect(
      screen.queryByText(/operador en control de este thread/i),
    ).not.toBeInTheDocument();
  });

  it("opens the reason dialog when 'Tomar control' is clicked", async () => {
    const user = userEvent.setup();
    render(<TakeoverPanel {...baseProps} agentActive={true} />);
    await user.click(screen.getByRole("button", { name: /tomar control/i }));
    expect(
      screen.getByRole("dialog", { name: /tomar control de la conversación/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/razón \(opcional\)/i)).toBeInTheDocument();
    expect(
      screen.getByLabelText(/notas para el agente \(opcional\)/i),
    ).toBeInTheDocument();
  });

  it("submits the dialog with reason + notes + expectedVersion", async () => {
    const user = userEvent.setup();
    toggleAction.mockResolvedValue({
      ok: true,
      data: { agent_active: false, agent_active_version: 4 },
    });
    render(<TakeoverPanel {...baseProps} agentActive={true} />);
    await user.click(screen.getByRole("button", { name: /tomar control/i }));
    await user.type(screen.getByLabelText(/razón/i), "queja");
    await user.type(screen.getByLabelText(/notas/i), "estaba enojado");
    await user.click(
      screen
        .getAllByRole("button", { name: /tomar control/i })
        .find((b) => (b as HTMLButtonElement).type === "submit")!,
    );
    expect(toggleAction).toHaveBeenCalledWith(
      "tnt-1",
      "conv-1",
      false,
      expect.objectContaining({
        reason: "queja",
        notes: "estaba enojado",
        expectedVersion: 3,
      }),
    );
  });
});

describe("TakeoverPanel — agent paused state", () => {
  it("shows the composer and 'Reactivar agente' button", () => {
    render(<TakeoverPanel {...baseProps} agentActive={false} />);
    expect(
      screen.getByRole("button", { name: /reactivar agente/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/responder como operador/i)).toBeInTheDocument();
  });

  it("renders takeover_context banner when present", () => {
    render(
      <TakeoverPanel
        {...baseProps}
        agentActive={false}
        takeoverContext={{
          reason: "queja del cliente",
          notes: "estaba enojado",
          started_at: "2026-05-25T10:00:00Z",
          operator_id: "luis1234",
        }}
      />,
    );
    expect(screen.getByText(/operador en control de este thread/i)).toBeInTheDocument();
    expect(screen.getByText(/queja del cliente/i)).toBeInTheDocument();
    expect(screen.getByText(/estaba enojado/i)).toBeInTheDocument();
  });

  it("sends operator message via action", async () => {
    const user = userEvent.setup();
    sendAction.mockResolvedValue({ ok: true, data: { message_id: "m1" } });
    render(<TakeoverPanel {...baseProps} agentActive={false} />);
    await user.type(
      screen.getByLabelText(/responder como operador/i),
      "te confirmo el envío",
    );
    await user.click(
      screen.getByRole("button", { name: /enviar como operador/i }),
    );
    expect(sendAction).toHaveBeenCalledWith(
      "tnt-1",
      "conv-1",
      "te confirmo el envío",
    );
  });

  it("disables the send button when textarea is empty", () => {
    render(<TakeoverPanel {...baseProps} agentActive={false} />);
    const send = screen.getByRole("button", { name: /enviar como operador/i });
    expect(send).toBeDisabled();
  });

  it("calls toggle with expectedVersion when resuming the agent", async () => {
    const user = userEvent.setup();
    toggleAction.mockResolvedValue({
      ok: true,
      data: { agent_active: true, agent_active_version: 4 },
    });
    render(<TakeoverPanel {...baseProps} agentActive={false} />);
    await user.click(screen.getByRole("button", { name: /reactivar agente/i }));
    expect(toggleAction).toHaveBeenCalledWith(
      "tnt-1",
      "conv-1",
      true,
      expect.objectContaining({ expectedVersion: 3 }),
    );
  });
});
