import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { ChannelPage } from "@/lib/backend/channel-config-types";

import { RECEPCION, REF, ok, page } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agents/channel-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  listTemplatesAction: vi.fn(async () => ({ ok: true, data: { items: [], approved: 0, rejected: 0, pending: 0 } })),
}));

const { ChannelConfigPage } = await import("../channel-page");
const { ChannelWizard } = await import("../channel-picker");
type Actions = NonNullable<React.ComponentProps<typeof ChannelConfigPage>["actions"]>;

/**
 * Spec 049, apertura a todos los partners (2026-11-20). La página de un canal
 * se hizo para WhatsApp y en Instagram y Messenger seguía hablando de «este
 * número», de un modo de prueba que allí no existe y de conservar las
 * conversaciones al desconectar, cuando lo que pasa (requisito 5.3, y lo que
 * se le dijo a Meta) es que se borran a los 30 días. La pantalla no miente
 * (constitución §V): cada canal dice lo que de verdad hace.
 */

const social = (type: "instagram" | "messenger", over: Partial<ChannelPage> = {}) =>
  page({
    type,
    identifier: type === "instagram" ? "@demo.store" : "Demo Store",
    visible_state: { code: "everyone", tone: "positive", reason: null },
    config: {
      audience: { mode: "everyone", test_numbers: [], exceptions: [] },
      escalation: { recipients: [], summary: true },
      wait_message: null,
      notify_from: "auphere",
    },
    // La API da la sección «Comentarios» a los dos (`_COMMENT_CHANNELS`).
    instagram_comments: { enabled: true, public_reply: null },
    ...over,
  });

function view(p: ChannelPage) {
  const actions: Actions = {
    save: vi.fn(),
    undo: vi.fn(),
    reload: vi.fn(async () => ok(p)),
    history: vi.fn(async () => ok([])),
    comments: vi.fn(),
    menu: { move: vi.fn(), pause: vi.fn(), resume: vi.fn(), disconnect: vi.fn() },
  };
  return render(
    <LocaleProvider locale="es">
      <ChannelConfigPage refId={REF} agentId={RECEPCION} page={p} history={[]} canWrite actions={actions} />
    </LocaleProvider>,
  );
}

describe.each(["instagram", "messenger"] as const)("la página de un canal de %s", (type) => {
  it("«A quién responde» no promete un modo de prueba que no hay ni excepciones", () => {
    view(social(type));
    const section = screen.getByRole("region", { name: "A quién responde" });
    expect(within(section).getByText(/Aquí no hay modo de prueba/)).toBeVisible();
    expect(within(section).getByText("Responde a todas las personas que le escriban.")).toBeVisible();
    expect(section.textContent).not.toMatch(/número|excepciones|tu equipo antes/);
  });

  it("los avisos salen del número de avisos de Auphere, sin hablar de la plantilla de este canal", () => {
    view(social(type));
    const from = document.querySelector("[data-slot=notify-from]") as HTMLElement;
    expect(from.textContent).toBe("Los avisos por WhatsApp saldrán del número de avisos de Auphere.");
  });

  it("al desconectar dice que los mensajes se borran a los 30 días, salvo que se vuelva a conectar", async () => {
    const user = userEvent.setup();
    const p = social(type);
    view(p);
    await user.click(screen.getByRole("button", { name: `Más acciones de ${p.identifier}` }));
    await user.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Desconectar" }));
    const dialog = await screen.findByRole("dialog", { name: `¿Desconectar ${p.identifier}?` });
    expect(within(dialog).getByText(/se borran a los 30 días, salvo que lo vuelvas a conectar antes/)).toBeVisible();
    expect(dialog.textContent).not.toMatch(/se conservan/);
  });

  it("desconectado, recuerda el plazo de 30 días", () => {
    view(social(type, { status: "disconnected", visible_state: { code: "disconnected", tone: "muted", reason: null }, allowed: [] }));
    expect(screen.getByText(/se borran a los 30 días de desconectarlo/)).toBeVisible();
    expect(screen.queryByText(/Este número está desconectado/)).toBeNull();
  });
});

describe("textos que valen para cualquier canal", () => {
  it("quién decide pasar a una persona es el agente, no el canal", () => {
    view(social("instagram"));
    expect(screen.getByText("Lo decide el agente, no el canal.")).toBeVisible();
  });

  it("WhatsApp sigue con su modo de prueba, sus excepciones y su plantilla de avisos", () => {
    view(page());
    const section = screen.getByRole("region", { name: "A quién responde" });
    expect(within(section).getByText("Prueba con tu equipo antes de abrirlo a todos. Vale solo para este número.")).toBeVisible();
    expect(screen.getByText(/porque este número aún no tiene aprobada la plantilla de aviso/)).toBeVisible();
  });
});

describe("conectar otra cuenta o Página", () => {
  it("Messenger conecta Páginas, no cuentas", () => {
    render(
      <LocaleProvider locale="es">
        <ChannelWizard step={0} connected={{ whatsapp: 0, instagram: 1, messenger: 1 }} available={["instagram", "messenger"]} onConnect={vi.fn()} />
      </LocaleProvider>,
    );
    expect(within(screen.getByRole("button", { name: /Messenger/ })).getByText("Conectar otra Página")).toBeVisible();
    expect(within(screen.getByRole("button", { name: /Instagram/ })).getByText("Conectar otra cuenta")).toBeVisible();
  });
});
