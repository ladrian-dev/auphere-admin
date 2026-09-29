import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { messages } from "@/i18n/messages";
import type { ChannelDetail } from "@/lib/backend/channels";

import { ChannelCard, disconnectBodyKey, tierKey } from "../channel-card";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
const disconnectChannelAction = vi.fn();
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  setChannelRoleAction: vi.fn(),
  disconnectChannelAction: (...args: unknown[]) => disconnectChannelAction(...args),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const CANAL: ChannelDetail = {
  logo_url: null,
  id: "9f1b4e8a-6f3c-4c2a-9a6d-2f7e5c1b3d40",
  type: "whatsapp",
  provider: "meta",
  agent_enabled: true,
  provider_identifier: "+34653321693",
  status: "active",
  role: null,
  verified_name: "Auphere",
  quality_rating: "GREEN",
  messaging_tier: "TIER_250",
  mode: "coexistence",
  unlink_pending: [],
  last_health_check_at: "2026-09-29T14:08:00Z",
  created_at: "2026-09-23T20:27:00Z",
};

function pintar(channel: Partial<ChannelDetail> = {}, manage = true) {
  return render(
    <LocaleProvider locale="es">
      <ul>
        <ChannelCard refId="demo" channel={{ ...CANAL, ...channel }} manage={manage} showRoles />
      </ul>
    </LocaleProvider>,
  );
}

describe("La tarjeta del canal dice lo que significa", () => {
  it("el límite de Meta se lee en conversaciones, no en «TIER_250»", () => {
    // `TIER_250` no dice ni que son conversaciones, ni que el límite es
    // diario, ni que solo cuenta iniciar. Las tres cosas hay que saberlas
    // para entender la cifra.
    pintar();
    expect(screen.getByText(/250 conversaciones nuevas al día/)).toBeInTheDocument();
    expect(screen.queryByText("TIER_250")).not.toBeInTheDocument();
  });

  it("un tier que Meta añada mañana no se inventa una traducción", () => {
    expect(tierKey("TIER_250")).toBe("ch.tier.TIER_250");
    expect(tierKey("TIER_NUEVO")).toBeNull();
    expect(tierKey(null)).toBeNull();
  });

  it("el número es la cabecera, porque es lo que el partner reconoce", () => {
    pintar();
    expect(screen.getByText("+34653321693")).toBeInTheDocument();
  });
});

describe("Desvincular un número (2026-09-29)", () => {
  it("se ofrece cuando se puede gestionar", () => {
    // Conectar era autoservicio y desconectar no existía **ni en la API**: el
    // partner que se equivocaba de número tenía que escribirnos.
    pintar();
    expect(screen.getByRole("button", { name: /Acciones de/ })).toBeInTheDocument();
  });

  it("quien solo mira no ve la acción", () => {
    pintar({}, false);
    expect(screen.queryByRole("button", { name: /Acciones de/ })).not.toBeInTheDocument();
  });

  it("un canal ya desvinculado no ofrece desvincularlo otra vez", () => {
    pintar({ status: "disconnected" });
    expect(screen.queryByRole("button", { name: /Acciones de/ })).not.toBeInTheDocument();
  });

  it("lo que el aviso promete es lo que la API hace", () => {
    // El menú de Base UI no se abre bajo jsdom —el disparador se queda en
    // `aria-expanded="false"`— y abrirlo de verdad pide un navegador. Lo que
    // sí se puede fijar aquí, y es lo que más importa, es **que el texto no
    // prometa ni de más ni de menos**: desde la spec 021 el endpoint da de
    // baja el número de nuestra aplicación en Meta, así que el aviso ya no
    // puede decir «sigue registrado en Meta» a secas; y sacarlo de la
    // cuenta del partner sigue sin ser cosa nuestra, así que lo dice.
    for (const key of ["ch.disconnect.body", "ch.disconnect.body.coexistence"] as const) {
      expect(messages[key].es).toMatch(/volver a conectarlo/i);
      expect(messages[key].es).toMatch(/de baja de nuestra aplicación/i);
      expect(messages[key].es).toMatch(/Business Manager/);
      expect(messages[key].es).not.toMatch(/sigue registrado en Meta/i);
      expect(messages[key].en).toMatch(/connect it again/i);
      expect(messages[key].en).toMatch(/deregister it from our application/i);
      expect(messages[key].en).not.toMatch(/stays registered with Meta/i);
    }
  });

  it("en coexistencia el aviso dice que el número seguirá chateando desde su teléfono", () => {
    // Desvincular es soltarlo de nosotros, no dejarlo sin WhatsApp (R2.5).
    // Sin esta frase, un partner en coexistencia dudaría en pulsar.
    expect(disconnectBodyKey("coexistence")).toBe("ch.disconnect.body.coexistence");
    expect(disconnectBodyKey("cloud_api")).toBe("ch.disconnect.body");
    expect(disconnectBodyKey(null)).toBe("ch.disconnect.body");
    expect(messages["ch.disconnect.body.coexistence"].es).toMatch(/seguirá chateando desde su teléfono/i);
    expect(messages["ch.disconnect.body"].es).not.toMatch(/teléfono/i);
  });
});

