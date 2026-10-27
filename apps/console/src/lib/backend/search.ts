import type { Call, SearchResult } from "../backend";

/**
 * Lane module `shell` — `GET /console/search?q=` (spec 047, R47.2), the ⌘K
 * palette of the new frame. The API answers with what the person may see and
 * do; pantallas y acciones travel as stable keys and the console writes the
 * words. `q` always travels, also empty: what to offer with no text is the
 * API's call.
 */
export function searchApi(call: Call) {
  return {
    search: (text: string) => call<SearchResult>(`/console/search?${new URLSearchParams({ q: text }).toString()}`),
  };
}
