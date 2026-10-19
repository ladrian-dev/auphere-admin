# Bug Fix: la Bandeja lite avisa en tiempo real antes de confirmar lo que avisa

- **Slug**: bandeja-publica-antes-del-commit
- **Fixed**: 2026-10-19
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`LiteScope` acepta trabajo para después del commit (`scope.after_commit(fn)`) y
`lite_scope` lo corre solo cuando su `async with session.begin()` sale sin
excepción. Las siete acciones de la Bandeja que avisan dejan ahí su
`publish_inbox_event` en vez de llamarlo tras el `flush()`: quien oye el aviso
lee lo confirmado, y un rollback no avisa de nada.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/api/console/lite/deps.py` | modified | `LiteScope.after_commit` + `_run_after_commit`; `lite_scope` lo corre tras el bloque de la transacción. Un fallo de un aviso se registra (`lite_scope.after_commit_failed`) y no tumba la petición ni los demás avisos. |
| `apps/api/src/nexus_api/api/console/lite/inbox.py` | modified | `_publish` pasa a síncrono y registra el aviso en `scope.after_commit`; las seis llamadas pierden el `await`. |
| `apps/api/src/nexus_api/api/console/lite/inbox_media.py` | modified | `send_attachment` usa `_publish` de `inbox.py` en vez de `publish_inbox_event` directo. |
| `docs/consola-lite.md` | modified | «Tiempo real»: quién publica (añade `announce_waiting`), qué acciones de la Bandeja avisan, y cómo se garantiza el «después del commit». |
| `apps/api/tests/unit/test_lite_inbox_publish_after_commit.py` | added test | 7 acciones + rollback + barrido de rutas. |

## Diff Highlights

```python
# deps.py — lite_scope
            async with session.begin():
                ...
                scope = LiteScope(principal=principal, tenant=tenant, session=session)
                yield scope
            # Solo se llega aquí si el bloque confirmó: una excepción de la ruta
            # o del commit hace rollback y salta esta línea.
            await scope._run_after_commit()
```

```python
# inbox.py
def _publish(redis, scope, conv_id, event="conversation.updated", **fields) -> None:
    async def _announce() -> None:
        await publish_inbox_event(redis, tenant_id=scope.principal.tenant_id, ...)
    scope.after_commit(_announce)
```

## Tests Added or Updated

- `test_lite_inbox_publish_after_commit.py::test_what_an_event_announces_is_already_committed[takeover|release|messages|attachments|resolve|reopen|tags]`
  — un suscriptor que, al oír el aviso, relee la conversación (estado, control,
  asignación, mensajes, etiquetas) por **su propia conexión** lee exactamente lo
  que quedó confirmado. Antes del arreglo, las siete en rojo: leía el estado
  previo a la acción.
- `…::test_an_action_that_rolls_back_announces_nothing` — tomar el control escribe
  y luego falla (`_detail_out` lanza): no queda nada escrito y no se oye ningún
  aviso. Antes del arreglo, rojo: el aviso ya había salido.
- `…::test_every_lite_route_that_announces_is_checked` — toda ruta lite de
  escritura que recibe su propio Redis (`redis = Depends(get_redis)`) está en la
  tabla de acciones de la primera prueba; una ruta nueva que avise no se escapa.

## Local Verification

- Rojo antes del arreglo: `uv run pytest tests/unit/test_lite_inbox_publish_after_commit.py`
  → 8 failed (las 7 acciones con «llegó antes del commit» y el rollback con un
  aviso oído), 1 passed (el barrido, que comprueba cobertura, no comportamiento).
- Verde tras el arreglo: el mismo archivo → 9 passed.
- `uv run pytest tests/unit/test_lite_inbox_*.py tests/unit/test_lite_by_agent.py tests/isolation/test_lite_*.py tests/integration/channels/test_member_messages_outbound.py`
  → 342 passed.
- `./scripts/verify.sh lint` → todo ok (ruff check/format y mypy --strict en
  api, worker, channels, mcp).
- `./scripts/verify.sh py` → ver `test.md`.

## Deviations from Assessment

- El barrido de rutas no puede usar «depende de Redis» a secas: **todas** las
  rutas lite dependen de Redis por debajo de `lite_scope` (la verificación de la
  persona). Se cuenta solo el Redis que la ruta recibe ella misma, que es con el
  que publica.
- `docs/consola-lite.md` también lista `announce_waiting` entre quienes publican;
  el párrafo lo omitía.

## Follow-ups

- La respuesta HTTP de las rutas lite sale antes del commit (cierre de
  dependencia `yield` de alcance `request` en FastAPI 0.136): la propia consola
  puede releer antes de que lo suyo esté confirmado, y un commit fallido llega al
  navegador como éxito. Es otra carrera, de lectura de lo propio; no la cubre este
  arreglo.
- El docstring de `services/inbox_stream.py` dice que publica «la API en cada
  acción de la Bandeja o del admin»; ninguna ruta del admin publica hoy.
- Spec 031 (app móvil): los avisos push pueden colgarse de `scope.after_commit`
  o de los mismos eventos, con la misma garantía.
