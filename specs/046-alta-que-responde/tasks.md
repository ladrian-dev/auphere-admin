# Tasks: un alta que termina en un agente que responde

## Iteración 1a · Canales en la consola como en Admin (PR 1)

- [X] T001 Constitución 1.2.0: el catálogo de canales de la consola enseña «Próximamente» (§V).
- [X] T002 API `GET /console/channel-catalog` con textos para el partner; test de forma y de que nada interno se filtra.
- [X] T003 Ya existía como `PATCH /console/clients/{ref}/channels/{id}/agent` (spec 030, `agents_list.py`), con sus tests en `test_agents_api.py`; el asistente la usa tal cual.
- [X] T004 Consola: asistente `clients/[ref]/channels/new` (Elegir canal → Conectar → Asignar agente → ¡Listo!), riel de pasos, tarjetas con logo; tests.
- [X] T005 Consola: detalles visibles (plurales, créditos fuera del selector de modelo, «Teammate» en pestañas, sin incidencia falsa en Canales).

Notas de la it. 1a (2026-10-24):
- La bifurcación por la app de escritorio (spec 002, R12.7) se mudó de la página de canales al paso «Conectar»; sigue siendo una sola (`shell-detect.test.ts`).
- El paso 3 escribe siempre el papel del número; solo asigna agente a un número que atiende.
- `t()` elige la variante `.one` cuando la cuenta es 1; un test prohíbe los «(s)».
- Verificado en local con una copia de la base (`nexus_046`) y un número falso: los cuatro pasos, en escritorio y a 375 px.

## Iteración 1b · Ningún cliente mudo sin saberlo (PR 2)

- [ ] T010 Worker: el control de saldo después de guardar el mensaje; `skipped_reason` para todos los motivos.
- [ ] T011 API: activar exige agente publicado, canal que conversa y saldo; códigos traducibles.
- [ ] T012 Canal degradado sigue recibiendo; una sola definición de «tiene dinero»; zona horaria validada; reconectar conserva la configuración.
- [ ] T013 Consola: «Por qué no responde» en la ficha; estado coherente; errores del alta visibles y que se limpian; errores del servidor traducidos.

## Iteración 2 · Encender tu agente (PR 3)

- [ ] T020 API: alta atómica; validación de relleno al publicar; `go-live`; modo prueba; Playground sobre borrador.
- [ ] T021 Consola: recorrido de cinco pasos con 6 grupos de plantillas, «Datos del negocio», pregunta de WhatsApp y detección de la primera respuesta.

## Iteración 3 · El Companion lo hace contigo (PR 4)

- [ ] T030 Herramientas `propose_go_live`, `propose_signup_link`, `propose_audience`; arreglos de `propose_client`.
