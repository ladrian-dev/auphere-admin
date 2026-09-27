# Iteración 2 · Capacidades e Integraciones — evidencia

Una pantalla donde había dos, y una pantalla propia para lo que estaba de
prestado. Herramientas y Habilidades cierran.

## Prototipo (T030)

- Story: `packages/ui/src/stories/prototypes/capabilities.stories.tsx`
  (`Prototipos/Capacidades`), nueve estados: Con sector · Ver todas · Sin
  sector · Todo conectado · Buscando · Sin resultados · Solo lectura ·
  Catálogo vacío · Móvil.
- Cómo verlo: `preview_start storybook` (Node ≥ 22.12) →
  `http://localhost:6006/?path=/story/prototipos-capacidades--con-sector`.
- **Aprobación del owner: 2026-09-26** («Me gusta, puedes continuar»), tras
  responder a las tres preguntas de diseño que bloqueaban.

### Las tres decisiones del owner (2026-09-26)

1. **Avisar, no bloquear.** A una capacidad a la que le falta su integración
   se la puede encender: encenderla es decir «la quiero», y empieza a
   funcionar en cuanto se conecte. Bloquearla castigaba al partner por un
   orden que no eligió. Esto **cambió la tarea T032**, que pedía un 409.
2. **«Nunca», no «Bloqueada».** El modo se lee en lenguaje de negocio.
3. **El bloque de integraciones desbloquea, no duplica.** Aparece en
   Capacidades solo si algo visible depende de una integración sin conectar,
   dice cuántas capacidades desbloquea cada una, y no ofrece pausar,
   desconectar ni sincronizar: eso vive en su pestaña, y hacerlo desde aquí
   rompería en silencio lo que el partner está mirando.

## Lo que se construyó

**API**

- `api/console/capability_names.py`: 60 capacidades con nombre y descripción
  de negocio en ES/EN, función, sectores y de qué conector dependen.
- `api/console/capabilities_client.py`: `GET`/`PUT
  /clients/{ref}/capabilities`. Un cambio por llamada — la pantalla vieja
  mandaba la lista blanca entera y dos personas editando a la vez se
  pisaban sin enterarse.
- Companion: `console.get_client_capabilities` (no `console.get_capabilities`,
  que ya es el documento de plataforma desde CO-08).

**Consola**

- `components/capabilities/{catalog,capability-card,blocking-integrations}.tsx`
  y `clients/[ref]/capabilities/{page,actions}.tsx`. El filtro por sector
  viaja en la URL (`?all=1`): así «Ver todas» se puede compartir y volver
  atrás hace lo que el partner espera.
- `components/integrations/{connector-card,integrations-list}.tsx` y
  `clients/[ref]/integrations/{page,actions,loading,error}.tsx`. La lista
  ordena por lo que necesita atención (roto → sin conectar → pendiente →
  pausado → conectado), no alfabéticamente.
- `/tools` y `/skills` pasan a `permanentRedirect` a `/capabilities`; la
  pestaña «Habilidades» sale del menú.

## Defectos encontrados y corregidos en esta iteración

Ninguno de estos estaba en la lista de tareas: salieron de escribir los
tests y de leer el código que ya estaba.

| Qué | Cómo salía | Corregido |
|---|---|---|
| Encender una habilidad no contaba como cambio | La entrada guarda `skill_id`, no `name`; el diff del borrador miraba `name` | `agent_drafts.py` |
| La hoja de revisión listaba seis cambios por una edición | El formulario de ajustes escribe la política entera | `settings_changes()` ignora lo ausente en `before` cuyo `after` es el defecto |
| Se podía encender una herramienta `INTERNAL`/`DEPRECATED` | La lectura las esconde, la escritura no las filtraba; salía bien solo por el rollback, y por una rama marcada `pragma: no cover` | La comprobación se hace **antes** de escribir |
| «Por defecto» no deshacía nada | Guardaba el valor por defecto **como** override, así que la ayuda «lo has fijado tú» se quedaba para siempre | `mode: "default"` borra el override |
| Una habilidad sin publicar mentía dos veces | Decía «requiere una herramienta o canal que falta» (falso: falta que la subamos) y contestaba 404 «no existe» (existe) | `activatable` en la lectura, «Aún no disponible» en la tarjeta, 409 `skill_not_published` |
| `connectors.error` decía «las herramientas siguen disponibles» | En la pantalla nueva las integraciones **son** la pantalla | Texto reescrito |
| 41 claves de copy sin dueño | Al cerrar las dos pantallas, su copy quedó describiendo un producto que ya no existe | Borradas |

## Suites (2026-09-27, rama `develop`)

| Suite | Resultado |
|---|---|
| `apps/console` (vitest) | 75 ficheros, **429 tests** en verde |
| `tests/integration/test_console_capabilities.py` | **17** en verde |
| `tests/isolation/test_42_capabilities_whitelist_scoped.py` | **5** en verde |
| `tests/unit/test_companion_tools_catalog.py` | **94** en verde |
| Companion isolation (5 ficheros) | **184** en verde |
| `e2e/record.spec.ts` | **10** en verde (2 saltados: sin credenciales de builder/analyst) |
| `e2e/a11y.spec.ts` | **26** en verde, incluidas `/capabilities`, `/capabilities?all=1` e `/integrations` |
| lint · typecheck (consola) · ruff · mypy | limpios |

**Accesibilidad**: cero violaciones serias o críticas de axe en las tres
vistas nuevas, sin scroll horizontal a 360 px ni a 1920 px, con el texto
inflado al 130 %, en español y en inglés.

**Comprobado por mutación**: quitar el filtro «solo las que cambian» del
botón de lote pone rojo su test (3 llamadas en vez de 2). Un test que no
sabe fallar no es evidencia.

## Verificación en el stack local

- `/clients/panaderia-la-espiga/integrations` lista las cuatro integraciones
  con «Desbloquea N capacidades» y «0 de 4 conectadas».
- `/tools` y `/skills` acaban en Capacidades.
- Servidor recién arrancado: **cero errores** en el log.

## Paridad

`parity.md` §Iteración 2, filas 24–62. Todas cerradas. La fila 57 —qué hacer
con una capacidad que no se puede activar— se resolvió el 2026-09-27: no es
una cuestión de política sino de si existe el dato. Sin `skill_id` no hay
nada que escribir, así que sigue sin poder encenderse; lo que cambia es que
se dice la verdad sobre de quién depende.

## Lo que queda fuera, a propósito

- **T002** (claves i18n de toda la spec) sigue abierta; esta iteración añadió
  las suyas (`cap.*`, `int.*`) y borró 41 huérfanas.
- **T009**, la barrida de aislamiento de los endpoints de la iteración 1.
- El test de claves huérfanas solo vigila el carril del puesto de trabajo;
  el barrido completo del diccionario sigue siendo deuda anotada en la KB.
