# Contrato — el hilo devuelve lo que la persona escribió (spec 013, R1)

El mensaje de la persona **ya se guarda**. Este contrato solo lo devuelve.

## La regla

**El resumen de un run lleva el texto que lo originó.**

Un run tiene exactamente un mensaje de persona: el que lo disparó
(`CompanionMessage(role="user", content=body.prompt)`, escrito en cada turno).
La relación es 1:1, así que un campo por run es completo y no una aproximación.

## Qué cambia

`GET /console/companion/threads/{thread_id}/runs` devuelve hoy, por cada run:

```
run_id, status, started_at, ended_at
```

Y pasa a devolver:

```
run_id, status, started_at, ended_at, prompt
```

`prompt` es el texto tal como la persona lo escribió. `null` solo si no hay fila
de mensaje para ese run — que es una anomalía, no un caso normal, y la pantalla
la trata como texto ausente y no como cadena vacía.

## Lo que NO cambia

- **La RLS.** Se sigue leyendo bajo `app.principal_id`, y `_thread_row` sigue
  dando el 404 opaco: la conversación de otra persona del mismo partner no se
  distingue de una que no existe. Ahora importa más, porque por aquí viaja texto.
- **El orden.** Ascendente por `started_at`, como ya estaba.
- **La ausencia de paginación.** Un hilo con cientos de runs sigue siendo un
  problema de CO-06; esta spec no lo resuelve ni lo empeora.
- **Los eventos.** El mensaje de la persona **no** se convierte en evento. Los
  eventos son del run en marcha; al reabrir un hilo viejo no hay stream que
  reproducir, y emitirlo además obligaría a guardar dos copias del mismo texto.

## Quién lo consume

Los dos clientes, y es deseable: la consola tiene hoy exactamente el mismo hueco.

| Cliente | Qué hace con él |
|---|---|
| Aplicación de escritorio | Pinta la burbuja de la persona antes de los eventos de ese run |
| Consola | Lo mismo, por el mismo camino |

## Cómo se prueba

1. **Ida y vuelta**: escribir, recargar, y encontrar el texto en el resumen.
2. **Orden**: con varios runs, los mensajes salen en el orden en que ocurrieron.
3. **Frontera**: pedir los runs de una conversación de otra persona del mismo
   partner responde como si no existiera. Va en `tests/isolation/` aunque no sea
   una de las siete garantías: por aquí viaja texto de una conversación.
4. **Turno vivo**: con un run en marcha, el `prompt` ya está ahí — es lo que
   permite que R1.4 se cumpla al recargar a mitad de respuesta.
