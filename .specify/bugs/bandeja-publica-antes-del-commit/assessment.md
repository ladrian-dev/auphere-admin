# Bug Assessment: la Bandeja lite avisa en tiempo real antes de confirmar lo que avisa

- **Slug**: bandeja-publica-antes-del-commit
- **Created**: 2026-10-19
- **Source**: pasted text (revisión del prototipo de la app móvil de la Consola Lite, 2026-10-19)
- **Verdict**: valid
- **Severity**: medium

## Report (verbatim or summarized)

> Las acciones de la Bandeja de la Consola Lite en la API publican el evento de
> tiempo real en Redis (`inbox:{tenant_id}`, sin cuerpo) antes de que la
> transacción haga commit. `inbox.py` `_publish` (~l.293) se llama tras
> `flush()` (~523, 559, 608); `inbox_media.py` ~l.184; todo dentro del
> `async with session.begin()` de `lite/deps.py:46-51`. `docs/consola-lite.md:193`
> dice que se publica siempre después del commit. Worker (`dispatcher.py`,
> `pipeline.py`), webhook de Meta y `announce_waiting` sí publican tras commit.

Contexto: es requisito previo de la spec 031 (app móvil), que colgará sus avisos
push de estos mismos eventos.

## Symptom

Cuando una persona actúa en la Bandeja lite (tomar el control, devolver,
contestar, adjuntar, resolver, reabrir, etiquetar), la API publica
`conversation.updated` / `message.new` en `inbox:{tenant_id}` **mientras la
transacción sigue abierta**. Un suscriptor (la SSE lite, otra pestaña, otra
persona del equipo) recibe el aviso, vuelve a pedir la conversación por su
ruta y puede leer el estado **anterior** —lo escrito aún no está confirmado—, y
no vuelve a pedir nada porque el aviso ya pasó. Si la transacción hace rollback,
el aviso de algo que nunca ocurrió ya salió.

Lo esperado (y lo que dice `docs/consola-lite.md`): se publica **después** del
commit, y nada si la transacción no se confirma.

## Reproduction

1. Un cliente con Bandeja y dos personas (o dos pestañas) suscritas a
   `GET /console/lite/inbox/stream`.
2. La persona A hace `POST /console/lite/inbox/conversations/{id}/takeover`.
3. La API hace `flush()` y publica `conversation.updated` dentro de la
   transacción de `lite_scope`; la pestaña B recibe el aviso y pide
   `GET …/conversations/{id}` por otra conexión.
4. Si esa lectura llega antes del commit (que en FastAPI 0.136 ocurre en el
   cierre de la dependencia, **después** de enviar la respuesta), B ve la
   conversación aún con el agente activo y sin asignar, y se queda así.

Reproducible de forma determinista en test: un `publish` que, en el momento de
recibir el evento, lee la conversación por una conexión aparte ve el estado
previo a la acción.

## Suspected Code Paths

- `apps/api/src/nexus_api/api/console/lite/deps.py:46-51` — `lite_scope` abre
  `async with session.begin()` y hace `yield`; el commit ocurre al salir del
  bloque, en el cierre de la dependencia.
- `apps/api/src/nexus_api/api/console/lite/inbox.py:293` — `_publish` publica
  en el acto.
- `apps/api/src/nexus_api/api/console/lite/inbox.py` — llamadas a `_publish`
  tras `flush()` y dentro de la transacción: `take_over` (523), `give_back`
  (559), `send_message` (608), `resolve` (627), `reopen` (641), `set_tags` (695).
- `apps/api/src/nexus_api/api/console/lite/inbox_media.py:184` —
  `send_attachment` llama a `publish_inbox_event` tras `flush()`, igual.
- `docs/consola-lite.md:193` — afirma «siempre **después** del commit».

Referencias que lo hacen bien (publican fuera del `async with … begin()`):
`apps/worker/src/nexus_worker/runtime/dispatcher.py:483`,
`apps/worker/src/nexus_worker/runtime/pipeline.py:1914`,
`apps/worker/src/nexus_worker/streams/outbound.py:463`,
`apps/api/src/nexus_api/api/webhooks/meta.py:661` y
`apps/api/src/nexus_api/services/inbox_lifecycle.py:148` (`announce_waiting`,
que `mark_waiting` deja explícitamente para después del commit).

## Root Cause Hypothesis

Confianza: alta. Las rutas lite no controlan su transacción: la abre y la
confirma `lite_scope`, y la ruta solo ve la sesión. Sin un sitio donde dejar
trabajo «para después del commit», cada ruta publicó donde podía —tras el
`flush()`—, que es antes del commit. Con FastAPI 0.136 el cierre de una
dependencia `yield` de alcance `request` corre después de enviar la respuesta,
así que la ventana entre el aviso y el commit incluye todo el envío de la
respuesta.

## Proposed Remediation

**Preferred**: que `LiteScope` acepte trabajo para después del commit
(`scope.after_commit(fn)`), y que `lite_scope` lo ejecute **solo** cuando el
`async with session.begin()` sale sin excepción, es decir, tras un commit
confirmado. Si la ruta lanza o el commit falla, la excepción salta ese código y
no se publica nada. `_publish` en `inbox.py` y la publicación de
`inbox_media.py` pasan a registrar el aviso en vez de enviarlo. Un fallo de un
aviso no rompe los demás ni la petición (el tiempo real es comodidad).

Sirve tal cual para la spec 031: los avisos push se cuelgan del mismo punto.

**Alternatives**:
- `await scope.session.commit()` en cada ruta antes de publicar: rompe el
  contrato de `lite_scope` (la ruta deja de leer con `app.tenant_id`, que es
  `SET LOCAL` y muere con el commit) y obliga a recordarlo en cada ruta nueva.
- Un listener `after_commit` de SQLAlchemy sobre la sesión: es síncrono y no
  puede `await` un `publish` asíncrono sin lanzar tareas sueltas.

**Files likely to change**:
- `apps/api/src/nexus_api/api/console/lite/deps.py`
- `apps/api/src/nexus_api/api/console/lite/inbox.py`
- `apps/api/src/nexus_api/api/console/lite/inbox_media.py`
- `docs/consola-lite.md`
- `apps/api/tests/unit/test_lite_inbox_publish_after_commit.py` (nuevo)

**Tests to add or update**:
- Por cada acción que publica (tomar, devolver, contestar, adjuntar, resolver,
  reabrir, etiquetar): lo que lee un suscriptor por otra conexión **en el
  momento** de recibir el aviso es lo que quedó confirmado.
- Una acción cuya transacción hace rollback después de escribir no publica
  nada y no deja nada escrito.

## Risks & Considerations

- El aviso sale después de la respuesta HTTP (ya ocurría con el commit): la
  consola de quien actúa no depende del aviso, pinta su propia respuesta.
- La propia respuesta HTTP también sale antes del commit (cierre de dependencia
  de alcance `request`). Es otra carrera, de lectura-de-lo-propio, y no la cubre
  este arreglo; se deja anotada como seguimiento.
- Sin cambios de API, de esquema ni de contrato (`realtime.md`): mismos
  eventos, mismos campos, solo cambia el momento.
- Ninguna garantía de aislamiento tocada: el canal sigue siendo el del cliente
  de la sesión.

## Open Questions

- Ninguna que bloquee el arreglo.
