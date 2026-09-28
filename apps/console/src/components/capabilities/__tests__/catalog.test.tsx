import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";
import type { Capability, CapabilitiesOut, CapabilityFunction } from "@/lib/backend/capabilities";

import { CapabilitiesCatalog } from "../catalog";

/**
 * Capacidades (spec 017, R5): una pantalla donde antes había dos.
 *
 * Lo que estos tests fijan no es que los componentes rendericen, sino las
 * decisiones que se tomaron y que serían fáciles de perder en una refactor:
 * que un clic ya guarda (no hay botón «Guardar»), que quien no puede
 * escribir no ve un control muerto, que «Requiere aprobación» no vuelve por
 * la puerta de atrás, y que a una capacidad sin su integración se la puede
 * encender igual — la decisión del owner del 2026-09-26, que es justo la
 * contraria de lo que la tarea T036 pedía cuando se escribió.
 */

const refresh = vi.fn();
// `useSearchParams`: desde la spec 018 la pantalla lee de la dirección qué
// se busca, qué pestaña está puesta y por qué categoría se filtra.
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn(), replace }),
  useSearchParams: () => new URLSearchParams(),
}));

const setCapabilityAction = vi.fn();
vi.mock("@/app/(console)/clients/[ref]/capabilities/actions", () => ({
  setCapabilityAction: (...args: unknown[]) => setCapabilityAction(...args),
}));

const toast = { success: vi.fn(), error: vi.fn() };
vi.mock("sonner", () => ({ toast: { success: (m: string) => toast.success(m), error: (m: string) => toast.error(m) } }));

function cap(over: Partial<Capability> & { key: string }): Capability {
  return {
    kind: "tool",
    business_name: over.key,
    description: "",
    function: "other",
    sectors: [],
    recommended: false,
    other_sector: false,
    enabled: false,
    enabled_in_active: false,
    usable: true,
    activatable: true,
    connector: null,
    mode: null,
    read_only: false,
    destructive: false,
    technical: { name: over.key, kind: over.kind ?? "tool", version: null, tags: [] },
    ...over,
  };
}

const reservar = cap({
  key: "booking.create_appointment",
  business_name: "Reservar una cita",
  description: "Deja la cita puesta en la agenda del negocio.",
  function: "appointments",
  recommended: true,
  mode: { default: "always", override: null, effective: "always", options: ["always", "blocked"] },
});
const pedidos = cap({
  key: "woocommerce.list_orders",
  business_name: "Consultar un pedido",
  description: "Dice en qué punto va un pedido.",
  function: "orders",
  connector: { slug: "woocommerce", display_name: "WooCommerce", status: "none" },
  enabled: true,
  usable: false,
});
const escalar = cap({
  key: "escalation-policy",
  kind: "skill",
  business_name: "Avisar a una persona",
  description: "Pasa la conversación a alguien del negocio.",
  function: "escalation",
  technical: { name: "escalation-policy", kind: "skill", version: "1.2.0", tags: [] },
});

function out(over: Partial<CapabilitiesOut> = {}): CapabilitiesOut {
  const groups = over.groups ?? [
    { function: "appointments" as CapabilityFunction, items: [reservar] },
    { function: "orders" as CapabilityFunction, items: [pedidos] },
    { function: "escalation" as CapabilityFunction, items: [escalar] },
  ];
  return { sector: "barbershop", has_draft: false, version: 2, active_version: 1, hidden_by_sector: 0, ...over, groups };
}

function mount(data: CapabilitiesOut = out(), canWrite = true) {
  return render(
    <LocaleProvider locale="es">
      <CapabilitiesCatalog
        refId="demo"
        data={data}
        canWrite={canWrite}
        seeAllHref="/clients/demo/capabilities?all=1"
        seeOwnHref="/clients/demo/capabilities"
      />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setCapabilityAction.mockResolvedValue({ ok: true, data: {} });
});

