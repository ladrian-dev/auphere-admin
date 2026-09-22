# Research — Fase 0, spec 012

Lo que había que resolver antes de diseñar. Cada decisión lleva por qué se
eligió y qué se descartó. Las evidencias de partida están en
`.specify/assessments/maquina-sin-emparejar/research.md`; aquí solo va lo que
**el plan** necesitaba y que aquél no cerraba.

---

## 1 · Atomicidad de «retirar todo el acceso» (R1.2)

**Decisión: una sola transacción de SQLAlchemy. No hace falta nada más.**

La pregunta era si se podía, porque las dos mitades viven en sitios que *parecen*
distintos: `console_auth.principal_sessions` y `partner_devices`.

**No son distintos.** `CONSOLE_AUTH_SCHEMA = "console_auth"`
(`db/models/console_identity.py:33`) es un **esquema del mismo Postgres**, y los
dos modelos heredan del mismo `Base` (`db/base`), luego comparten engine y
sesión. Una transacción cubre las dos tablas y el `ROLLBACK` deshace las dos.

**Alternativas descartadas:**

- *Dos operaciones con compensación* (cerrar sesiones, y si falla archivar,
  volver a abrirlas): imposible de hacer bien —un token cerrado no se «reabre»—
  y resolvía un problema que no existe.
- *Cola de trabajo asíncrona*: retirar el acceso tiene que ser inmediato. Una
  cola convierte «ya no puede entrar» en «no podrá entrar dentro de un rato», que
  es justo lo que hoy está mal.

**Lo que sí hay que vigilar, y no es la atomicidad:** la RLS. `partner_devices`
está protegida por partner, pero `archive_all_for_principal`
(`repositories/local_workstation.py:138-147`) **corre con el rol dueño a
propósito** y su docstring lo dice: «es mantenimiento de plataforma que ocurre
cuando la persona ya no está». Eso significa que la garantía que hay que probar
aquí no es la RLS: es que **la operación no alcance a nadie más que a la persona
nombrada** (R1.5). Es un test de aislamiento distinto al habitual, y por eso
tiene su propia tarea.

---

## 2 · De qué campo sale «sesión recién confirmada» (R3.2)

**Decisión: del momento de apertura de la sesión, no del de último uso. Umbral:
una hora.**

`ConsoleSession` tiene los dos campos y son cosas distintas
(`db/models/console_identity.py:96-101`):

- `created_at` — cuándo se abrió la sesión, o sea, **cuándo la persona entró por
  el navegador**. No se mueve.
- `last_used_at` — se mueve con cada petición que la usa.

Usar `last_used_at` sería un error silencioso y merece decirse por qué: una
sesión abierta hace seis días y usada hace diez segundos daría «recién
confirmada» siendo exactamente el caso que R3.2 quiere atajar. **Tener la app
abierta no es haber demostrado nada.**

**El umbral, una hora.** Es el estándar de re-autenticación para acciones
sensibles (el *sudo mode* de GitHub y equivalentes). En el camino normal
—instalar, entrar, volver— la sesión tiene segundos de vida y no se nota. Solo
muerde en el caso que debe morder: abrir la aplicación en una máquina sin
registrar con una sesión vieja.

**Alternativas descartadas:**

- *Minutos (5-15)*: obligaría a entrar de nuevo en escenarios legítimos —salir a
  comer entre instalar y registrar— sin comprar seguridad real, porque el
  atacante que tiene la cookie también la tendría hace cinco minutos.
- *Sin umbral (Opción A de la evaluación)*: descartado en la puerta de decisión.
  Deja viva la única objeción honesta.
- *Pedir la contraseña*: reintroduce una ceremonia y encima una peor, porque
  pone la contraseña en juego en una pantalla más.

**Nota de coherencia con la 011:** la sesión tiene caducidad absoluta de siete
días y **no se renueva** (`console_identity.py:77`). Así que «vieja» aquí
significa como mucho siete días, y el umbral de una hora parte ese rango en dos
de forma razonable.

---

## 3 · Por dónde viaja el registro (R3.1)

**Decisión: una ruta nueva en el BFF de la consola, llamada desde el proceso
principal de Electron con la cookie de la partición humana. Devuelve la
credencial una vez.**

El camino ya está abierto y en uso para otra cosa
(`apps/desktop/src/electron/main.ts:665-671`). El motivo de que pase por el BFF
y no por la API está escrito en el código, y no es una preferencia de estilo
(`apps/console/src/app/api/desktop/redeem/route.ts:9-12`):

> La ruta de la API exige la credencial de servicio del BFF
> (`require_console_service`), y la cáscara no tiene ninguna ni puede tenerla.

Y hay un test que existe **por un fallo ya desplegado** —llamar directo a la API
y recibir `401 Missing bearer token`—, o sea que este camino ya se equivocó una
vez y quedó vigilado.

**La diferencia con `redeem`, y es la que hay que diseñar con cuidado:**
`redeem` contesta `204` sin cuerpo porque lo que entrega es una **cookie**, que
viaja sola a la partición. Aquí lo que se entrega es una **credencial que la
aplicación guarda cifrada**, así que la respuesta lleva cuerpo. Eso hace que esta
ruta sea la única del BFF que devuelve un secreto, y de ahí sale el Requisito 7:
una sola vez, sin poder releerla.

**Alternativas descartadas:**

- *Que la aplicación llame a la API directamente*: no tiene credencial de
  servicio ni puede tenerla. Es el fallo que ya se desplegó.
