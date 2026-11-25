# Especificación: el panel solo obedece a operadores activos

**Rama**: `hotfix/admin-actions-require-operator` · **Creada**: 2026-11-25 · **Estado**: Hotfix P0, spec retroactiva (excepción §2 de `docs/spec-driven-development.md`)

**Entrada**: revisión de seguridad del 2026-11-22 (informe provisional, fuera del repo). Luis, 2026-11-25: «también trabajemos en el P0 para solucionarlo».

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | El panel de operadores (`apps/admin`): sus Server Actions, sus páginas y sus rutas de `app/api`. No se abre ni se cierra ninguna ruta de la API. |
| **Garantías de aislamiento tocadas** | **Ninguna de las 7.** Se protege el acceso al panel, que habla con la API con el token de servicio. La guarda es una prueba estructural en `apps/admin`, no en `tests/isolation/`: lo que comprueba vive en TypeScript. |
| **Nota de KB que la justifica** | Ninguna: hotfix P0. |
| **Qué se mide** | **Nada.** |

## Por qué

El panel llama a la API con un token de servicio, así que la API no sabe qué operador pide cada cosa. Quien decide si se obedece es el panel, con `requireOperator()`. Había dos huecos:

- varias Server Actions no llamaban a `requireOperator()`;
- `requireOperator()` dejaba pasar a una cuenta deshabilitada (`access: "disabled"`), y nada más la frenaba.

## Requisitos

### 1. Toda acción comprueba al operador

1.1 WHEN se ejecuta cualquier función exportada de un archivo `"use server"` de `apps/admin/src` THEN el sistema DEBE llamar a `requireOperator()` **como primera sentencia**, directamente o devolviendo una función del mismo archivo que empiece por ella. No vale dentro de un `try` (el `catch` se traga la redirección), ni después de leer o escribir, ni en un `Promise.all`.

1.2 Las únicas excepciones son `loginAction` y `logoutAction` (`app/(auth)/login/actions.ts`), que abren y cierran la sesión.

1.3 WHEN alguien añade una acción sin la comprobación THEN una prueba DEBE fallar y nombrar el archivo y la función.

### 2. Una cuenta deshabilitada no opera

2.1 WHEN `requireOperator()` resuelve una sesión con `access !== "ok"` THEN el sistema DEBE llevarla a `/sin-acceso` y no devolver el operador.

2.2 `/sin-acceso` dice que la cuenta ya no puede operar y ofrece cerrar sesión. Sin sesión lleva a `/login`; con una cuenta activa, a `/tenants`.

2.3 WHEN una ruta de `app/api` del panel recibe una sesión con `access !== "ok"` THEN DEBE contestar 403 sin llamar a la API.

2.4 El login no cambia: una cuenta deshabilitada con la contraseña buena entra y ve `/sin-acceso`. El mensaje del login sigue siendo el mismo para cualquier fallo (ADR-034).

### 3. Toda página comprueba al operador

Next no vuelve a ejecutar un layout al navegar entre las páginas que lo comparten: la guarda de `(dashboard)/layout.tsx` no protege las lecturas de cada página, que van con el token de servicio. Lo encontró la revisión independiente del 2026-11-25.

3.1 WHEN se pinta una página o un layout de servidor de `app/(dashboard)` THEN el sistema DEBE llamar a `requireOperator()` como primera sentencia de su función por defecto. Antes solo puede leer `params`/`searchParams`, y en páginas la guarda puede ir dentro de un `Promise.all`: una página solo lee, y si la guarda redirige no se envía nada.

3.2 WHEN un `generateMetadata` lee la API THEN DEBE empezar igual.

3.3 WHEN alguien añade una página sin la guarda THEN una prueba DEBE fallar y nombrarla.

### 4. Después del login, solo a una ruta del panel *(enmienda, 2026-11-25)*

El login vuelve a `?from=`. El middleware lo rellena con una ruta propia, pero cualquiera puede escribir un enlace al login con otro valor. Con `//otro-sitio`, el operador acababa en otra web justo después de un login de verdad.

4.1 WHEN el login termina THEN el sistema DEBE volver a `from` solo si, resuelto contra el origen del panel, sigue en ese origen; si no, DEBE volver a `/tenants`.

### 5. Un solo token de servicio, y nunca el de desarrollo en producción *(enmienda, 2026-11-25)*

5.1 El token con el que el panel llama a la API DEBE salir de un único sitio (`lib/admin-token.ts`). Ningún otro archivo lee `NEXUS_ADMIN_TOKEN` ni repite el valor de desarrollo.

5.2 WHEN el panel corre en producción (`NODE_ENV=production`) sin `NEXUS_ADMIN_TOKEN` o con un valor `change-me` THEN DEBE fallar al hacer la llamada, con un mensaje que nombre la variable. La API ya se niega a arrancar así en producción. Se comprueba al llamar y no al cargar, para que `next build` no lo necesite.

## Fuera

- **El rol.** `requireOperator()` mira si la cuenta está activa, no su rol. Un operador `viewer` («Solo lectura» en su menú) puede ejecutar cualquier acción. Lo trata una spec aparte.
- Un stream de conversación abierto sigue vivo si se deshabilita la cuenta mientras está conectado.
- Que la API sepa qué operador pide cada cosa (token por operador). Es el arreglo de fondo y lleva su propia spec.
- El resto de hallazgos de la revisión del 2026-11-22.
