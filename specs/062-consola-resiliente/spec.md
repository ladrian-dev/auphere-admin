# Especificación: La consola aguanta una API lenta

**Rama**: `062-consola-resiliente` · **Creada**: 2026-11-17 · **Estado**: Hotfix P0, implementado y verificado en la rama, pendiente del commit de Luis. Spec retroactiva (excepción «Hotfix P0» de `docs/spec-driven-development.md` §2), escrita el mismo día.

**Entrada**: descripción del usuario: "Revisa el estado de producción, a algunos clientes les da error." Y después: "Haz los dos arreglos". El primero es que la consola de prod llame a la API sin pasar por Cloudflare. El segundo, que una llamada lenta o cortada no tumbe la pantalla ni saque a nadie de su sesión.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la consola de partners y su cliente hacia la API, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **Ninguna.** Cada intento acuña su token con el mismo principal, que dura 60 s, y la API lo vuelve a verificar con `partner_memberships`. Reintentar no amplía qué puede leer ni escribir nadie. El token de un intento nunca sirve para otro, porque la API sigue quemando cada `jti`. La consola sigue sin credencial estática. |
| **Nota de KB que la justifica** | `[[bugs/2026-11-17-consola-lenta-por-cloudflare]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada.** No llama al modelo ni a herramientas de pago. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 056, **10.2** | La consulta de sesión tiene límite de tiempo y reintenta una vez lo que puede pasar solo: red, plazo agotado o 5xx. | Igual, pero **cada intento lleva un token nuevo** (requisito 1.1). El reintento con el token del primer intento era un 401 seguro cada vez que el primero había llegado. |

## Por qué

El 2026-11-17, desde las 18:34 UTC, la consola de producción tardaba y a veces
mostraba «No se pudieron cargar los clientes» o «No se pudo cargar esta
pantalla». A veces también devolvía a `/login` a una persona con la sesión
válida. La API estaba sana todo el tiempo.

Sus funciones (Vercel `iad1`) llamaban a `api.auphere.com` por Cloudflare, y
Cloudflare las atendía en Tokio y São Paulo. Desde allí, la respuesta del origen
tenía un p99 de 26,4 s. El detalle está en la nota de KB.

Una llamada lenta no debería tumbar una pantalla. Lo hacía por tres fallos de
`apps/console/src/lib/backend.ts`:

1. **La consulta de sesión reintentaba con el mismo token.** La API quema cada
   `jti` la primera vez que lo ve: si el primer intento había llegado tarde, el
   segundo era un 401 y la persona acababa en `/login`.
2. **Ninguna otra llamada reintentaba un fallo de conexión.** Una conexión que no
   se abre en los 10 s de undici, o que se corta, lanzaba una excepción y la ruta
   caía entera.
3. **Las lecturas no tenían límite de tiempo.** Una página podía quedarse colgada
   minutos.

Cloudflare puede volver a hacerlo, y la red siempre fallará alguna vez. La consola
tiene que aguantarlo.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Una API lenta no saca a nadie de su sesión (Prioridad: P1)

Una persona navega por la consola mientras la red hasta la API va lenta. La
primera consulta de su sesión tarda más de 5 s y se abandona. La segunda sale con
un token nuevo y la API la contesta. La persona sigue dentro.

**Prueba independiente**: la consulta de sesión agota su plazo en el primer
intento y contesta en el segundo; el token del segundo es distinto del primero.

**Escenarios**:

1. **Dado** que el primer intento de la consulta de sesión agota su plazo,
   **cuando** se reintenta, **entonces** el segundo intento lleva un token
   distinto y su respuesta es la que vale.

### Historia 2 — Un corte de red no tumba la pantalla (Prioridad: P1)

Rafael edita los servicios de un cliente. Una de las diez lecturas que hace la
página se corta a mitad. La consola la repite una vez y la página se pinta.
Cuando guarda, la conexión no llega a abrirse: como nada salió hacia la API, la
consola lo vuelve a intentar y el cambio se guarda una sola vez.

**Prueba independiente**:
- una lectura con `ECONNRESET` se repite y se pinta;
- una escritura con `UND_ERR_CONNECT_TIMEOUT` se repite;
- una escritura con `ECONNRESET` no se repite.

**Escenarios**:

1. **Dado** que una lectura falla por red, por plazo agotado o con 5xx, **cuando**
   es el primer intento, **entonces** se repite una vez con un token nuevo.
2. **Dado** que una escritura falla porque la conexión no llegó a abrirse,
   **cuando** es el primer intento, **entonces** se repite una vez con un token
   nuevo.
3. **Dado** que una escritura falla después de haberse enviado (conexión cortada,
   plazo agotado o 5xx), **entonces** no se repite y el error llega a la pantalla
   como hoy.

### Historia 3 — Una lectura perdida no deja la página colgada (Prioridad: P2)

Una lectura que no contesta en 15 s se abandona y se repite una vez. La página
termina en unos 30 s como mucho, en vez de esperar sin fin.

## Requisitos *(obligatorio)*

**1. Un token por intento**

- 1.1 WHEN la consola repite una llamada a la API THEN el sistema DEBE acuñar un token nuevo para ese intento.
- 1.2 WHEN la consulta de sesión recibe un 401 THEN el sistema DEBE tratarlo como «no hay sesión» sin repetirla.

**2. Qué se repite**

- 2.1 WHEN una lectura (GET), o una llamada marcada como repetible, falla por red, por plazo agotado o con un 5xx THEN el sistema DEBE repetirla una vez.
- 2.2 WHEN cualquier llamada falla porque la conexión no llegó a abrirse (`UND_ERR_CONNECT_TIMEOUT`, `ECONNREFUSED`, `ENOTFOUND`, `EAI_AGAIN`, `EHOSTUNREACH`, `ENETUNREACH`, sueltos o agrupados por dirección) THEN el sistema DEBE repetirla una vez, aunque sea una escritura.
- 2.3 WHEN una escritura falla después de enviarse, o recibe un 5xx THEN el sistema NO DEBE repetirla.
- 2.4 WHEN la respuesta es un 4xx THEN el sistema NO DEBE repetirla.
- 2.5 WHEN quien llama cancela la llamada THEN el sistema NO DEBE repetirla.
- 2.6 WHEN el segundo intento también falla THEN el sistema DEBE entregar ese error al llamante. Nunca hay más de dos intentos.
- 2.7 WHEN el sistema repite una llamada THEN DEBE dejar una línea `console.backend_retry` con método, ruta sin query, número de intento y motivo, sin el token ni el cuerpo.

**3. Plazos**

- 3.1 WHEN la consola hace una lectura THEN el sistema DEBE abandonar cada intento a los 15 s.
- 3.2 WHEN la consola hace una escritura THEN el sistema NO DEBE poner un plazo propio, porque el constructor puede tardar minutos. Quien llama puede pasar el suyo.
- 3.3 WHEN la consola consulta la sesión THEN el sistema DEBE mantener el plazo de 5 s por intento (spec 056, 10.2).

**4. Sin Cloudflare de servidor a servidor (configuración de prod)**

- 4.1 WHEN la consola de producción llama a la API THEN DEBE hacerlo por un nombre solo DNS que llegue directo al ALB de prod con certificado válido, como staging. Hoy es `https://webhooks.auphere.com`.
- 4.2 WHEN se cambie ese nombre THEN el cambio DEBE quedar escrito en `infra/README-console.md`.

