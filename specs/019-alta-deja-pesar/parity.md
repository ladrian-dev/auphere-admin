# Paridad — el alta deja de pesar

**Qué es esto.** Una fila por cada cosa que el alta **pedía, enseñaba o
permitía** antes de esta spec, y dónde está ahora. Nada se retira sin una fila
que diga dónde acabó; una fila sin destino es una pérdida, y la constitución no
las permite (§«no se borra una capacidad sin decisión escrita»).

**Punto de partida**: `bee76a1`, el último commit del alta de cuatro pasos.
**Medido el 2026-09-28** contra la consola en marcha y el catálogo de semillas.

---

## 1 · Los pasos

| Antes (4) | Ahora (3) | Destino |
|---|---|---|
| 1 · Datos (`details`) | 2 · El negocio | Se parte: la plantilla pasa delante, porque decide qué campos existen |
| 2 · Plantilla (`template`) | 1 · A qué se dedica | **Primero**, y sin nada preseleccionado |
| 3 · Canal (`channel`) | — | **Se retira entero.** No viajaba al servidor: `case "channel": return done()`. La elección se descartaba y solo cambiaba el botón final. Conectar canal ya es un paso de la ficha |
| 4 · Confirmar (`review`) | 3 · Confirmar | Se queda, sin la pregunta de publicar |

## 2 · Los campos del formulario

| Campo | Antes | Ahora | Destino |
|---|---|---|---|
| `name` | paso 1, obligatorio | paso 2, obligatorio | Igual |
| `external_client_ref` | paso 1, **segundo campo**, a mano | paso 2, **plegado** bajo opciones avanzadas | Se deriva del nombre; editable si alguien quiere. El duplicado se avisa **antes** de crear, proponiendo una libre |
| `timezone` | paso 1, `<datalist>` que abría en el centro de la pantalla | paso 2, desplegable con filtro | `Combobox` de `@nexus/ui`; teclear filtra, solo una elección cambia el valor |
| `seed_template` | paso 2, **preseleccionada** la primera alfabética (`aesthetic_clinic_v1`) | paso 1, **nada marcado** | Elegir es obligatorio; «sin plantilla» existe como opción nombrada que dice qué implica |
| `channel` (`ChannelChoice`) | paso 3 | — | **Retirado**: la respuesta se descartaba. Se conecta en la ficha, donde «Pasos para activar tu agente» ya lo pide |
| `publish_now` | paso 4, casilla | — | **Retirado** (Historia 4 y R6 revocadas, owner 2026-09-28). El agente nace en borrador y la ficha decide cuándo publicar |

## 3 · Los campos de plantilla (placeholders)

Antes se pintaban **todos**: obligatorios y opcionales. Ahora solo los que la
plantilla exige, derivado del dato que ya viajaba (`placeholders[].required`) y
no de una lista escrita a mano.

| Plantilla | Antes en pantalla | Ahora | Diferencia |
|---|---|---|---|
| `barbershop_v1` | 9 | 2 | −7 |
| `beauty_salon_v1` | 10 | 2 | −8 |
| `clinica_v1` | 9 | 2 | −7 |
| `dental_v1` | 9 | 2 | −7 |
| `spa_v1` | 10 | 2 | −8 |
| `medspa_v1` | 11 | 2 | −9 |
| `nail_studio_v1` | 11 | 2 | −9 |
| `restaurante_v1` | 12 | 2 | −10 |
| `generic_v1` | 5 | 2 | −3 |
| `cobranza_v1` | 4 | 1 | −3 |
| `inventario_v1` | 4 | 1 | −3 |
| `woocommerce_sales_v1` | 8 | 4 | −4 |
| `aesthetic_clinic_v1` | **23** | **12** | −11 |

**Destino de los opcionales**: los ajustes del agente, donde ya viven. No se
pierde ninguno — dejan de pedirse **antes** de que el cliente exista.

## 4 · La excepción que sigue abierta

`aesthetic_clinic_v1` exige doce, y cinco son justo los que el owner señaló
como impropios del alta el 2026-09-28:

| Campo obligatorio hoy | Qué dijo el owner |
|---|---|
| `tenant.pricing_table_label` | «Tabla de precios no se carga aquí» |
| `tenant.payment_methods_label` | «formas de pago tampoco se carga aquí» |
| `clinical.titular_credential` | «Credenciales del titular tampoco va» |
| `tenant.consultation_price_label` | «Precio de la consulta tampoco va» |
| `tenant.saturday_label` | «¿Para qué tiene el input de Sábados?» — disuelto ya por el selector de horario, pero **la semilla lo sigue exigiendo** |

Mientras sigan marcados `required: true` en la semilla, el alta los pide: el
paso 2 enseña exactamente lo que la plantilla exige, ni uno más ni uno menos.
**Eso es T036**, y por eso T036 no es cosmética — es lo que baja esta plantilla
de doce campos a cuatro. Con la decisión del 2026-09-28 («el agente calla lo
que nadie le dijo») el camino es el mismo para las dos mitades del problema:
dejan de ser obligatorios, y donde no haya valor el prompt no afirma nada.

## 5 · Lo que el alta hacía al terminar

| Etapa | Antes | Ahora | Destino |
|---|---|---|---|
| `create` | sí | sí | Igual |
| `seed` | sí | sí | Se salta, y se dice, si no hay plantilla |
| `publish` | sí | — | La ficha |
| `activate` | sí | — | La ficha |
| `channel` | «etapa» que no llamaba a nadie | — | Retirada con el paso 3 |
| Cuota inicial | 50 000 créditos | **0**, con su fila | Owner, 2026-09-28. La fila **se sigue sembrando**: su ausencia es el silencio del 31-ago |
| Reintento por etapa | sí (spec 016 R4.2) | sí | Conservado, con test |

## 6 · Lo que había alrededor del alta

| Cosa | Antes | Ahora | Destino |
|---|---|---|---|
| Contador «{used} de {max} clientes» | cabecera de `/clients` | — | **Retirado**: crear un cliente no tiene límite (owner, 2026-09-28) |
| Aviso de cupo lleno en el alta | `wizard.quota.blocked` | — | Retirado con el límite |
| Botón «Nuevo cliente» deshabilitado al llenarse | sí | — | Retirado |
| Comprobación bajo bloqueo de fila | sí, a 5 | sí, a **10 000** | **Se conserva como guarda** (migración 0130): acota el daño de una clave filtrada o un bucle. Deja de ser producto, no desaparece |

---

## Estado

| Sección | Paridad |
|---|---|
| 1 · Pasos | ✅ completa |
| 2 · Campos | ✅ completa |
| 3 · Placeholders | ✅ completa |
| 4 · La excepción | ⏳ **abierta** — depende de T036 |
| 5 · Al terminar | ✅ completa |
| 6 · Alrededor | ✅ completa |

T019 no puede cerrarse mientras la sección 4 siga abierta.
