# Investigación: datos al día en la consola

Spec 082 · 2026-11-26 · Validado en `main` `44a43298`.

## R1 — Por qué Luis no vio la cancelación

**Pregunta.** El 25-nov Luis canceló una reserva en la consola web y no vio el cambio hasta recargar. ¿Dónde falla?

**Lo que dicen los logs de prod** (`/nexus/prod/api`, líneas de acceso de uvicorn, 2026-11-25 17:08 UTC):

- `17:08:23` y `17:08:24`: lecturas de la agenda en **vista de semana** (`bookings?from=2026-11-23&to=2026-11-29`).
- `17:08:26` ficha (`GET /bookings/{id}`), `17:08:28` `cancel-preview`, `17:08:33.216` `POST …/cancel` 200.
- `17:08:33.869` a `17:08:34.239`: la relectura completa (`settings`, `staff`, `offers`, `bookings`, `waitlist`, `services`), **todas 200**. No hubo lectura parcial.
- `17:08:39`: la persona pasa a Ajustes (lecturas sin `bookings`, y `templates`).

Otro caso, el 20-nov a las 19:32: «No vino» respondió 200 a las `19:32:42.767` y, 1,4 s después, otro «No vino» sobre la misma reserva dio **412** (versión vieja). La ficha guarda su propia lectura y sus botones siguen activos mientras se guarda, así que un segundo clic manda otra orden.

**Lo que se probó y se descartó** (pruebas en `apps/console/e2e/datos-al-dia*.e2e.ts` y `apps/api/tests/integration/reservas/test_082_datos_al_dia.py`):

| Hipótesis | Cómo se probó | Resultado |
|---|---|---|
| La API responde antes de confirmar y la relectura no ve la cancelación | Prueba ASGI que apunta el orden entre el commit que lleva la reserva cancelada y el último trozo del cuerpo de la respuesta | **Descartada.** Se confirma antes de responder |
| `router.refresh()` no repinta la agenda | Playwright con `next dev` y una API simulada que confirma al momento: cancelar en día, semana, lista y por enlace `?booking=` | **Descartada.** Se repinta en las cuatro vías |
| Diferencia entre desarrollo y producción (prefetch de `<Link>`, caché del router) | Lo mismo con `next build` + `next start` | **Descartada** |
| Una lectura vieja en vuelo (el sondeo de 45 s) llega después y pisa la nueva | La simulada retiene 4 s una lectura tomada antes de cancelar | **Descartada.** Next ordena las relecturas |
| `useLastGood` conserva la lectura anterior porque una parte falla | Los logs: las seis partes dieron 200 | **Descartada** para este caso |

**Conclusión.** El fallo del 25-nov no se reproduce. Lo que sí queda probado:

1. La agenda depende de `router.refresh()` como **único** mecanismo para ponerse al día. No hay una lectura con identidad que se pueda invalidar, ni nada que releer cuando otro proceso cambia una reserva.
2. La ficha y la agenda leen por separado. Mientras se guarda, la ficha no se bloquea: eso explica el 412 del 20-nov.
3. Las reservas que hacen otros (el agente, la lista de espera, los automatismos) solo llegan con el sondeo: nadie emite `reservations.changed`.

**Decisión.** La agenda y la ficha pasan a una sola fuente de datos (React Query) que se invalida tras cada escritura y con cada aviso. La lectura sigue siendo la misma, la del servidor: se mueve de la página a una función que comparten la página (primera pintura) y una Server Action (relecturas). La prueba de navegador queda como regresión del requisito 1.1.

## R2 — Dónde emitir `reservations.changed`

**Pregunta.** Las reservas se escriben desde la consola (rutas lite), el agente (`apps/mcp`, de la 080), la lista de espera y los automatismos (`apps/worker`). ¿Cómo se avisa siempre, y solo tras confirmar, sin tocar el código de la 080?

**Hallazgo.** Toda escritura que cambia lo que la agenda enseña pasa por `core.add_event(...)`: crear, mover, cancelar, confirmar, llegó, no vino, deshacer, pedir confirmación, liberar, hecho y aceptar de la lista de espera. Las únicas otras escrituras sobre `reservations` son las de `calendar_sync`, que solo cambian `external_event_id` (no se ve en la agenda).

**Decisión.** `add_event` marca la sesión con el negocio que cambió (`session.info`). Un oyente de SQLAlchemy sobre `Session.after_commit` publica `reservations.changed` una vez por negocio y por transacción; `after_rollback` borra la marca. Así:

