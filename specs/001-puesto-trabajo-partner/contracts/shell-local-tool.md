# Contrato — la herramienta de ejecución local

**Una herramienta por destino.** `shell_local` ejecuta en la máquina del partner y
**no existe** ninguna herramienta de ejecución con un parámetro que diga dónde
ejecuta (Requisito 1.2). Si un día hay ejecución remota, será otra herramienta con
otro nombre: si el destino es un parámetro, el modelo se equivoca, y equivocarse
aquí es correr un comando en el portátil de una persona.

## Presencia en el catálogo

`shell_local` **solo aparece** en el catálogo del turno si:

1. el tenant tiene al menos un ejecutable en su lista blanca, **y**
2. hay un dispositivo con latido vigente.

Si no, **no está**. No aparece deshabilitada ni acompañada de una explicación de lo
que el partner no tiene: la ausencia se diseña (§V).

## Entrada

| Campo | Tipo | Regla |
|---|---|---|
| `executable` | string | Debe estar en la lista blanca del tenant. Sin separadores de ruta |
| `args` | string[] | **Lista, nunca una cadena.** Que sea lista es lo que hace verificable la prohibición de metacaracteres |
| `cwd_relative` | string \| null | Relativo al `workdir` declarado. Nunca absoluto, nunca con `..` |

## Resultados posibles

| Resultado | Cuándo |
|---|---|
| `ejecutada` | Permitido, aprobado si hacía falta, terminó dentro del límite |
| `esperando_aprobación` | Ejecutable permitido, argumentos nuevos. Devuelve la acción durable |
| `denegada` | Con motivo, de la lista cerrada de `denial_reason` |
| `expirada` | Alcanzó el límite de reloj; el árbol de procesos fue recogido |
| `no_disponible` | El dispositivo dejó de estar presente entre la composición del catálogo y la llamada |

## Invariantes

1. **Fail-closed.** Si el gate no puede verificar la llamada, se deniega, y **no**
   se ofrece como decisión aprobable (Requisito 2.6). Una llamada que no se pudo
   comprobar nunca es una llamada pendiente de un `sí`.
2. **Un ejecutable ausente de la lista no genera decisión pendiente.** Se deniega y
   se dice dónde se añade — en la consola, por una persona.
3. **Metacaracteres**: tuberías, encadenamiento, subshells, redirecciones y
   sustitución de comandos se rechazan en `executable` y en cada elemento de
   `args`, esté o no permitido el ejecutable.
4. **La salida es dato.** Lo que el comando imprime no cambia lo que el agente hace
   a continuación (§III). Se le entrega como contenido leído, nunca como
   instrucción.
5. **Todo intento se registra**, incluidas las denegaciones, etiquetado por tenant.
