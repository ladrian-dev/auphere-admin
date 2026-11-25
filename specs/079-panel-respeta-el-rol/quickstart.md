# Cómo se comprueba: el panel respeta el rol del operador

Guía para validar cada fase de punta a punta. Los detalles están en
[`contracts/`](contracts/) y en [`data-model.md`](data-model.md).

## Antes

- La API local con su base (`docker compose` del repo) y el panel con `pnpm dev` en
  `apps/admin`.
- Tres operadores locales, uno por rol, con el script de alta:

```bash
cd apps/api && uv run python scripts/seed_operator.py --email admin@local.test --role admin
```

```bash
cd apps/api && uv run python scripts/seed_operator.py --email qa@local.test --role qa_operator
```

```bash
cd apps/api && uv run python scripts/seed_operator.py --email viewer@local.test --role viewer
```

El script imprime una contraseña por cuenta, una sola vez.

## Fase 1 — pruebas automáticas

```bash
cd apps/admin && pnpm vitest run src/__tests__/server-actions-require-operator.test.ts src/lib/__tests__/permissions.test.ts
```

```bash
cd apps/api && uv run pytest tests/unit/test_operator_permissions.py
```

Esperado: verde. Para ver que la prueba estructural muerde, se quita el permiso de una
acción cualquiera (`requireOperator()` sin argumento) y la prueba falla nombrando el
archivo y la función.

## Fase 1 — recorrido en el navegador

| Con | Hacer | Esperado |
|---|---|---|
| `viewer` | Abrir Partners, una ficha, Clientes, una ficha, Consumo, Estado | Todo se lee; no hay ningún botón de escritura, ni apagado ni explicado |
| `viewer` | Abrir el menú lateral y ⌘K | No aparecen Playground QA ni las altas |
| `viewer` | Ir a `/tenants/new` escribiendo la URL | «No encontrada» |
| `viewer` | Abrir las conversaciones de un cliente | Se leen, también en vivo |
| `qa_operator` | Pausar y reanudar un cliente; abrir el Playground | Funciona |
| `qa_operator` | Ficha de un partner | No hay «Recargar», «Rotar clave» ni «Suplantar» |
| `admin` | Lo mismo | Todo como hoy |
| `admin` → `viewer` | Con una ficha abierta como `admin`, cambiar el rol con el script y pulsar «Recargar» | La página se vuelve a pintar sin el botón y avisa de que no se hizo nada; el saldo no cambia |

Después, el registro del panel tiene una línea `operator.permission_denied` con el
operador, el permiso y la acción, sin datos del cliente.

## Fase 2 — pruebas automáticas

```bash
cd apps/api && uv run pytest tests/unit/test_admin_routes_declare_permission.py tests/integration/test_panel_operator_credential.py
```

Esperado: verde. Comprueban que cada ruta `/admin/*` declara su permiso, que el token de
servicio solo no basta, que un `viewer` recibe 403 en una escritura y que la auditoría
nombra a la persona.

## Fase 2 — a mano, contra staging

Con el panel desplegado, una escritura de un `admin` aparece en la auditoría con su
correo. Una llamada a una ruta de escritura con el token de servicio y sin sesión de
operador recibe 401.
