import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { AdMeasurement, ChannelPage } from "@/lib/backend/channel-config-types";

import { CH, RECEPCION, REF, fail, ok, page } from "./channel-fixtures";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/agents/channel-actions", () => ({}));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  listTemplatesAction: vi.fn(async () => ({ ok: true, data: { items: [], approved: 0, rejected: 0, pending: 0 } })),
}));

const { ChannelConfigPage } = await import("../channel-page");
type Actions = NonNullable<React.ComponentProps<typeof ChannelConfigPage>["actions"]>;

/**
 * Spec 076 (requisito 4; T042): la sección «Resultados en anuncios» de la
 * página de un número de WhatsApp. Solo existe si la API manda el bloque;
 * activar pide confirmar qué sale a Meta; sin el permiso de eventos pide
 * volver a conectar el número, con la configuración que eligió la API.
 */

const META = { appId: "APP", graphVersion: "v23.0", configIdCloudApi: "CFG-NORMAL", configIdCoexistence: "CFG-COEX" };

const measurement = (over: Partial<AdMeasurement> = {}): AdMeasurement => ({
  state: "off",
  enabled: false,
  dataset_linked: false,
  sent_7d: 0,
  last_error: null,
  reconnect_config_id: "CFG-EVENTS",
  ...over,
});

function view(
  p: ChannelPage,
  { adMeasurement = vi.fn(), reconnect = vi.fn(), canWrite = true, meta = META }: Partial<Pick<Actions, "adMeasurement" | "reconnect">> & { canWrite?: boolean; meta?: typeof META | null } = {},
) {
  const actions: Actions = {
    save: vi.fn(),
    undo: vi.fn(),
    reload: vi.fn(),
    history: vi.fn(async () => ok([])),
    adMeasurement,
    reconnect,
  };
  return render(
    <LocaleProvider locale="es">
      <ChannelConfigPage refId={REF} agentId={RECEPCION} page={p} history={[]} canWrite={canWrite} actions={actions} meta={meta} />
    </LocaleProvider>,
  );
}

const section = () => screen.getByRole("region", { name: "Resultados en anuncios" });

beforeEach(() => {
  toast.success.mockClear();
  toast.error.mockClear();
});

