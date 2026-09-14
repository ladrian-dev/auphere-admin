# Fase 1 — modelo de datos

**Spec**: [spec.md](./spec.md) · **Investigación**: [research.md](./research.md)

Esta feature **casi no tiene datos**, y eso es una señal de que la superficie que
abre no es de información sino de ejecución. Lo que hay es una configuración de
plataforma, un estado en memoria y un conjunto de objetos en un canal.

---

## Versión mínima admisible — configuración de plataforma

**Tenant**: ninguno. Es de plataforma: no lleva `tenant_id` ni RLS, igual que
`model_profiles`. Un cliente final no tiene ninguna ruta por la que alcanzarla.

| Campo | Qué es |
|---|---|
| versión mínima | La más baja que el latido acepta. **Ausente = no se rechaza nada**, que es el estado del primer despliegue (R4.4) |
| motivo | Por qué se exige: contrato roto o seguridad. R4.7 cierra la lista |
| desde cuándo | La fecha a partir de la cual empieza a rechazarse, para que R4.5 —el preaviso— sea comprobable y no una intención |

**Por qué un dato y no una constante**: exigir una versión mínima es una decisión
de operación que puede hacer falta un domingo. Con la cifra en el código, subirla
es un despliegue; con la cifra en la base, es un `UPDATE` — el mismo criterio con
el que la `0072` puso los precios en la base.

**Ausente es un estado válido y es el de partida.** No se siembra ningún mínimo.

---

## Estado de actualización — en memoria, y a propósito

**No se persiste nada.** Vive en el proceso principal de la aplicación mientras
está abierta, y se pierde al cerrar — que es exactamente cuando la actualización
se aplica y el estado deja de tener sentido.

| Campo | Qué es |
|---|---|
| versión descargada | La que está lista para instalar, si la hay |
| por qué espera | `ninguna` · `lista para instalar al cerrar` · `esperando trabajo vivo` |

Alimentado por dos cifras que la política ya declara en su tipo `Activity`:
sesiones de agente vivas (`liveCount`, que `e100564` ya añadió al concentrador de
streams) y acciones esperando confirmación (que hoy **nadie le pasa**).

---

## Artefacto publicado — objetos en el canal

**No es una tabla.** Es lo que hay en el canal, y su modelo lo fija el formato
del actualizador (D5):

| Objeto | Qué es |
|---|---|
| índice de plataforma | Qué versión es la actual y cómo verificarla |
| paquete de actualización | Un fichero por arquitectura |
| paquete de instalación | El que se abre la primera vez |

**Publicar es añadir y mover el puntero, nunca sustituir** (R2.5): los paquetes
de versiones anteriores **no se borran**, porque son la única marcha atrás que
existe cuando el puente es saliente.

---

## Lo que **no** cambia

- `partner_devices.app_version`: se sigue fijando al emparejar y al renovar. El
  latido la recibe para decidir y **sigue sin persistirla** (`T072`).
- Ninguna tabla gana `tenant_id`, ninguna política de RLS se toca y no hay
  herramienta nueva en ninguna lista blanca.
- El libro, el pool y los precios: esta feature no gasta nada que se mida.
