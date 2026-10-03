# Plan de implementación: Recuperar la contraseña, y salir con la puerta cerrada

**Rama**: `011-recuperar-la-contrasena` | **Fecha**: 2026-09-23 | **Spec**: [spec.md](./spec.md)

---

## Resumen

Una tabla de peticiones en la partición de identidad, dos rutas públicas
—pedir y canjear—, dos pantallas en `(auth)/`, y **la transacción que ya estaba
esperando**: restablecer la contraseña llama a `revoke_all_access`, que la spec
012 construyó con su docstring diciendo que la 011 la usaría.

Una migración, la única. Superficie `0` + `3a`.

---

## Contexto técnico

**Lenguaje**: Python 3.11 (`apps/api`, `uv`) · TypeScript 5 + React 19 (`apps/console`)

**Dependencias principales**: ninguna nueva. FastAPI, SQLAlchemy 2, Alembic,
Pydantic v2, `httpx` — todas en el árbol

**Almacenamiento**: PostgreSQL, esquema `console_auth`. Una tabla nueva

**Pruebas**: `pytest` (unit, integration, isolation) · `vitest` (consola)

**Restricciones**: `send_email` **no lanza, devuelve `False`** · el rechazo no
puede ser un oráculo · `revoke_all_access` **no hace commit** a propósito

---

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; whitelist exhaustiva | ✅ | Ninguna garantía se debilita. La operación corre con **rol dueño** y la RLS no la protege: lo acota el `WHERE` por `principal_id`. `test_38` ya lo vigila para la 012; esta spec añade el suyo para el camino nuevo |
| II | Corte por superficie | ✅ | `0` + `3a`, declarado. **No abre nada**: el correo ya es autoridad de la cuenta desde `identity_link.py:72-90` — quien lo tiene verificado en Google entra hoy sin contraseña. Esto usa esa autoridad para quien no tiene Google |
| III | Lo leído es dato, nunca instrucción | ✅ | No aplica: aquí no hay modelo ni herramientas |
| IV | Acción `mutates` con aprobación durable; auditoría con nombre | ✅ | El asiento de retirada de acceso ya existe (vocabulario de la 012) y se reutiliza. La «aprobación» aquí es el propio enlace: uso único y caducidad |
| V | Estados honestos; la ausencia se diseña | ✅ | Es el principio que más aprieta: la pantalla dice **lo mismo** haya cuenta o no, y también cuando el envío falla. Y avisa **antes** de restablecer de que cerrará las sesiones |
| VI | Por API `console.*` | ✅ | Nada navega |
| VII | Test primero; el rojo antes | ✅ | Tres rojos que no son el camino feliz, enumerados abajo |
| VIII | Licencias enteras | ✅ | **Ninguna dependencia nueva** |
| IX | La KB es dueña del porqué | ✅ | Enlazada en el encabezado de la spec |

### Las tres puertas

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | Ninguna se debilita. Hace falta un test que fije que restablecer **no alcanza a otra persona** — es la única forma nueva de llegar a `revoke_all_access` | `T0xx` en `tests/isolation/` |
| **Licencias** | **Ninguna dependencia nueva.** Declarado y comprobable con `git diff` sobre `pyproject.toml` y `package.json` | `T0xx` |
| **Medidor** | **Nada nuevo se mide.** Ni modelo, ni reloj de máquina, ni herramienta de pago. Un correo por petición, acotado | `T0xx` |

---

## Las seis decisiones

### D-1 · La tabla, en `console_auth` y con el hash

`password_reset_requests`, hermana de `SignupRequest`
(`db/models/signup.py:49-90`), que es el precedente más cercano y está en
producción: `token_hash` `String(64)` con índice único, `expires_at`, y el
momento de uso.

**Lo que se guarda es el hash**, nunca el enlace (R1.4 y R5.2). Y vive en la
partición de identidad, que es **de persona y no de tenant**: la RLS de tenant no
aplica aquí y quien acota es el `WHERE` por cuenta.

**Pedir uno nuevo invalida los anteriores** (R1.6): un `UPDATE` que marca como
usadas las vivas de esa cuenta, en la misma transacción que crea la nueva. Sin
eso, tres peticiones dejan tres llaves buenas.

### D-2 · El rechazo no puede ser un oráculo, y eso manda sobre el orden del código

Cuatro caminos dan **la misma respuesta**: la dirección no tiene cuenta, el
envío falló, se pasó el tope, la cuenta está archivada.

**Consecuencia práctica y contraintuitiva**: la ruta de pedir **no puede
devolver códigos distintos** ni tardar de forma distinguible. El tope se
comprueba **antes** de mirar si la cuenta existe, para que el tiempo no delate; y
el envío se hace sin que su resultado cambie la respuesta.

*(Es la misma lección de la 012 R3.4, aplicada donde sí protege: aquí quien
llama **no ha demostrado ser nadie**, que es justo el caso en que uniformar sirve
de algo.)*

### D-3 · La transacción, y por qué la pieza no hace commit

`revoke_all_access` (`services/principal_access.py:45`) **no hace commit**, y su
docstring dice por qué: *«el llamante abre la transacción, porque es él quien
sabe qué más va dentro — en la spec 011, restablecer la contraseña irá en la
misma»*.

Así que el canje abre **una** transacción con las tres cosas dentro:
`set_password`, cerrar sesiones, archivar máquinas. R3.3 exige que o las tres o
ninguna, y esa es la única forma de cumplirlo.

