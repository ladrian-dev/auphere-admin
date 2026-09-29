import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import { messages } from "@/i18n/messages";
import type { ChannelDetail } from "@/lib/backend/channels";

import { ChannelCard, tierKey } from "../channel-card";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  setChannelRoleAction: vi.fn(),
  disconnectChannelAction: vi.fn(),
}));

const CANAL: ChannelDetail = {
  id: "9f1b4e8a-6f3c-4c2a-9a6d-2f7e5c1b3d40",
  type: "whatsapp",
  provider_identifier: "+34653321693",
  status: "active",
  role: null,
  verified_name: "Auphere",
  quality_rating: "GREEN",
  messaging_tier: "TIER_250",
  mode: "coexistence",
  last_health_check_at: "2026-09-29T14:08:00Z",
  created_at: "2026-09-23T20:27:00Z",
} as ChannelDetail;

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
    // prometa de más**: el endpoint deja la fila y la marca
    // `disconnected`, así que reconectar funciona; y no toca nada en Meta,
    // así que el aviso tiene que decirlo en vez de insinuar que lo deshizo
    // todo. El recorrido con el menú abierto es del e2e, y necesita un
    // número conectado de verdad.
    expect(messages["ch.disconnect.body"].es).toMatch(/volver a conectarlo/i);
    expect(messages["ch.disconnect.body"].es).toMatch(/sigue registrado en Meta/i);
    expect(messages["ch.disconnect.body"].en).toMatch(/connect it again/i);
    expect(messages["ch.disconnect.body"].en).toMatch(/stays registered with Meta/i);
  });
});
