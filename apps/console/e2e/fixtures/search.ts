import WORLD from "./search-world.json";

/**
 * `GET /console/search?q=` como lo contesta la API (spec 047, R47.2,
 * `api/console/search.py`): clientes por nombre o nicho y agentes por nombre,
 * solo con texto; pantallas y acciones, **todas las permitidas** siempre, y
 * la consola las empareja con lo escrito por su texto. Lo usan
 * `shell.spec.ts` (interceptando `/api/search`) y `mock-api.mjs`.
 */
export type SearchWorld = typeof WORLD;

const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export function searchWorld(q: string, world: SearchWorld = WORLD) {
  const needle = fold(q.trim());
  const base = { screens: world.screens, actions: world.actions };
  if (!needle) return { clients: [], agents: [], ...base };
  return {
    clients: world.clients.filter((c) => fold(`${c.name} ${c.ref} ${c.niche ?? ""}`).includes(needle)),
    agents: world.agents.filter((a) => fold(a.name).includes(needle)),
    ...base,
  };
}

export { WORLD };
