# Quickstart — cómo se comprueba la 063

## En local

```bash
./scripts/verify.sh lint
```

```bash
cd apps/api && uv run pytest tests/unit -k "063" -x
```

```bash
cd apps/api && uv run pytest tests/isolation/test_063_builder_foreign_names.py -x
```

```bash
cd apps/worker && uv run pytest tests/unit -k "063" -x
```

```bash
cd apps/console && pnpm vitest run -t "063"
```

Qué tiene que salir:

| Requisito | Prueba en local |
|---|---|
| 1 | La regla de idioma, sin límite, con límite y sin `policies.console`, como último mensaje de sistema del turno, también con un prompt que dice «Never answer in English». La reescritura del evaluador conserva el idioma. La sincronía de `voice` a la política al guardar. Que `merge_console_policy` conserve los idiomas. Que el validador rechace `languages_limited` cambiado por el constructor. |
| 2 | Que el resumen traiga `audience_mode`. Que la regla del principal (`agents.principal_agent_id`) dé el asignado, el vivo por defecto o el vivo más antiguo, y lo mismo en la página del canal y en la pestaña del agente. Que la tarjeta enseñe «Configurar», «No responde a nadie» y el estado sin agente. Que la conexión navegue a la configuración. Que el agente se vea «Listo · número sin configurar». |
| 3 | Que, con un modelo que lo admite, la llamada lleve `response_format`, comprobado con el transporte real y el mapa local en un subproceso, y que el registro diga `json_mode`. Que un JSON válido con «```» dentro se lea entero. Que `finish_reason="length"` dé `truncated`. Que un JSON roto registre tipo y posición sin texto. |
| 4 | Los cuatro casos de `research.md` §3 dan borrador. Una instrucción que nombra a otro cliente se quita sola. La plantilla responde `422 draft_invalid`. |

## En staging, después de desplegar `develop`

Sin datos de clientes reales: con los agentes de prueba del partner interno.

1. **Idioma (CE-001, CE-002).** Ejecutar los guiones de `repro/`
   (`research.md` §1). Es el mismo `ecs exec` en `nexus-staging-api`, pero sin
   sustituir nada, contra la versión publicada.
   - Esperado: inglés en 4 de 4, también tras una conversación en español y con
     «Never answer in English» en el prompt. Para este último caso sirve la versión
     activa de staging que ya lo lleva.
   - Luego, limitar uno a `es` y `en` desde «Cómo habla», publicar y escribirle en
     francés. Esperado: español en 4 de 4.
2. **Probador.** En la consola de staging, abrir el probador de un agente y escribir
   en inglés. Debe contestar en inglés.
3. **Canal (CE-003).** En un cliente de prueba:
   - Crear un agente y, ya publicado y sin número, pulsar su tarjeta en Agentes.
     Debe abrirse su página en la pestaña Canales, y no Canales del cliente.
   - Conectar un número desde Canales del cliente, sin número de prueba.
   - Al terminar se abre su configuración, con la barra de «Sin configurar».
   - De vuelta en Canales del cliente, la tarjeta dice «No responde a nadie».
   - La cabecera del agente dice «Listo · número sin configurar».
4. **Borrador (CE-004).** Generar dos borradores con descripción libre. En
   `/nexus/staging/runner`, `llm.call_complete` del rol `build` y el job en `done`.
5. **Plantilla (CE-005).** En un partner con un cliente llamado como una palabra
   corriente, crear un agente desde una plantilla que la use en otro de sus
   clientes. Esperado: borrador creado, sin 500.

## En producción, después del paso a `main`

- **CE-004:** durante dos semanas, `filter event="jobs.agent_draft.unavailable"` en
  `/nexus/prod/runner`. Ningún `why=bad_json`. Cualquier fallo, con su detalle. Antes
  de nada, comprobar que `builder.model_output` dice `json_mode=true`: si no, el
  arreglo no está encendido.
- **CE-005:** ningún `500` en `POST …/agents/draft-jobs` en `/nexus/prod/api`.
- **El número del partner que se quejó:** Luis le indica dónde decidir a quién
  responde. La spec no lo cambia por él.
