# T002 — la superficie de aprobación de subagentes · **CONTRATO ESTABLECIDO, NO VERIFICADO DE PUNTA A PUNTA**

Ejecutado el **2026-09-09**. No es un pase. Lo que sigue dice qué se averiguó, qué
no, y por qué la tarea estaba mal planteada de origen.

## El error de planificación, primero

T002 pedía verificar que **la aplicación de escritorio** puede contestar la
aprobación de un `spawn`. Esa aplicación es `apps/desktop/`, que **no existe
todavía**: es la tarea T005. Una puerta que exige lo que aún no se ha construido no
es una puerta, es un bloqueo circular. El fallo es mío, al ordenar las tareas.

Las dos salidas obvias eran malas: compilar la SPA del sustrato (`npm ci` en su
`website/`) es trabajo tirado, porque nuestra cáscara envuelve **la consola de
Auphere**, no su dashboard; y escribir un cliente de usar y tirar responde una
pregunta distinta de la que importa.

## Lo que sí se estableció, y es lo que T005 necesitaba

**1. El predicado que decide si hay superficie** — `session_surface.py`:

```python
if session_key.startswith("dashboard:") or session_key.startswith("dashboard_"):
    return True
return session_key in _dashboard_surfaced
```

El prefijo gana **antes** de consultar el registro, y su docstring dice que vale
*«even before the dashboard has published anything (startup, or a process where the
dashboard never runs)»*. El registro (`set_dashboard_surfaced`) es para sesiones
nacidas en otro canal que tienen una pestaña abierta.

**2. Existe una cola global de aprobaciones**, independiente de que haya pestaña de
chat. Lo dice el propio gate en `subagent_manager/admission.py`: *«an unowned spawn
(the CLI posts none) raises its prompt with `slot=""`, so it is surfaced only on the
global approvals feed and appears in no chat tab»*. Sus endpoints son
`GET /api/approvals` y `POST /api/approvals/{id}/{action}`
(`dashboard/routes/system.py`).

**3. Por qué falló en la evaluación**: con `parent=cli_chat`, la clave de sesión no
lleva el prefijo `dashboard:` ni está en el registro, así que
`has_dashboard_surface()` da falso. No era el backend ni la falta de kiro-cli: era
la clave de sesión.

## Lo que NO se demostró

**No se ejecutó la aprobación de punta a punta.** Dos muros, los dos informativos:

- `kirocrew chat -m` deniega automáticamente **cualquier** herramienta que pida
  aprobación, un peldaño **antes** de la puerta de admisión del spawn, así que
  `spawn_run` ni se llamó. Reproducirlo con un pty daría el resultado que la
  evaluación ya conoce —gateway arriba, `parent=cli_chat`, rechazado por falta de
  superficie—, así que no añade información.
- Su API de dashboard rechazó un token generado aparte con `token superseded`. No se
  persiguió: **su esquema de auth no es el que usaremos** —la consola de Auphere
  acuña tokens EdDSA de 60 s por llamada— así que aprender su rotación era trabajo
  tirado.

## Consecuencia para el plan

El riesgo del Requisito 11 **baja mucho pero no desaparece**. Ya no es «puede que no
haya forma de contestar la aprobación»: la hay, existe la cola global y el predicado
se satisface con el prefijo de la clave de sesión. Lo que queda es comprobar que
**nuestro** cliente la contesta, y eso solo se puede hacer cuando ese cliente exista.

Por eso T002 se cierra como **contrato establecido** y la verificación de punta a
punta pasa a la Phase 7, como criterio de la tarea que construye el soporte de
subagentes — que ahora se construye contra un contrato conocido en vez de a ciegas.

## Ficheros

| Fichero | Qué contiene |
|---|---|
| `gateway-t002.log` | Arranque del gateway con las tres variables y el envoltorio activo. Incluye el aviso de que su SPA no está compilada y el de que no hay techos de recursos fuera de Linux |
| `C-spawn.log` | El intento de spawn: denegado en la puerta de herramientas de `chat -m`, un peldaño antes de la de admisión |

---

## Segunda pasada (2026-09-09, tarde) — la cola de aprobaciones **sí** es alcanzable

Lo que en la primera pasada quedó como *«su API rechazó el token con `token
superseded`»* ya tiene explicación y solución:

**El registro de nonces vive en la memoria del proceso del gateway.**
`token_auth.py:289` devuelve `token superseded` cuando el nonce presentado no está
en ese registro — y un token generado en **otro proceso** nunca lo está. No era un
token caducado ni una firma mala: era el proceso equivocado.

**La forma correcta es pedírselo al gateway**, que expone `kirocrew token`. Con
ése:

```
GET /api/approvals?token=…  →  HTTP 200, []
```

**Nuestro propio cliente puede leer la cola global de aprobaciones.** Eso era
justamente lo que T002 no pudo demostrar, y ya está demostrado.

### Lo que sigue sin verificarse, y por qué no se fuerza

Falta la última junta: que **contestar** por esa cola desencadene el subagente. Para
originar una sesión que satisfaga `has_dashboard_surface()` hace falta un *slot* de
chat —la clave es `dashboard:{slot}`— y los slots se crean desde el dashboard, cuyo
chat va por **WebSocket**. El CLI no tiene bandera para colgarse de un slot
(`kirocrew chat -h` no la ofrece), y su SPA no está compilada («gateway is serving a
stale dashboard — assets missing»).

Las dos salidas son caras y **tiradas**: compilar su SPA, o escribir un cliente de su
protocolo WebSocket. Nuestra cáscara de escritorio habla con **la consola de
Auphere**, no con su dashboard, así que ninguna de las dos cosas se usaría después.
Es la misma trampa que ya se evitó en la primera pasada, y se evita otra vez por la
misma razón.

**Dónde se cierra barato**: cuando exista la cáscara de escritorio, que es el
cliente que de verdad va a contestar. Entonces la comprobación es un paso natural
del producto en vez de un andamio para tirar.