**El motivo de archivado** es el vocabulario que la 012 sembró; se reutiliza, no
se inventa otro. **Comprobar leyendo la migración**, no suponerlo — es lo que
costó una enmienda en la 012.

### D-4 · Mailhog se cablea, y el circuito se recorre en local

`send_email` solo habla con Resend por HTTP (`services/email.py:1-8`). Mailhog
está en `docker-compose.yml:34-39` **sin conectar a nada**.

**Decisión: se cablea**, con un repliegue SMTP que se enciende **solo cuando no
hay clave de Resend y sí hay `NEXUS_SMTP_URL`**. En producción no hay `SMTP_URL`,
así que su camino no cambia ni un byte.

**Rechazado — escribir el enlace en los registros en desarrollo**: es la salida
fácil y es cómo un secreto acaba en producción. Un sumidero SMTP local no
comparte código con el camino de producción más allá de la elección del
transporte.

*(La alternativa honesta era escribir «este flujo no se prueba de punta a punta
en local». Se descarta porque CE-006 existe y porque el coste de cablear es una
función de veinte líneas.)*

### D-5 · Qué pasa después de restablecer

R2.5 pide que la pantalla **no mienta sobre cuál de las dos cosas hace**.

**Decisión: lleva a la entrada, diciendo que ya puede entrar.** No se inicia
sesión automáticamente.

**La razón es R3**: restablecer acaba de cerrar todas las sesiones de esa
persona. Abrir una nueva en el mismo acto es contradecir lo que se acaba de
hacer, y deja la duda de si la revocación alcanzó a todas. Que entre ella, con su
contraseña nueva, es la prueba de que el circuito funciona.

### D-6 · Los números, con su razón

| Qué | Valor | Por qué |
|---|---|---|
| Caducidad del enlace | **1 hora** | Es el mismo umbral que la 012 fijó para «sesión recién confirmada», y por el mismo motivo: suficiente para ir al correo, corto para que un enlace olvidado en una bandeja no siga abriendo la cuenta |
| Techo de peticiones | **5 por dirección y hora** | Suficiente para quien no encuentra el correo; insuficiente para barrer direcciones. Reutiliza `one_time_code_limits`, que ya tiene la forma de dos claves y borra ambas al acertar |

---

## Lo que tiene que verse en rojo antes de implementar (§VII)

1. **La atomicidad (R3.3)** — no se ve por el camino feliz. Hay que **forzar un
   fallo entre las mitades** y comprobar que no queda una contraseña cambiada
   con las sesiones vivas. Si pasa sin haber roto nada, no prueba la atomicidad.
2. **El no-oráculo (R1.3)** — hay que comparar **carácter a carácter** la
   respuesta de una dirección con cuenta, una sin cuenta, una con el envío
   caído y una en el tope. Un test que solo mire el código de estado no ve la
   diferencia que importa.
3. **El alcance (R3.5)** — el test de aislamiento no se prueba restableciendo la
   propia: hay que montar **dos** personas con sesiones y máquinas, restablecer
   una, y comprobar que la otra **no se movió**.

---

## Orden de entrega

| # | Historia | Qué deja entregado | Migración |
|---|---|---|---|
| 1 | **H1** — pedir y canjear | Deja de hacer falta escribir un hash a mano en producción | **Sí, la única** |
| 2 | **H2** — retirar todo el acceso | Restablecer deja fuera a quien entró | No |
| 3 | **H3** — el aviso | Un secuestro silencioso pasa a ser uno que se ve | No |

**H1 no depende de H2**: el circuito de recuperación funciona sin la revocación,
y entregarlo solo ya retira el procedimiento manual. Pero **H2 no se puede
soltar indefinidamente**: sin ella, la pantalla de H1 no puede prometer lo que
R3.6 dice, así que su texto cambia según esté o no.

---

## Estructura

```text
apps/api/src/nexus_api/
├── db/models/console_identity.py        # D-1: PasswordResetRequest
├── services/password_reset.py           # pedir, canjear, invalidar las vivas
├── services/console_identity.py         # `set_password` ya existe, sin llamantes
├── services/email.py                    # D-4: repliegue SMTP solo en local
├── api/console/password_reset.py        # dos rutas públicas
└── alembic/versions/0128_*.py           # la ÚNICA migración

apps/console/src/app/(auth)/
├── forgot/page.tsx                      # pedir el enlace
└── reset/[token]/page.tsx               # elegir la nueva

apps/api/tests/
├── isolation/test_42_reset_scope.py     # R3.5
├── integration/test_password_reset.py   # el circuito, el no-oráculo, la atomicidad
└── unit/…
```

**El panel de operador no se toca.** La recuperación de un operador de Auphere
(`operator_identity`) es otra identidad y está fuera de alcance.

---

## Verificación

`./scripts/verify.sh` entero. Aquí se tocan **`apps/api`** y **`apps/console`**;
el worker **no** — pero se corre igual, porque «no debería moverse» no es una
comprobación, y este repositorio ha roto la tubería dos veces justo ahí.

**Una sola ejecución de `pytest` a la vez**, comprobada con `ps` antes de lanzar.

---

## Complexity Tracking

| Añadido | Por qué | Alternativa rechazada |
|---|---|---|
| Repliegue SMTP en `send_email` | Sin él, el circuito no se recorre en local y CE-006 queda sin cumplir | Escribir el enlace en los registros: es cómo un secreto acaba en producción |
| Invalidar las peticiones vivas al crear una nueva | Sin ello, tres peticiones dejan tres llaves buenas a la vez | Dejarlas vivas: multiplica la ventana de un enlace reenviado por error |
