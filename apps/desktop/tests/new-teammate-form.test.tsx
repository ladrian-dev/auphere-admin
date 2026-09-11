// @vitest-environment jsdom
/**
 * Requisitos 2.1 y 12.5 — el formulario de crear teammate.
 *
 * Es el único sitio de la aplicación donde la persona **escribe** algo largo, y
 * por eso los cinco estados de Hurff no son ceremonia: si el fallo del envío
 * borra lo escrito, la persona vuelve a empezar; si el botón deja pulsar dos
 * veces, el partner acaba con dos teammates iguales y no sabe cuál usar.
 *
 * Lo que NO se prueba aquí porque no es de la pantalla: qué herramientas da
 * cada interruptor. Eso lo decide la API y se prueba en
 * `tests/integration/test_teammates_crud.py` — la pantalla solo manda los cinco
 * booleanos, y esa separación es la garantía 2.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { LangProvider } from "../src/app/i18n";
import { NewTeammateForm, type NewTeammateFormProps } from "../src/app/routes/new-teammate";

afterEach(cleanup);

const JOBS = [
  "Atención al cliente",
  "Ventas y CRM",
  "Investigación",
  "Desarrollo",
  "Finanzas",
  "Datos y reportes",
  "Documentos",
  "Operaciones",
];

const MODELS = [
  { id: "openai/gpt-5.6-sol", note: "Sol", cost_label: "bajo" as const },
  { id: "openai/gpt-5.6-terra", note: "Terra", cost_label: "alto" as const },
];

function paint(props: Partial<NewTeammateFormProps> = {}) {
  const onSubmit = vi.fn().mockResolvedValue({ ok: true });
  const onCancel = vi.fn();
  const onRetry = vi.fn();
  render(
    <LangProvider value="es">
      <NewTeammateForm
        status="ready"
        jobs={JOBS}
        models={MODELS}
        onSubmit={onSubmit}
        onCancel={onCancel}
        onRetry={onRetry}
        {...props}
      />
    </LangProvider>,
  );
  return { onSubmit, onCancel, onRetry };
}

const nameField = () => screen.getByLabelText(/nombre/i);
const createButton = () => screen.getByRole("button", { name: /crear teammate/i });

describe("el formulario de crear teammate", () => {
  it("nace vacío y no deja crear nada sin nombre", () => {
    paint();
    expect(nameField()).toHaveValue("");
    expect(createButton()).toBeDisabled();
  });

  it("no acepta un nombre más largo que la columna", async () => {
    // 80 es el límite de la base. Cortarlo aquí evita que la persona escriba un
    // formulario entero para que la plataforma lo rechace al final.
    const user = userEvent.setup();
    paint();
    await user.type(nameField(), "x".repeat(90));
    expect((nameField() as HTMLInputElement).value).toHaveLength(80);
  });

  it("ofrece los ocho oficios de la semilla y deja escribir otro", async () => {
    const user = userEvent.setup();
    paint();
    const job = screen.getByLabelText(/oficio/i);
    for (const seed of JOBS) {
      expect(screen.getByRole("option", { name: seed, hidden: true })).toBeInTheDocument();
    }
    await user.clear(job);
    await user.type(job, "Cobranzas");
    expect(job).toHaveValue("Cobranzas");
  });

  it("dice lo que gasta cada modelo, sin inventar un precio", () => {
    paint({
      models: [...MODELS, { id: "openai/gpt-5.6-luna", note: "Luna", cost_label: "desconocido" }],
    });
    // El coste va en el **nombre accesible** de cada opción, no suelto al lado:
    // quien navega con lector de pantalla oye «Sol, gasta poco» al elegir.
    expect(screen.getByRole("radio", { name: /Sol.*gasta poco/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Terra.*gasta más/i })).not.toBeChecked();
    // Un modelo sin tarifa cargada lo dice; poner «bajo» sería inventarlo.
    expect(screen.getByRole("radio", { name: /Luna.*no consta/i })).toBeInTheDocument();
  });

  it("empieza con lo mínimo encendido: leer sí, el resto no", () => {
    paint();
    expect(screen.getByRole("switch", { name: /leer/i })).toBeChecked();
    for (const perm of [/proponer cambios/i, /gastar/i, /publicar/i, /invitar/i]) {
      expect(screen.getByRole("switch", { name: perm })).not.toBeChecked();
    }
    expect(screen.getByRole("switch", { name: /ejecutar en tu máquina/i })).not.toBeChecked();
  });

  it("manda lo que la persona eligió y nada más", async () => {
    const user = userEvent.setup();
    const { onSubmit } = paint();
    await user.type(nameField(), "Sofía");
    await user.click(screen.getByRole("switch", { name: /proponer cambios/i }));
    await user.click(createButton());

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Sofía",
      job: JOBS[0],
      model: MODELS[0]!.id,
      permissions: { read: true, write: true, spend: false, publish: false, contact: false },
      local_exec: false,
    });
  });

  it("mientras envía, no se puede enviar otra vez", async () => {
    const user = userEvent.setup();
    let resolve: (v: { ok: true }) => void = () => {};
    const onSubmit = vi.fn().mockReturnValue(new Promise((r) => (resolve = r)));
    paint({ onSubmit });
    await user.type(nameField(), "Sofía");

    await user.click(createButton());
    expect(createButton()).toBeDisabled();
    await user.click(createButton()).catch(() => undefined);
    expect(onSubmit).toHaveBeenCalledTimes(1);

    resolve({ ok: true });
    await waitFor(() => expect(createButton()).not.toBeDisabled());
  });

  it("si falla, lo dice y conserva lo escrito", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue({ ok: false, error: "model_not_allowed" });
    paint({ onSubmit });
    await user.type(nameField(), "Sofía");
    await user.type(screen.getByLabelText(/oficio/i), " sénior");

    await user.click(createButton());

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent(/no está en la lista/i);
    expect(nameField()).toHaveValue("Sofía");
    expect(screen.getByLabelText(/oficio/i)).toHaveValue(`${JOBS[0]} sénior`);
    // Y se puede volver a intentar: el fallo no deja el botón muerto.
    expect(createButton()).not.toBeDisabled();
  });

  it("un error que no conocemos también se dice, sin código crudo", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue({ ok: false, error: "boom_desconocido" });
    paint({ onSubmit });
    await user.type(nameField(), "Sofía");
    await user.click(createButton());
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert")).not.toHaveTextContent("boom_desconocido");
  });

  it("mientras carga la lista de oficios no pinta un formulario a medias", () => {
    paint({ status: "loading", jobs: [], models: [] });
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("button", { name: /crear teammate/i })).not.toBeInTheDocument();
  });

  it("si no se pudo leer la lista, ofrece reintentar", async () => {
    const user = userEvent.setup();
    const { onRetry } = paint({ status: "error", jobs: [], models: [] });
    await user.click(screen.getByRole("button", { name: /reintentar/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("sin modelos que ofrecer no finge un formulario que no puede terminar", () => {
    paint({ models: [] });
    expect(screen.getByRole("status")).toHaveTextContent(/ningún modelo/i);
    expect(screen.queryByRole("button", { name: /crear teammate/i })).not.toBeInTheDocument();
  });

  it("se puede salir sin crear nada", async () => {
    const user = userEvent.setup();
    const { onCancel, onSubmit } = paint();
    await user.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
