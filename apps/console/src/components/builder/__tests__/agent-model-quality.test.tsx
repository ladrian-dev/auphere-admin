import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { QualityJob } from "@/lib/backend/agent-quality-types";
import type { ModelPolicy, ModelQuality } from "@/lib/backend/model-quality-types";

import { AGENT, JOB, REF, fail, noWait, ok, profile, quality } from "./connector-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agents/model-quality-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/connector-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/integrations/actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/life-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/agents/builder-actions", () => ({
  builderDraftAction: vi.fn(),
  decideProposalAction: vi.fn(),
  saveAgentSpecAction: vi.fn(),
}));

const { AgentModelQuality } = await import("../agent-model-quality");
type Actions = NonNullable<React.ComponentProps<typeof AgentModelQuality>["actions"]>;

/**
 * Spec 047 (historia 23; T147; requisito 39) — Agente › Avanzado › Calidad:
 * cada opción con su línea, su precio estimado por mensaje y la diferencia con
 * la actual; el precio real de 7 días; «Comprobar la calidad» como un trabajo
 * con «Comprobando la calidad…»; solo lo comprobado va al borrador; «Solo UE»;
 * la propuesta de «Automático» a un migrado; quien solo lee no cambia nada.
 */

const plain = (el: HTMLElement) => (el.textContent ?? "").replace(/ /g, " ");
const job = (status: QualityJob["status"]): QualityJob => ({
  job_id: JOB,
  kind: "tests",
  status,
  agent_id: AGENT,
  progress: null,
  result: null,
  error_code: null,
  created_at: "2026-10-28T10:00:00Z",
  finished_at: null,
});

function view(
  data: ModelQuality | null | "lazy" = quality(),
  over: Partial<Actions> = {},
  { canWrite = true, drafted = null as ModelPolicy | null, onUse = vi.fn(async () => ok(null)) as ((p: ModelPolicy) => Promise<{ ok: true; data: null }>) | undefined } = {},
) {
  const actions: Actions = {
    load: vi.fn(async () => ok(quality())),
    check: vi.fn(async () => ok({ job_id: JOB })),
    poll: vi.fn(async () => ok(job("done"))),
    ...over,
  };
  const out = render(
    <LocaleProvider locale="es">
      <AgentModelQuality
        refId={REF}
        agentId={AGENT}
        quality={data === "lazy" ? undefined : data}
        canWrite={canWrite}
        drafted={drafted}
        onUse={onUse}
        actions={actions}
        wait={noWait}
      />
    </LocaleProvider>,
  );
  return { ...out, actions, onUse };
}

