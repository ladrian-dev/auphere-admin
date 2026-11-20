import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Locale } from "@/i18n/messages";
import type { AgentModel, AgentModelOption, ModelEstimate } from "@/lib/backend/models";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => router }));
vi.mock("@/app/(console)/clients/[ref]/agents/agent-model-actions", () => ({}));

const { AgentModelSelect } = await import("../agent-model-select");
type Actions = NonNullable<React.ComponentProps<typeof AgentModelSelect>["actions"]>;

/**
 * Spec 065 (T026; requisitos 1.5, 2.4, 2.7, 4.8, 9.1 y 9.2) — Agente › Avanzado ›
 * Modelo: solo los modelos que el partner puede elegir, del más barato al más
 * caro, con su proveedor, la línea de su gama y su precio estimado por cada
 * 1.000 respuestas; el que responde lleva «Ahora» y sale elegido al abrir. Sin
 * chips de origen ni opción para volver al modelo por defecto. Los cinco
 * estados, las dos líneas de un modelo fuera de la oferta, el aviso de un
 * modelo que no puede usar las Skills del agente, solo lectura y guardar.
 */

const REF = "barberia-cultor";
const AGENT = "11111111-1111-4111-8111-111111111111";

const est = (amount_micros: number, basis: ModelEstimate["basis"] = "agent_7d"): ModelEstimate => ({ amount_micros, currency: "USD", basis });
const LUNA: AgentModelOption = { model_id: "openai/gpt-5.6-luna", display_name: "Luna", provider: "openai", line: "economy", estimate: est(550) };
const TERRA: AgentModelOption = { model_id: "openai/gpt-5.6-terra", display_name: "Terra", provider: "openai", line: "balanced", estimate: est(6269) };
const OPUS: AgentModelOption = { model_id: "anthropic/claude-opus-5-5", display_name: "Claude Opus 5.5", provider: "anthropic", line: "max", estimate: est(25075) };

function model(over: Partial<AgentModel> = {}): AgentModel {
  return {
    agent_id: AGENT,
    choice: null,
    effective: { model_id: TERRA.model_id, display_name: "Terra", source: "platform", outside_offer: null, estimate: est(6269) },
    options: [LUNA, TERRA, OPUS],
    notice: null,
    can_change: true,
    ...over,
  };
}

const ok = <T,>(data: T) => ({ ok: true as const, data });

function view(
  data: AgentModel | null | "lazy" = model(),
  over: Partial<Actions> = {},
  { canWrite = true, locale = "es" as Locale, agentName = "Recepción" } = {},
) {
  const actions: Actions = {
    load: vi.fn(async () => ok(model())),
    save: vi.fn(async ({ model_id }: { model_id: string }) => {
      const picked = [LUNA, TERRA, OPUS].find((o) => o.model_id === model_id)!;
      return ok(
        model({
          choice: { model_id, display_name: picked.display_name, set_by: "partner", set_at: "2026-11-20T10:00:00Z" },
          effective: { model_id, display_name: picked.display_name, source: "agent", outside_offer: null, estimate: picked.estimate },
        }),
      );
    }),
    ...over,
  };
  const out = render(
    <LocaleProvider locale={locale}>
      <AgentModelSelect refId={REF} agentId={AGENT} agentName={agentName} model={data === "lazy" ? undefined : data} canWrite={canWrite} actions={actions} />
    </LocaleProvider>,
  );
  return { ...out, actions };
}

