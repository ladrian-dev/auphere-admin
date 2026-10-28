import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { ChannelPage } from "@/lib/backend/channel-config-types";

import { CH, HISTORY, RECEPCION, REF, VENTAS, fail, ok, page } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/app/(console)/clients/[ref]/agents/channel-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({}));

const { ChannelConfigPage } = await import("../channel-page");
type Actions = NonNullable<React.ComponentProps<typeof ChannelConfigPage>["actions"]>;

/**
 * Spec 047 (historia 11; requisitos 32 y 33; T115) — la página de un canal: las
 * cinco secciones, guardar con la revisión leída, el conflicto con lo que
 * cambió otra persona, los errores con su arreglo, deshacer durante 10 minutos,
 * el historial con el antes y el después, de qué número salen los avisos y los
 * disparadores del agente en solo lectura. Quien solo lee no ve campos.
 */

function view(p: ChannelPage = page(), over: Partial<Actions> = {}, { canWrite = true, balanceHref = null as string | null } = {}) {
  const actions: Actions = {
    save: vi.fn(async ({ config }) => ok(page({ revision: p.revision + 1, config: { ...config, notify_from: p.config.notify_from }, undo_until: new Date(Date.now() + 600_000).toISOString() }))),
    undo: vi.fn(async () => ok(page({ revision: p.revision + 2 }))),
    reload: vi.fn(async () => ok(page({ revision: 5, config: { ...p.config, wait_message: "Ya vamos" } }))),
    history: vi.fn(async () => ok(HISTORY)),
    menu: {
      move: vi.fn(async () => ok(page({ agent: { id: VENTAS, name: "Ventas" } }))),
      pause: vi.fn(async () => ok(page({ status: "paused", visible_state: { code: "paused", tone: "warn", reason: null }, allowed: ["configure", "move", "resume", "disconnect"] }))),
      resume: vi.fn(async () => ok(page())),
      disconnect: vi.fn(),
    },
    ...over,
  };
  const rendered = render(
    <LocaleProvider locale="es">
      <ChannelConfigPage refId={REF} agentId={RECEPCION} page={p} history={HISTORY} canWrite={canWrite} balanceHref={balanceHref} actions={actions} />
    </LocaleProvider>,
  );
  return { ...rendered, actions };
}

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
  router.replace.mockClear();
});