describe("los resultados en anuncios de un número", () => {
  it("sin el bloque no hay sección, ni en el índice", () => {
    view(page());
    expect(screen.queryByRole("region", { name: "Resultados en anuncios" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Resultados en anuncios" })).toBeNull();
  });

  it("activar pide confirmar qué sale a Meta, y sin marcarla no se activa; pasa axe", async () => {
    const user = userEvent.setup();
    const adMeasurement = vi.fn(async () => ok(measurement({ state: "on", enabled: true, dataset_linked: true })));
    const { container } = view(page({ ad_measurement: measurement() }), { adMeasurement });

    expect(within(section()).getByText("Desactivada")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resultados en anuncios" })).toHaveAttribute("href", "#canal-anuncios");
    expect(await axeViolations(container)).toEqual([]);

    await user.click(within(section()).getByRole("button", { name: "Activar" }));
    const dialog = await screen.findByRole("dialog", { name: "¿Enviar los resultados a Meta?" });
    expect(within(dialog).getByText(/el clic en el anuncio por el que llegó, o su teléfono cifrado/)).toBeInTheDocument();
    expect(within(dialog).getByText(/importe y su moneda/)).toBeInTheDocument();
    const confirm = within(dialog).getByRole("button", { name: "Activar" });
    expect(confirm).toBeDisabled();
    expect(adMeasurement).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("checkbox", { name: /puede compartir estos datos con Meta/ }));
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    expect(adMeasurement).toHaveBeenCalledWith({ ref: REF, channel: CH, enabled: true, confirm_data_sharing: true });
    expect(toast.success).toHaveBeenCalledWith("Los resultados de este número ya van a Meta.");
    expect(within(section()).getByText("Activada")).toBeInTheDocument();
    expect(within(section()).getByText("Vinculado")).toBeInTheDocument();
  });

  it("sin el permiso de eventos pide volver a conectar con la configuración de la API, y después confirmar", async () => {
    const user = userEvent.setup();
    const adMeasurement = vi.fn(async () => fail(409, "reauthorize"));
    const reconnect = vi.fn(async () => ({ ok: true as const, data: {} as never }));
    view(page({ ad_measurement: measurement() }), { adMeasurement, reconnect });

    await user.click(within(section()).getByRole("button", { name: "Activar" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("checkbox"));
    await user.click(within(dialog).getByRole("button", { name: "Activar" }));

    expect(await within(section()).findByText("Hay que volver a conectar el número")).toBeInTheDocument();
    expect(within(section()).getByText("Falta un permiso de Meta")).toBeInTheDocument();
    await user.click(within(section()).getByRole("button", { name: "Volver a conectar" }));

    expect(reconnect).toHaveBeenCalledWith(
      expect.objectContaining({
        refId: REF,
        mode: "cloud_api",
        meta: expect.objectContaining({ appId: "APP", configIdCloudApi: "CFG-EVENTS", configIdCoexistence: null }),
      }),
    );
    // Volver a conectar no enciende nada: se vuelve a pedir la confirmación.
    expect(await screen.findByRole("dialog", { name: "¿Enviar los resultados a Meta?" })).toBeInTheDocument();
    expect(adMeasurement).toHaveBeenCalledTimes(1);
  });

  it("la espera de Meta al volver a conectar se cancela, y lo que Meta mande tarde no cuenta (047 T101; 049 7.2)", async () => {
    const user = userEvent.setup();
    const seen: Array<{ signal?: AbortSignal; onMetaDone?: () => void }> = [];
    let late: (v: { ok: true; data: never }) => void = () => {};
    const reconnect = vi.fn((body: { signal?: AbortSignal; onMetaDone?: () => void }) => {
      seen.push(body);
      return new Promise<{ ok: true; data: never }>((resolve) => (late = resolve));
    });
    view(page({ ad_measurement: measurement({ state: "reauthorize", last_error: { code: "reauthorize", at: null, hint: "reauthorize" } }) }), {
      reconnect: reconnect as unknown as Actions["reconnect"],
    });

    await user.click(within(section()).getByRole("button", { name: "Volver a conectar" }));
    expect(await screen.findByText("Estamos en la ventana de Meta")).toBeInTheDocument();
    expect(seen[0]?.signal).toBeInstanceOf(AbortSignal);
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByText("Estamos en la ventana de Meta")).toBeNull();
    expect(seen[0]!.signal!.aborted).toBe(true);
    expect(within(section()).getByRole("button", { name: "Volver a conectar" })).toBeEnabled();

    late({ ok: true, data: {} as never });
    await new Promise((r) => setTimeout(r, 0));
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "¿Enviar los resultados a Meta?" })).toBeNull();
  });

  it("mientras se canjea el código de la reconexión, el velo ya no ofrece «Cancelar»", async () => {
    const user = userEvent.setup();
    const reconnect = vi.fn((body: { onMetaDone?: () => void }) => {
      body.onMetaDone?.();
      return new Promise<never>(() => {});
    });
    view(page({ ad_measurement: measurement({ state: "reauthorize", last_error: { code: "reauthorize", at: null, hint: "reauthorize" } }) }), {
      reconnect: reconnect as unknown as Actions["reconnect"],
    });
    await user.click(within(section()).getByRole("button", { name: "Volver a conectar" }));
    expect(await screen.findByText("Estamos en la ventana de Meta")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancelar" })).toBeNull();
  });

  it("sin las claves de Meta no ofrece volver a conectar, y dice quién tiene que hacerlo", () => {
    view(page({ ad_measurement: measurement({ state: "reauthorize", last_error: { code: "reauthorize", at: null, hint: "reauthorize" } }) }), {
      meta: null,
    });
    expect(within(section()).queryByRole("button", { name: "Volver a conectar" })).toBeNull();
    expect(within(section()).getByText(/tiene que volver a conectarlo/)).toBeInTheDocument();
  });

  it("con el número en pausa no ofrece volver a conectar, porque lo reanudaría: pide reanudarlo antes", () => {
    const reconnect = vi.fn();
    view(
      page({
        status: "paused",
        ad_measurement: measurement({ state: "reauthorize", enabled: true, last_error: { code: "reauthorize", at: null, hint: "reauthorize" } }),
      }),
      { reconnect },
    );
    expect(within(section()).queryByRole("button", { name: "Volver a conectar" })).toBeNull();
    expect(within(section()).getByText(/Reanuda el número y después vuelve a conectarlo/)).toBeInTheDocument();
    // Encendida con el permiso perdido: se puede desactivar.
    expect(within(section()).getByRole("button", { name: "Desactivar" })).toBeInTheDocument();
    expect(reconnect).not.toHaveBeenCalled();
  });

  it("encendida: lo enviado en 7 días, el último error con qué hacer, y desactivar", async () => {
    const user = userEvent.setup();
    const adMeasurement = vi.fn(async () => ok(measurement()));
    view(
      page({
        ad_measurement: measurement({
          state: "on",
          enabled: true,
          dataset_linked: true,
          sent_7d: 12,
          last_error: { code: "page_required", at: "2026-11-24T10:00:00Z", hint: "page_required" },
        }),
      }),
      { adMeasurement },
    );

    expect(within(section()).getByText("12")).toBeInTheDocument();
    expect(within(section()).getByText("El último envío a Meta falló")).toBeInTheDocument();
    expect(within(section()).getByText(/unida a una página de Facebook/)).toBeInTheDocument();

    await user.click(within(section()).getByRole("button", { name: "Desactivar" }));
    expect(adMeasurement).toHaveBeenCalledWith({ ref: REF, channel: CH, enabled: false, confirm_data_sharing: false });
    expect(toast.success).toHaveBeenCalledWith("Este número ya no envía resultados a Meta.");
    expect(within(section()).getByText("Desactivada")).toBeInTheDocument();
  });

  it("un error que la consola no conoce dice lo general, y sin error no hay aviso", () => {
    const { unmount } = view(
      page({ ad_measurement: measurement({ state: "on", enabled: true, last_error: { code: "meta_100", at: null, hint: "meta_100" } }) }),
    );
    expect(within(section()).getByText(/Meta rechazó un resultado/)).toBeInTheDocument();
    unmount();
    view(page({ ad_measurement: measurement({ state: "on", enabled: true }) }));
    expect(within(section()).queryByText("El último envío a Meta falló")).toBeNull();
  });

  it("quien solo lee ve el estado sin botones", () => {
    view(page({ ad_measurement: measurement({ state: "on", enabled: true, sent_7d: 3 }) }), { canWrite: false });
    expect(within(section()).getByText("Activada")).toBeInTheDocument();
    expect(within(section()).queryByRole("button")).toBeNull();
  });
});
