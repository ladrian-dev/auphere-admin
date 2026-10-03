# Contratos de pantalla (consola) — spec 016

Qué ve y qué puede hacer cada rol. Sin detalle de componentes; eso va en `tasks.md`.

## Canales (`/clients/{ref}/channels`)

| Condición | Lo que se ve |
|---|---|
| Meta configurado, `channels:write`, cupo de canales disponible | Botón «Conectar WhatsApp» → diálogo con modo (Cloud API / Coexistencia) → ventana de Meta → al volver, tarjeta del número activa y toast «WhatsApp conectado» |
| Meta configurado, cupo lleno | Sin botón; texto «Has alcanzado los N números de este cliente» |
| Meta **no** configurado en el entorno | Sin botón; nota «En este entorno WhatsApp lo conecta Auphere. Escríbenos a … con el número y el nombre del cliente» |
| Sin `channels:write` | Sin botón ni nota de acción; tarjetas en solo lectura |
| Dentro de la app de escritorio | «Continuar en el navegador» → misma ruta en el navegador con el botón real |

## Ficha del cliente (`/clients/{ref}`)

- Tarjeta de estado: «Listo» o «Falta: …» con **cada elemento enlazado** a su pestaña: agente → Agente; WhatsApp → Canales; cupo → Consumo (fila del cliente); activación → botón Activar.
- «Sin cupo» aparece como estado propio (tono aviso) aunque el cliente esté listo.

## Lista de clientes (`/clients`)

- Columna Estado: badge de ciclo de vida + punto «sin cupo» cuando aplique, con `title` explicativo.

## Portada (`/`)

- «Agentes con incidencia» cuenta también «sin cupo»; la lista de incidencias lo nombra y enlaza a Consumo.

## Consumo (`/usage`)

- «Mover cupo»: origen, destino, cantidad → **una** confirmación → un solo resultado («20.000 créditos movidos de A a B»). Errores en su idioma: «A solo tiene 30.000 de tope», «Elige dos clientes distintos».
- Fila de un cliente sin cupo: badge «sin cupo» + acción «Asignar».

## Ajustes del agente (`/clients/{ref}/agent/settings`)

- Tarjeta «Modelo» **separada del formulario**: modelo actual, lista de permitidos con «×N créditos», guardar → toast «El siguiente mensaje lo atiende {modelo}». Si el elegido ya no está permitido: aviso en la tarjeta con el modelo por defecto que se está usando.

## Herramientas (`/clients/{ref}/tools`)

- AgendaPro: «Enlazar la agenda» → campo URL pública de reservas (con ejemplo) → guardar → estado «conectado», herramientas de citas activables. «Desenlazar» con confirmación.
- Conectores por clave: diálogo de credenciales con etiquetas traducidas → guardar → resultado en la misma tarjeta («Conectado · 12 herramientas» o «Guardado, pero no se pudo sincronizar: {motivo} · Reintentar»). El botón «Sincronizar» permanente desaparece; queda «Reintentar» solo tras un fallo.

## Alta (`/clients/new`)

- Revisión: cuatro etapas «Crear el cliente · Generar el agente · Publicar la versión 1 · Activar», cada una con estado y reintento propio; al terminar, aterriza en la ficha con «Falta: WhatsApp → Conectar».

## Notificaciones

- «{Cliente} se ha quedado sin cupo: sus mensajes no se atienden. Asignar cupo →» (aviso, una vez al día por cliente).
- «El modelo de {Cliente} pasó a {modelo} porque tu plan ya no incluye {anterior}.» (info).
