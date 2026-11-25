import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { toast } from "sonner";

import { NewTenantWizard } from "../wizard-form";

const createTenant = vi.fn();
const finish = vi.fn();
const replace = vi.fn();
const refresh = vi.fn();
vi.mock("../actions", () => ({
  createTenantAction: (...a: unknown[]) => createTenant(...a),
  checkSlugAction: () => Promise.resolve({ available: true }),
  finishSendOnlySetupAction: (...a: unknown[]) => finish(...a),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, back: vi.fn(), refresh }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const partners = [{ id: "p1", name: "Agencia Sur" }];

async function fillIdentity(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Slug"), "tecfin");
  await user.type(screen.getByLabelText("Nombre comercial"), "Tecfin");
}

describe("new client wizard (spec 077, T024)", () => {
  beforeEach(() => {
    createTenant.mockReset();
    finish.mockReset();
    replace.mockReset();
    refresh.mockReset();
    vi.mocked(toast.warning).mockReset();
    createTenant.mockResolvedValue({ kind: "ok", tenantId: "t9" });
    finish.mockResolvedValue({ notSaved: [] });
  });

  it("«Con agente» is today's path: no send-only flag, on to connect a channel", async () => {
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    expect(screen.getByRole("radio", { name: /Con agente/ })).toBeChecked();
    expect(screen.getByLabelText("Plan")).toBeInTheDocument();
    await fillIdentity(user);
    await user.click(screen.getByRole("button", { name: "Crear tenant" }));
    await waitFor(() => expect(createTenant).toHaveBeenCalled());
    expect(createTenant.mock.calls[0]![0]).not.toHaveProperty("send_only");
    expect(finish).not.toHaveBeenCalled();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/tenants/t9/channels/new"));
  });

  it("«Solo envío por API» hides the agent's sections and offers the balance only with a partner", async () => {
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    expect(screen.queryByLabelText("Plan")).toBeNull();
    expect(screen.getByLabelText("Partner")).toHaveDisplayValue("Auphere (directo)");
    await user.click(screen.getByRole("checkbox", { name: /Exigir una membresía mensual/ }));
    expect(screen.getByRole("radio", { name: /El cliente, con tarjeta/ })).toBeChecked();
    expect(screen.queryByRole("radio", { name: /Del saldo del partner/ })).toBeNull();
    await user.selectOptions(screen.getByLabelText("Partner"), "p1");
    expect(screen.getByLabelText("Partner")).toHaveDisplayValue("Agencia Sur");
    expect(screen.getByRole("radio", { name: /Del saldo del partner/ })).toBeInTheDocument();
  });

  it("creates the send-only client, then its partner and membership, and opens its Resumen", async () => {
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    await fillIdentity(user);
    await user.selectOptions(screen.getByLabelText("Partner"), "p1");
    await user.click(screen.getByRole("checkbox", { name: /Exigir una membresía mensual/ }));
    await user.click(screen.getByRole("radio", { name: /Del saldo del partner/ }));
    await user.click(screen.getByRole("button", { name: "Crear cliente" }));
    await waitFor(() => expect(createTenant).toHaveBeenCalled());
    expect(createTenant.mock.calls[0]![0]).toMatchObject({ slug: "tecfin", name: "Tecfin", send_only: true });
    await waitFor(() =>
      expect(finish).toHaveBeenCalledWith("t9", {
        partnerId: "p1",
        membership: { payer: "partner_wallet", amount_cents: 4000, billing_email: null },
      }),
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/tenants/t9"));
  });

  it("asks for the billing e-mail before creating anything, when the client pays by card", async () => {
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    await fillIdentity(user);
    await user.click(screen.getByRole("checkbox", { name: /Exigir una membresía mensual/ }));
    await user.click(screen.getByRole("button", { name: "Crear cliente" }));
    const error = await screen.findByText(/correo al que Stripe manda/);
    expect(error).toHaveAttribute("role", "alert");
    // Focus goes to the field, which reads its error with it.
    const email = screen.getByLabelText("Correo de facturación");
    await waitFor(() => expect(email).toHaveFocus());
    expect(email).toHaveAccessibleDescription(/correo al que Stripe manda/);
    expect(createTenant).not.toHaveBeenCalled();
  });

  it("an edited field drops its error, and a missing name and e-mail show in the same round", async () => {
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    await user.click(screen.getByRole("checkbox", { name: /Exigir una membresía mensual/ }));
    await user.click(screen.getByRole("button", { name: "Crear cliente" }));
    // Identity failed too: both errors are on screen after one click.
    expect(await screen.findByText(/correo al que Stripe manda/)).toBeInTheDocument();
    expect(screen.getByLabelText("Slug")).toHaveAttribute("aria-invalid", "true");
    await user.type(screen.getByLabelText("Correo de facturación"), "f@tecfin.test");
    expect(screen.queryByText(/correo al que Stripe manda/)).toBeNull();
    expect(createTenant).not.toHaveBeenCalled();
  });

  it("switching to «Solo envío» and back keeps what was typed for the agent", async () => {
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.type(screen.getByLabelText("Email del owner"), "dueno@tecfin.test");
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    expect(screen.queryByLabelText("Email del owner")).toBeNull();
    await user.click(screen.getByRole("radio", { name: /Con agente/ }));
    expect(screen.getByLabelText("Email del owner")).toHaveValue("dueno@tecfin.test");
  });

  it("a send-only client is created with the defaults, not with what was typed for the agent", async () => {
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.type(screen.getByLabelText("Email del owner"), "no-es-un-correo");
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    await fillIdentity(user);
    await user.click(screen.getByRole("button", { name: "Crear cliente" }));
    await waitFor(() => expect(createTenant).toHaveBeenCalled());
    expect(createTenant.mock.calls[0]![0]).toMatchObject({ owner_email: null, send_only: true });
  });

  it("once the client exists, a failing follow-up opens its Facturación, where it is finished, and says what is missing", async () => {
    finish.mockRejectedValue(new Error("network"));
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    await fillIdentity(user);
    await user.click(screen.getByRole("button", { name: "Crear cliente" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/tenants/t9/billing"));
    expect(createTenant).toHaveBeenCalledTimes(1);
    expect(toast.warning).toHaveBeenCalledWith(
      expect.stringContaining("sin guardar el partner ni la membresía"),
      expect.objectContaining({ duration: Infinity }),
    );
  });

  it("a partner that could not be saved also opens Facturación", async () => {
    finish.mockResolvedValue({ notSaved: ["el partner (Este cliente ya no existe.)"] });
    const user = userEvent.setup();
    render(<NewTenantWizard partners={partners} />);
    await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
    await fillIdentity(user);
    await user.selectOptions(screen.getByLabelText("Partner"), "p1");
    await user.click(screen.getByRole("button", { name: "Crear cliente" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/tenants/t9/billing"));
  });

  describe("when the partner list could not be read", () => {
    it("says so next to the select and does not create a send-only client blind", async () => {
      const user = userEvent.setup();
      render(<NewTenantWizard partners={[]} partnersError />);
      await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
      expect(screen.getByText("No se pudieron leer los partners; recarga antes de elegir.")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Recargar" }));
      expect(refresh).toHaveBeenCalled();

      await fillIdentity(user);
      await user.click(screen.getByRole("button", { name: "Crear cliente" }));
      const select = screen.getByLabelText("Partner");
      await waitFor(() => expect(select).toHaveFocus());
      expect(select).toHaveAttribute("aria-invalid", "true");
      expect(select).toHaveAccessibleDescription(/recarga la página antes de crear el cliente/);
      expect(createTenant).not.toHaveBeenCalled();
    });

    it("once the reload brings the list, the error about it goes", async () => {
      const user = userEvent.setup();
      const view = render(<NewTenantWizard partners={[]} partnersError />);
      await user.click(screen.getByRole("radio", { name: /Solo envío por API/ }));
      await fillIdentity(user);
      await user.click(screen.getByRole("button", { name: "Crear cliente" }));
      expect(await screen.findByText(/recarga la página antes de crear el cliente/)).toBeInTheDocument();
      view.rerender(<NewTenantWizard partners={partners} />);
      expect(screen.queryByText(/recarga la página antes de crear el cliente/)).toBeNull();
      expect(screen.getByLabelText("Partner")).not.toHaveAttribute("aria-invalid");
    });

    it("«Con agente» does not need it and is created as always", async () => {
      const user = userEvent.setup();
      render(<NewTenantWizard partners={[]} partnersError />);
      await fillIdentity(user);
      await user.click(screen.getByRole("button", { name: "Crear tenant" }));
      await waitFor(() => expect(replace).toHaveBeenCalledWith("/tenants/t9/channels/new"));
    });
  });
});