const option = (name: string) => screen.getByRole("radio", { name: new RegExp(`^${name}`) });
const card = (name: string) => option(name).closest("label") as HTMLElement;

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("Calidad · leer (39.4, 39.5)", () => {
  it("cada opción con su línea, su precio por mensaje y la diferencia con la actual, y el real de 7 días, y pasa axe", async () => {
    const { container } = view();
    const group = screen.getByRole("group", { name: "Opciones de calidad" });
    expect(within(group).getAllByRole("radio").slice(0, 4).map((r) => (r.closest("label")?.querySelector(".font-medium")?.textContent ?? ""))).toEqual([
      "Automático",
      "Económico",
      "Equilibrado",
      "Máximo",
    ]);
    expect(option("Automático")).toBeChecked();
    expect(within(card("Automático")).getByText("Actual")).toBeVisible();
    expect(plain(card("Automático"))).toContain("0,002 USD por mensaje");
    expect(within(card("Automático")).getByText("Auphere elige en cada tarea el modelo más barato que la hace bien.")).toBeVisible();
    expect(plain(card("Económico"))).toContain("0,0012 USD menos que la actual");
    expect(plain(card("Equilibrado"))).toContain("0,0042 USD por mensaje");
    expect(plain(card("Equilibrado"))).toContain("0,0022 USD más que la actual");
    expect(within(card("Económico")).getByText("Sin comprobar con este agente")).toBeVisible();
    expect(within(card("Equilibrado")).getByText("Comprobada con este agente")).toBeVisible();
    expect(within(card("Máximo")).getByText("No pasó la comprobación")).toBeVisible();
    expect(plain(screen.getByText("Precio real medio por mensaje, últimos 7 días").nextElementSibling as HTMLElement)).toBe("0,0023 USD por mensaje");
    expect(screen.getByText("Estimado con los mensajes de este agente en los últimos 30 días.")).toBeVisible();
    // «Fijar un modelo»: los modelos con su proveedor y dónde se ejecutan.
    expect(screen.getByText("Fijar un modelo")).toBeVisible();
    expect(within(card("Claude Sonnet \\(UE\\)")).getByText("Anthropic · En la UE")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sin tráfico, la estimación es del sector, y sin mensajes en 7 días lo dice", () => {
    view(quality({ estimate_source: "sector", real_price_7d: null }));
    expect(screen.getByText("Estimado con un agente típico de su sector, hasta que este tenga mensajes.")).toBeVisible();
    expect(screen.getByText("Aún no hay mensajes en los últimos 7 días.")).toBeVisible();
  });

  it("con «Solo UE», lo que no tiene modelo en la UE no se ofrece (39.10)", () => {
    view(quality({ eu_only: true, profiles: [profile({ profile: "auto", current: true }), profile({ profile: "max", offered: false })] }));
    expect(screen.getByText("Este cliente tiene «Solo UE». Solo se ofrecen las opciones con modelos en la UE.")).toBeVisible();
    expect(screen.queryByRole("radio", { name: /^Máximo/ })).not.toBeInTheDocument();
  });

  it("a un agente migrado se le propone «Automático» con su precio, y elegirlo lo marca (39.11)", async () => {
    const user = userEvent.setup();
    view(quality({ current: { kind: "legacy" }, suggest_auto: true, profiles: quality().profiles.map((p) => ({ ...p, current: false })) }));
    expect(screen.getByText("El modelo que tenía antes de la consola nueva")).toBeVisible();
    const callout = screen.getByText(/Te proponemos «Automático»/);
    expect(plain(callout)).toContain("0,002 USD por mensaje");
    expect(screen.queryByRole("radio", { checked: true })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Automático" }));
    expect(option("Automático")).toBeChecked();
    expect(screen.getByRole("button", { name: "Usar Automático en el borrador" })).toBeVisible();
  });

  it("quien solo lee lo ve todo sin poder elegir ni comprobar (39.12)", () => {
    view(quality({ allowed: [] }));
    expect(screen.getByText("Tu rol puede ver la calidad, no cambiarla.")).toBeVisible();
    expect(option("Económico")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Comprobar/ })).not.toBeInTheDocument();
  });
});

describe("Calidad · los estados", () => {
  it("sin datos del servidor, carga al montar y lo dice mientras tanto", async () => {
    view("lazy");
    expect(screen.getByText("Cargando las opciones de calidad…")).toBeVisible();
    expect(await screen.findByRole("group", { name: "Opciones de calidad" })).toBeVisible();
  });

  it("si no se pudo leer lo dice y deja reintentar", async () => {
    const user = userEvent.setup();
    const load = vi.fn(async () => fail(500));
    view(null, { load });
    expect(screen.getByText("No se pudieron cargar las opciones de calidad.")).toBeVisible();
    load.mockResolvedValueOnce(ok(quality()) as never);
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("group", { name: "Opciones de calidad" })).toBeVisible();
  });
});