const radio = (name: string) => screen.getByRole("radio", { name });
const card = (name: string) => radio(name).closest("label") as HTMLElement;
const saveButton = () => screen.getByRole("button", { name: "Guardar modelo" });

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Agente › Avanzado › Modelo · los cinco estados", () => {
  it("cargando: un esqueleto con la forma de las tarjetas, sin spinner", async () => {
    let resolve: (value: ReturnType<typeof ok<AgentModel>>) => void = () => {};
    const load = vi.fn(() => new Promise<ReturnType<typeof ok<AgentModel>>>((r) => (resolve = r)));
    view("lazy", { load });
    const loading = document.querySelector("[data-slot=agent-model-loading]") as HTMLElement;
    expect(loading).toHaveAttribute("aria-busy", "true");
    expect(within(loading).getByRole("status")).toHaveTextContent("Cargando…");
    // Tres tarjetas del mismo marco que las de verdad, cada una con sus cuatro líneas.
    const cards = loading.querySelectorAll("[data-slot=model-option-skeleton]");
    expect(cards).toHaveLength(3);
    for (const c of cards) expect(c.querySelectorAll("[data-slot=skeleton]").length).toBe(4);
    expect(document.querySelector(".animate-spin")).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(load).toHaveBeenCalledWith({ ref: REF, agent: AGENT });

    resolve(ok(model()));
    expect(await screen.findByRole("radio", { name: "Luna" })).toBeInTheDocument();
    expect(document.querySelector("[data-slot=agent-model-loading]")).toBeNull();
  });

  it("error: lo dice, el agente sigue respondiendo, y «Reintentar» vuelve a leer", async () => {
    const user = userEvent.setup();
    const { actions } = view(null);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("No se pudo leer el modelo de este agente");
    expect(alert).toHaveTextContent("Vuelve a intentarlo en un momento. El agente sigue respondiendo como hasta ahora.");
    expect(screen.queryByRole("radio")).toBeNull();
    await user.click(within(alert).getByRole("button", { name: "Reintentar" }));
    expect(actions.load).toHaveBeenCalledWith({ ref: REF, agent: AGENT });
    expect(await screen.findByRole("radio", { name: "Terra" })).toBeChecked();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("vacío: dice con qué responde, su precio, y que se escriba para pedir otro", () => {
    view(model({ options: [] }));
    expect(screen.getByText("Responde con Terra · ≈ 62,69 USD por 1.000 respuestas")).toBeVisible();
    expect(screen.getByText("Tu cuenta no tiene otros modelos para elegir. Si necesitas otro, escríbenos.")).toBeVisible();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("button", { name: "Guardar modelo" })).toBeNull();
  });

  it("vacío como lo manda la API (sin opciones, el que responde queda fuera de la oferta): solo esas dos líneas", () => {
    view(model({ options: [], effective: { ...model().effective, outside_offer: "operator" } }));
    expect(screen.getByText("Responde con Terra · ≈ 62,69 USD por 1.000 respuestas")).toBeVisible();
    expect(screen.getByText("Tu cuenta no tiene otros modelos para elegir. Si necesitas otro, escríbenos.")).toBeVisible();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByText(/Auphere eligió/)).toBeNull();
    expect(screen.queryByText(/ya no se ofrece/)).toBeNull();
  });

  it("vacío sin precio: solo el modelo", () => {
    view(model({ options: [], effective: { ...model().effective, outside_offer: "retired", estimate: null } }));
    expect(screen.getByText("Responde con Terra")).toBeVisible();
  });

  it("parcial: sin estimación lo dice, las tarjetas van sin precio y se puede cambiar igual", async () => {
    const user = userEvent.setup();
    view(model({ options: [{ ...LUNA, estimate: null }, { ...TERRA, estimate: null }], effective: { ...model().effective, estimate: null } }));
    expect(screen.getByText("Ahora no se puede calcular lo que cuesta cada modelo. Puedes cambiarlo igual.")).toBeVisible();
    expect(screen.queryByText(/USD por 1\.000 respuestas/)).toBeNull();
    await user.click(radio("Luna"));
    expect(saveButton()).toBeEnabled();
  });

  it("ideal: la oferta del partner del más barato al más caro, con «Ahora» en el que responde, elegido al abrir", async () => {
    const { container } = view();
    const names = screen.getAllByRole("radio").map((r) => r.getAttribute("value"));
    expect(names).toEqual([LUNA.model_id, TERRA.model_id, OPUS.model_id]);
    expect(radio("Terra")).toBeChecked();
    expect(radio("Luna")).not.toBeChecked();
    expect(screen.getAllByText("Ahora")).toHaveLength(1);
    expect(within(card("Terra")).getByText("Ahora")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Modelo" })).toBeVisible();
    expect(
      screen.getByText(
        "Cada modelo cuesta distinto y se paga de la bolsa del cliente. El precio es una estimación por cada 1.000 respuestas, hecha con lo que gastó este agente la última semana.",
      ),
    ).toBeVisible();
    // Sin cabecera «Responde con …»: el «Ahora» ya lo dice.
    expect(screen.queryByText(/Responde con/)).toBeNull();
    expect(screen.getByText("Vale desde el próximo mensaje. No hace falta publicar.")).toBeVisible();
    expect(saveButton()).toBeDisabled();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("Agente › Avanzado › Modelo · lo que dice cada tarjeta", () => {
  it("el proveedor, la línea de su gama (1.5) y el precio estimado por cada 1.000 respuestas", () => {
    view();
    const luna = card("Luna");
    expect(within(luna).getByText("OpenAI")).toBeVisible();
    expect(within(luna).getByText("Para preguntas frecuentes y respuestas cortas")).toBeVisible();
    expect(within(luna).getByText("≈ 5,50 USD por 1.000 respuestas")).toBeVisible();
    const terra = card("Terra");
    expect(within(terra).getByText("Para la mayoría de agentes de atención y reservas")).toBeVisible();
    expect(within(terra).getByText("≈ 62,69 USD por 1.000 respuestas")).toBeVisible();
    const opus = card("Claude Opus 5.5");
    expect(within(opus).getByText("Anthropic")).toBeVisible();
    expect(within(opus).getByText("Para agentes con muchas herramientas o casos difíciles")).toBeVisible();
    expect(within(opus).getByText("≈ 250,75 USD por 1.000 respuestas")).toBeVisible();
  });

  it("en inglés, el precio con su formato", () => {
    view(model(), {}, { locale: "en" });
    expect(within(screen.getByRole("radio", { name: "Terra" }).closest("label") as HTMLElement).getByText("≈ 62.69 USD per 1,000 responses")).toBeVisible();
    expect(screen.getByRole("button", { name: "Save model" })).toBeDisabled();
  });

  it("sin chip de origen ni opción para volver al modelo por defecto (2.7)", () => {
    view(model({ choice: { model_id: TERRA.model_id, display_name: "Terra", set_by: "operator", set_at: null }, effective: { ...model().effective, source: "agent_operator" } }));
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.queryByText(/El de Auphere/i)).toBeNull();
    expect(screen.queryByText(/Elegido por/i)).toBeNull();
    expect(screen.queryByText(/por defecto/i)).toBeNull();
    expect(screen.queryByText(/Auphere/)).toBeNull();
  });

  it("un modelo fuera de `options` no aparece, aunque sea el elegido", () => {
    view(
      model({
        choice: { model_id: "anthropic/claude-sonnet-4-6", display_name: "Claude Sonnet 4.6", set_by: "operator", set_at: null },
        effective: { model_id: "anthropic/claude-sonnet-4-6", display_name: "Claude Sonnet 4.6", source: "agent_operator", outside_offer: "retired", estimate: est(9000) },
      }),
    );
    expect(screen.queryByRole("radio", { name: "Claude Sonnet 4.6" })).toBeNull();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
  });
});

describe("Agente › Avanzado › Modelo · fuera de la oferta y el aviso", () => {
  it("«ya no se ofrece»: la línea con el modelo y su precio, sin «Ahora» y sin nada elegido", () => {
    view(
      model({
        choice: { model_id: "anthropic/claude-sonnet-4-6", display_name: "Claude Sonnet 4.6", set_by: "operator", set_at: null },
        effective: { model_id: "anthropic/claude-sonnet-4-6", display_name: "Claude Sonnet 4.6", source: "agent_operator", outside_offer: "retired", estimate: est(9000) },
      }),
    );
    expect(
      screen.getByText(
        "Este agente responde con Claude Sonnet 4.6 (≈ 90,00 USD por 1.000 respuestas), que ya no se ofrece. Sigue con él hasta que elijas otro. Después no podrás volver a él.",
      ),
    ).toBeVisible();
    expect(screen.queryByText("Ahora")).toBeNull();
    for (const r of screen.getAllByRole("radio")) expect(r).not.toBeChecked();
    expect(saveButton()).toBeDisabled();
  });

  it("«Auphere eligió»: la línea con el modelo, su precio y que no podrá volver a él", async () => {
    const user = userEvent.setup();
    view(
      model({
        choice: { model_id: "anthropic/claude-sonnet-5-5", display_name: "Claude Sonnet 5.5", set_by: "operator", set_at: null },
        effective: { model_id: "anthropic/claude-sonnet-5-5", display_name: "Claude Sonnet 5.5", source: "agent_operator", outside_offer: "operator", estimate: est(12538) },
      }),
    );
    expect(
      screen.getByText(
        "Auphere eligió Claude Sonnet 5.5 para este agente (≈ 125,38 USD por 1.000 respuestas). No está entre los modelos de tu cuenta: puedes cambiarlo por uno de estos, pero después no podrás volver a él.",
      ),
    ).toBeVisible();
    expect(screen.queryByText("Ahora")).toBeNull();
    await user.click(radio("Luna"));
    expect(saveButton()).toBeEnabled();
  });

  it("el elegido no puede usar las Skills del agente: el aviso dice con cuál responde mientras tanto (4.8)", () => {
    view(
      model({
        choice: { model_id: "openai/gpt-5.6-sol", display_name: "Sol", set_by: "partner", set_at: "2026-11-19T10:00:00Z" },
        effective: { ...model().effective, source: "platform" },
        notice: "chosen_model_cannot_run_agent",
        options: [LUNA, TERRA, OPUS],
      }),
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Sol no puede usar las Skills de este agente");
    expect(alert).toHaveTextContent("Mientras las tenga, responde con Terra. Elige uno de estos o quita las Skills.");
    expect(screen.queryByRole("radio", { name: "Sol" })).toBeNull();
  });
});

describe("Agente › Avanzado › Modelo · la estimación y el aviso", () => {
  it("con lo que gastó el agente, la entrada lo dice", () => {
    view();
    expect(screen.getByText(/hecha con lo que gastó este agente la última semana\./)).toBeVisible();
  });

  it("un agente sin consumo se estima con una conversación típica, y la entrada no dice otra cosa", () => {
    const nominal = (o: AgentModelOption): AgentModelOption => ({ ...o, estimate: est(o.estimate!.amount_micros, "nominal") });
    view(
      model({
        effective: { ...model().effective, estimate: est(6269, "nominal") },
        options: [nominal(LUNA), nominal(TERRA), nominal(OPUS)],
      }),
    );
    expect(screen.getByText(/hecha con una conversación típica, porque este agente aún no tiene consumo\./)).toBeVisible();
    expect(screen.queryByText(/la última semana/)).toBeNull();
  });

  it("con el aviso, guardar el que responde ahora lo deja como elegido y el aviso se va (4.8)", async () => {
    const user = userEvent.setup();
    const { actions } = view(
      model({
        choice: { model_id: "openai/gpt-5.6-sol", display_name: "Sol", set_by: "partner", set_at: "2026-11-19T10:00:00Z" },
        effective: { ...model().effective, source: "platform" },
        notice: "chosen_model_cannot_run_agent",
        options: [LUNA, TERRA, OPUS],
      }),
    );
    expect(radio("Terra")).toBeChecked();
    expect(saveButton()).toBeEnabled();
    await user.click(saveButton());
    await waitFor(() => expect(actions.save).toHaveBeenCalledWith({ ref: REF, agent: AGENT, model_id: TERRA.model_id }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});

describe("Agente › Avanzado › Modelo · cambiarlo", () => {
  it("con `agents:read` se ve la lista apagada y quién puede cambiarlo (2.4)", () => {
    view(model({ can_change: false }));
    for (const r of screen.getAllByRole("radio")) expect(r).toBeDisabled();
    expect(screen.getByText("Solo quien edita agentes puede cambiarlo.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Guardar modelo" })).toBeNull();
    expect(radio("Terra")).toBeChecked();
  });

  it("sin permiso de escritura en la pantalla, igual", () => {
    view(model(), {}, { canWrite: false });
    for (const r of screen.getAllByRole("radio")) expect(r).toBeDisabled();
    expect(screen.getByText("Solo quien edita agentes puede cambiarlo.")).toBeVisible();
  });

  it("guardar llama a la acción, enseña el toast, mueve «Ahora» y refresca", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(radio("Luna"));
    expect(saveButton()).toBeEnabled();
    await user.click(saveButton());
    await waitFor(() => expect(actions.save).toHaveBeenCalledWith({ ref: REF, agent: AGENT, model_id: LUNA.model_id }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Recepción responde con Luna desde el próximo mensaje."));
    expect(router.refresh).toHaveBeenCalled();
    expect(within(card("Luna")).getByText("Ahora")).toBeVisible();
    expect(within(card("Terra")).queryByText("Ahora")).toBeNull();
    expect(saveButton()).toBeDisabled();
  });

  it("volver a elegir el que responde deja «Guardar modelo» apagado", async () => {
    const user = userEvent.setup();
    view();
    await user.click(radio("Luna"));
    await user.click(radio("Terra"));
    expect(saveButton()).toBeDisabled();
  });

  it("lo elegido sin guardar sigue elegido si la página se vuelve a leer con el mismo modelo", async () => {
    const user = userEvent.setup();
    const { rerender, actions } = view();
    await user.click(radio("Luna"));
    rerender(
      <LocaleProvider locale="es">
        <AgentModelSelect refId={REF} agentId={AGENT} agentName="Recepción" model={model()} canWrite actions={actions} />
      </LocaleProvider>,
    );
    expect(radio("Luna")).toBeChecked();
    expect(saveButton()).toBeEnabled();
  });

  it("un 422 dice que ya no está disponible, y la elección no se pierde", async () => {
    const user = userEvent.setup();
    view(model(), { save: vi.fn(async () => ({ ok: false as const, status: 422, message: "", code: "unknown_model" })) });
    await user.click(radio("Luna"));
    await user.click(saveButton());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("No se pudo cambiar el modelo: ya no está disponible en tu cuenta. Recarga la página y elige otro."),
    );
    expect(toast.success).not.toHaveBeenCalled();
    expect(router.refresh).not.toHaveBeenCalled();
    expect(radio("Luna")).toBeChecked();
  });

  it("un 403 dice que el rol no lo permite", async () => {
    const user = userEvent.setup();
    view(model(), { save: vi.fn(async () => ({ ok: false as const, status: 403, message: "forbidden" })) });
    await user.click(radio("Luna"));
    await user.click(saveButton());
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Tu rol no permite esta acción."));
  });
});

describe("Agente › Avanzado › Modelo · textos largos (alemán, +30 %)", () => {
  it("un nombre y una línea largos no desbordan la tarjeta", () => {
    const long = "Donaudampfschifffahrtsgesellschaftskapitänsmützenherstellungsbetrieb";
    view(model({ options: [{ ...LUNA, display_name: long }, TERRA] }));
    const name = screen.getByText(long);
    expect(name.className).toMatch(/min-w-0/);
    expect(name.className).toMatch(/break-words/);
    const label = name.closest("label") as HTMLElement;
    expect(label.className).toMatch(/min-w-0/);
    expect((label.querySelector("[data-slot=model-option-body]") as HTMLElement).className).toMatch(/min-w-0/);
    expect(screen.getByText("Para preguntas frecuentes y respuestas cortas").className).toMatch(/text-pretty/);
    expect(screen.getByText("Vale desde el próximo mensaje. No hace falta publicar.").className).toMatch(/min-w-0/);
  });

  it("el título de la sección se equilibra, como todos los títulos (T092, regla 2 del workspace)", () => {
    view();
    expect(screen.getByRole("heading", { name: "Modelo" }).className).toMatch(/text-balance/);
  });
});
