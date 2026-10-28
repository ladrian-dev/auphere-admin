import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Gate } from "@/lib/backend/agent-quality-types";

import { AGENT, JOB, REF, fail, job, noWait, ok, preview } from "./quality-fixtures";

const nav = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/agents/quality-actions", () => ({
  publishAction: vi.fn(),
  publishPreviewAction: vi.fn(),
  qualityJobAction: vi.fn(),
  undoPublishAction: vi.fn(),
}));

const { PublishBar } = await import("../publish-bar");
type Actions = NonNullable<React.ComponentProps<typeof PublishBar>["actions"]>;

/**
 * Spec 047 (historia 9, T094; requisitos 23 y 24.1) — guardar es publicar, con
 * red: el botón dice lo que pasa, «Guardar cambios» enseña antes el diff, sin
 * canales lleva a Canales, la puerta se explica condición a condición,
 * «Guardar igualmente» con confirmación para las pruebas normales, el motivo
 * solo para owner y admin, y «Deshacer» en el aviso.
 */

const inTenMinutes = () => new Date(Date.now() + 9 * 60 * 1000).toISOString();
const DONE = () => ok(job({ status: "done", result: { number: 4, undo_until: inTenMinutes(), gate: {} } }));

function gate(over: Partial<Gate> = {}): Gate {
  return {
    conditions: [
      { condition: "validator", ok: true },
      { condition: "critical_tests", ok: true },
      { condition: "regression", ok: true },
      { condition: "ai_disclosure", ok: true },
      { condition: "review", ok: true },
    ],
    hard: [],
    overridable: [],
    normal_failures: [],
    rate: 90,
    reference_rate: null,
    ...over,
  };
}
const blocked = (g: Gate) => ok(job({ status: "failed", error_code: "gate_blocked", progress: { step: "blocked", blocks: [{ key: "gate", ...g }] } }));

function screenWith(props: Partial<React.ComponentProps<typeof PublishBar>> = {}, actions: Partial<Actions> = {}) {
  const full: Actions = {
    preview: vi.fn(async () => ok(preview())),
    publish: vi.fn(async () => ok({ job_id: JOB })),
    poll: vi.fn(async () => DONE()),
    undo: vi.fn(async () => ok({ number: 3 })),
    ...actions,
  };
  const onPublished = vi.fn();
  const view = render(
    <LocaleProvider locale="es">
      <PublishBar refId={REF} agentId={AGENT} preview={preview()} hadActive canWrite onPublished={onPublished} actions={full} wait={noWait} {...props} />
    </LocaleProvider>,
  );
  return { ...view, actions: full, onPublished };
}

