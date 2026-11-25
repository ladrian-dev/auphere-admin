# Contrato: la credencial del operador ante la API (fase 2)

Lo que el panel manda y lo que la API exige en cada llamada a `/admin/*`. Decisiones
en [`research.md`](../research.md) D9–D13.

## Qué manda el panel

En cada llamada, desde cada sitio que ya llama a `adminToken()` (D10):

| Cabecera | Valor | Dice |
|---|---|---|
| `Authorization` | `Bearer <NEXUS_ADMIN_TOKEN>` | «Soy el panel», como hoy. |
| `X-Operator-Session` | El token de sesión del operador, el mismo de su cookie | «Soy esta persona». |

`X-Operator-Id` deja de enviarse.

Las llamadas de login (`/admin/auth/login`) y de resolver la sesión
(`/admin/auth/session`, `/admin/auth/logout`) siguen yendo solo con el token de
servicio: todavía no hay sesión, o la sesión va en el cuerpo.

Ni el panel ni la API registran nunca el valor de `X-Operator-Session`.

## Qué hace la API

Una dependencia, `require_panel_operator(permission)` en `api/admin/operator.py`:

1. Comprueba el token de servicio (como hoy).
2. Lee `X-Operator-Session` y la resuelve con el mismo código que
   `/admin/auth/session`: hash, caducidad y cuenta activa.
3. Lee el rol **de la base**, nunca de la petición.
4. Comprueba el permiso de la ruta con `core/operator_permissions.py`.
5. Devuelve el operador; las escrituras lo usan como actor de la auditoría.

| Caso | Respuesta |
|---|---|
| Sin token de servicio, o uno que no es | 401, como hoy |
| Sin `X-Operator-Session` en una ruta que actúa por un operador | 401 `{"detail": {"code": "operator_session_required"}}` |
| Sesión inexistente, caducada o de una cuenta deshabilitada | 401 `{"detail": {"code": "operator_session_invalid"}}` (las tres iguales, como el login) |
| Rol sin el permiso | 403 `{"detail": {"code": "permission_denied", "permission": "<permiso>"}}` |
| Todo bien | La ruta, como hoy |

Sustituye a `require_operator`, `require_enabled_operator`, `operator_from_header` y a la
cabecera de `require_qa_operator`. En QA, el `app.operator_id` que usa la RLS sale del
operador verificado.

## Cómo declara una ruta su permiso

```python
@router.post("/{partner_id}/wallet/purchased")
async def recharge_wallet(
    ...,
    operator: OperatorAccount = Depends(require_panel_operator("money")),
): ...
```

Una ruta que no actúa en nombre de un operador lo declara con
`Depends(panel_service_route("<razón>"))`, y solo se admite si está en la lista de
rutas de servicio de abajo.

## Rutas de servicio

La lista cerrada (research D12):

| Ruta | Razón |
|---|---|
| `POST /admin/auth/login` | Abre la sesión: aún no la hay. |
| `POST /admin/auth/session` | Resuelve la sesión, que va en el cuerpo. |
| `POST /admin/auth/logout` | Cierra la sesión, que va en el cuerpo. |
| `GET /admin/integrations/tiktok/callback` | La abre el navegador del dueño del negocio; se confía en el `state` firmado, sin token de servicio. |

Añadir una exige cambiar esta lista y la de la prueba de barrido en el mismo cambio, con
su razón.

Los guiones y pruebas que hoy llaman a `/admin/*` a mano con el token de servicio
pasan a entrar como operador o se retiran (research D12).

## Las pruebas

- **Barrido** (`tests/unit/test_admin_routes_declare_permission.py`): recorre
  `app.routes`. Toda ruta bajo `/admin` depende de `require_panel_operator` con un
  permiso de la matriz, o de `panel_service_route` y está en la lista. Si no, falla con
  el método y la ruta.
- **Credencial** (`tests/integration/test_panel_operator_credential.py`), una prueba por
  fila de la tabla de respuestas, y además:
  - el token de servicio sin sesión no escribe nada;
  - un `viewer` recibe 403 en una escritura y la base no cambia;
  - un `admin` escribe y la auditoría nombra su correo;
  - un operador deshabilitado a mitad de sesión recibe 401 en la llamada siguiente.
- **Panel** (`src/lib/__tests__/operator-session-header.test.ts`): todo archivo que llama
  a `adminToken()`, salvo `operator-auth.ts`, manda también `X-Operator-Session`.
