import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { ClientSummary } from "../client-summary";
import type { SummaryProps } from "../client-summary";

/**
 * El Resumen del cliente (spec 018, R1/R2).
 *
 * Lo que estos tests fijan es la decisión aprobada el 2026-09-27: el Resumen
 * contesta **cuatro preguntas**, no enseña todos los datos. Y las tres reglas
 * que lo hacen honesto — sin actividad no es cero, una lectura caída no tumba
 * la pantalla, y quien no puede escribir no ve controles muertos.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("@/app/(console)/clients/actions", () => ({ updateClientAction: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const CLIENTE: SummaryProps["client"] = {
  name: "Panadería La Espiga",
  timezone: "Europe/Madrid",
  status: "active",
  sector: "barbershop",
  health: { ready: true, agent_version: 3, whatsapp_connected: true, display_phone_number: "+34 600 123 456" },
  quota: { cap: 50_000, remaining: 31_400 },
};

function props(over: Partial<SummaryProps> = {}): SummaryProps {
  return {
    refId: "demo",
    role: "owner",
    client: CLIENTE,
    usage: { ok: true, data: { units: 18_600, projected: 17_778, basisDays: 27, daysInMonth: 30 } },
    conversations: { ok: true, data: { conversations: 128, escalated: 9, failed_messages: 2 } },
    connected: {
      ok: true,
      data: [
        { key: "woocommerce", name: "WooCommerce", status: "error", unlocks: 12 },
        { key: "whatsapp", name: "WhatsApp", status: "connected", detail: "+34 600 123 456" },
      ],
    },
    ...over,
  };
}

function mount(over: Partial<SummaryProps> = {}) {
  return render(
    <LocaleProvider locale="es">
      <ClientSummary {...props(over)} />
    </LocaleProvider>,
  );
}

describe("Resumen · las cuatro preguntas", () => {
  it("contesta las cuatro, cada una en su bloque", () => {
    mount();
    const titulos = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    // El orden cuenta una historia: quién es, cuánto gasta, cómo va la
    // conversación y con qué está conectado. Los datos van primero porque
    // son la identidad y porque son lo único que se edita aquí.
    expect(titulos).toEqual(["Datos del cliente", "Crédito y consumo", "Conversaciones", "Lo que tiene conectado"]);
    // Y el estado de atención es UNA línea dentro del primer bloque, no un
    // bloque propio: la cabecera y la tarjeta de pasos ya lo decían, y
    // decirlo tres veces es lo que hacía el Resumen confuso.
    const identidad = screen.getByRole("region", { name: "Datos del cliente" });
    expect(within(identidad).getByText(/Atendiendo|Sin atender/)).toBeInTheDocument();
  });

  it("cada cifra lleva a su detalle: la cifra responde, el clic explica", () => {
    mount();
    expect(screen.getByRole("link", { name: /Conversaciones/ })).toHaveAttribute("href", "/clients/demo/conversations");
    expect(screen.getByRole("link", { name: /Escaladas/ })).toHaveAttribute(
      "href",
      "/clients/demo/conversations?escalated=true",
    );
    expect(screen.getByRole("link", { name: /Mensajes fallidos/ })).toHaveAttribute(
      "href",
      "/clients/demo/conversations?with_errors=true",
    );
  });

  it("el crédito dice lo que queda, lo gastado y a qué ritmo acaba el mes", () => {
    mount();
    const bloque = screen.getByRole("region", { name: "Crédito y consumo" });
    // `getAllByText`: el medidor repite la cifra en su etiqueta accesible, y
    // que esté dos veces es correcto — lo que se afirma es que está.
    expect(within(bloque).getAllByText(/31\.400/).length).toBeGreaterThan(0);
    expect(within(bloque).getAllByText(/18\.600/).length).toBeGreaterThan(0);
    expect(within(bloque).getByText(/17\.778/)).toBeInTheDocument();
  });

  it("lo que necesita atención va primero, aunque llegue el segundo", () => {
    mount();
    const bloque = screen.getByRole("region", { name: "Lo que tiene conectado" });
    const nombres = within(bloque).getAllByRole("listitem").map((li) => li.textContent);
    expect(nombres[0]).toMatch(/WooCommerce/);
    expect(nombres[0]).toMatch(/desbloquea 12/);
  });
});

describe("Resumen · sin actividad no es cero", () => {
  it("un cliente recién creado dice que aún no hay datos, y no enseña ceros", () => {
    mount({
      conversations: { ok: true, data: { conversations: 0, escalated: 0, failed_messages: 0 } },
      usage: { ok: true, data: { units: 0, projected: 0, basisDays: 0, daysInMonth: 30 } },
    });
    const conv = screen.getByRole("region", { name: "Conversaciones" });
    expect(within(conv).getByText(/todavía no ha habido ninguna conversación/i)).toBeInTheDocument();
    // Un cero grande se lee como una caída, no como un cliente nuevo.
    expect(within(conv).queryByText("0")).toBeNull();

    const credito = screen.getByRole("region", { name: "Crédito y consumo" });
    expect(within(credito).getByText(/todavía no ha gastado nada/i)).toBeInTheDocument();
  });
});

describe("Resumen · una lectura caída no tumba la pantalla", () => {
  it("lo dice en su bloque, ofrece reintentar, y los demás siguen", () => {
    mount({ usage: { ok: false } });
    const credito = screen.getByRole("region", { name: "Crédito y consumo" });
    expect(within(credito).getByText(/no se pudo leer/i)).toBeInTheDocument();
    expect(within(credito).getByRole("button", { name: /reintentar/i })).toBeInTheDocument();

    // Las otras tres preguntas siguen contestadas.
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Lo que tiene conectado" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Datos del cliente" })).toBeInTheDocument();
  });

  it("si caen dos, caen dos: no se esconde una detrás de la otra", () => {
    mount({ usage: { ok: false }, connected: { ok: false } });
    expect(screen.getAllByText(/no se pudo leer/i)).toHaveLength(2);
    expect(screen.getByText("128")).toBeInTheDocument();
  });
});

describe("Resumen · lo que cada rol ve", () => {
  it("el analista lee las cifras y no ve un control que le diría que no", () => {
    mount({ role: "analyst" });
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Crédito y consumo" })).toBeInTheDocument();
    // Ni edición de datos, ni botones de escritura.
    expect(screen.queryByRole("textbox", { name: "Nombre" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Guardar" })).toBeNull();
    // Pero los datos se leen igual.
    expect(screen.getByText("Panadería La Espiga")).toBeInTheDocument();
    expect(screen.getByText("Europe/Madrid")).toBeInTheDocument();
  });

  it("sin permiso de conversaciones, el bloque no existe en vez de existir vacío", () => {
    mount({ conversations: null });
    expect(screen.queryByRole("region", { name: "Conversaciones" })).toBeNull();
    // Y el resto del Resumen sigue entero.
    expect(screen.getByRole("region", { name: "Crédito y consumo" })).toBeInTheDocument();
  });

  it("quien puede escribir edita nombre y zona horaria aquí mismo", () => {
    mount();
    // El formulario es el mismo que tenía la pestaña retirada: mismos campos
    // y misma validación, en su sitio nuevo. Eso es paridad, no rehacerlo.
    expect(screen.getByRole("textbox", { name: "Nombre" })).toHaveValue("Panadería La Espiga");
    // `combobox`, no `textbox`: la zona se elige de una lista desplegada
    // bajo el campo y se teclea para filtrarla. Ese rol ES la mejora — lo
    // que queda guardado sale de la lista, no de lo que alguien escriba.
    expect(screen.getByRole("combobox", { name: "Zona horaria" })).toHaveValue("Europe/Madrid");
    expect(screen.getByRole("button", { name: "Guardar" })).toBeInTheDocument();
    // Y la pantalla dice que esto NO crea un borrador, porque cambiar el
    // nombre del negocio no es cambiar lo que el agente hace.
    expect(screen.getByText(/no crea un borrador/i)).toBeInTheDocument();
  });
});

describe("Resumen · sin crédito", () => {
  it("lo dice donde está la cifra que lo explica, con la salida al lado", () => {
    mount({ client: { ...CLIENTE, quota: { cap: 50_000, remaining: 0 }, health: { ...CLIENTE.health, ready: false } } });
    const credito = screen.getByRole("region", { name: "Crédito y consumo" });
    expect(within(credito).getByText(/sin crédito/i)).toBeInTheDocument();
    expect(within(credito).getByRole("link", { name: /asignar más crédito/i })).toBeInTheDocument();
  });

  it("sin tope configurado lo dice, en vez de pintar una barra vacía", () => {
    mount({ client: { ...CLIENTE, quota: null } });
    const credito = screen.getByRole("region", { name: "Crédito y consumo" });
    expect(within(credito).getByText(/sin crédito asignado/i)).toBeInTheDocument();
    expect(within(credito).queryByRole("meter")).toBeNull();
  });
});

describe("Resumen · una integración con un estado que hay que nombrar (2026-09-29)", () => {
  it("«hay que volver a autorizar» se dice, y se marca como rota", () => {
    // La ficha entera cayó en staging —«No se pudieron cargar los
    // clientes»— porque el bloque pedía `connectors.status.needs_reauth`
    // sin que existiera. El estado es real (Meta caduca tokens) y merece
    // su frase, no un hueco.
    mount({ connected: { ok: true, data: [{ key: "meta", name: "WhatsApp Business", status: "needs_reauth" }] } });
    expect(screen.getByText("Hay que volver a autorizar")).toBeInTheDocument();
  });

  it("un estado que la API añada mañana no tumba la ficha", () => {
    mount({ connected: { ok: true, data: [{ key: "x", name: "Algo nuevo", status: "made_up_tomorrow" }] } });
    expect(screen.getByText("Algo nuevo")).toBeInTheDocument();
    expect(screen.getByText("No conectado")).toBeInTheDocument();
  });
});