## Criterios de éxito

- **CE-1**: ningún 401 `console_auth.replayed_jti` en `/nexus/prod/api` causado por un reintento de la consola.
- **CE-2**: en una tanda de `/login` de prod y de staging alternados, prod no va peor que staging.
  - Medido el 2026-11-17 a las 20:43–20:46 UTC, ya sin Cloudflare: prod p50 0,34 s y máximo 1,59 s; staging p50 0,47 s y máximo 1,24 s.
- **CE-3**: ningún `fetch failed` ni `TimeoutError` en los errores de producción de Vercel del proyecto `auphere-console`, salvo los que llegan tras el segundo intento.

## Fuera de alcance

- **Por qué Cloudflare elige esos centros de datos.**
- **Un host propio para la consola.** Sería solo DNS y tendría su certificado en el listener, en lugar de reutilizar el de Meta. Es Terraform en prod y va aparte.
- **El panel de admin.** También llama por Cloudflare, pero hoy entra por Newark.
- **Los flujos en vivo** (Playground, Bandeja, teammates, companion). Sus manejadores llaman a la API con `fetch` propio, sin este reintento. Al ir sin Cloudflare, el balanceador los corta tras 60 s sin datos, en lugar de los 100 s de Cloudflare, igual que en staging.
- **El 500 de `demo-farmacia` del mismo día.** Es una carrera en `section_write.ensure_profile` y es otro bug.
