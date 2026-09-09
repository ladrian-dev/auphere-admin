# Quickstart — validar el recorrido de punta a punta

**Rama**: `002-identidad-app-escritorio` · **Fecha**: 2026-09-09

Recorre la Historia 1 entera y toca las otras cuatro. Cada paso dice qué se
espera ver; si no se ve, el paso está en rojo.

## Prerrequisitos

```bash
docker compose up -d                                  # Postgres + Redis + API
cd apps/api && uv run alembic upgrade head            # llega a 0107
uv run pytest tests/isolation/ -x                     # 733 + test_30 en verde
cd ../console && pnpm dev                             # http://localhost:3000
cd ../desktop && pnpm build && AUPHERE_CONSOLE_URL=http://localhost:3000 AUPHERE_API_URL=http://localhost:8000 pnpm start
```

Un partner con dos clientes (`cultor`, `retail-sur`) y dos personas (owner y
builder) — el seed de `quickstart` de la 001 vale, más una invitación aceptada.

## §1 · Primera apertura (R1)

- La ventana muestra el login de la consola; la barra dice **«Esta máquina no está
  emparejada»**. No hay ningún control apagado.
- `ls ~/Library/Application\ Support/Auphere/` **no** contiene `credentials.bin`.

## §2 · Entrar (R2)

- Login con el owner. La barra sigue en `sin_emparejar`.
- Cerrar sesión desde Cuenta → la barra no cambia (no había puente).
- Entrar con una cuenta sin pertenencia → `no-access` de la consola, **sin** barra
  de emparejar.

## §3 · Emparejar (R3, Historia 1)

- Home → tarjeta «Tu puesto de trabajo» con cuatro pasos; el primero señalado.
- `/workstation` → «Emparejar esta máquina» → código `XXXX-XXXX` con cuenta atrás.
- Barra → «Introducir código» → teclear en minúsculas y con guion → `emparejando`
  → **`conectada`** con «MacBook-de-Luis.local».
- `/workstation` lista la máquina con **dueño = owner**, `presente`.
- Volver a canjear el mismo código → «ese código ya no vale».
- `credentials.bin` existe y **no** contiene texto legible (`strings` no encuentra
  `eyJ`).

## §4 · Clientes y directorios (R4, R7, Historia 2)

- En la máquina: «Clientes» → añadir `cultor` y `retail-sur`. Sondeo siguiente:
  la barra dice «falta el directorio de 2 clientes».
- Barra → Directorios → `cultor` → selector nativo → carpeta válida → guardado.
  Elegir un fichero o una carpeta sin permiso → mensaje con la condición que
  falla; **nada** guardado.
- `retail-sur` sin directorio: en el playground de `retail-sur` el teammate **no**
  tiene `shell_local`; en el de `cultor`, sí.
- Declarar `retail-sur` → el teammate de `retail-sur` lista su directorio y no
  alcanza el de `cultor` (`test_30` lo automatiza).
- **Una** fila en `partner_devices`, **una** credencial, **dos** vínculos.

## §5 · Renovación (R10)

- Forzar `credential_rotated_at` y `gen` en la base → la app renueva en el
  siguiente ciclo; `audit_log` tiene `device.renewed` con actor `device:…`.
- Poner `last_heartbeat_at` a hace 31 días → la barra pasa a **«Hay que volver a
  emparejar»**; sin herramientas locales.

## §6 · Cerrar sesión, desemparejar, archivar (R11, Historia 4)

- Cerrar sesión desde Cuenta → en < 5 s la barra dice **«Sin sesión»**; en 30 s
  `/workstation` (en el navegador) muestra `ausente`. Volver a entrar con la misma
  persona → `conectada` sin código.
- Entrar con el builder en la misma app → «Emparejada por otra persona · empareja
  la tuya» (Historia 5). Emparejar → dos máquinas con el mismo hostname y dueños
  distintos.
- Barra → Desemparejar → `sin_emparejar` con «archívala desde la consola si no vas
  a volver»; `credentials.bin` ya no tiene la entrada; `/workstation` la muestra
  `ausente` en 30 s. Desde `/workstation` → Archivar → aparece archivada con persona,
  fecha y motivo `archivada_consola`.
- Volver a emparejar; desde `/workstation` (owner) → Archivar → en < 1 min la barra
  dice **«Archivada desde la consola»** y deja de latir (`last_heartbeat_at` no
  avanza).
- Quitar al builder del equipo → su máquina aparece archivada con motivo
  `pertenencia_retirada`.

## §7 · Consumo y Meta (R8, R9, R12.7)

- `/usage` dentro de la ventana funciona igual que en el navegador. La barra no
  muestra ninguna cifra. `usage_ledger` no tiene asientos nuevos por nada de lo
  anterior.
- Cliente → Canales → conectar Meta: dentro de la app **no** hay botón; hay
  «Continúa en el navegador» con el enlace. En el navegador, el botón está.

## §8 · Auditorías de la barra y de `/workstation`

```bash
# en el repo, con el dev server arriba
/a11y-audit apps/desktop/src/bar  &&  /responsive-audit apps/console/src/app/(console)/workstation
```

Cero hallazgos 🔴. `grep -rn "#[0-9a-fA-F]\{6\}" apps/desktop/src/bar` → vacío.
