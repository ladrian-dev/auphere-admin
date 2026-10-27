import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { axeViolations } from "@nexus/ui/test/axe";

import { LocaleProvider } from "@/i18n/client";
import type { Job } from "@/lib/backend";
import type { ClientRead, ReadResult } from "@/lib/backend/clients-v2";

vi.mock("@/app/(console)/clients/new-client-actions", () => ({
  getClientReadAction: vi.fn(),
  startClientReadAction: vi.fn(),
}));

const { ClientReadCard } = await import("../client-read-card");
const { foundSummary, pollDelay, readView } = await import("../client-read-model");
const { t } = await import("@/i18n/messages");

/**
 * Spec 047 (T050, requisitos 5.5, 5.7 y 14.7): la tarjeta de lectura que usará
 * el Panel. Sus cinco estados: cargando, vacío (sin web ni redes, no pinta),
 * error (no se sabe cómo va), parcial (una red no se dejó leer) e ideal.
 */

const ok = <T,>(data: T) => ({ ok: true as const, data });
const RESULT: ReadResult = {
  website: "cultorbarber.com",
  sources: [{ network: "web", value: "cultorbarber.com", status: "read", failure: null, pages: 7 }],
  found: { locations: 2, hours: 1, services: 12, policies: 2, faqs: 3, links: 1 },
  applied: 3,
  suggested: 18,
  translated_from: null,
};

function job(over: Partial<Job> = {}): Job {
  return {
    job_id: "11111111-1111-4111-8111-111111111111",
    kind: "client_read",
    status: "running",
    agent_id: null,
    progress: { step: "pages", blocks: [{ key: "pages", read: 3 }] },
    questions: null,
    result: null,
    error_code: null,
    created_at: "2026-10-26T10:00:00Z",
    finished_at: null,
    ...over,
  };
}
const read = (j: Job | null, website: string | null = "cultorbarber.com"): ClientRead => ({ job: j, website, networks: ["instagram"] });

function card(props: Partial<React.ComponentProps<typeof ClientReadCard>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <ClientReadCard refId="barberia-cultor" {...props} />
    </LocaleProvider>,
  );
}

describe("ClientReadCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("cargando: un esqueleto del tamaño de la tarjeta", () => {
    const load = vi.fn(() => new Promise<never>(() => {}));
    card({ actions: { load } });
    expect(screen.getByLabelText("Cargando cómo va la lectura…")).toHaveAttribute("aria-busy", "true");
  });

  it("vacío: sin trabajo de lectura no pinta nada", async () => {
    const load = vi.fn(async () => ok(read(null, null)));
    const { container } = card({ actions: { load } });
    await waitFor(() => expect(load).toHaveBeenCalled());
    await waitFor(() => expect(container.querySelector("[data-slot=client-read-card]")).toBeNull());
  });

  it("leyendo: dice qué web se lee y cuántas páginas lleva, y sigue mirando hasta que termina", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(ok(read(job())))
      .mockResolvedValueOnce(ok(read(job({ status: "done", result: RESULT, finished_at: "2026-10-26T10:01:00Z" }))));
    card({ actions: { load } });
    expect(await screen.findByText("Leyendo cultorbarber.com para completar la ficha: sedes, horario y servicios…")).toBeInTheDocument();
    expect(screen.getByText("3 páginas leídas")).toBeInTheDocument();
    expect(await screen.findByText(/Leímos cultorbarber.com: 2 sedes, el horario, 12 servicios/, {}, { timeout: 3000 })).toBeInTheDocument();
    // «Revisar» es un enlace a Negocio con la forma de un botón.
    expect(screen.getByText("Revisar").closest("a")).toHaveAttribute("href", "/clients/barberia-cultor/business");
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("parcial: lo que se leyó, y la red que no se dejó leer", () => {
    const partial: ReadResult = {
      ...RESULT,
      website: null,
      sources: [
        { network: "instagram", value: "@cultorbarber", status: "failed", failure: "blocked", pages: 0 },
        { network: "tiktok", value: "@cultorbarber", status: "read", failure: null, pages: 1 },
      ],
      found: { locations: 0, hours: 0, services: 0, policies: 0, faqs: 1, links: 0 },
      translated_from: "en",
    };
    card({ initial: read(job({ status: "done", result: partial }), null) });
    expect(screen.getByText(/Leímos sus redes: 1 pregunta frecuente/)).toBeInTheDocument();
    expect(screen.getByText("Instagram no se deja leer.")).toBeInTheDocument();
    expect(screen.getByText("Traducido de inglés.")).toBeInTheDocument();
  });

  it("fallida: dice por qué y ofrece reintentar, que vuelve a «leyendo»", async () => {
    const retry = vi.fn(async () => ok({ job_id: "22222222-2222-4222-8222-222222222222" }));
    const load = vi.fn(async () => ok(read(job({ status: "running", progress: {} }))));
    const user = userEvent.setup();
    card({ initial: read(job({ status: "failed", error_code: "unreachable", finished_at: "x" })), actions: { load, retry } });
    expect(screen.getByText("No pudimos leer cultorbarber.com: no responde.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalledWith({ ref: "barberia-cultor" });
    expect(await screen.findByText(/Leyendo cultorbarber.com/)).toBeInTheDocument();
  });

  it("sin permiso de escritura no hay «Reintentar»", () => {
    card({ initial: read(job({ status: "failed", error_code: "blocked" })), canWrite: false });
    expect(screen.getByText(/no deja que se lea/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).toBeNull();
  });

  it("error: si no se sabe cómo va, lo dice y deja volver a mirar", async () => {
    const load = vi.fn(async () => ({ ok: false as const, status: 502, message: "upstream" }));
    card({ actions: { load } });
    expect(await screen.findByText("No pudimos saber cómo va la lectura.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("pasa axe leyendo, hecha y fallida", async () => {
    const { unmount } = card({ initial: read(job()), actions: { load: vi.fn(() => new Promise<never>(() => {})) } });
    expect(await axeViolations()).toEqual([]);
    unmount();
    const done = card({ initial: read(job({ status: "done", result: RESULT })) });
    expect(await axeViolations()).toEqual([]);
    done.unmount();
    card({ initial: read(job({ status: "failed", error_code: "too_large" })) });
    expect(await axeViolations()).toEqual([]);
  });
});

describe("client-read-model", () => {
  const tt = (key: Parameters<typeof t>[1], vars?: Record<string, string | number>) => t("es", key, vars);

  it("resume lo encontrado en una frase", () => {
    expect(foundSummary(RESULT.found, tt)).toBe("2 sedes, el horario, 12 servicios, sus políticas, 3 preguntas frecuentes y 1 red");
    expect(foundSummary({ locations: 1, hours: 0, services: 0, policies: 0, faqs: 0, links: 0 }, tt)).toBe("1 sede");
    expect(foundSummary({ locations: 0, hours: 0, services: 0, policies: 0, faqs: 0, links: 0 }, tt)).toBe("");
  });

  it("espera 1, 2, 4… hasta 10 s", () => {
    expect([0, 1, 2, 3, 4, 9].map(pollDelay)).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });

  it("un código que no conoce se dice como un fallo nuestro", () => {
    expect(readView(read(job({ status: "failed", error_code: "internal" })))).toMatchObject({ kind: "failed", reason: "other" });
    expect(readView(read(job({ kind: "agent_draft" })))).toEqual({ kind: "none" });
  });
});
