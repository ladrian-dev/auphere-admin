import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { TemplateComposer } from "../template-composer";

const createTemplateAction = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/app/(console)/clients/[ref]/channels/actions", () => ({
  createTemplateAction: (...args: unknown[]) => createTemplateAction(...args),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function mount() {
  return render(
    <LocaleProvider locale="es">
      <TemplateComposer refId="demo" open onOpenChange={vi.fn()} />
    </LocaleProvider>,
  );
}

const body = () => screen.getByLabelText("Texto del mensaje") as HTMLTextAreaElement;
const send = () => screen.getByRole("button", { name: "Enviar a Meta para revisión" });

describe("Nueva plantilla de WhatsApp", () => {
  it("explica para qué sirve cada categoría y empieza en Utilidad", () => {
    mount();
    const utility = screen.getByRole("radio", { name: /Utilidad/ });
    expect(utility).toHaveAttribute("aria-checked", "true");
    expect(utility).toHaveTextContent("Meta la aprueba antes y cuesta menos.");
    expect(screen.getByRole("radio", { name: /Marketing/ })).toHaveAttribute("aria-checked", "false");
  });

  it("convierte el nombre al formato de Meta mientras se escribe", () => {
    mount();
    const name = screen.getByLabelText("Nombre");
    fireEvent.change(name, { target: { value: "Aviso de Pago" } });
    expect(name).toHaveValue("aviso_de_pago");
  });

  it("dice qué falta en lugar de solo deshabilitar el botón", () => {
    mount();
    expect(send()).toBeDisabled();
    expect(screen.getByText("Falta el nombre, el texto del mensaje.")).toBeInTheDocument();
  });

  it("inserta una variable, pide su ejemplo y lo pinta en la vista previa", () => {
    mount();
    fireEvent.change(body(), { target: { value: "Hola , tu pedido sale hoy." } });
    body().setSelectionRange(5, 5);
    fireEvent.click(screen.getByRole("button", { name: "{{nombre}}" }));
    expect(body().value).toBe("Hola {{nombre}}, tu pedido sale hoy.");
    const example = screen.getByLabelText("Ejemplo de nombre");
    fireEvent.change(example, { target: { value: "Camila" } });
    const preview = screen.getByLabelText("Así lo verá el cliente");
    expect(preview).toHaveTextContent("Hola Camila, tu pedido sale hoy.");
  });

  it("avisa de lo que Meta rechaza en el texto, bajo el propio campo", () => {
    mount();
    fireEvent.change(body(), { target: { value: "{{nombre}}, tu pedido es el {{pedido}}" } });
    expect(screen.getByText(/no puede empezar con una variable/)).toBeInTheDocument();
    expect(screen.getByText(/no puede terminar con una variable/)).toBeInTheDocument();
  });

  it("envía el nombre limpio, el texto, los botones y un ejemplo por variable", async () => {
    createTemplateAction.mockReset();
    createTemplateAction.mockResolvedValue({ ok: true, data: { id: "T1", name: "aviso", status: "PENDING", category: "UTILITY" } });
    mount();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "aviso pago_" } });
    fireEvent.change(body(), { target: { value: "Hola {{nombre}}, recibimos tu pago." } });
    fireEvent.change(screen.getByLabelText("Ejemplo de nombre"), { target: { value: "Camila" } });
    fireEvent.click(screen.getByRole("button", { name: "Añadir botón" }));
    fireEvent.change(screen.getByLabelText("Texto del botón 1"), { target: { value: "Ver pedido" } });
    fireEvent.click(send());
    await waitFor(() => expect(createTemplateAction).toHaveBeenCalled());
    const sent = createTemplateAction.mock.calls[0]?.[0];
    expect(sent).toMatchObject({
      name: "aviso_pago",
      language: "es",
      category: "UTILITY",
      body_text: "Hola {{nombre}}, recibimos tu pago.",
      examples: { nombre: "Camila" },
      buttons: [{ type: "QUICK_REPLY", label: "Ver pedido" }],
    });
  });

  it("enseña el motivo de Meta dentro del diálogo cuando no la acepta", async () => {
    createTemplateAction.mockReset();
    createTemplateAction.mockResolvedValue({ ok: false, status: 400, message: "Meta rechazó la creación: nombre en uso." });
    mount();
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "aviso" } });
    fireEvent.change(body(), { target: { value: "Gracias por tu compra." } });
    fireEvent.click(send());
    expect(await screen.findByText("Meta no aceptó la plantilla")).toBeInTheDocument();
    expect(screen.getByText("Meta rechazó la creación: nombre en uso.")).toBeInTheDocument();
  });
});