describe("Capacidades · agrupación y sector", () => {
  it("agrupa por lo que el negocio quiere conseguir, no por herramienta o habilidad", () => {
    mount();
    // Los encabezados son los de la función, en el orden en que se leen.
    const titulos = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(titulos).toEqual(["Citas", "Pedidos", "Escalado"]);
    // Y una habilidad convive con las herramientas sin anunciarse como otra cosa.
    expect(screen.getByText("Avisar a una persona")).toBeInTheDocument();
    expect(screen.getByText("Reservar una cita")).toBeInTheDocument();
  });

  it("dice cuántas esconde el sector y ofrece verlas, con un enlace compartible", () => {
    mount(out({ hidden_by_sector: 7 }));
    expect(screen.getByText(/7 habilidades son de otros sectores/)).toBeInTheDocument();
    const verTodas = screen.getByRole("link", { name: "Ver todas" });
    // Viaja en la URL, no en estado del cliente: así se puede compartir y
    // volver atrás hace lo que el partner espera.
    expect(verTodas).toHaveAttribute("href", "/clients/demo/capabilities?all=1");
  });

  it("una sola escondida se dice en singular", () => {
    mount(out({ hidden_by_sector: 1 }));
    expect(screen.getByText(/1 habilidad es de otro sector/)).toBeInTheDocument();
  });

  it("sin sector no filtra nada y lo explica en vez de callarse", () => {
    mount(out({ sector: null }));
    expect(screen.getByText(/no tiene sector, así que se ven todas/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ver todas" })).toBeNull();
  });

  it("viendo todas, ofrece volver a las de su sector", () => {
    mount(out({ hidden_by_sector: 0 }));
    expect(screen.getByRole("link", { name: "Ver solo las de este sector" })).toHaveAttribute(
      "href",
      "/clients/demo/capabilities",
    );
  });
});

describe("Capacidades · buscador", () => {
  it("filtra por el nombre de negocio y por la descripción, y cuenta lo que queda", () => {
    mount();
    // Desde la spec 018 el buscador, el contador y los carteles son los del
    // patrón compartido: las mismas palabras que en Conectores y en Canales.
    // Y el contador dice **de cuántos** quedan los que se ven; «1» a secas no
    // decía si sobraban veinte o ninguno.
    expect(screen.getByText("3 de 3 · 1 activos")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Buscar en la lista"), { target: { value: "cita" } });
    expect(screen.getByText("Reservar una cita")).toBeInTheDocument();
    expect(screen.queryByText("Consultar un pedido")).toBeNull();
    // Los grupos vacíos desaparecen con lo que contenían.
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Citas"]);
    expect(screen.getByText("1 de 3 · 0 activos")).toBeInTheDocument();

    // También busca en la descripción, no solo en el título.
    fireEvent.change(screen.getByLabelText("Buscar en la lista"), { target: { value: "agenda" } });
    expect(screen.getByText("Reservar una cita")).toBeInTheDocument();
  });

  it("sin resultados dice con qué se filtró y deja salir", () => {
    mount();
    fireEvent.change(screen.getByLabelText("Buscar en la lista"), { target: { value: "zzz" } });
    expect(screen.getByText("Nada coincide con lo que buscas")).toBeInTheDocument();
    // La palabra buscada sigue estando: lo que cambia es que ahora la frase
    // nombra **todos** los filtros puestos, no solo el buscador (R4.3).
    expect(screen.getByText(/buscando «zzz»/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Quitar los filtros" }));
    expect(screen.getByText("Reservar una cita")).toBeInTheDocument();
  });
});

describe("Capacidades · un clic guarda", () => {
  it("el conmutador guarda al soltarlo: una llamada, y ningún botón «Guardar»", async () => {
    mount();
    // No hay botón de guardar en ninguna parte: si lo hubiera, el conmutador
    // mentiría diciendo que ya está hecho.
    expect(screen.queryByRole("button", { name: /Guardar/i })).toBeNull();

    const conmutadores = screen.getAllByRole("switch");
    fireEvent.click(conmutadores[0]!);

    await waitFor(() => expect(setCapabilityAction).toHaveBeenCalledTimes(1));
    expect(setCapabilityAction).toHaveBeenCalledWith({
      ref: "demo",
      key: "booking.create_appointment",
      kind: "tool",
      enabled: true,
    });
    expect(toast.success).toHaveBeenCalledWith("Guardado en el borrador.");
  });

  it("si el guardado falla, el conmutador vuelve a donde estaba", async () => {
    setCapabilityAction.mockResolvedValue({ ok: false, status: 500, message: "boom" });
    mount();
    const conmutador = screen.getAllByRole("switch")[0]!;
    expect(conmutador).toHaveAttribute("aria-checked", "false");

    fireEvent.click(conmutador);
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    // No se queda encendido celebrando algo que no ocurrió.
    expect(conmutador).toHaveAttribute("aria-checked", "false");
  });

  it("el lote llama una vez por capacidad, y solo por las que cambian", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Encender las visibles" }));

    // Tres visibles, una ya encendida: dos llamadas, no tres.
    await waitFor(() => expect(setCapabilityAction).toHaveBeenCalledTimes(2));
    const claves = setCapabilityAction.mock.calls.map((c) => c[0].key);
    expect(claves).toEqual(["booking.create_appointment", "escalation-policy"]);
    expect(claves).not.toContain("woocommerce.list_orders");
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("el lote se detiene en el primer fallo en vez de insistir", async () => {
    setCapabilityAction.mockResolvedValue({ ok: false, status: 500, message: "boom" });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Encender las visibles" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    expect(setCapabilityAction).toHaveBeenCalledTimes(1);
  });
});

describe("Capacidades · lo que le falta para funcionar", () => {
  it("una capacidad sin su integración se puede encender igual, y se dice qué falta", () => {
    mount();
    // Decisión del owner (2026-09-26): avisar, no bloquear. Encenderla es
    // decir «la quiero». T036 pedía lo contrario (tarjeta sin conmutador) y
    // esa parte de la tarea quedó fuera a propósito.
    expect(screen.getByText("Necesita WooCommerce para funcionar.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Conectarlo" })[0]).toHaveAttribute(
      "href",
      "/clients/demo/integrations",
    );
    expect(screen.getAllByRole("switch")).toHaveLength(3);
  });

  it("una habilidad que Auphere no ha publicado dice de quién depende, y no finge un control", () => {
    // Paridad fila 57. Aquí NO vale «avisar y dejar encender»: con una
    // integración que falta, encenderla es una decisión que se cumple al
    // conectarla; aquí no hay `skill_id` que escribir hasta que la subamos,
    // así que un conmutador siempre fallaría.
    const sinPublicar = { ...escalar, activatable: false, usable: false };
    mount(out({ groups: [{ function: "escalation", items: [sinPublicar] }] }));

    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.getByText("Aún no disponible")).toBeInTheDocument();
    expect(screen.getByText(/No depende de ti/)).toBeInTheDocument();
    // Y no se cuela el texto viejo, que mandaba a buscar el problema en la
    // configuración del cliente.
    expect(screen.queryByText(/requiere una herramienta o canal/i)).toBeNull();
  });

  it("el bloque de integraciones dice cuántas desbloquea cada una y no duplica su pestaña", () => {
    mount();
    expect(screen.getByText(/Falta un conector/)).toBeInTheDocument();
    expect(screen.getByText("desbloquea 1 de las que ves")).toBeInTheDocument();
    // Pausar, desconectar y sincronizar viven solo en Integraciones: hacerlo
    // desde aquí rompería en silencio lo que se está mirando.
    expect(screen.getByText(/Pausar, desconectar o sincronizar se hace en Conectores/)).toBeInTheDocument();
    for (const nombre of ["Sincronizar", "Desconectar", "Pausar"]) {
      expect(screen.queryByRole("button", { name: nombre })).toBeNull();
    }
  });

  it("si todo está conectado, el bloque no ocupa sitio", () => {
    const conectado = { ...pedidos, connector: { slug: "woocommerce", display_name: "WooCommerce", status: "connected" }, usable: true };
    mount(out({ groups: [{ function: "orders", items: [conectado] }] }));
    expect(screen.queryByText(/Falta un conector/)).toBeNull();
    expect(screen.queryByText(/Necesita WooCommerce/)).toBeNull();
  });
});

describe("Capacidades · modo y detalle técnico", () => {
  it("«Requiere aprobación» no se puede ni pedir: solo Siempre y Nunca", () => {
    mount();
    const select = screen.getByLabelText("Cuándo la usa") as HTMLSelectElement;
    const opciones = [...select.options].map((o) => o.textContent);
    expect(opciones).toEqual(["Por defecto (Siempre)", "Siempre", "Nunca"]);
    expect(opciones.join(" ")).not.toMatch(/aprobaci/i);
  });

  it("cambiar el modo guarda solo el modo", async () => {
    mount();
    fireEvent.change(screen.getByLabelText("Cuándo la usa"), { target: { value: "blocked" } });
    await waitFor(() => expect(setCapabilityAction).toHaveBeenCalledTimes(1));
    expect(setCapabilityAction).toHaveBeenCalledWith({
      ref: "demo",
      key: "booking.create_appointment",
      kind: "tool",
      mode: "blocked",
    });
  });

  it("volver a «Por defecto» pide borrar lo fijado, no guardar el defecto", async () => {
    // Paridad fila 35. Guardar el valor por defecto como override dejaba la
    // ayuda «Lo has fijado tú» puesta para siempre: la elección se volvía
    // irreversible desde la propia pantalla que la ofrecía.
    const fijada = {
      ...reservar,
      mode: { default: "always" as const, override: "blocked" as const, effective: "blocked" as const, options: ["always", "blocked"] as const },
    };
    mount(out({ groups: [{ function: "appointments", items: [fijada as never] }] }));

    // Con override hay dos cosas con esa etiqueta: el selector y la ayuda
    // que explica que lo fijaste tú. Aquí se quiere el selector.
    const selector = screen.getByLabelText("Cuándo la usa", { selector: "select" });
    fireEvent.change(selector, { target: { value: "__default" } });
    await waitFor(() => expect(setCapabilityAction).toHaveBeenCalledTimes(1));
    expect(setCapabilityAction).toHaveBeenCalledWith({
      ref: "demo",
      key: "booking.create_appointment",
      kind: "tool",
      mode: "default",
    });
    expect(setCapabilityAction.mock.calls[0]![0].mode).not.toBe("always");
  });

  it("una habilidad no inventa un modo vacío para que la tabla quede simétrica", () => {
    mount(out({ groups: [{ function: "escalation", items: [escalar] }] }));
    expect(screen.queryByLabelText("Cuándo la usa")).toBeNull();
  });

  it("el nombre interno existe pero llega plegado, sin competir con el del negocio", () => {
    mount(out({ groups: [{ function: "escalation", items: [escalar] }] }));
    const detalle = document.querySelector("details");
    expect(detalle).not.toBeNull();
    expect((detalle as HTMLDetailsElement).open).toBe(false);
    expect(screen.getByText("Detalle técnico")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Detalle técnico"));
    expect(screen.getByText("escalation-policy")).toBeInTheDocument();
    // «Skill» y no «Habilidad»: la pantalla entera se llama Habilidades desde
    // el 2026-09-28, así que el detalle técnico usa el nombre interno — que
    // es de lo que va ese bloque— en vez de repetir el de la pantalla.
    expect(screen.getByText("Skill")).toBeInTheDocument();
    expect(screen.getByText("1.2.0")).toBeInTheDocument();
  });

  it("las insignias dicen el estado de publicación sin que haya que ir a otra pestaña", () => {
    const enViva = { ...reservar, enabled: true, enabled_in_active: true };
    const sinPublicar = { ...escalar, enabled: true };
    mount(out({ groups: [{ function: "appointments", items: [enViva] }, { function: "escalation", items: [sinPublicar] }] }));
    expect(screen.getByText("En la versión activa")).toBeInTheDocument();
    expect(screen.getByText("Aún no publicada")).toBeInTheDocument();
    expect(screen.getByText("Recomendada para tu sector")).toBeInTheDocument();
  });
});

describe("Capacidades · solo lectura", () => {
  it("quien no puede escribir no ve controles muertos, y el estado se lee igual", () => {
    mount(out(), false);
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Encender las visibles" })).toBeNull();
    expect(screen.queryByLabelText("Cuándo la usa")).toBeNull();
    expect(screen.getByText(/Tu rol permite ver las habilidades, no cambiarlas/)).toBeInTheDocument();
    // El estado sigue siendo legible: dos apagadas y la de pedidos encendida.
    expect(screen.getAllByText("Apagada")).toHaveLength(2);
    expect(screen.getByText("Encendida")).toBeInTheDocument();
  });

  it("sin catálogo, las integraciones siguen arriba en vez de esconderse con el vacío", () => {
    mount(out({ groups: [], hidden_by_sector: 0 }));
    expect(screen.getByText(/todavía no ha publicado habilidades/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Encender las visibles" })).toBeNull();
  });
});
