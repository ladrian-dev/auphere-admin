/**
 * Spec 059 (requisito 2; research D9): the one setting that parks the router
 * in the operator panel while it is studied. Parked (`false`), the panel shows
 * nothing that only makes sense with the router deciding: neither Router nor
 * Certificaciones (sidebar, command palette, their addresses give «no existe»),
 * nor the Router block of Estado, nor «Nuevo despliegue», «Activar»,
 * «Certificado en» and «Le falta» in Modelos.
 *
 * Turning it to `true` brings all of it back as it was, with no other change
 * (2.7, CE-005). A constant and not an environment variable: the sidebar is
 * painted in the browser, and parked is the value in every environment.
 * `components/shell/__tests__/nav.test.ts` pins it. The API and the worker do
 * not read it (2.8).
 */
export const ROUTER_PANEL_VISIBLE = false;
