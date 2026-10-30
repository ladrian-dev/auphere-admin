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
