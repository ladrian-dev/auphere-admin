import { describe, expect, it, vi } from "vitest";

import type { QualityJob } from "@/lib/backend/agent-quality-types";

import { channelsHref, groupTests, partKey, reviewFixLink, simTimeLabel, undoOpen, waitForJob, wallTime } from "../quality-model";

import { REF, TESTS, job } from "./quality-fixtures";

/**
 * Spec 047 (T089, T094) — lo que el probador, las pruebas, la revisión y
 * «Guardar» deciden sin pintar nada.
 */

describe("esperar a un trabajo", () => {
  it("espera 1, 2, 4… mientras el paso no cambia, vuelve a 1 s al cambiar y para al terminar", async () => {
    const steps: QualityJob[] = [
      job({ progress: { step: "testing" } }),
      job({ progress: { step: "testing" } }),
      job({ progress: { step: "testing" } }),
      job({ progress: { step: "deciding" } }),
      job({ status: "done", result: { number: 4 } }),
    ];
    const waits: number[] = [];
    const seen: string[] = [];
    let i = 0;
    const res = await waitForJob(async () => ({ ok: true as const, data: steps[i++]! }), {
      wait: async (ms) => {
        waits.push(ms);
      },
      onUpdate: (j) => seen.push(`${j.status}:${j.progress?.step ?? ""}`),
    });
    expect(res).toMatchObject({ ok: true, data: { status: "done" } });
    expect(waits).toEqual([1000, 1000, 2000, 4000, 1000]);
    expect(seen.at(-1)).toBe("done:testing");
  });

  it("un 404 se devuelve, un 500 se reintenta y cancelar para", async () => {
    const poll = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500, message: "" })
      .mockResolvedValueOnce({ ok: false, status: 404, message: "" });
    expect(await waitForJob(poll, { wait: async () => undefined })).toMatchObject({ ok: false, status: 404 });
    expect(poll).toHaveBeenCalledTimes(2);
    expect(await waitForJob(poll, { wait: async () => undefined, cancelled: () => true })).toBeNull();
  });
});

describe("la hora simulada", () => {
  it("se dice en la zona del negocio y se edita en su hora de pared", () => {
    const label = simTimeLabel("2026-10-27T11:20:00+01:00", "Europe/Madrid", "es");
    expect(label).toMatch(/11:20/);
    expect(label).toMatch(/mar/);
    expect(wallTime("2026-10-27T11:20:00+01:00", "Europe/Madrid")).toBe("2026-10-27T11:20");
    // Sin desfase (UTC con Z), se pasa a la zona del negocio.
    expect(wallTime("2026-10-27T10:20:00Z", "Europe/Madrid")).toBe("2026-10-27T11:20");
  });
});

describe("las pruebas, los arreglos y las partes", () => {
  it("las pruebas se agrupan del caso, del sector y añadidas, en ese orden", () => {
    expect(groupTests(TESTS).map((g) => [g.kind, g.tests.length])).toEqual([
      ["case", 3],
      ["sector", 2],
      ["person", 1],
    ]);
  });

  it("cada arreglo «link» lleva a su sitio", () => {
    expect(reviewFixLink(REF, { kind: "link", target: "integrations" })?.href).toBe(`/clients/${REF}/integrations`);
    expect(reviewFixLink(REF, { kind: "link", target: "business/hours" })?.href).toBe(`/clients/${REF}/business#business-hours`);
    expect(reviewFixLink(REF, { kind: "link", target: "business/services" })?.href).toBe(`/clients/${REF}/business#business-services`);
    expect(reviewFixLink(REF, { kind: "link", target: "channel", channel_id: "c1" })?.href).toBe(channelsHref(REF));
    expect(reviewFixLink(REF, { kind: "link", target: "otra" })).toBeNull();
  });

  it("«Deshacer» solo mientras dura su ventana", () => {
    const now = Date.parse("2026-10-27T10:00:00Z");
    expect(undoOpen("2026-10-27T10:09:00Z", now)).toBe(true);
    expect(undoOpen("2026-10-27T09:59:00Z", now)).toBe(false);
    expect(undoOpen(null, now)).toBe(false);
  });

  it("las partes del AgentSpec tienen palabra; las desconocidas, no", () => {
    expect(partKey("rules")).toBe("builder.part.rules");
    expect(partKey("test_suite")).toBeNull();
  });
});
