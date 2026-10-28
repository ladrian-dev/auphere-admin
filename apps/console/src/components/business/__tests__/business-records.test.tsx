import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Change, Provenance, Source, Sources } from "@/lib/backend/client-records";

const toast = vi.hoisted(() => Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/app/(console)/clients/[ref]/client-v2-actions", () => ({
  addSourceUrlAction: vi.fn(),
  confirmSectionAction: vi.fn(),
  getHistoryAction: vi.fn(),
  listSourcesAction: vi.fn(),
  putLinksAction: vi.fn(),
  removeSourceAction: vi.fn(),
  rereadSourceAction: vi.fn(),
  restoreSourceAction: vi.fn(),
  undoChangeAction: vi.fn(),
  uploadSourceAction: vi.fn(),
}));

const { ProvenanceLabel } = await import("../provenance/provenance-label");
const { provenanceText, sectionNeedsReview, sectionProvenance } = await import("../provenance/provenance-model");
const { SectionHistory } = await import("../history/section-history");
const { BusinessSources, nextDelay } = await import("../sources/business-sources");
const { BusinessLinks, handleOf, linksFrom, profileUrl, rowsFrom } = await import("../sources/business-links");
const { t } = await import("@/i18n/messages");

/**
 * Spec 047 (T069, T071, historia 17): la procedencia («Escrito por ti»,
 * «Leído de la web · revísalo», «Editado por Marta desde la app»…) con «Es
 * correcto»; el historial con «Deshacer» y su conflicto; «Documentos y webs»
 * con sus estados y el deshacer de 10 minutos; y «Redes». Los cinco estados
 * donde hay datos que cargar, y axe.
 */
const ok = <T,>(data: T) => ({ ok: true as const, data });
const es = (key: Parameters<typeof t>[1], vars?: Record<string, string | number>) => t("es", key, vars);
const wrap = (node: React.ReactNode) => render(<LocaleProvider locale="es">{node}</LocaleProvider>);
const at = new Date(Date.now() - 2 * 3600_000).toISOString();
const prov = (over: Partial<Provenance>): Provenance => ({
  source: "person",
  by: { kind: "partner_member", id: "ana", name: "Ana" },
  origin: "console",
  at,
  source_url: null,
  translated_from: null,
  review: "confirmed",
  ...over,
});

describe("la procedencia", () => {
  beforeEach(() => vi.clearAllMocks());

  it("dice los cinco tipos con su autor", () => {
    expect(provenanceText(es, prov({}), "ana")).toBe("Escrito por ti");
    expect(provenanceText(es, prov({}), "luis")).toBe("Escrito por Ana");
    expect(provenanceText(es, prov({ origin: "app", by: { kind: "client_user", id: "m", name: "Marta" } }), "ana")).toBe(
      "Editado por Marta desde la app",
    );
    expect(provenanceText(es, prov({ source: "web", review: "pending" }), null)).toBe("Leído de la web · revísalo");
    expect(provenanceText(es, prov({ source: "migrated", review: "pending" }), null)).toBe("Migrado · revísalo");
    expect(provenanceText(es, prov({ source: "builder" }), null)).toBe("Sugerido · confírmalo");
    expect(provenanceText(es, prov({ source: "inbox_correction" }), null)).toBe("Corregido desde la Bandeja");
  });

  it("la de una sección es la más reciente de sus datos, y sabe si queda algo por revisar", () => {
    const all = {
      "/policies/cancellation": prov({ source: "web", review: "pending", at: "2026-10-26T10:00:00Z" }),
      "/policies/payments": prov({ at: "2026-10-27T10:00:00Z" }),
      "/business/name": prov({ at: "2026-10-28T10:00:00Z" }),
    };
    expect(sectionProvenance(all, "policies")?.at).toBe("2026-10-27T10:00:00Z");
    expect(sectionNeedsReview(all, "policies")).toBe(true);
    expect(sectionNeedsReview(all, "basics")).toBe(false);
  });

  it("«Es correcto» confirma lo leído (escenario 1)", async () => {
    const user = userEvent.setup();
    const confirm = vi.fn(async () => ok({ confirmed: 2 }));
    const onConfirmed = vi.fn();
    const { container } = wrap(
      <ProvenanceLabel provenance={prov({ source: "web", review: "pending" })} meId="ana" refId="cultor" section="hours" canConfirm confirm={confirm} onConfirmed={onConfirmed} />,
    );
    expect(screen.getByText(/Leído de la web · revísalo · hace 2 horas/)).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Es correcto" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith({ ref: "cultor", section: "hours" }));
    expect(onConfirmed).toHaveBeenCalled();
  });

  it("sin permiso no ofrece confirmar", () => {
    wrap(<ProvenanceLabel provenance={prov({ source: "web", review: "pending" })} meId={null} refId="cultor" section="hours" />);
    expect(screen.queryByRole("button", { name: "Es correcto" })).toBeNull();
  });
});