describe("Lo que quedó pendiente en Meta (spec 021, R3.2)", () => {
  it("con algo pendiente, la tarjeta dice qué falta y ofrece reintentar", () => {
    pintar({ status: "disconnected", unlink_pending: ["deregister", "unsubscribe"] });
    const aviso = screen.getByRole("alert");
    expect(aviso).toHaveTextContent("Falta terminar en Meta");
    expect(aviso).toHaveTextContent(/darlo de baja y desuscribir nuestra aplicación/);
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeEnabled();
  });

  it("sin nada pendiente, ni aviso ni reintento", () => {
    pintar({ status: "disconnected", unlink_pending: [] });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reintentar" })).toBeNull();
  });

  it("quien solo mira ve lo pendiente, pero no puede reintentar", () => {
    // Lo pendiente es estado del canal y se enseña a todos (constitución
    // §V); reintentar escribe, y escribir pide `channels:write`.
    pintar({ status: "disconnected", unlink_pending: ["unsubscribe"] }, false);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).toBeNull();
  });

  it("reintentar llama al mismo endpoint de desvincular", async () => {
    // Un solo verbo: el endpoint sabe qué quedó y no repite lo hecho.
    disconnectChannelAction.mockResolvedValueOnce({ ok: true, data: { ...CANAL, status: "disconnected", unlink_pending: [] } });
    pintar({ status: "disconnected", unlink_pending: ["unsubscribe"] });
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() => expect(disconnectChannelAction).toHaveBeenCalledWith({ ref: "demo", channelId: CANAL.id }));
  });

  it("un paso que la API añada mañana se enseña por su nombre, no se calla", () => {
    pintar({ status: "disconnected", unlink_pending: ["revoke_token"] });
    expect(screen.getByRole("alert")).toHaveTextContent("revoke_token");
  });
});

describe("Una sola insignia de estado (2026-09-29)", () => {
  it("«Activo» es la única pastilla: la calidad no es un estado del canal", () => {
    // La tarjeta desplegada tenía dos insignias idénticas —«Activo» y
    // «Alta»— una al lado de la otra, y se leían como dos estados de la
    // misma cosa. Solo una lo es: la otra la mide Meta.
    const { container } = pintar();
    const pastillas = container.querySelectorAll("[data-slot=status-badge]");
    expect(pastillas).toHaveLength(1);
    expect(pastillas[0]!.textContent).toContain("Activo");
    // La calidad sigue estando, y sigue teniendo color: punto y palabra.
    expect(screen.getByText("Alta")).toBeInTheDocument();
  });

  it("el icono de la aplicación se pide a nuestro origen, no al proveedor", () => {
    // `img-src 'self'` bloquea cualquier otro dominio: es el fallo que tenían
    // los conectores, y esta tarjeta lo habría repetido.
    const { container } = pintar({ logo_url: "https://upload.wikimedia.org/…/WhatsApp.svg" });
    const img = container.querySelector("[data-slot=channel-icon] img");
    expect(img?.getAttribute("src")).toBe("/api/channel-logo/demo/9f1b4e8a-6f3c-4c2a-9a6d-2f7e5c1b3d40");
  });

  it("sin logotipo en el catálogo, un icono en vez de un hueco gris", () => {
    const { container } = pintar({ logo_url: null });
    expect(container.querySelector("[data-slot=channel-icon] img")).toBeNull();
    expect(container.querySelector("[data-slot=channel-icon] svg")).not.toBeNull();
  });
});
