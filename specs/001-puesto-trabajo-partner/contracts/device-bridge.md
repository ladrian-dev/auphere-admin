# Contrato — el puente con el dispositivo

**El puente es saliente y no tiene excepción.** La aplicación abre la conexión
desde la máquina del partner hacia la plataforma, sondea trabajo, ejecuta y
responde. **Nada entra desde internet hacia esa máquina** (Requisito 6.1): instalar
esto no abre un puerto en casa ni en la oficina de nadie.

> **Sustituido en parte (2026-09-09).** La credencial, sus claims y las
> operaciones que autoriza los redefine
> [`specs/002-identidad-app-escritorio/contracts/device-bridge-v2.md`](../../002-identidad-app-escritorio/contracts/device-bridge-v2.md):
> la máquina pasa a ser del partner (enmienda del Requisito 6.3), `enrol` se
> sustituye por el canje de un código de emparejamiento, y aparecen `renew` y
> `links`. Los invariantes de abajo —saliente, sin entrantes, latido que caduca
> solo— siguen vigentes.

## Del dispositivo hacia la plataforma

| Mensaje | Para qué |
|---|---|
| `enrol` | Alta: plataforma, versión de la aplicación y `workdir` declarado |
| `heartbeat` | Latido. Su caducidad —no un booleano— es lo que define la presencia |
| `execution_result` | Resultado de una ejecución: resultado, código de salida, hijos recogidos |
| `execution_progress` | Señal de vida de una ejecución larga, para distinguir «tarda» de «colgada» |

## De la plataforma hacia el dispositivo

Siempre como **respuesta a un sondeo del dispositivo**, nunca como conexión
entrante.

| Mensaje | Para qué |
|---|---|
| `execute` | Ejecutable, argumentos, `cwd` relativo y límite de reloj |
| `cancel` | Cancelar una ejecución en curso y recoger su árbol de procesos |

## Invariantes

1. **Sin conexiones entrantes.** Ni puerto a la escucha, ni túnel inverso, ni
   descubrimiento en la red local.
2. **Ninguna credencial de cliente final** viaja en ninguno de estos mensajes
   (§Restricciones adicionales de la constitución).
3. **Mientras la conexión se cae**, la interfaz muestra `reconectando` — que es un
   estado del catálogo de §V, no un error.
4. **El latido caduca solo.** Si el proceso que lo emite muere, la presencia decae
   sin que nadie tenga que escribir nada: por eso el estado se deriva y no se
   guarda.
