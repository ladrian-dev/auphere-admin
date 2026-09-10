/**
 * Requisito 5.3 — decidir en un sitio se ve en el otro, sin recargar.
 *
 * Y el caso que el análisis destapó: el stream **no tiene historia**, así que
 * un aviso perdido durante la reconexión tiene que recuperarse con la verdad
 * (`GET /inbox`) en vez de dejar una tarjeta vieja en pantalla.
 */
import { describe, expect, it, vi } from "vitest";

import { InboxWatcher, type InboxItem, type WatcherPorts } from "../src/inbox-watcher.js";
import type { Effect } from "../src/notifications-policy.js";

const item = (id: string, level: InboxItem["level"] = "aviso"): InboxItem => ({
  action_id: id,
  task_id: `task-${id}`,
  thread_id: "t1",
  run_id: "r1",
  teammate: { id: "tm1", name: "Sofía" },
  title: `Decidir ${id}`,
  kind: "prompt",
  level,
  client_ref: "cultor",
  proposed_at: "2026-09-10T10:00:00Z",
  can_decide: true,
});

function ports(inboxes: InboxItem[][]) {
  const effects: Effect[] = [];
  const pushes: Array<[string, unknown]> = [];
  let n = 0;
  const p: WatcherPorts = {
    fetchInbox: vi.fn(async () => inboxes[Math.min(n++, inboxes.length - 1)] ?? []),
    openStream: vi.fn(async () => {}),
    apply: (e) => effects.push(...e),
    push: (c, payload) => pushes.push([c, payload]),
    prefs: () => ({ silenceAviso: false }),
    wait: async () => {},
  };
  return { p, effects, pushes, calls: () => n };
}

describe("la bandeja se reconcilia contra la verdad", () => {
  it("la primera pasada avisa en resumen y empuja la lista", async () => {
    const { p, effects, pushes } = ports([[item("a"), item("b", "critico")]]);
    const w = new InboxWatcher(p);
    await w.reconcile();
    expect(pushes[0]?.[0]).toBe("app:inbox");
    expect((pushes[0]?.[1] as InboxItem[]).length).toBe(2);
    expect(effects.filter((e) => e.kind === "notify")).toHaveLength(1);
    expect(effects).toContainEqual({ kind: "badge", count: 2 });
  });

  it("lo que llega después avisa por tarjeta, y lo que ya estaba no vuelve a sonar", async () => {
    const { p, effects } = ports([[item("a")], [item("a"), item("b", "critico")]]);
    const w = new InboxWatcher(p);
    await w.reconcile();
    const before = effects.filter((e) => e.kind === "notify").length;
    const added = await w.reconcile();
    expect(added.map((i) => i.action_id)).toEqual(["b"]);
    expect(effects.filter((e) => e.kind === "notify").length).toBe(before + 1);
  });

  it("un aviso perdido en la reconexión se recupera con la verdad", async () => {
    // La primera bandeja tiene dos; mientras el stream estaba cortado, una se
    // decidió en otra pantalla. Al reconectar, la verdad dice que queda una.
    const { p, pushes } = ports([[item("a"), item("b")], [item("b")]]);
    const w = new InboxWatcher(p);
    await w.reconcile();
    await w.reconcile();
    const last = pushes.filter(([c]) => c === "app:inbox").at(-1);
    expect((last?.[1] as InboxItem[]).map((i) => i.action_id)).toEqual(["b"]);
  });
});

describe("un aviso del stream retira la tarjeta sin recargar", () => {
  it("`inbox.changed` la quita y avisa a la pantalla", async () => {
    const { p, pushes } = ports([[item("a"), item("b")]]);
    const w = new InboxWatcher(p);
    await w.reconcile();
    w.onChanged("a");
    expect(pushes.some(([c, v]) => c === "app:inbox.changed" && (v as { action_id: string }).action_id === "a")).toBe(true);
    expect(w.items.map((i) => i.action_id)).toEqual(["b"]);
  });

  it("un aviso de algo que ya no está no hace nada", async () => {
    const { p, pushes } = ports([[item("a")]]);
    const w = new InboxWatcher(p);
    await w.reconcile();
    const before = pushes.length;
    w.onChanged("desconocida");
    expect(pushes.length).toBe(before);
  });
});

describe("el bucle", () => {
  it("reconecta y vuelve a reconciliar; parar lo detiene", async () => {
    const { p, calls } = ports([[item("a")]]);
    let opens = 0;
    p.openStream = vi.fn(async () => {
      opens += 1;
      if (opens >= 3) w.stop();
      throw new Error("cortado");
    });
    const w = new InboxWatcher(p);
    await w.start();
    expect(opens).toBe(3);
    expect(calls()).toBe(3);
  });

  it("al perder la sesión, la bandeja se olvida", async () => {
    const { p, pushes } = ports([[item("a")]]);
    const w = new InboxWatcher(p);
    await w.reconcile();
    w.reset();
    expect(w.items).toEqual([]);
    expect(pushes.at(-1)).toEqual(["app:inbox", []]);
  });
});