describe("Calidad · comprobar y usar (39.1, 39.9)", () => {
  it("una opción sin comprobar pide «Comprobar la calidad», que se sigue como un trabajo hasta que pasa", async () => {
    const user = userEvent.setup();
    const passed = quality({
      profiles: quality().profiles.map((p) => (p.profile === "economy" ? { ...p, check: { status: "passed" as const, job_id: JOB, reasons: [] } } : p)),
    });
    let release: () => void = () => {};
    const poll = vi.fn(() => new Promise<ReturnType<typeof ok<QualityJob>>>((r) => (release = () => r(ok(job("done"))))));
    const { actions } = view(quality(), { poll, load: vi.fn(async () => ok(passed)) });
    await user.click(option("Económico"));
    expect(screen.getByText(/Comprueba la calidad antes de usarla/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Comprobar la calidad con Económico" }));
    expect(actions.check).toHaveBeenCalledWith({ ref: REF, agent: AGENT, policy: { kind: "profile", profile: "economy" } });
    expect(await screen.findAllByText("Comprobando la calidad…")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Comprobar la calidad con Económico" })).toBeDisabled();
    await waitFor(() => expect(poll).toHaveBeenCalledWith({ ref: REF, job: JOB }));
    release();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Económico pasó la comprobación."));
    expect(within(card("Económico")).getByText("Pasó la comprobación")).toBeVisible();
    expect(screen.getByRole("button", { name: "Usar Económico en el borrador" })).toBeVisible();
  });

  it("una que no pasó dice por qué y deja volver a comprobar", async () => {
    const user = userEvent.setup();
    view();
    await user.click(option("Máximo"));
    const reasons = screen.getByRole("list", { name: "No pasó la comprobación" });
    expect(within(reasons).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Falló una prueba crítica.",
      "Las pruebas bajan 5 puntos frente a la última pasada.",
    ]);
    expect(screen.getByRole("button", { name: "Comprobar otra vez con Máximo" })).toBeEnabled();
  });

  it("los errores de comprobar se dicen con palabras", async () => {
    const user = userEvent.setup();
    const check = vi.fn().mockResolvedValueOnce(fail(402, "build_budget_exhausted")).mockResolvedValueOnce(fail(409, "no_version"));
    view(quality(), { check });
    await user.click(option("Económico"));
    await user.click(screen.getByRole("button", { name: "Comprobar la calidad con Económico" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Construcción y pruebas/);
    await user.click(screen.getByRole("button", { name: "Comprobar la calidad con Económico" }));
    expect(await screen.findByText("Este agente aún no tiene una versión que comprobar.")).toBeVisible();
  });

  it("una comprobación en marcha al abrir se sigue igual", async () => {
    const running = quality({
      profiles: quality().profiles.map((p) => (p.profile === "economy" ? { ...p, check: { status: "running" as const, job_id: JOB, reasons: [] } } : p)),
    });
    const { actions } = view(running);
    expect(within(card("Económico")).getByText("Comprobando la calidad…")).toBeVisible();
    await waitFor(() => expect(actions.poll).toHaveBeenCalledWith({ ref: REF, job: JOB }));
    await waitFor(() => expect(actions.load).toHaveBeenCalled());
  });

  it("una opción comprobada se lleva al borrador; la del borrador lo dice y no pide nada", async () => {
    const user = userEvent.setup();
    const { onUse } = view();
    await user.click(option("Equilibrado"));
    await user.click(screen.getByRole("button", { name: "Usar Equilibrado en el borrador" }));
    await waitFor(() => expect(onUse).toHaveBeenCalledWith({ kind: "profile", profile: "balanced" }));
    expect(toast.success).toHaveBeenCalledWith("Equilibrado queda en el borrador. Pulsa «Guardar» para aplicarlo.");
  });

  it("lo que ya está en el borrador lo marca", () => {
    view(quality(), {}, { drafted: { kind: "profile", profile: "balanced" } });
    expect(screen.getByText("En el borrador: Equilibrado. Se aplica al guardar.")).toBeVisible();
    expect(option("Equilibrado")).toBeChecked();
    expect(within(card("Equilibrado")).getByText("En el borrador")).toBeVisible();
    expect(screen.queryByRole("button", { name: /en el borrador/ })).not.toBeInTheDocument();
  });

  it("si el borrador no se pudo cambiar, lo dice", async () => {
    const user = userEvent.setup();
    view(quality(), {}, { onUse: vi.fn(async () => fail(409)) as never });
    await user.click(option("Equilibrado"));
    await user.click(screen.getByRole("button", { name: "Usar Equilibrado en el borrador" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo cambiar el borrador. Vuelve a intentarlo.");
  });
});

// La pantalla del agente ya no monta Calidad (spec 047, 64.1; D55): lo prueba
// `agent-builder.test.tsx` («Avanzado sin «Calidad»»). El componente se queda,
// probado aquí, para cuando la gestión de modelos vuelva a la consola (64.4).
