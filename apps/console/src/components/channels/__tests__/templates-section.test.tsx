import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { TemplateRow } from "@/lib/backend/channels";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({ deleteTemplateAction: vi.fn(), createTemplateAction: vi.fn() }));

const { TemplatesSection } = await import("../templates-section");

const row = (over: Partial<TemplateRow>): TemplateRow => ({
  id: "1",
  name: "recordatorio_cita",
  language: "es",
  category: "UTILITY",
  status: "APPROVED",
  quality_score: null,
  pending_category: null,
  components: [],
  rejection_reason: null,
  suggested_action: "none",
  last_event_at: null,
  ...over,
});

describe("las plantillas dicen su calidad y su cambio de categoría (spec 050, 4.1)", () => {
  it("la calidad en palabras y la categoría que Meta va a aplicar", () => {
    render(
      <LocaleProvider locale="es">
        <TemplatesSection
          refId="demo"
          manage={false}
          error={null}
          list={{
            items: [row({ quality_score: "YELLOW", pending_category: "MARKETING" }), row({ name: "bienvenida", quality_score: "UNKNOWN" })],
            approved: 2,
            rejected: 0,
            pending: 0,
          }}
        />
      </LocaleProvider>,
    );
    expect(screen.getByText("Media")).toBeVisible();
    expect(screen.getByText("Meta la pasa a Marketing en un día")).toBeVisible();
    // Sin puntuación de Meta, una raya y no un código.
    expect(screen.queryByText("UNKNOWN")).toBeNull();
  });
});

describe("una plantilla rechazada se lee entera y se corrige (QA 2026-10-30)", () => {
  const rejected = row({
    name: "aviso_pago",
    language: "es_CL",
    status: "REJECTED",
    rejection_reason: "INVALID_FORMAT: The parameter format is not supported because it has a variable at the end of the message.",
    suggested_action: "fix_format",
    components: [
      { type: "BODY", text: "Hola {{nombre}}, tu pago vence hoy {{fecha}}", example: { body_text_named_params: [{ param_name: "nombre", example: "Ana" }] } },
      { type: "BUTTONS", buttons: [{ type: "QUICK_REPLY", text: "Pagar" }] },
    ],
  });

  it("el idioma en palabras, el motivo completo en el detalle y «Duplicar y corregir» abre el compositor con lo enviado", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(
      <LocaleProvider locale="es">
        <TemplatesSection refId="demo" manage error={null} list={{ items: [rejected], approved: 0, rejected: 1, pending: 0 }} />
      </LocaleProvider>,
    );
    expect(screen.getByText("Español de Chile")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "aviso_pago" }));
    const dialog = await screen.findByRole("dialog", { name: "aviso_pago" });
    expect(dialog).toHaveTextContent("it has a variable at the end of the message.");
    expect(dialog).toHaveTextContent("Hola Ana");
    await user.click(screen.getByRole("button", { name: "Duplicar y corregir" }));
    expect(await screen.findByLabelText("Nombre")).toHaveValue("aviso_pago_v2");
  });
});
