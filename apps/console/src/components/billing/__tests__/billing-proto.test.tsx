import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/app/(console)/billing/actions", () => ({
  deleteCardAction: vi.fn(),
  setChargingAction: vi.fn(),
  startCardAction: vi.fn(),
  setBillingEmailAction: vi.fn(),
  buyCreditAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";
import { t } from "@/i18n/messages";
import type { BillingCardView } from "@/lib/backend";

import { BillingEmailForm } from "../billing-email-form";
import { CardCharges, CardSection } from "../card-section";
import { receiptStatus } from "../receipt-status";

/**
 * Spec 047 — Facturación como el prototipo «Consola de partners v2»: todo en
 * tarjetas, la tarjeta de pago con «Cambiar» y «Quitar», los modos de cobro en
 * opciones con su descripción, los cobros en su propia tarjeta y los estados
 * de los recibos traducidos. Ningún texto lleva «US$» escrito a mano.
 */
const view = (over: Partial<BillingCardView> = {}): BillingCardView => ({
  card: { brand: "visa", last4: "4242", exp_month: 8, exp_year: 2028 },
  mode: "auto_recharge",
  recharge_threshold_cents: 1000,
  recharge_amount_cents: 2000,
  credit_limit_cents: 0,
  owed_cents: 0,
  paused_reason: null,
  failed_attempts: 0,
  charges: [],
  ...over,
});
const wrap = (ui: React.ReactNode) => render(<LocaleProvider locale="es">{ui}</LocaleProvider>);

describe("Facturación · como el prototipo", () => {
  it("«Tarjeta y cobro automático» es una tarjeta con la tarjeta guardada y los modos en opciones", async () => {
    const { container } = wrap(<CardSection view={view()} canManage justSaved={false} />);
    const card = screen.getByRole("region", { name: "Tarjeta y cobro automático" });
    expect(card).toHaveAttribute("data-slot", "billing-card");
    expect(within(card).getByText("VISA terminada en 4242")).toBeInTheDocument();
    expect(within(card).getByText("Caduca 08/2028")).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Cambiar" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Quitar" })).toBeInTheDocument();
    const modes = within(card).getByRole("radiogroup", { name: "Cómo se cobra" });
    expect(within(modes).getByRole("radio", { name: /Manual.*Compro saldo cuando lo necesito/ })).not.toBeChecked();
    expect(within(modes).getByRole("radio", { name: /Recarga automática/ })).toBeChecked();
    // Sin línea de crédito, el pospago se ve y no se elige.
    expect(within(modes).getByRole("radio", { name: /Pospago/ })).toBeDisabled();
    expect(within(card).getByLabelText("Cuando el saldo baje de")).toHaveValue(10);
    expect(within(card).getByLabelText("Recargar")).toHaveValue(20);
    expect(card.textContent?.replace(/ /g, " ")).toContain("La recarga mínima es de 5,00 US$.");
    expect(card.textContent).not.toContain("(US$)");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin tarjeta: lo dice, ofrece añadirla y el cobro automático no se elige", async () => {
    const user = userEvent.setup();
    wrap(<CardSection view={view({ card: null, mode: "manual" })} canManage justSaved={false} />);
    expect(screen.getByText("No hay ninguna tarjeta guardada.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Añadir tarjeta" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Recarga automática/ })).toBeDisabled();
    expect(screen.getByText("Añade una tarjeta para elegir un cobro automático.")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Manual/ }));
    expect(screen.getByRole("radio", { name: /Manual/ })).toBeChecked();
  });

  it("los cobros a la tarjeta van en su tarjeta, con el estado en palabras", () => {
    wrap(
      <CardCharges
        view={view({
          charges: [
            { id: "c1", kind: "auto_recharge", amount_cents: 2000, period: null, status: "paid", failure_code: null, has_invoice: true, created_at: "2026-10-20T10:00:00Z", settled_at: null },
            { id: "c2", kind: "postpaid", amount_cents: 1500, period: "2026-09", status: "action_required", failure_code: null, action_url: "https://stripe.example/x", created_at: "2026-10-01T10:00:00Z", settled_at: null },
          ],
        })}
        canManage
      />,
    );
    const card = screen.getByRole("region", { name: "Cobros a la tarjeta" });
    expect(within(card).getByText("Pagado")).toBeInTheDocument();
    expect(within(card).getByText("Falta confirmar")).toBeInTheDocument();
    expect(within(card).getByText("Confirmar el pago").closest("a")).toHaveAttribute("href", "https://stripe.example/x");
    expect(within(card).getByText("Ver factura").closest("a")).toHaveAttribute("href", "/api/billing/charges/c1/invoice");
  });

  it("el estado de un recibo se lee en español, no «paid» ni «issued»", () => {
    const tr = (k: Parameters<typeof t>[1]) => t("es", k);
    expect(receiptStatus("paid", tr)).toEqual({ label: "Pagado", tone: "positive" });
    expect(receiptStatus("issued", tr)).toEqual({ label: "Emitido", tone: "info" });
    expect(receiptStatus("draft", tr).label).toBe("Borrador");
    expect(receiptStatus("void", tr).label).toBe("Anulado");
  });

  it("el correo de facturación es una tarjeta con «Añadir» en su cabecera", () => {
    wrap(<BillingEmailForm email={null} contactEmail="luis@ladrian.studio" canManage />);
    const card = screen.getByRole("heading", { name: "Correo de facturación" }).closest("[data-slot=billing-email]") as HTMLElement;
    expect(within(card).getByRole("button", { name: "Añadir" })).toBeInTheDocument();
    expect(within(card).getByText("No configurado. Los avisos van a luis@ladrian.studio.")).toBeInTheDocument();
    expect(within(card).getByText(/Aquí llegan los recibos/)).toBeInTheDocument();
  });
});