describe("la página de un canal", () => {
  it("tiene sus cinco secciones, el estado visible y los disparadores del agente en solo lectura", async () => {
    const { container } = view();
    expect(screen.getByRole("heading", { level: 2, name: "Canal +34 611 20 48 93" })).toBeVisible();
    for (const name of ["A quién responde", "Excepciones", "Escalado a personas", "Mensaje de espera", "Comprobaciones", "Historial"]) {
      expect(screen.getByRole("region", { name })).toBeVisible();
    }
    expect(screen.getAllByText("Solo mi equipo")[0]).toBeVisible();
    expect(screen.getByRole("link", { name: "Lo atiende Recepción" })).toHaveAttribute("href", `/clients/${REF}/agents/${RECEPCION}`);
    expect(screen.getByText(/saldrán del número de avisos de Auphere/)).toBeVisible();
    const triggers = container.querySelector("[data-slot=channel-triggers]") as HTMLElement;
    expect(within(triggers).getByText("Cuando pide hablar con una persona")).toBeVisible();
    expect(within(triggers).getByText("Si pide factura")).toBeVisible();
    expect(within(triggers).getByRole("link", { name: "Cambiarlo en el agente" })).toHaveAttribute("href", `/clients/${REF}/agents/${RECEPCION}#bloque-escalation`);
    expect(screen.getByText("Todo guardado.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("los avisos saldrán de este número si tiene la plantilla aprobada (33.3)", () => {
    view(page({ config: { ...page().config, notify_from: "channel" } }));
    expect(screen.getByText("Los avisos por WhatsApp saldrán de este número.")).toBeVisible();
  });

  it("guarda la configuración entera con la revisión leída, en E.164", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    const exceptions = screen.getByRole("region", { name: "Excepciones" });
    await user.type(within(exceptions).getByRole("textbox", { name: /Número nuevo/ }), "+56 9 1234 5678");
    await user.click(within(exceptions).getByRole("button", { name: "Añadir a Excepciones" }));
    expect(within(exceptions).getByRole("list", { name: "Excepciones" })).toHaveTextContent("+56912345678");
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    expect(screen.getByText("Tienes cambios sin guardar.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(actions.save).toHaveBeenCalledWith({
      ref: REF,
      channel: CH,
      revision: 3,
      config: {
        audience: { mode: "everyone", test_numbers: ["+34611204893"], exceptions: ["+56912345678"] },
        escalation: { summary: true, recipients: [{ name: "Marta", via: "whatsapp", phone_e164: "+34600000009" }] },
        wait_message: null,
      },
    });
    expect(toast.success).toHaveBeenCalledWith("Guardado. Vale desde el siguiente mensaje.");
    expect(await screen.findByRole("button", { name: "Deshacer el último cambio" })).toBeVisible();
    expect(actions.history).toHaveBeenCalled();
  });

  it("un número mal escrito o repetido no entra en la lista (32.4)", async () => {
    const user = userEvent.setup();
    view();
    const audience = screen.getByRole("region", { name: "A quién responde" });
    const field = within(audience).getByRole("textbox", { name: /Número nuevo/ });
    await user.type(field, "611 20 48");
    await user.click(within(audience).getByRole("button", { name: "Añadir a Números de prueba" }));
    expect(within(audience).getByText(/«611 20 48» no es un número válido/)).toBeVisible();
    await user.clear(field);
    await user.type(field, "+34 611 20 48 93");
    await user.click(within(audience).getByRole("button", { name: "Añadir a Números de prueba" }));
    expect(within(audience).getByText("Ese número ya está en la lista.")).toBeVisible();
  });

  it("«Solo mi equipo» sin números de prueba se dice antes de mandar", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("button", { name: "Quitar +34611204893" }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(screen.getByText("«Solo mi equipo» necesita al menos un número de prueba.")).toBeVisible();
    expect(actions.save).not.toHaveBeenCalled();
  });

  it("«A todos» sin agente guardado lo dice con su arreglo: guardar el agente", async () => {
    const user = userEvent.setup();
    view(page(), { save: vi.fn(async () => fail(409, "agent_not_published", { fix: "publish_agent", blocking: ["agent_not_published"] })) });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    const error = await screen.findByText(/«A todos» necesita el agente guardado/);
    expect(within(error).getByRole("link", { name: "Guardar el agente" })).toHaveAttribute("href", `/clients/${REF}/agents/${RECEPCION}`);
  });

  it("sin saldo: «Asignar saldo» si se puede, y si no, solo la frase", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async () => fail(409, "bag_empty", { fix: "assign_balance" }));
    const { unmount } = view(page(), { save }, { balanceHref: `/usage?client=${REF}&assign=1` });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByRole("link", { name: "Asignar saldo" })).toHaveAttribute("href", `/usage?client=${REF}&assign=1`);
    unmount();
    view(page(), { save });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(/Pide a quien gestiona el saldo/)).toBeVisible();
    expect(screen.queryByRole("link", { name: "Asignar saldo" })).toBeNull();
  });

  it("un número que la API no acepta dice cuál", async () => {
    const user = userEvent.setup();
    view(page(), { save: vi.fn(async () => fail(422, "invalid_phone", { value: "+3460" })) });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(/«\+3460» no es un número válido/)).toBeVisible();
  });

  it("con plantilla de solo administradores, «A todos» no se ofrece y se dice por qué (32.5)", () => {
    view(page({ admin_only_template: true }));
    expect(screen.queryByRole("radio", { name: /A todos/ })).toBeNull();
    expect(screen.getByText(/«A todos» no se puede elegir: este agente viene de una plantilla solo para administradores/)).toBeVisible();
  });

  it("si otra persona guardó antes, dice qué cambió y deja elegir (412)", async () => {
    const user = userEvent.setup();
    const save = vi.fn().mockResolvedValueOnce(fail(412, "revision_conflict", { current: 5, changes: ["wait_message"] })).mockResolvedValue(ok(page({ revision: 6 })));
    const { actions } = view(page(), { save });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Alguien guardó antes que tú")).toBeVisible();
    expect(screen.getByText(/Mientras editabas cambió el mensaje de espera/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Guardar los míos encima" }));
    expect(save).toHaveBeenLastCalledWith(expect.objectContaining({ revision: 5 }));
    expect(actions.reload).not.toHaveBeenCalled();
  });

  it("«Ver lo que hay ahora» descarta lo mío y lee lo de ahora", async () => {
    const user = userEvent.setup();
    const { actions } = view(page(), { save: vi.fn(async () => fail(412, "revision_conflict", { current: 5, changes: [] })) });
    await user.click(screen.getByRole("radio", { name: /A todos/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    await user.click(await screen.findByRole("button", { name: "Ver lo que hay ahora" }));
    expect(actions.reload).toHaveBeenCalledWith({ ref: REF, channel: CH });
    await waitFor(() => expect(screen.getByRole("textbox", { name: /Mensaje/ })).toHaveValue("Ya vamos"));
    expect(screen.getByRole("radio", { name: /Solo mi equipo/ })).toBeChecked();
  });

  it("deshacer durante 10 minutos, y pasado el plazo lo dice", async () => {
    const user = userEvent.setup();
    const undo = vi.fn().mockResolvedValueOnce(ok(page({ revision: 5 }))).mockResolvedValueOnce(fail(409, "undo_window_closed"));
    const open = page({ undo_until: new Date(Date.now() + 300_000).toISOString() });
    const { actions } = view(open, { undo, reload: vi.fn(async () => ok(open)) });
    expect(screen.getByText(/Se puede deshacer hasta las/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Deshacer el último cambio" }));
    expect(actions.undo).toHaveBeenCalledWith({ ref: REF, channel: CH });
    expect(toast.success).toHaveBeenCalledWith("Cambio deshecho.");
    expect(screen.queryByRole("button", { name: "Deshacer el último cambio" })).toBeNull();
  });

  it("el escalado admite hasta 10 personas, cada una con su vía", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    const escalation = screen.getByRole("region", { name: "Escalado a personas" });
    await user.click(within(escalation).getByRole("button", { name: "Añadir persona" }));
    const second = within(escalation).getByRole("group", { name: "Persona 2" });
    await user.type(within(second).getByRole("textbox", { name: /Nombre/ }), "Recepción");
    await user.selectOptions(within(second).getByRole("combobox", { name: "Por dónde" }), "inbox");
    expect(within(second).getByText(/Avisa en la Bandeja a todas las personas del cliente/)).toBeVisible();
    await user.click(within(escalation).getByRole("checkbox", { name: /Incluir un resumen/ }));
    await user.click(screen.getByRole("button", { name: "Guardar" }));
    expect(actions.save).toHaveBeenCalledWith(
      expect.objectContaining({
        config: expect.objectContaining({
          escalation: {
            summary: false,
            recipients: [
              { name: "Marta", via: "whatsapp", phone_e164: "+34600000009" },
              { name: "Recepción", via: "inbox", client_user_id: null },
            ],
          },
        }),
      }),
    );
    const ten = Array.from({ length: 10 }, (_, i) => ({ name: `P${i}`, via: "inbox", client_user_id: null }));
    view(page({ config: { ...page().config, escalation: { recipients: ten, summary: true } } }));
    expect(screen.getAllByText("Como mucho 10 personas.")[0]).toBeVisible();
  });

  it("las comprobaciones avisan, y las que impiden «A todos» llevan su arreglo", () => {
    view(
      page({
        checks: [
          { code: "tests_up_to_date", ok: false, level: "warn", fix: "run_tests" },
          { code: "escalation_recipient", ok: false, level: "warn", fix: "add_recipient" },
          { code: "agent_not_published", ok: false, level: "block", fix: "publish_agent" },
        ],
      }),
    );
    const checks = screen.getByRole("list", { name: "Comprobaciones" });
    expect(within(checks).getByRole("link", { name: "Ir a las pruebas" })).toHaveAttribute("href", `/clients/${REF}/agents/${RECEPCION}#agente-pruebas`);
    expect(within(checks).getByRole("link", { name: "Añadir a alguien" })).toHaveAttribute("href", "#canal-escalado");
    expect(within(checks).getByText(/El agente no está guardado/)).toBeVisible();
    expect(within(checks).getByText("Impide «A todos»:")).toBeInTheDocument();
  });

  it("el historial enseña quién, cuándo, el antes y el después", () => {
    view();
    const history = screen.getByRole("list", { name: "Historial" });
    expect(within(history).getByText("A quién responde: Todavía a nadie → Solo mi equipo")).toBeVisible();
    expect(within(history).getByText("Al conectar")).toBeVisible();
    expect(within(history).getAllByText(/luis@ladrian.studio/)[0]).toBeVisible();
  });

  it("su ⋯ no repite «Configuración», y pasar el número lleva a su nuevo agente", async () => {
    const user = userEvent.setup();
    const { actions } = view();
    await user.click(screen.getByRole("button", { name: "Más acciones de +34 611 20 48 93" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual(["Pasar a otro agente", "Pausar este canal", "Desconectar"]);
    await user.click(within(menu).getByRole("menuitem", { name: "Pasar a otro agente" }));
    const dialog = await screen.findByRole("dialog", { name: "Pasar +34 611 20 48 93 a otro agente" });
    expect(within(dialog).getByRole("radio", { name: "Ventas" })).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Pasar el número" }));
    expect(actions.menu!.move).toHaveBeenCalledWith({ ref: REF, channel: CH, to: VENTAS });
    expect(router.replace).toHaveBeenCalledWith(`/clients/${REF}/agents/${VENTAS}/channels/${CH}`);
  });

  it("quien solo lee lo ve todo como texto, sin campos ni botones (§V)", () => {
    view(page({ allowed: [] }), {}, { canWrite: false });
    expect(screen.getByText("Tu rol solo permite ver esta configuración.")).toBeVisible();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Marta")).toBeVisible();
    expect(screen.getByText("+34611204893")).toBeVisible();
  });
});
