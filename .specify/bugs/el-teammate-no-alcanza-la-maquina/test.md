# Bug Verification: el teammate alcanza la máquina y ve lo que pasó

- **Slug**: el-teammate-no-alcanza-la-maquina
- **Tested**: 2026-09-20
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: **verified**. Los cuatro defectos.

## Los tests se escribieron primero

**D2 — la salida no llegaba al modelo.** `tests/unit/test_teammate_sees_what_it_ran.py`,
2 casos. El primer intento dio rojo por un motivo equivocado —mi doble del toolbelt
estaba incompleto y el grafo ni llegaba a `execute`—, así que **se reutilizó el
`FakeActionBelt` que ya existía** y se volvió a medir. Con el doble bueno:

```
2 failed  →  (arreglo)  →  2 passed
```

Y se comprobó que el rojo era del defecto y no del andamio: con `content = None`
forzado en el nodo, los dos vuelven a fallar. Restaurado después.

**D3 — stderr y el final.** `apps/desktop/tests/executor-sample.test.ts`, 5 casos:
`5 failed → 5 passed`.

**D1 — la presencia.** `tests/integration/test_teammate_reaches_the_machine.py`, 8
casos. Rojo por ausencia: `principal_presence` no existía.

## Checks Performed

| Check | Command | Result | Notes |
|---|---|---|---|
| D2 | `pytest tests/unit/test_teammate_sees_what_it_ran.py` | **pass** | 2 |
| D3 | `vitest run executor-sample` | **pass** | 5 |
| D1 | `pytest tests/integration/test_teammate_reaches_the_machine.py` | **pass** | 8 |
| Escritorio entero | `pnpm --filter @nexus/desktop exec vitest run` | **pass** | 932 en 96 ficheros |
| Worker | `pytest tests/ -q` | **pass** | 419 |
| D4 | `pytest tests/integration/test_execution_carries_its_subdirectory.py` | **pass** | 3, rojos antes |
| Migración 0123 | `alembic upgrade head` → `downgrade -1` → `upgrade head` | **pass** | Ensayada en local, ida y vuelta |
| API entera | `pytest tests/ -q -p no:randomly` | **pass** | **3597** |
| `ruff` + `mypy --strict` | `./scripts/verify.sh lint` | **pass** | «Todo verde» |

## Las tres guardas que el arreglo tocó, y por qué no se borraron

El techo de la muestra estaba afirmado **a mano en tres sitios**, con el número
escrito:

| Guarda | Qué defendía |
|---|---|
| `apps/desktop/tests/executor.test.ts` | «la salida no se guarda (§III): muestra acotada, no transcripción» |
| `apps/desktop/tests/local-runner.test.ts` | «acotada por el techo del ejecutor, no por lo que escriba el comando» |
| `tests/integration/test_device_bridge.py` | «el campo existe, está acotado y no se guarda» — la enmienda de §III entera |

Las tres siguen ahí y siguen afirmando lo mismo. Lo único que cambió es **contra qué
número**, y ahora contra una constante compartida
(`services/local_dispatch.OUTPUT_SAMPLE_CHARS`) en vez de un literal — porque tres
copias de un número divergen, y estas ya habían divergido de la aplicación.

Que este arreglo las rompiera **es parte de la verificación**: si subir el techo no
hubiera hecho fallar nada, no habría habido techo que subir.

## Lo que NO está verificado

- **Nada de esto se ha visto funcionar de punta a punta contra una máquina real.**
  Los tests cubren presencia, catálogo, el viaje de la muestra y el nodo del grafo,
  cada uno por su lado. Falta el ensayo entero —emparejar, declarar directorio,
  pedirle a un teammate que corra un build que falla y leer el error en el hilo— y
  eso pide una máquina emparejada y una sesión de verdad.
- **Windows.** La contención tiene su variante NT (T039/T043) y **nunca se ha
  ejecutado**. Este arreglo hace que por fin haya algo que ejecutar ahí.