const change = (over: Partial<Change>): Change => ({
  id: "c1",
  section: "links",
  kind: "edit",
  at,
  by: { kind: "client_user", id: "m", name: "Marta" },
  origin: "app",
  before: null,
  after: null,
  undone_at: null,
  undo_of: null,
  undoable: true,
  ...over,
});

describe("el historial", () => {
  beforeEach(() => vi.clearAllMocks());

  it("carga al abrirse, enseña quién y cuándo, y deshace el último", async () => {
    const user = userEvent.setup();
    const load = vi.fn(async () => ok([change({}), change({ id: "c0", undoable: false, by: { kind: "partner_member", id: "ana", name: "Ana" } })]));
    const undo = vi.fn(async () => ok({ revision: 7 }));
    wrap(<SectionHistory refId="cultor" section="links" meId="ana" canUndo actions={{ load, undo }} />);
    await user.click(screen.getByRole("button", { name: "Ver el historial de Redes" }));
    expect(await screen.findByText("Marta · hace 2 horas")).toBeTruthy();
    expect(screen.getByText("Escrito por ti · hace 2 horas")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Deshacer" })).toHaveLength(1);
    expect(await axeViolations()).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Deshacer" }));
    await waitFor(() => expect(undo).toHaveBeenCalledWith({ ref: "cultor", change_id: "c1" }));
    expect(toast.success).toHaveBeenCalledWith("Cambio deshecho. Los agentes ya usan lo anterior.");
  });

  it("si alguien escribió después, lo dice y no pisa (412)", async () => {
    const user = userEvent.setup();
    const load = vi.fn(async () => ok([change({})]));
    const undo = vi.fn(async () => ({ ok: false as const, status: 412, message: "x", code: "revision_conflict" }));
    wrap(<SectionHistory refId="cultor" section="links" meId="ana" canUndo actions={{ load, undo }} />);
    await user.click(screen.getByRole("button", { name: "Ver el historial de Redes" }));
    await user.click(await screen.findByRole("button", { name: "Deshacer" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Alguien cambió esta sección después: no se deshizo para no pisarlo."));
  });

  it("vacío y con error", async () => {
    const user = userEvent.setup();
    const empty = vi.fn(async () => ok([] as Change[]));
    const { unmount } = wrap(<SectionHistory refId="cultor" section="hours" meId={null} canUndo={false} actions={{ load: empty }} />);
    await user.click(screen.getByRole("button", { name: "Ver el historial de Horarios" }));
    expect(await screen.findByText("Sin cambios todavía.")).toBeTruthy();
    unmount();
    const broken = vi.fn(async () => ({ ok: false as const, status: 500, message: "x" }));
    wrap(<SectionHistory refId="cultor" section="hours" meId={null} canUndo={false} actions={{ load: broken }} />);
    await user.click(screen.getByRole("button", { name: "Ver el historial de Horarios" }));
    expect((await screen.findByRole("alert")).textContent).toContain("No pudimos cargar el historial.");
  });
});

const source = (over: Partial<Source>): Source => ({
  id: "11111111-1111-4111-8111-111111111111",
  kind: "file",
  title: "carta.pdf",
  url: null,
  status: "read",
  failure: null,
  size_bytes: 2_400_000,
  read_at: at,
  created_at: at,
  ...over,
});
const sources = (over: Partial<Sources> = {}): Sources => ({ items: [source({})], removed: [], max_bytes: 10 * 1024 * 1024, allowed: ["add", "remove", "reread"], ...over });

describe("documentos y webs", () => {
  beforeEach(() => vi.clearAllMocks());

  it("cada fuente dice su estado, su tamaño y cuándo se leyó", async () => {
    const { container } = wrap(
      <BusinessSources
        refId="cultor"
        canWrite
        initial={sources({
          items: [
            source({}),
            source({ id: "2", kind: "web", title: "cultorbarber.com/precios", url: "https://cultorbarber.com/precios", status: "reading", size_bytes: 0 }),
            source({ id: "3", title: "vieja.pdf", status: "failed", failure: "too_large" }),
          ],
        })}
        actions={{ load: vi.fn(async () => ok(sources())) }}
      />,
    );
    const list = screen.getByRole("list", { name: "Documentos y webs del negocio" });
    const items = within(list).getAllByRole("listitem");
    expect(within(items[0]!).getByText("Leído hace 2 horas")).toBeTruthy();
    expect(within(items[0]!).getByText(/2,3\sMB|2,4\sMB/)).toBeTruthy();
    expect(within(items[1]!).getByText("Leyendo…")).toBeTruthy();
    expect(within(items[2]!).getByText("No se pudo leer: pasa de 10 MB")).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("vacío, cargando y con error", async () => {
    const { unmount } = wrap(<BusinessSources refId="cultor" canWrite initial={sources({ items: [] })} />);
    expect(screen.getByText("Aún no hay documentos ni webs.")).toBeTruthy();
    unmount();
    const load = vi.fn(async () => ({ ok: false as const, status: 500, message: "x" }));
    wrap(<BusinessSources refId="cultor" canWrite actions={{ load }} />);
    expect(screen.getByLabelText("Cargando los documentos…")).toBeTruthy();
    expect((await screen.findByRole("alert")).textContent).toContain("No pudimos cargar los documentos.");
  });

  it("no sube un archivo de más de 10 MB", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const upload = vi.fn();
    wrap(<BusinessSources refId="cultor" canWrite initial={sources()} actions={{ upload }} />);
    const big = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "enorme.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Subir archivo", { selector: "input" }), big);
    expect(upload).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Ese archivo pasa de 10 MB.");
  });

  it("quitar deja de usarse y el aviso trae «Deshacer» (10 minutos)", async () => {
    const user = userEvent.setup();
    const remove = vi.fn(async () => ok({ id: source({}).id, restore_until: new Date(Date.now() + 600_000).toISOString() }));
    const restore = vi.fn(async () => ok(source({})));
    const load = vi.fn(async () => ok(sources({ items: [] })));
    wrap(<BusinessSources refId="cultor" canWrite initial={sources()} actions={{ remove, restore, load }} />);
    await user.click(screen.getByRole("button", { name: "Quitar carta.pdf" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith({ ref: "cultor", id: source({}).id }));
    const [message, options] = toast.success.mock.calls[0] as [string, { action: { label: string; onClick: () => void } }];
    expect(message).toBe("Quitado. Los agentes ya no lo usan.");
    expect(options.action.label).toBe("Deshacer");
    options.action.onClick();
    await waitFor(() => expect(restore).toHaveBeenCalledWith({ ref: "cultor", id: source({}).id }));
  });

  it("sin permiso no ofrece subir ni quitar", () => {
    wrap(<BusinessSources refId="cultor" canWrite={false} initial={sources({ allowed: [] })} />);
    expect(screen.queryByRole("button", { name: "Subir archivo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Quitar carta.pdf" })).toBeNull();
  });

  it("espera más cada vez mientras algo se lee, hasta 10 s", () => {
    expect([0, 1, 2, 3, 4, 5].map(nextDelay)).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });
});

describe("redes", () => {
  beforeEach(() => vi.clearAllMocks());

  it("Instagram y Facebook están siempre, con su logo; se escribe el usuario y se ve su enlace", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async () => ok({ links: [{ id: "l1", network: "instagram" as const, url: "https://www.instagram.com/jhondoe", handle: "@jhondoe" }], revision: 3 }));
    const { container } = wrap(<BusinessLinks refId="cultor" links={[]} revision={2} canWrite save={save} />);
    expect(container.querySelector("[data-brand=instagram]")).not.toBeNull();
    expect(container.querySelector("[data-brand=facebook]")).not.toBeNull();
    expect(screen.getByLabelText("Usuario en Facebook")).toBeTruthy();
    expect(await axeViolations(container)).toEqual([]);
    // Andrés, 2026-10-28: «Mi Instagram es @Jhondoe» → https://www.instagram.com/jhondoe
    await user.type(screen.getByLabelText("Usuario en Instagram"), "@Jhondoe");
    expect(screen.getByRole("link", { name: "https://www.instagram.com/jhondoe" })).toHaveAttribute("href", "https://www.instagram.com/jhondoe");
    await user.click(screen.getByRole("button", { name: "Guardar redes" }));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ ref: "cultor", revision: 2, links: [{ network: "instagram", handle: "jhondoe" }] }));
    expect(toast.success).toHaveBeenCalledWith("Redes guardadas. Los agentes ya las usan.");
  });

  it("un usuario que no vale lo dice y no se guarda", async () => {
    const user = userEvent.setup();
    const save = vi.fn();
    wrap(<BusinessLinks refId="cultor" links={[]} revision={2} canWrite save={save} />);
    await user.type(screen.getByLabelText("Usuario en Instagram"), "mi negocio!");
    await user.click(screen.getByRole("button", { name: "Guardar redes" }));
    expect(await screen.findByText("Solo letras, números, puntos y guiones bajos.")).toBeVisible();
    expect(save).not.toHaveBeenCalled();
  });

  it("si otra persona guardó antes, lo dice (412)", async () => {
    const user = userEvent.setup();
    const save = vi.fn(async () => ({ ok: false as const, status: 412, message: "x", code: "revision_conflict" }));
    wrap(<BusinessLinks refId="cultor" links={[]} revision={2} canWrite save={save} />);
    await user.click(screen.getByRole("button", { name: "Guardar redes" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("Alguien cambió las redes")));
  });

  it("de las filas a la API y de vuelta: el usuario de cada red y su enlace", () => {
    const rows = rowsFrom([
      { id: "w", network: "web", url: "https://cultorbarber.com", handle: null },
      { id: "i", network: "instagram", url: "https://www.instagram.com/cultor", handle: "@cultor" },
      { id: "l", network: "linkedin", url: "https://www.linkedin.com/company/cultor-barber", handle: null },
    ]);
    expect(rows.map((r) => [r.network, r.value])).toEqual([
      ["instagram", "cultor"],
      ["facebook", ""],
      ["web", "https://cultorbarber.com"],
      ["linkedin", "cultor-barber"],
    ]);
    expect(linksFrom([...rows, { key: "t", network: "tiktok", value: "https://www.tiktok.com/@Cultor" }])).toEqual([
      { network: "instagram", handle: "cultor" },
      { network: "web", url: "https://cultorbarber.com" },
      { network: "linkedin", url: "https://www.linkedin.com/company/cultor-barber" },
      { network: "tiktok", handle: "cultor" },
    ]);
    expect(handleOf(" @Jhon.Doe ")).toBe("jhon.doe");
    expect(handleOf("https://www.instagram.com/jhondoe/")).toBe("jhondoe");
    expect(profileUrl("tiktok", "cultor")).toBe("https://www.tiktok.com/@cultor");
    expect(profileUrl("youtube", "cultor")).toBe("https://www.youtube.com/@cultor");
    expect(profileUrl("x", "cultor")).toBe("https://x.com/cultor");
    expect(profileUrl("threads", "cultor")).toBe("https://www.threads.net/@cultor");
    expect(profileUrl("facebook", "cultor")).toBe("https://www.facebook.com/cultor");
  });
});
