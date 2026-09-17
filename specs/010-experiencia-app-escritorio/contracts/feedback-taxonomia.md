# Contrato — la taxonomía de avisos (spec 010)

Una sola API decide **cómo** se comunica algo, para que la elección no se tome
componente a componente. Cubre R5 de la spec.

## La decisión, en una tabla

| Mecanismo | Cuándo se usa | Persistencia | Anuncio a tecnologías de apoyo |
|---|---|---|---|
| **En línea** (junto al control o la tarjeta) | Validación y **cualquier fallo de una acción concreta**: guardar, decidir, declarar un directorio, enviar | Hasta resolverse | Vinculado al control; si bloquea, se anuncia con urgencia |
| **Banner de vista** | Estado del sistema que afecta a la vista entera: sin conexión, consumo cercano al tope, trabajo en pausa, cobro degradado, versión no admitida | Persistente; descartable **solo** si no es crítico | Educado, una sola región por vista |
| **Aviso efímero** | Confirmación **no crítica** de algo que la persona acaba de hacer: «archivado», «copiado», con «Deshacer» como mucho | Corta; se pausa al pasar el ratón o recibir foco | Educado |
| **Diálogo** | Decisión inmediata sobre algo crítico o irreversible: desemparejar, archivar, salir con trabajo vivo | Hasta decidir | Foco atrapado; escape cancela |
| **Aviso del sistema** | Solo con la **ventana sin foco**: espera tu decisión, terminó, falló | Centro de notificaciones del sistema | Lo gestiona el sistema |
| **Número en icono** | Cuántas decisiones esperan | Mientras existan | Replicado en texto dentro de la ventana |
| **Bandeja (Pendientes)** | El historial de lo que espera y lo que se decidió | Permanente | Lista navegable |

## Reglas duras

1. **Ningún error de datos, de red o del agente se comunica solo con un aviso
   efímero.** Va en línea o en banner, con motivo y salida.
2. **Ninguna acción termina en silencio**: o se ve el resultado, o se explica el
   fallo. (Hoy hay siete sitios donde se falla o se sale de la aplicación sin
   decirlo.)
3. **Un hecho, un mecanismo.** Nada se anuncia por dos vías a la vez (hoy, la
   pausa por consumo se cuenta dos veces y con salidas distintas).
4. **Con la ventana enfocada no se emiten avisos del sistema** de lo que ya es
   visible.
5. **El aviso del sistema dice el motivo y nunca el contenido**: ni el comando,
   ni el texto leído, ni datos del cliente final.
6. **Los mensajes de estado no mueven el foco.**
7. **El número sale del derivado único**, nunca de un recuento local.
8. El silencio voluntario de avisos **no puede ocultar lo que espera decisión**
   sin decirlo en la propia preferencia.

## La forma de la API

```
notify({
  severidad: "info" | "exito" | "aviso" | "error",
  alcance:   "elemento" | "vista" | "aplicacion",
  urgencia:  "diferible" | "inmediata",
  accion?:   { etiqueta, destino },      // una sola
  clave:     string                       // la del catálogo de textos
})
```

El mecanismo **no se elige en la llamada**: lo decide una función pura a partir
de `alcance`, `severidad`, `urgencia` y si la ventana tiene foco. Esa función
tiene test propio con la tabla de arriba como casos.

## Catálogo de estados que esta taxonomía tiene que cubrir

Sin conexión · sesión caducada · sin pertenencia a partner · máquina sin
emparejar · máquina reconectando con causa · directorio inválido · plan sin la
capacidad · plan lleno · consumo cercano · consumo agotado sin saldo · cobro
fallido · versión nueva lista · versión no admitida · trabajo en pausa · turno
fallido · decisión pendiente · decisión fallida · sin permiso para decidir · sin
permiso para contratar.

Cada uno, en `data-model.md` §5, con su mecanismo, su texto y **su salida**.