beforeEach(() => {
  nav.push.mockClear();
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("«Guardar» (23.4, 23.5)", () => {
  it("guarda, avisa con «Deshacer» y deshace (24.1)", async () => {
    const user = userEvent.setup();
    const { actions, onPublished, container } = screenWith();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(actions.publish).toHaveBeenCalledWith({ ref: REF, agent: AGENT });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const [message, options] = toast.success.mock.calls[0] as [string, { action: { label: string; onClick: () => void }; duration: number }];
    expect(message).toBe("Guardado como v4. Ya atiende con esta versión.");
    expect(options.action.label).toBe("Deshacer");
    expect(options.duration).toBeGreaterThan(8 * 60 * 1000);
    expect(onPublished).toHaveBeenCalled();
    options.action.onClick();
    await waitFor(() => expect(actions.undo).toHaveBeenCalledWith({ ref: REF, agent: AGENT }));
    await waitFor(() => expect(toast.success).toHaveBeenLastCalledWith("Deshecho: vuelve a atender la v3."));
  });

  it("la primera versión no ofrece «Deshacer»: no hay adónde volver", async () => {
    const user = userEvent.setup();
    screenWith({ hadActive: false });
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(toast.success.mock.calls[0]![1]).toEqual({});
  });

  it("sin canales: «Guardar y conectar un canal» y después a Canales", async () => {
    const user = userEvent.setup();
    screenWith({ preview: preview({ action: "save_and_connect" }) });
    await user.click(screen.getByRole("button", { name: "Guardar y conectar un canal" }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith(`/clients/${REF}/channels`));
  });

  it("con canales: «Guardar cambios» enseña antes el diff en lenguaje llano", async () => {
    const user = userEvent.setup();
    const { actions } = screenWith({
      preview: preview({
        action: "save_changes",
        has_channels: true,
        diff: [
          { part: "rules", label: "Reglas", change: "add" },
          { part: "instructions", label: "Instrucciones", change: "replace" },
          { part: "tools", label: "Lo que puede hacer", change: "replace", added: ["reservas.create"], removed: [] },
        ],
      }),
    });
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));
    const sheet = await screen.findByRole("dialog", { name: "Qué cambia al guardar" });
    expect(actions.publish).not.toHaveBeenCalled();
    expect(within(sheet).getByText("+ Reglas")).toBeVisible();
    expect(within(sheet).getByText("~ Instrucciones")).toBeVisible();
    expect(within(sheet).getByText("Añade: reservas.create")).toBeVisible();
    await user.type(within(sheet).getByRole("textbox", { name: /Nota del cambio/ }), "Lista de espera");
    await user.click(within(sheet).getByRole("button", { name: "Guardar cambios" }));
    expect(actions.publish).toHaveBeenCalledWith({ ref: REF, agent: AGENT, note: "Lista de espera" });
  });

  it("sin borrador no hay botón, sino lo que pasa; quien solo lee tampoco lo ve", () => {
    const { unmount } = screenWith({ preview: preview({ has_draft: false }) });
    expect(screen.getByText("No hay cambios sin guardar.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Guardar/ })).toBeNull();
    unmount();
    screenWith({ canWrite: false });
    expect(screen.getByText(/Solo lectura/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Guardar/ })).toBeNull();
  });
});

describe("la puerta (23.1, 23.2, 23.3)", () => {
  it("con un bloqueante que no se puede saltar, lo explica y no ofrece nada", async () => {
    const user = userEvent.setup();
    const g = gate({
      conditions: [
        { condition: "validator", ok: true },
        { condition: "ai_disclosure", ok: false },
      ],
      hard: [{ condition: "ai_disclosure", code: "ai_disclosure_undecided", message: "Falta decidir si el agente dice que es una IA." }],
    });
    const { container } = screenWith({ preview: preview({ can_override: true }) }, { poll: vi.fn(async () => blocked(g)) });
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    const notice = await screen.findByRole("alert");
    expect(within(notice).getByText("No se guardó: no pasa la puerta")).toBeVisible();
    expect(within(notice).getByText("Falta decidir si el agente dice que es una IA.")).toBeVisible();
    expect(within(notice).getByText("El aviso de IA está decidido")).toBeVisible();
    expect(within(notice).getByText(/No se cumple/)).toBeInTheDocument();
    expect(within(notice).queryByRole("button")).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("con pruebas normales en rojo: «Guardar igualmente» con confirmación", async () => {
    const user = userEvent.setup();
    const publish = vi.fn(async () => ok({ job_id: JOB }));
    const poll = vi.fn<Actions["poll"]>().mockResolvedValueOnce(blocked(gate({ normal_failures: ["Pide un descuento"] }))).mockResolvedValueOnce(DONE());
    screenWith({}, { publish, poll });
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    const notice = await screen.findByRole("alert");
    expect(within(notice).getByText("Pide un descuento")).toBeVisible();
    await user.click(within(notice).getByRole("button", { name: "Guardar igualmente" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Guardar con pruebas en rojo?" });
    expect(within(dialog).getByText(/Fallan pruebas que no son críticas: Pide un descuento/)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Guardar igualmente" }));
    expect(publish).toHaveBeenLastCalledWith({ ref: REF, agent: AGENT, accept_normal_failures: true });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("con una crítica en rojo, el owner o admin la salta escribiendo el motivo", async () => {
    const user = userEvent.setup();
    const publish = vi.fn(async () => ok({ job_id: JOB }));
    const g = gate({
      conditions: [{ condition: "critical_tests", ok: false }],
      overridable: [{ condition: "critical_tests", code: "critical_test_failing", message: "La prueba crítica «Reserva una cita» no pasa 3 de 3." }],
    });
    const poll = vi.fn<Actions["poll"]>().mockResolvedValueOnce(blocked(g)).mockResolvedValueOnce(DONE());
    screenWith({ preview: preview({ can_override: true }) }, { publish, poll });
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    const notice = await screen.findByRole("alert");
    await user.click(within(notice).getByRole("button", { name: "Guardar igualmente…" }));
    const dialog = await screen.findByRole("dialog", { name: "Guardar saltando la puerta" });
    await user.click(within(dialog).getByRole("button", { name: "Guardar con este motivo" }));
    expect(within(dialog).getByText("Escribe el motivo, con al menos 3 caracteres.")).toBeVisible();
    await user.type(within(dialog).getByRole("textbox", { name: /Motivo/ }), "AgendaPro se conecta mañana");
    await user.click(within(dialog).getByRole("button", { name: "Guardar con este motivo" }));
    expect(publish).toHaveBeenLastCalledWith({ ref: REF, agent: AGENT, override_reason: "AgendaPro se conecta mañana", accept_normal_failures: true });
  });

  it("sin permiso para saltarla, se explica y no hay control (§V)", async () => {
    const user = userEvent.setup();
    const g = gate({ overridable: [{ condition: "review", code: "unknown_tool", message: "Cita una herramienta que no existe." }] });
    screenWith({ preview: preview({ can_override: false }) }, { poll: vi.fn(async () => blocked(g)) });
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    const notice = await screen.findByRole("alert");
    expect(within(notice).getByText("Solo un owner o un admin puede guardarlo igualmente:")).toBeVisible();
    expect(within(notice).queryByRole("button")).toBeNull();
  });

  it("dice por qué no empezó: saltar la puerta sin permiso o sin borrador", async () => {
    const user = userEvent.setup();
    screenWith({}, { publish: vi.fn(async () => fail(409, "no_draft")) });
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("No hay borrador que guardar.")).toBeVisible();
  });
});
