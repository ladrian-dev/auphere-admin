# El puesto de trabajo en la aplicación de escritorio

**Spec viva.** Describe lo que existe hoy en `apps/desktop`, `apps/api` y
`apps/console` para la identidad y el puesto de trabajo de la máquina del
partner. Si cambias lo que describe, este documento va **en el mismo commit**
(`docs/spec-driven-development.md` §3). Especificaciones de origen:
`specs/001-puesto-trabajo-partner/` (ejecución local, contención, lista blanca)
y `specs/002-identidad-app-escritorio/` (identidad, emparejamiento, dueño de la
máquina).

## Qué es la aplicación

Una **cáscara** de Electron con dos vistas en una `BaseWindow`:

| Vista | Partición | `preload` | Qué carga |
|---|---|---|---|
| Consola | `persist:auphere-console` (persistente) | **ninguno** | `https://console.auphere.com` — las pantallas son las de la consola, no se reimplementan |
| Barra del puesto | `auphere-bar` (no persistente) | `bar-preload.cjs`, seis funciones | `dist/bar/index.html`, 44 px, abajo |

El ambiente del agente vive en una tercera partición (`auphere-agent`, no
persistente) y no alcanza ninguna de las otras dos. `session-isolation.ts` lo
comprueba al arrancar y `tests/session-isolation.test.ts` lo afirma.

**La consola no puede hablarle a la cáscara.** Sin `preload` en su vista no hay
canal. El canal entre la consola y la barra es la persona: la consola muestra un
código, la persona lo teclea en la barra.

## Cómo entra una persona

Con el login de la consola, dentro de la ventana. La aplicación **no tiene
flujo de autenticación propio** (`tests/no-own-auth.test.ts`) y no guarda
ninguna credencial de backend: en su partición solo hay la cookie opaca de la
consola. El alta de un partner es un acto de Auphere seguido de una invitación
por correo; no hay registro.

Quién está dentro lo lee el **proceso principal** con
`GET /api/session/whoami` del BFF, con la cookie de la partición humana, al
arrancar y en cada cambio de la cookie `nexus-console.session`
(`src/session-gate.ts`, `src/electron/adapters.ts`). La respuesta trae también el
idioma de la cuenta, y la barra lo adopta para hablar como la consola:

| `whoami` | La barra | El puente |
|---|---|---|
| 200 `{user_id, partner_slug, locale}` con credencial guardada para ese `user_id` | `conectada` (en el idioma de la cuenta) | arranca |
| 200 sin credencial, nadie más emparejó | `sin_emparejar` | parado |
| 200 sin credencial, otra persona emparejó | `sin_emparejar` + «emparejada por otra persona» | parado |
| 401 (sin sesión) · 403 `no_membership` | `sin_sesion`, sin oferta de emparejar | parado |

## Cómo se empareja una máquina

1. En la consola, `/workstation` → «Emparejar esta máquina» →
   `POST /console/workstation/pairing-codes` (permiso `workstation:pair`:
   owner · admin · builder). Código de 8 símbolos del alfabeto
   `ABCDEFGHJKMNPQRSTVWXYZ23456789`, mostrado `XXXX-XXXX`, **una sola vez**;
   la base guarda su hash. Diez minutos; un código vivo por persona.
2. En la barra, «Introducir código» → `POST /device/pair`
   (`{code, hostname, platform, app_version}`; sin credencial: el código lo es).
   Un solo cuerpo para todo fallo (`404 pairing_code_invalid`); cinco fallos por
   máquina → `429` con `Retry-After` creciente.
3. La respuesta trae la credencial **una vez**. La aplicación la guarda cifrada
   con `safeStorage` en `userData/credentials.bin`, en un mapa por `user_id`
   (`src/credential-store.ts`). Sin cifrado disponible no se guarda nada y la
   barra lo dice.

La máquina queda a nombre del **partner y de la persona** que pidió el código
(`partner_devices.partner_id`, `principal_id`).

## La credencial y sus cinco operaciones

JWT HS256, claims `{svc: "device", sub: device_id, pid: partner_id, gen}`,
12 h. **No lleva tenant.** `require_device` (`api/device_bridge.py`) verifica
la firma y **carga la fila** en cada petición: archivada → `403
device_archived` con motivo; generación vieja fuera de la gracia de 60 s →
`401`; treinta días sin latir → `403 pairing_required`.

