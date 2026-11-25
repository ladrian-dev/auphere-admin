# Tareas: el panel solo obedece a operadores activos (078)

Hotfix P0. Es el único plan de ejecución.

- [X] T001 Prueba estructural: cada función exportada de un archivo `"use server"` de `apps/admin/src` llama a `requireOperator()` (directa o por una función del mismo archivo), salvo `loginAction` y `logoutAction`. Verla en rojo. _Requisitos: 1.1, 1.2, 1.3_ Roja con 36 acciones sin la guarda; también falla ante un `export default`, un export construido con una llamada o un `"use server"` dentro de una función.
- [X] T002 Prueba de `requireOperator()`: sin sesión va a `/login`; con `access: "disabled"` va a `/sin-acceso`; con `access: "ok"` devuelve el operador. Verla en rojo. _Requisitos: 2.1_
- [X] T003 `requireOperator()` lleva a `/sin-acceso` a una cuenta deshabilitada. _Requisitos: 2.1_
- [X] T004 Página `/sin-acceso` en `(auth)`, con cerrar sesión. _Requisitos: 2.2, 2.4_
- [X] T005 `await requireOperator()` en las acciones que no la llamaban (`partners`, `tenants`, `tenants/new`, `_integrations`, `backchannel`, `conversations`). _Requisitos: 1.1_
- [X] T006 Las rutas de streaming de conversaciones contestan 403 a una cuenta deshabilitada. _Requisitos: 2.3_
- [X] T007 Corregir los comentarios de `lib/session.ts` y `middleware.ts`, y anotar el cambio en `docs/` si alguno describe la sesión del panel. _Requisitos: 2.1_
- [X] T008 Vitest del panel, `tsc`, eslint y `next build` del panel en verde el 2026-11-25. _Requisitos: todos_
- [X] T009 Revisión de seguridad independiente del diff (2026-11-25). Ninguna escritura queda al alcance sin sesión o con la cuenta deshabilitada. Dejó tres cosas, que se recogen en T011–T013 y en «Fuera» de la spec. _Requisitos: todos_
- [X] T011 La prueba exige la guarda como **primera** sentencia (no en un `try`, ni después de leer o escribir, ni en un `Promise.all` de una acción), y lee también `.js`, `.jsx` y `.mjs`. Verla en rojo: 2 acciones de membresía, 8 guardas dentro de un `try` en `partners/actions.ts` y 5 páginas. _Requisitos: 1.1, 1.3_
- [X] T012 Sacar del `try` las 8 guardas de `partners/actions.ts` y poner la guarda antes de validar en `putMembershipAction`. _Requisitos: 1.1_
- [X] T013 La guarda en las 57 páginas y layouts de servidor de `app/(dashboard)` que no la tenían, y en los `generateMetadata` que leen la API. La prueba estructural lo exige; las 8 pruebas que pintan páginas simulan la sesión. _Requisitos: 3.1, 3.2, 3.3_
- [X] T014 Prueba de `safeRedirect`: deja pasar rutas del panel y devuelve `/tenants` con `//otro-sitio`, `/\otro-sitio`, una URL absoluta, un esquema o una ruta relativa. Verla en rojo. _Requisitos: 4.1_
- [X] T015 `lib/safe-redirect.ts` y el login lo usa. _Requisitos: 4.1_
- [X] T016 Prueba de `adminToken()`: en producción falla sin token y con el de desarrollo; en desarrollo usa el de siempre; ningún otro archivo lee `NEXUS_ADMIN_TOKEN`. Verla en rojo. _Requisitos: 5.1, 5.2_
- [X] T017 `lib/admin-token.ts`, y las seis copias (`backend`, `operator-auth`, `qa-api` y las tres rutas de streaming) llaman a `adminToken()` al hacer la llamada. _Requisitos: 5.1, 5.2_
- [ ] T010 En staging: una acción del panel con sesión sigue funcionando, una página del panel se pinta, y una cuenta deshabilitada acaba en `/sin-acceso`. _Requisitos: 1.1, 2.1, 2.2, 3.1_
