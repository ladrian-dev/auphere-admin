# Guía de comprobación: spec 056

Cómo se demuestra que la spec funciona. Las pruebas automáticas están en `tasks.md`. Esto es lo que se corre o se mira a mano.

## Antes

```bash
docker compose up -d
cd apps/api && uv run alembic upgrade head      # llega a 0227_notice_handled
uv run python scripts/dev_seed_client_access.py  # cliente con acceso y una persona
```

Para pytest en paralelo con otra sesión, usa una base propia: `NEXUS_DATABASE_URL=…/nexus_test_056`.

## 1 · El freno de citas (Requisito 1)

- **Unidad y pipeline:**

  ```bash
  cd apps/worker && uv run pytest tests/unit/test_booking_brake.py tests/unit/test_pipeline_booking_brake.py -q
  ```

  Esperado:
  - en es, en y pt, una afirmación sin respaldo se detecta;
  - «¿quieres que te reserve?» no;
  - con un `reservas.create` rechazado y `status: ok` no hay respaldo;
  - dos afirmaciones dan el paso a una persona.
- **Integración:**

  ```bash
  cd apps/api && uv run pytest tests/integration/test_booking_brake_turn.py tests/isolation/test_056_booking_brake_same_conversation.py -q
  ```

  Esperado:
  - `waiting_reason = booking_unbacked`;
  - la fila de auditoría `agent.booking_brake`;
  - el cobro de la clasificación dentro del turno;
  - una reserva de otra conversación no respalda.
- **Punta a punta en staging (CE-001)**, a mano y con las claves de Meta:

  ```bash
  cd apps/api && uv run pytest tests/release/test_booking_brake_staging.py -m manual_only -q
  ```

  Agente de pruebas con Reservas sin horario, 20 intentos. Esperado: cero salientes que confirmen una cita.

## 2 · Agentes y Negocio fuera (Requisito 2)

1. Entra en la consola como persona de un cliente que tenía Agentes y Negocio. La barra solo tiene sus otros módulos.
2. Abre `/agentes` y `/negocio`: llevan al primer módulo.
3. En la app (Expo, simulador): ni pestañas ni tarjetas de Inicio ni grupo en Ajustes. Un push de pausa abre Inicio.
4. Comprueba la migración:

   ```bash
   cd apps/api && uv run pytest tests/integration/test_migration_0224_client_modules_retire.py -q
   ```

## 3 · Acceso desde la consola de partners (Requisitos 3 y 4)

1. Como owner de un partner (local, partner de pruebas), abre un cliente › **Acceso**. Están las dos tarjetas.
2. Enciende Panel y Reservas (elige el modo). Guardado, y en Auditoría: «tu-correo cambió el acceso de …».
3. Invita a una persona. Sale el enlace una vez. Ábrelo en una ventana privada, acepta y entra: ve Panel y Reservas.
4. Revoca: confirmación en rojo, y la sesión de la ventana privada se cierra.
5. Como builder o analyst no hay pestaña, y `/clients/{ref}/access` da 404.
6. Aislamiento:

   ```bash
   cd apps/api && uv run pytest tests/isolation/test_console_scope.py tests/isolation/test_console_client_access_scope.py tests/isolation/test_lite_route_scope.py -q
   ```

## 4 · Horario y servicios (Requisito 5, CE-005)

1. En la ficha (partner), pon el lunes con tres turnos y uno que cruza la medianoche. Crea un servicio «Gratis» de 50 minutos.
2. Como cliente, en Reservas › Ajustes, cambia solo el martes y guarda. El lunes sigue igual.
3. Cambia el precio del servicio de 50 minutos: se guarda. Vuelve a «Gratis»: sigue «Gratis».
4. Intenta renombrarlo: el nombre no es editable.
5. Repite diez guardados alternos entre la ficha y Reservas. Nada cambia.

## 5 · Bandeja (Requisitos 6 a 9)

1. Con solo conversaciones resueltas: «No tienes conversaciones abiertas · 2 resueltas» y un botón a Resueltas.
2. Un escalado `agent_unpublished` se lee «Agente sin publicar» en la fila, el hilo y la actividad.
3. Escala una conversación y toma el control: el número de la campana baja.
4. Con dos agentes publicados, corrige una regla con «Todo el negocio». Como partner hay dos propuestas del mismo lote, y aceptarlo aplica las dos.

## 6 · Pulido (Requisitos 10 a 16)

- **Reservas (10.2)**: con Playwright contra staging, diez veces «Semana › Mes › Lista › Cuadrícula › Día › Día siguiente › Hoy». Las diez cargan, y en el registro `console.request_error` no aparece nada.
- **Error (10.1)**: fuerza un error en `/reservas` (API apagada). El texto está traducido, sin la frase de Next.
- **Acceso (14)**: con el navegador en inglés y sin cookie, la cabecera y el cuerpo de `/login` salen en inglés. Una ruta inventada con sesión enseña la 404 con el menú.
- **Sesión (15)**: con una sesión a 23 horas de caducar, sale el aviso una sola vez.
- **Formatos (13)**: «10,00 US$» en la ficha, en Reservas y en el Panel. El teléfono del contacto lleva «+».

## Cierre

```bash
./scripts/verify.sh lint
cd apps/console && pnpm typecheck && pnpm test -- src/i18n   # words.test.ts y no-orphan-keys
cd apps/admin && pnpm typecheck && pnpm test -- access
cd apps/mobile && pnpm gen:check && pnpm test
```

Además, los archivos de prueba tocados o nuevos, en la API y en el worker, cada suite por separado.
