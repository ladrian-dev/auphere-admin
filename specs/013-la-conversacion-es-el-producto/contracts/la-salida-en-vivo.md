# Contrato — la salida de un comando se ve y no se guarda (spec 013, R3)

El requisito más caro de esta spec, y el único que roza un contrato congelado.

## Las dos cosas que cierran las puertas fáciles

**1. `CONTRACT-V3` prohíbe llevarla por el stream.** Dice, literal, sobre
`exec.completed`: *«**Sin salida**: la muestra viaja al modelo como resultado de
herramienta, nunca por el stream»*. No es un olvido — el mismo contrato prohíbe
la clave `reason` en `task.state` *«porque podría llevar prosa»*. **Los eventos
llevan hechos estructurados, nunca texto libre de un programa.**

Este contrato **no enmienda `CONTRACT-V3`**: lo respeta y busca otro camino.

**2. Hoy hay un solo lector, y consume.** `await_result` hace `LPOP` sobre
`result_key(execution_id)`. El turno se lleva el payload; quien llegue segundo no
encuentra nada.

## La regla

**Dos destinos al publicar, dos vidas distintas, y ninguna en Postgres.**

Cuando la máquina contesta, `publish_result` deja:

| Destino | Quién lo lee | Cómo | Qué pasa después |
|---|---|---|---|
| La cola de siempre | El turno | `LPOP` — se la lleva | Igual que hoy. **No se toca** |
| Una clave de solo lectura | La pantalla | lectura sin consumir | Caduca a los **quince minutos** |

Quince minutos porque es el mismo reloj que ya caduca una aprobación (§IV), y
porque cubre leer el resultado de un build sin convertirse en un sitio donde
buscar cosas viejas.

## Cómo la pide la pantalla

Una ruta dedicada, bajo el **alcance de cliente que ya existe** —el mismo por el
que se piden las ejecuciones—, que devuelve:

```
outcome, exit_code, output, truncated, available
```

- `output` es la muestra: los dos flujos, hasta 16 KB, con cabeza y cola
  (`core/local_exec_limits.OUTPUT_SAMPLE_CHARS`).
- `truncated` dice si se recortó, que es lo que R3.5 exige decir.
- **`available: false`** es la respuesta normal pasados los quince minutos, y
  **no es un error**: es lo que hace posible R3.3, decir que la salida no se
  conserva en vez de dejar un hueco que parezca un fallo.

## Lo que este contrato prohíbe

- **Escribir la salida en `local_executions`**, en la auditoría o en cualquier
  tabla. CE-005 se comprueba mirando la base de datos, no confiando.
- **Meterla en un evento del stream**, por lo dicho arriba.
- **Servirla a quien no aprobó esa ejecución.** La ruta hereda el alcance de
  cliente; sin él no hay respuesta.

## Dónde se pinta, y dónde no

**No en la tarjeta de aprobación.** Su comentario dice *«nunca la salida: la
salida es del turno siguiente, no de la decisión»* y **sigue siendo verdad**: esa
tarjeta es para decidir, y decidir ocurre antes de que exista resultado.

Lo que se añade es un **hermano**: un elemento de resultado que aparece cuando la
máquina contesta, con el desenlace, el código de salida y la muestra. Va marcado
como **contenido leído** y distinguible de lo que dice el teammate (R3.4, §III):
quien lo mire tiene que poder ver de un vistazo que eso lo escribió un programa,
no el agente.

## Cómo se prueba

1. **Se ve**: un comando que falla y escribe por el flujo de error; el motivo
   aparece en pantalla.
2. **No se guarda**: tras ejecutar, ninguna tabla contiene el texto. Se escribe
   **primero** y se comprueba consultando, porque un criterio que afirma que algo
   **no** está es el más fácil de dar por bueno sin mirar.
3. **Caduca**: pasados los quince minutos, `available: false`, y la pantalla lo
   dice con palabras en vez de dejar un espacio.
4. **El turno no se queda sin lo suyo**: publicar para dos lectores no cambia lo
   que recibe el modelo. Es una regresión fácil y cara.
5. **No se sirve a un tercero**: otra persona del mismo partner no obtiene la
   salida de una ejecución que no aprobó.
