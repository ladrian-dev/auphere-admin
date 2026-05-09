/**
 * Adapter to Stagehand v3's page-acquisition API.
 *
 * Stagehand v3 removed the convenience accessor `Stagehand.page`. The
 * active Page is now reached through `Stagehand.context.activePage()`,
 * which returns `undefined` when no top-level page has been registered
 * yet. Use this helper to obtain a Page reference suitable for
 * `goto`/`waitForLoadState`/etc.
 *
 * `act` and `extract` moved to the top-level Stagehand instance in v3 —
 * call them directly as `sh.act(...)` / `sh.extract(...)` instead of
 * `page.act(...)` / `page.extract(...)`.
 */

import type { Stagehand } from '@browserbasehq/stagehand';

export async function pageOf(sh: Stagehand) {
  const active = sh.context.activePage();
  if (active) return active;
  return await sh.context.newPage();
}
