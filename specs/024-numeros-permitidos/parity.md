# Paridad — los números permitidos se editan en Ajustes del agente

Qué hace hoy el modo «solo administradores» y qué le pasa a cada parte
aquí. **Nada se retira.**

| Lo que hacía | Aquí |
|---|---|
| `policies.admin_access.admin_only` + `admin_phones` gatean el turno en el worker (`pipeline.skipped.not_admin`) | Igual; además el entrante suprimido queda con `skipped_reason = not_admin` |
| El webhook no marca como leído lo que no se va a responder | Igual |
| La API de partners fija la lista y promueve al momento (`PUT /v2/partners/clients/{ref}/admins`) | Igual; escribe el mismo dato que la consola («el último que guarda gana») |
| El asistente de alta pide los números cuando la plantilla es de solo administradores | Igual |
| Ajustes del agente edita solo `policies.console` | **Cambia**: además lee y escribe `admin_access` como «A quién responde»; `policies.console` sigue igual |
| La consola no dice si un cliente responde solo a una lista | **Nuevo**: cabecera y lista de clientes lo dicen; Conversaciones cuenta los mensajes sin responder por número no permitido |
| Roles por número (`full` / `readonly`) en la API de partners | Igual; la consola no los enseña y conserva el que haya |
