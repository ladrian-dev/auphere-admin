# Contrato — el despacho de trabajo local (puente v3)

Amplía `specs/002-identidad-app-escritorio/contracts/device-bridge-v2.md`. Las
cinco operaciones autenticadas siguen siendo cinco; cambian dos cuerpos.

## `GET /device/poll` → `work[]` deja de estar vacío

```json
{
  "work": [
    {
      "execution_id": "uuid",
      "client_ref": "cultor",
      "executable": "make",
      "args": ["test"],
      "cwd_relative": "src",
      "timeout_ms": 600000,
      "idle_timeout_ms": 300000
    }
  ],
  "links": []
}
```

- Solo ejecuciones en `pending` cuya máquina es **esta** (`local_executions.device_id`)
  y cuyo vínculo con el cliente sigue activo. Se marcan `dispatched_at` al
  entregarse; una ejecución no se entrega dos veces.
- `args` es lista; nunca cadena. `cwd_relative` es relativo al `workdir`
  declarado; la app vuelve a comprobar la contención (001).
- La app ya lo consume: `app-runtime.ts` (`kind: "execute"`) → `runExecuteMessage`.

## `POST /device/result` gana `stdout_sample`

```json
{
  "execution_id": "uuid",
  "outcome": "completada",
  "exit_code": 0,
  "children_reaped": 0,
  "stdout_sample": "…≤ 2048 bytes…"
}
```

- `stdout_sample` es opcional, ≤ 2 048 bytes, UTF-8 con reemplazo. **No** se
  persiste en `local_executions` ni en auditoría: viaja a Redis
  (`local_exec:{execution_id}`, TTL 15 min) y de ahí al resultado de la
  herramienta con `untrusted: true`.
- Si el run que esperaba ya no existe, el resultado se guarda igual en la fila
  (outcome, exit code) y la muestra se descarta.

## Presencia y ausencia

- Si no hay máquina presente con vínculo al cliente, `shell_local` **no
  despacha**: devuelve `{"refused": "machine_absent"}` al modelo y el hilo pinta
  `maquina_ausente` (R3.5). No se crea fila `pending`.
- Una ejecución `pending` cuya máquina deja de latir 5 min pasa a `expirada`
  con `denial_reason=dispositivo_ausente`, y el run que esperaba recibe
  `exec.completed {outcome: expirada}`.

## Auditoría

Sin cambios de forma: `local_executions` responde «qué pasó»; gana `task_id` y
`teammate_id` para leerlo desde el hilo. La consola lo lista en
`/console/clients/{ref}/workstation/executions` como hoy.