- vale para la API, el MCP y el worker sin tocar sus rutas ni sus herramientas;
- el aviso sale **después** del commit, y nunca si se deshace;
- la publicación es una tarea del bucle de eventos: no retrasa la respuesta y no puede tumbarla (como `publish_inbox_event`, nunca lanza).

**Alternativa descartada.** Publicar en cada ruta y en cada herramienta: deja fuera lo que no se mire (constitución §I: «un arreglo que se aplica donde se vio el defecto deja el defecto donde no se miró») y obliga a tocar `apps/mcp`, que es de la 080.

## R3 — La línea en vivo, compartida y para Reservas

- **Hoy** la Bandeja abre su propio `EventSource` y el contador de la barra sondea cada 60 s. La ruta de la API exige el módulo `inbox`.
- **Decisión.** Un solo `EventSource` por pestaña en el marco de la consola (`LiveStreamProvider`), solo para personas de un cliente con Bandeja o Reservas. Cada aviso invalida sus claves de React Query; la Bandeja se suscribe a la misma línea en lugar de abrir otra.
- La ruta de la API admite a quien tenga `inbox` **o** `reservas`. Reenvía los avisos de conversaciones solo a quien tiene `inbox`, y `reservations.changed` solo a quien tiene `reservas`. El canal sigue siendo el del negocio de la sesión.
- La ruta BFF declara `maxDuration = 300`: la plataforma la corta limpia y `EventSource` reconecta sola. Cada reconexión mint un token nuevo, así que una persona a la que se quita el acceso deja de recibir en la siguiente.
- **Al reconectar** (un `ready` después de un `error`) se invalida todo lo vivo y la Bandeja relee su lista y su conversación.

## R4 — React Query en la consola

- **Versión.** `@tanstack/react-query` `^5.108.4` (la última 5.x a 2026-11-26). `peerDependencies`: `react: ^18 || ^19`, compatible con React 19.2.4. La app del teléfono usa la misma serie (`^5.104.5`), fuera del workspace de pnpm.
- **Licencia.** MIT. El fichero `LICENSE` del paquete dice: «Permission is hereby granted, free of charge, to any person obtaining a copy of this software […] to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software». Permite el uso comercial y como servicio (constitución §VIII). Sin dependencias en tiempo de ejecución salvo `@tanstack/query-core`, también MIT.
- **Patrón.** El de `apps/mobile/src/api/query.ts`: claves jerárquicas (`["reservas", …]`, `["inbox", "counts"]`, `["agent", ref, id, "knowledge"]`), invalidación por aviso, relectura al recuperar el foco o la conexión, sin reintentar un 4xx, solo en memoria.
- **Sin credenciales en el navegador.** Las funciones de consulta llaman a las Server Actions que ya existen o a nuevas del mismo tipo; nunca a la API.
- **Primera pintura del servidor.** Cada consulta arranca con lo que leyó la página (`initialData`), con su hora, así que no hay un segundo viaje al cargar.

## R5 — El sonido

- **Web Audio, sin fichero**: dos tonos cortos (≈ 880 y 1320 Hz, 90 ms cada uno, envolvente de 10 ms) con `OscillatorNode` y `GainNode`. Sin licencias que leer.
- **Autoplay.** El `AudioContext` se crea al primer gesto de la persona en la página (`pointerdown` o `keydown`) y se reanuda si está suspendido. Antes de eso, no suena y no se dice nada.
- **Ajuste por navegador** en `localStorage` (`nexus.inbox.sound`), encendido por defecto, en el diálogo de ajustes de la Bandeja.

## R6 — El resumen del agente

`inbox_view.detail` toma `customer_summary` del último `escalated` de los 50 eventos más recientes. **Decisión**: se devuelve solo si no hay un `resolved` posterior a ese escalado y si el escalado no es anterior a `conversation.context_from`. Sin llamar al modelo.

## R7 — Avatar y nombre

- **Color por contacto.** Seis pares de fondo y texto, todos de tokens de `@nexus/ui` y verdes, neutros o el azul de información: nunca ámbar ni rojo. El índice sale de un hash estable del id de la conversación. Una prueba comprueba el contraste AA de cada par en los dos temas a partir de `tokens.css`.
- **Sin letras**, el icono `UserRound` de Lucide.
- **`@usuario`.** `customers.username` ya se guarda (migración 0206). Se añade `contact.username` al detalle de la conversación de la API lite.
- **Nombre de perfil.** `upsert_customer` guarda en `preferences.profile_name` el último nombre de perfil y actualiza `name` cuando cambia, salvo `preferences.name_by == "person"`, que pone `contact_customer` al crear un contacto desde Reservas con el nombre que escribió la persona. Sin migración.
