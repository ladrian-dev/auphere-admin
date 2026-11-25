# Modelo de datos: el panel respeta el rol del operador

No hay tablas nuevas ni columnas nuevas. Cambia un valor por defecto, y la matriz es
código, no datos.

## Operador (`operator_auth.principals`, ya existe)

| Campo | Cambio |
|---|---|
| `role` | `admin` · `qa_operator` · `viewer` (la restricción `ck_operator_principals_role` no cambia). El `server_default` pasa de `qa_operator` a `viewer`, con migración. Las filas existentes no se tocan. |
| `disabled_at` | Sin cambio. Una cuenta deshabilitada no tiene ningún permiso (spec 078). |

No pertenece a ningún tenant y no tiene RLS: es la identidad del equipo de Auphere
(ADR-034).

## Sesión del operador (`operator_auth.principal_sessions`, ya existe)

Sin cambio de forma. En la fase 2 pasa a ser también la credencial que el panel
presenta en cada llamada a `/admin/*` (research D9). La clave primaria es el hash del
token, así que resolverla es una búsqueda por clave.

## Permiso (código)

Nueve valores fijos: `read`, `qa`, `operate`, `money`, `credentials`, `impersonate`,
`people`, `delete` y `platform`. Qué cubre cada uno está en
[`inventario.md`](inventario.md).

## Matriz (código)

Permiso → roles que lo tienen. Autoridad: `apps/api/src/nexus_api/core/operator_permissions.py`.
Copia vigilada: `apps/admin/src/lib/permissions.ts`.

| Permiso | `admin` | `qa_operator` | `viewer` |
|---|---|---|---|
| `read` | sí | sí | sí |
| `qa` | sí | sí | no |
| `operate` | sí | sí | no |
| `money` | sí | no | no |
| `credentials` | sí | no | no |
| `impersonate` | sí | no | no |
| `people` | sí | no | no |
| `delete` | sí | no | no |
| `platform` | sí | no | no |

Reglas:

- Un rol que no está en la matriz no tiene ningún permiso.
- Una cuenta con `access !== "ok"` no tiene ningún permiso, sea cual sea su rol.
- Cada acción, ruta y página declara **un** permiso.

## Transiciones

- **Cambio de rol** (script de alta con `--role`): surte efecto en la siguiente petición
  del operador, sin cerrar su sesión.
- **Alta sin rol**: `viewer`.
