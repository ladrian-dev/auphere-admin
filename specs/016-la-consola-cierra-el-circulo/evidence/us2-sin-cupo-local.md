# US2 · «Sin cupo» — recorrido local (2026-09-23)

Stack local, partner `demo-audit`, cliente `panaderia-la-espiga`.

1. `/usage`: tope de Panadería La Espiga bajado a **0** con el campo de la fila.
2. `/usage?client=panaderia-la-espiga`: la fila queda resaltada (`aria-current`),
   con el punto de aviso junto al nombre y la etiqueta **«Sin cupo»** junto al
   restante; el campo de tope de la fila es la acción «asignar».
3. `/clients/panaderia-la-espiga`: tarjeta de estado con la línea
   «Sin cupo: sus mensajes no se atienden. Asígnale créditos en Consumo.» y el
   enlace **«Asignar cupo»** → `/usage?client=…`. `Falta: WhatsApp conectado`
   sigue siendo lo que bloquea «listo»; el cupo no lo bloquea.
4. `/clients`: la fila muestra «Activo · Sin cupo» (punto de aviso con nombre).
5. `/`: «Agentes con incidencia: 1» e «Incidencias → Panadería La Espiga: Sin
   cupo: sus mensajes no se atienden» (enlace a Consumo).
6. Tope restaurado a 50 000: los cuatro estados desaparecen.

No se envió un turno real por el canal (no hay WhatsApp en local); el aviso
`client.out_of_quota` está cubierto por los tests del despachador y del
servicio, y por el cron de avisos de cartera como red de seguridad.
