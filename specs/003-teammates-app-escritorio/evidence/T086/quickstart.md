# T086 — El quickstart, ejecutado

Fecha: 2026-09-11. Contra la API y la consola locales (`:8000`, `:3110`), con la
base de desarrollo del partner de Luis.

## §1 Plataforma — ✅

```
alembic upgrade head                                   → 0113_teammate_changes
test_31 · test_32 · test_33 · test_34                  → 21 passed
test_teammates_*.py · test_local_dispatch.py           → 40 passed
tests/isolation/ (CE-011: 001 y 002 siguen en verde)   → 835 passed
```

## §2 Paquete compartido y consola — ✅

```
@nexus/companion-ui  → 144 passed
console              → 186 passed · tsc limpio · eslint limpio
```

El cajón de la consola sigue igual y ninguna página de la consola tiene
teammates; el techo de ejecución local está en la página de equipo.

## §3 Escritorio — ✅

```
desktop  → 307 passed
build    → tsc + vite (dist/app) + preloads
electron → arranca contra la consola local, `window.auphere` es `object`
```

## §4 El recorrido — parcial, y aquí está lo que falta

Lo hecho con display, con su evidencia:

| Paso | Estado | Dónde |
|---|---|---|
| 1 · roster y crear teammate | ✅ | `evidence/US4/` (crear, cambiar, archivar) |
| 2–4 · ejecutar, la tarjeta, el techo, el denegado | ✅ en pruebas + `evidence/US3/` | `test_local_dispatch.py` (12), `test_34`, `test_local_exec_policy_api.py` |
| 5 · cerrar la app, esperar, aviso del SO, Pendientes | ⏳ **parcial** | La tarea que espera y la bandeja están probadas (`test_teammate_tasks.py`, `test_teammate_inbox.py`, `inbox-sync.test.ts`); **la espera real de más de 15 minutos con el aviso del sistema operativo no se ha recorrido** |
| 6 · segunda persona del partner | ⏳ **pendiente** | Probado en la plataforma (`test_32`: dos personas, mismo teammate, hilos que no se ven) pero **no con dos sesiones reales en dos máquinas** |
| 7 · Cuenta con el mismo número | ✅ | `evidence/US5/`, y `test_teammates_usage.py` compara el objeto entero |

**Un hallazgo del recorrido, corregido**: al abrir un hilo vacío de un teammate
que necesita la máquina, la pantalla enseñaba el vacío **del cajón de la
consola** («pregunta lo que quieras sobre tus clientes, sus agentes o tu
consumo») debajo de la banda de «necesita tu máquina». El vacío propio solo se
pintaba cuando el estado derivado se llamaba `vacio`, y con la máquina ausente
se llama otra cosa. Ahora se mira si el hilo tiene cero elementos, exigiendo
además que haya cargado bien — un hilo que falló también tiene cero, y decirle
«está vacío» taparía el error.

## §5 Auditorías de UI — ✅ con alcance declarado

En `evidence/T082/auditorias.md`: cero 🔴 en las cuatro, dos 🟡 de accesibilidad
corregidos, y escrito con todas las letras que son revisión del fuente con
capturas reales al lado, no medición del render con `axe-core`.

## Lo que no puedo cerrar yo

**CE-009 pide una persona ajena al equipo** haciendo el recorrido de §4 sin
ayuda, y eso no lo puede firmar quien escribió el código: el valor de ese
criterio está justamente en que la persona no sepa dónde mirar. Queda para una
sesión con alguien delante, y con ello los pasos 5 y 6 de la tabla.

**CE-001 queda condicionado a la spec 004** (la edición empaquetada), como
estaba previsto: esta spec no la incluye.
