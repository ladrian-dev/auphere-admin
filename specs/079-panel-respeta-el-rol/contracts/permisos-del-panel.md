# Contrato: permisos del panel (fase 1)

Lo que el código del panel (`apps/admin`) y su prueba estructural dan por cierto.
Decisiones y alternativas en [`research.md`](../research.md) D1–D8.

## La matriz

Autoridad: `apps/api/src/nexus_api/core/operator_permissions.py`, un diccionario
literal:

```python
OPERATOR_PERMISSIONS: Final[dict[str, tuple[str, ...]]] = {
    "read": ("admin", "qa_operator", "viewer"),
    "qa": ("admin", "qa_operator"),
    "operate": ("admin", "qa_operator"),
    "money": ("admin",),
    "credentials": ("admin",),
    "impersonate": ("admin",),
    "people": ("admin",),
    "delete": ("admin",),
    "platform": ("admin",),
}
```

Copia: `apps/admin/src/lib/permissions.ts`, módulo puro (sin `server-only`) para que lo
usen el menú, los componentes y las pruebas:

```ts
export type Permission =
  | "read" | "qa" | "operate" | "money" | "credentials"
  | "impersonate" | "people" | "delete" | "platform";
export const PERMISSIONS: Record<Permission, readonly Role[]>;
export function can(operator: { role: string; access: string }, permission: Permission): boolean;
```

`can()` devuelve `false` si `access !== "ok"` o si el rol no está en la lista.

## La guarda

```ts
// src/lib/session.ts
export async function requireOperator(permission: Permission): Promise<Operator>;
```

Hay una variante por superficie, y la prueba estructural exige la que toca en cada
sitio. Con el permiso, las tres devuelven el operador. Sin él:

| Superficie | Función | Sin sesión | Cuenta deshabilitada o rol desconocido | Sin el permiso |
|---|---|---|---|---|
| Server Action | `requireOperator(p)` | `redirect("/login")` | `redirect("/sin-acceso")` | Registra `operator.permission_denied`, invalida el layout de `(dashboard)` y redirige a la misma página con `?sin-permiso=1` (abajo). |
| Página o layout de `app/(dashboard)` | `requirePageOperator(p)` | `redirect("/login")` | `redirect("/sin-acceso")` | `notFound()`. |
| Ruta (cualquier `route.ts` de `app`) | `routeOperator(p)` | 401 `{ "error": "unauthorized" }` | 403 `{ "error": "forbidden" }` | 403 `{ "error": "forbidden" }` |

- **`routeOperator` nunca redirige.** Devuelve `Operator | Response`, y la ruta retorna
  la respuesta tal cual sin llamar a la API. Las rutas de `app/api` las piden `fetch` y
  flujos de eventos, que no saben qué hacer con un HTML. Es lo que ya exigía la 078
  (2.3) y lo que hacía `requireQAOperator`.
- **La misma página, sin redirección abierta.** La ruta sale de la cabecera `Referer`
  de la petición de la acción. Solo vale si su host es el de la propia petición; su
  ruta y su búsqueda pasan por `safeRedirect(path, "/")` de `src/lib/safe-redirect.ts`
  (enmienda de la 078), y se añade `sin-permiso=1` a la búsqueda que ya tenga. El panel
  no fija `Referrer-Policy`, así que el navegador manda la ruta completa dentro del
  mismo origen.
- **`/sin-acceso` usa la misma regla.** Hoy manda a `/tenants` a toda cuenta activa.
  Pasa a mandar solo a quien tiene algún permiso (`can(operator, "read")`). Si no, un
  rol desconocido iría y volvería entre las dos páginas.
- **Lo que se invoca solo pide `read`.** Una acción que se llama al montar un
  componente o por sondeo, y no por un clic, debe pedir `read`. Si no, un rol sin el
  permiso volvería a cargar la página en bucle. Hoy son cinco y lo cumplen:
  `checkSlugAction`, `getSeedMetricsAction`, `getRunAction`, `listPhonesAction` y
  `loadSearchIndexAction`.

`requireQAOperator()` y `QA_ROLES` desaparecen (D5).

## El aviso

Un componente del armazón lee `?sin-permiso=1`, enseña un aviso no bloqueante («Tu rol
no permite esa acción; no se hizo nada») y quita el parámetro de la URL sin recargar.

## El registro

Una línea estructurada por rechazo:

```json
{ "event": "operator.permission_denied", "operator_id": "…", "role": "viewer",
  "permission": "money", "target": "partners/actions.ts::rechargePartnerWallet" }
```

Nunca lleva los argumentos de la acción.

## La prueba estructural

`src/__tests__/server-actions-require-operator.test.ts`, la de la 078, ampliada. Barre
el código; no tiene una lista de sitios.

- Toda función exportada de un archivo `"use server"` empieza por
  `await requireOperator("<permiso>")`, con un literal de cadena que está en la matriz.
  Exentas: `loginAction` y `logoutAction`.
- Si delega en una función del mismo archivo (como `guarded()` en
  `models/actions.ts`), la llamada lleva el permiso como primer argumento literal
  (`return guarded("platform", (op) => …)`), y esa función empieza por
  `await requireOperator(permission)` con su primer parámetro. La prueba comprueba el
  literal en cada llamada y la forma de la función.
- Toda página y layout de servidor de `app/(dashboard)` empieza por
  `await requirePageOperator("<permiso>")` (en páginas puede ir dentro de un
  `Promise.all`, como en la 078). También su `generateMetadata` si lee la API.
- Todo handler exportado de cualquier `route.ts` de `app`, no solo de `app/api`, empieza por
  `routeOperator("<permiso>")` y devuelve su respuesta si es un rechazo.
- Una llamada sin argumento, con una variable o con un permiso que no existe hace
  fallar la prueba con el archivo y la función.

## La prueba de la matriz

- `src/lib/__tests__/permissions.test.ts` lee `operator_permissions.py`, extrae el
  diccionario y lo compara con `PERMISSIONS`. Falla en cuanto difieren.
- La misma prueba fija, rol por rol, la tabla de la spec (1.2).
- En la API, `tests/unit/test_operator_permissions.py` fija la misma tabla.