| Operación | Ruta | Ámbito |
|---|---|---|
| Latir | `POST /device/heartbeat` | partner · solo mueve `last_heartbeat_at` |
| Sondear | `GET /device/poll` | partner · devuelve `work[]` y `links[]` (clientes vinculados y cuáles no tienen directorio) |
| Devolver resultado | `POST /device/result` | tenant del asiento, comprobado dentro del partner |
| Renovar | `POST /device/renew` | partner · `gen + 1`; la anterior vale 60 s más |
| Declarar directorio | `POST /device/links` | tenant resuelto desde `client_ref` **dentro del partner**; ajeno → `404` con asiento |

La máquina renueva sola cuando le quedan menos de 6 h (`AppRuntime.maybeRenew`).

`/workstation` refresca sus datos con la cadencia del latido mientras la
pestaña está visible (`components/workstation/presence-refresh.tsx`): la
presencia se ve sin recargar a mano.

## De quién es una máquina, y quién la ve

`partner_devices` lleva RLS **forzada con dos políticas OR**: la dueña
(`app.partner_id` + `app.principal_id`) y el gestor (`app.partner_id` +
`app.workstation_manager = 'true'`, que la dependencia de consola fija solo con
`workstation:write`). Sin GUC, cero filas. `PartnerDeviceRepository.list_visible`
no filtra nada: la RLS decide (`test_30`).

Los clientes a los que sirve una máquina y el directorio de cada uno viven en
`device_client_links`, por tenant (RLS de tenant) y legibles por quien ve la
máquina (política de lectura por máquina). El directorio se declara **desde la
máquina** con el selector nativo (`src/directory-declare.ts`, cuatro
comprobaciones); la consola no acepta rutas.

La presencia de un tenant pasa por sus vínculos con directorio cuya máquina late
y no está archivada (`services/device_presence.tenant_presence`).

## Cerrar sesión, desemparejar, archivar

| Acto | Dónde | Qué pasa |
|---|---|---|
| Cerrar sesión | Cuenta, en la consola | la cookie cambia → `whoami` 401 → el latido para, la barra dice `sin_sesion`; la credencial se conserva sellada para la misma persona |
| Desemparejar | la barra | la aplicación **olvida** la credencial y deja de latir; la máquina queda `ausente` hasta que alguien la archive |
| Archivar | `/workstation` → Archivar, o la pertenencia retirada | `revoked_at` + motivo (`archivada_consola` · `pertenencia_retirada` · `desemparejada`); el siguiente latido recibe `403 device_archived` y la barra pasa a `archivada_desde_consola`. Terminal: se empareja otra |

## Los siete estados de la barra

`sin_emparejar · emparejando · conectada · reconectando · sin_sesion ·
volver_a_emparejar · archivada_desde_consola` — `src/bar-state.ts`. Ninguno se
pinta como error; las herramientas locales solo existen en `conectada`; el
latido solo corre en `conectada` y `reconectando`.

## Lo que la consola sabe de la cáscara

Una sola cosa: el agente de usuario lleva `AuphereDesktop/<versión>`
(`lib/shell-ua.ts`). Se usa en **un solo sitio** — la página de canales, que
dentro de la aplicación sustituye la conexión de Meta por «continúa en el
navegador» — y `shell-detect.test.ts` afirma que no hay un segundo.

## Auditoría

`audit_log`, filas de partner (`target = partner:<id>`, `tenant_id` NULL) salvo
la declaración de directorio, que es del tenant del cliente. Vocabulario:
`device.pair_code_issued` · `device.paired` · `device.pair_denied` ·
`device.renewed` (actor `device:<id>`) · `device.link_declared` ·
`device.link_denied` · `device.unpaired` · `device.archived` (migración `0108`).

## Desarrollo local

```bash
docker compose up -d
cd apps/api && uv run alembic upgrade head && uv run uvicorn nexus_api.main:app --reload
cd apps/console && pnpm dev                     # http://localhost:3110
cd apps/desktop && pnpm build && \
  AUPHERE_CONSOLE_URL=http://localhost:3110 AUPHERE_API_URL=http://127.0.0.1:8000 pnpm start
```

La variable `AUPHERE_DEVICE_TOKEN` **ya no existe**: la credencial se obtiene
emparejando. `scripts/enrol_device_dev.py` se borró con la spec 002.
