import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/app/(console)/clients/[ref]/knowledge/actions", () => ({
  addKnowledgeUrlAction: vi.fn(),
  deleteKnowledgeAction: vi.fn(),
  reindexKnowledgeAction: vi.fn(),
  restoreKnowledgeAction: vi.fn(),
  uploadKnowledgeAction: vi.fn(),
}));

import { LocaleProvider } from "@/i18n/client";
import type { KnowledgeDocumentOut, KnowledgeListOut } from "@/lib/backend/agent-tools-types";

import { KnowledgeTable, type KnowledgeTableActions } from "../knowledge-table";

/**
 * Spec 047 — la Guía del partner como el prototipo «Consola de partners v2»:
 * «Subir archivo» con una zona de soltar y «Elegir archivo», que sube al elegir
 * (sin otro botón); «Añadir URL» al lado; y la tarjeta «Documentos» con su
 * recuento, el uso del presupuesto y la tabla dentro. El conocimiento del
 * cliente, que comparte la tabla, sigue con sus formularios de siempre.
 */
const doc = (over: Partial<KnowledgeDocumentOut> = {}): KnowledgeDocumentOut => ({
  id: "d1",
  kind: "file",
  title: "Tono y estilo de la agencia",
  source_url: null,
  mime: "application/pdf",
  size_bytes: 1_200_000,
  status: "indexed",
  error_code: null,
  chunk_count: 38,
  created_by: null,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
  indexed_at: "2026-10-20T10:14:00Z",
  ...over,
});
const data = (items: KnowledgeDocumentOut[]): KnowledgeListOut => ({ items, total: items.length, indexed_chars: 84_300, prompt_char_cap: 120_000 });
const ok = <T,>(d: T) => ({ ok: true as const, data: d });

let actions: KnowledgeTableActions;
beforeEach(() => {
  actions = {
    upload: vi.fn(async () => ok(doc({ title: "carta.pdf" }))),
    addUrl: vi.fn(async () => ok(doc())),
    remove: vi.fn(async () => ok(null)),
    reindex: vi.fn(async () => ok(doc())),
  };
});
const playbook = (d = data([doc()])) =>
  render(
    <LocaleProvider locale="es">
      <main>
        <h1>Guía del partner</h1>
        <KnowledgeTable variant="playbook" refId="" data={d} canWrite actions={actions} />
      </main>
    </LocaleProvider>,
  );

describe("Guía del partner · como el prototipo", () => {
  it("«Subir archivo» sube al elegir el archivo, sin otro botón", async () => {
    const user = userEvent.setup();
    playbook();
    const upload = screen.getByRole("region", { name: "Subir archivo" });
    expect(within(upload).getByText("PDF, TXT, MD o HTML · máx. 10 MB")).toBeInTheDocument();
    expect(within(upload).queryByRole("button", { name: "Subir e indexar" })).toBeNull();
    await user.type(within(upload).getByLabelText(/Título/), "Carta 2026");
    const file = new File(["hola"], "carta.pdf", { type: "application/pdf" });
    await user.upload(within(upload).getByLabelText("Elegir archivo"), file);
    await waitFor(() => expect(actions.upload).toHaveBeenCalledTimes(1));
    const fd = (actions.upload as ReturnType<typeof vi.fn>).mock.calls[0]![0] as FormData;
    expect((fd.get("file") as File).name).toBe("carta.pdf");
    expect(fd.get("title")).toBe("Carta 2026");
  });

  it("también se puede soltar el archivo en la zona", async () => {
    playbook();
    const zone = document.querySelector("[data-slot=knowledge-drop]") as HTMLElement;
    const file = new File(["hola"], "notas.md", { type: "text/markdown" });
    fireEvent.drop(zone, { dataTransfer: { files: [file], types: ["Files"] } });
    await waitFor(() => expect(actions.upload).toHaveBeenCalledTimes(1));
  });

  it("un archivo de más de 10 MB no sale de la pantalla", async () => {
    const user = userEvent.setup();
    playbook();
    const big = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "grande.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Elegir archivo"), big);
    expect(await screen.findByText("El archivo supera 10 MB.")).toBeInTheDocument();
    expect(actions.upload).not.toHaveBeenCalled();
  });

  it("«Documentos» es una tarjeta con su recuento, el presupuesto y la tabla dentro", async () => {
    const { container } = playbook(data([doc(), doc({ id: "d2", title: "Manual", status: "failed", error_code: "empty" })]));
    const docs = screen.getByRole("region", { name: "Documentos" });
    expect(within(docs).getByText("2")).toBeInTheDocument();
    expect(within(docs).getByText("Uso del presupuesto del prompt")).toBeInTheDocument();
    expect(within(docs).getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Añadir URL" })).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("eliminar dice que el Companion deja de consultarlo", async () => {
    const user = userEvent.setup();
    playbook();
    await user.click(screen.getByRole("button", { name: "Eliminar · Tono y estilo de la agencia" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("El Companion dejará de consultar este documento de inmediato. No se puede deshacer.");
  });
});

describe("el conocimiento del cliente no cambia", () => {
  it("sigue con su formulario de subida y «Subir e indexar»", () => {
    render(
      <LocaleProvider locale="es">
        <KnowledgeTable refId="flor" data={data([doc()])} canWrite />
      </LocaleProvider>,
    );
    expect(screen.getByRole("button", { name: "Subir e indexar" })).toBeInTheDocument();
    expect(screen.queryByText("PDF, TXT, MD o HTML · máx. 10 MB")).toBeNull();
  });
});