- *Reutilizar `/api/desktop/redeem`*: mezcla dos cosas que atan sujetos
  distintos —una persona y una máquina—. ADR-039 ya avisó de exactamente esta
  confusión: «se parecen y atan cosas distintas».

---

## 4 · Dónde se comprueba el permiso (R3.3)

**Decisión: en la ruta del BFF, antes de llamar a la API; y la API la vuelve a
comprobar por su cuenta.**

Hoy `workstation:pair` se comprueba al **emitir** el código
(`api/console/workstation_partner.py:174`) y `POST /device/pair` **no comprueba
nada** — leído entero: sus dependencias son la sesión de base de datos y Redis.
Al retirar la emisión, la comprobación se queda sin sitio, así que se muda al
único punto donde ahora se decide.

**Las dos comprobaciones, no una.** El BFF comprueba para poder decir que no
pronto y bien; la API comprueba porque es la que emite el secreto y no puede
fiarse de que su llamante haya mirado. Es el mismo patrón que la regla del
`CLAUDE.md` para la consola de partners: «la API re-verifica membresía».

**Cuidado con la doble definición**: el permiso está declarado en dos sitios que
tienen que coincidir, `core/console_auth.py:117` y
`apps/console/src/lib/permissions.ts:26-27`, y el segundo está **congelado por
test**. Si el conjunto de roles cambiara —y no debe— habría que tocar los dos.
Aquí no cambia: se mueve dónde se comprueba, no quién lo tiene.

---

## 5 · Migraciones

**Decisión: una sola, y al final.**

| Requisito | ¿Migración? | Por qué |
|---|---|---|
| R1 (retirar acceso) | **No** | `revoked_at`/`revoked_reason` ya existen, y `"desemparejada"` ya está en el CHECK de motivos (`db/models/local_workstation.py:97-105`) |
| R2 (desemparejar revoca) | **No** | Ídem. El motivo estaba declarado **sin escritor**; esto le pone el escritor |
| R3 (registro por sesión) | **No** | No hay dato nuevo: la máquina ya se da de alta igual, cambia quién lo pide |
| R4 (tope) | **No** | Es una cuenta sobre filas que ya existen |
| R5 (carpeta al frente) | **No** | `device_client_links` ya existe |
| R6 (retirar el código) | **Sí, una** | Elimina `device_pairing_codes` |

La única migración es **destructiva** y por eso va la última, cuando ya nadie
escribe en esa tabla. Se ensaya arriba, abajo y arriba —el repositorio ya lo hizo
así con la 0123— y su `downgrade` tiene que recrear la tabla vacía: no se
restauran códigos, que son secretos de diez minutos, pero sí la forma, para que
bajar no deje el esquema roto.

---

## 6 · Qué se conserva del código que se retira (R7)

La spec 009 dejó la lista al retirar el **otro** código
(`specs/009-…/spec.md:64-65`): «la tabla, el TTL de diez minutos, el uso único,
el hash y el rechazo indistinguible». Traducida a lo que aquí queda:

| Propiedad | Cómo aplica al canje nuevo |
|---|---|
| **Uso único** | La credencial se entrega una vez y no se puede releer. Ya es así (`PairedOut`: «se devuelve una sola vez») y se conserva |
| **Rechazo indistinguible** | R3.4. Ahora hay **más** motivos que distinguir que antes —sin sesión, sesión vieja, sin permiso, en el tope— y todos tienen que dar la misma respuesta |
| **Límite de intentos** | R3.5. El limitador existente va sobre `hostname+IP`; el canje nuevo tiene sesión, así que la clave natural pasa a ser la persona |
| **Hash en reposo** | **Deja de aplicar, y eso es una mejora, no una pérdida.** Ya no hay código que guardar: el secreto que había en la base desaparece con la tabla |

Sobre R7.4 («ningún secreto en claro»): tras retirar la tabla, **el único secreto
que queda en reposo es la credencial de máquina en el llavero del sistema**, que
ya está cifrada y fuera del alcance de esta spec. En la base de datos no queda
ninguno del registro. Eso es lo que hay que comprobar, y se comprueba buscando.

---

## 7 · El tope de máquinas (R4)

**Decisión: cinco activas por persona, y se rechaza en vez de archivar sola.**

No hay dato de producción que respalde un número. Se elige el que no estorba a
quien trabaje normal —portátil, sobremesa, y sitio para reinstalar y probar— y
que hace ruido si algo va mal.

**Rechazar, no archivar automáticamente.** Archivar la más antigua sería cómodo
de implementar y una sorpresa desagradable: la «más antigua» puede ser la que
está ejecutando algo ahora mismo. Y como archivar es terminal, la sorpresa no se
deshace. Decir «tienes cinco, retira una» deja la decisión donde hay contexto.

**Las archivadas no cuentan** (R4.3). Si contaran, el tope se agotaría solo con
el tiempo, porque cada restablecimiento de contraseña archiva todas (D-6) y
crearía filas nuevas. Sería un tope que se cierra solo: un defecto, no una
política.

---

## 8 · Lo que este research NO resolvió

- **Si alguien tiene hoy más de cinco máquinas activas** en producción. Si lo
  hubiera, el tope le rompería el trabajo al entregarse. Es una consulta barata
  y va como tarea de comprobación previa, no como supuesto.
- **Qué hace exactamente la aplicación si el registro falla por red** en el
  primer arranque. Hay estados para «sin emparejar», pero el estado «entré y no
  se pudo registrar» es nuevo y su pantalla se diseña en la fase de tareas.
