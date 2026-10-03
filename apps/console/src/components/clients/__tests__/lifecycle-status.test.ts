import { describe, expect, it } from "vitest";

import { deleteIsOffered, moreMenuItems, statusActionNeedsConfirm } from "../lifecycle-status";

describe("statusActionNeedsConfirm (QA-15)", () => {
  it("is true for paused and archived", () => {
    expect(statusActionNeedsConfirm("paused")).toBe(true);
    expect(statusActionNeedsConfirm("archived")).toBe(true);
  });
  it("is false for active (reactivate / unarchive / activate)", () => {
    expect(statusActionNeedsConfirm("active")).toBe(false);
  });
});

describe("deleteIsOffered", () => {
  it("only for an archived client, and only with the permission", () => {
    expect(deleteIsOffered("archived", true)).toBe(true);
    expect(deleteIsOffered("active", true)).toBe(false);
    expect(deleteIsOffered("paused", true)).toBe(false);
    expect(deleteIsOffered("archived", false)).toBe(false);
  });
});

describe("lo que hay dentro de «Más» (spec 017, R1.6)", () => {
  const owner = { canWrite: true, canDelete: true };
  const builder = { canWrite: true, canDelete: false };
  const analyst = { canWrite: false, canDelete: false };

  it("el propietario de un cliente que atiende puede pausarlo o archivarlo", () => {
    expect(moreMenuItems("active", owner)).toEqual(["pause", "archive", "copyRef"]);
  });

  it("en pausa se ofrece reanudar, no pausar otra vez", () => {
    expect(moreMenuItems("paused", owner)).toEqual(["resume", "archive", "copyRef"]);
  });

  it("eliminar solo aparece archivado, y solo con permiso para borrar", () => {
    expect(moreMenuItems("archived", owner)).toEqual(["unarchive", "copyRef", "delete"]);
    expect(moreMenuItems("archived", builder)).toEqual(["unarchive", "copyRef"]);
    expect(moreMenuItems("active", owner)).not.toContain("delete");
  });

  it("quien no puede escribir conserva el menú, con lo único que sí puede", () => {
    // El mismo control en el mismo sitio: buscar dos veces cansa.
    expect(moreMenuItems("active", analyst)).toEqual(["copyRef"]);
    expect(moreMenuItems("archived", analyst)).toEqual(["copyRef"]);
  });
});
