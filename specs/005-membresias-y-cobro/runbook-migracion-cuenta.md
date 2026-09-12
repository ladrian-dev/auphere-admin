# Runbook · cambiar la cuenta de Stripe sin perder el saldo de nadie

**Spec**: [spec.md](./spec.md) · **Decisión**: [research.md](./research.md) §D5
**Escrito**: 2026-09-12, **antes** de necesitarlo.

---

## Por qué existe este documento

La cuenta de Stripe con la que Nexus cobra es la de **Andrés Matos**, socio de
Auphere, mientras se completa el registro fiscal de la empresa. Se cobra de
verdad con ella. **Se va a migrar.**

Se escribe ahora y no cuando toque por una razón práctica: el runbook es lo que
obliga a comprobar, hoy, que el diseño soporta la migración. Escribirlo después
es descubrir entonces que no.

---

## El hecho duro

> **Stripe no traspasa Customers, Subscriptions ni métodos de pago entre
> cuentas.**

Los datos de tarjeta pueden migrarse mediante un proceso asistido por Stripe
entre cuentas que cumplen PCI, pero **las suscripciones no se mueven: se
recrean**. En la práctica, **cada partner vuelve a pasar por la página de
pago**.

Eso no se puede evitar. Lo que sí se puede es que sea lo **único** que duela.

---

## Lo que NO se pierde, y conviene decirlo primero

| Cosa | ¿Sobrevive? | Por qué |
|---|:--:|---|
| `included_remaining` (el pool) | **Sí** | Está en nuestra base de datos |
| `purchased_remaining` (el crédito pagado) | **Sí** | Igual. **Es dinero de los partners y no se toca** |
| El nivel de cada partner | **Sí** | `partner_subscriptions.tier_code` es nuestro |
| El libro entero, `usage_ledger` | **Sí** | Nunca estuvo fuera |
| Teammates, tareas, conversaciones, confirmaciones | **Sí** | Nada de esto sabe que Stripe existe |
| El método de pago | **No** | Vive en la cuenta vieja |
| La suscripción activa | **No** | Se recrea |
| El historial de facturas del proveedor | **No** | Se queda en la cuenta vieja, **accesible**. Ver §5 |

**Esto es consecuencia directa de ADR-037 D3.** Si el saldo viviera en Stripe
—que es lo que habrían hecho sus *credit grants*— esta migración sería una
reconstrucción contable cliente por cliente, con el riesgo de que a alguien le
desapareciera crédito que pagó.

---

## Precondiciones

1. La entidad existe y su cuenta de Stripe está **verificada y puede cobrar**.
2. Decidido el tratamiento fiscal (la precondición de despliegue que la spec ya
   declara).
3. Ventana anunciada a los partners **con al menos 14 días**, explicando que
   tendrán que volver a introducir la tarjeta y **que su saldo no se toca**.
4. Copia de seguridad de la base de datos verificada.

---

## El procedimiento

### 1 · Crear el catálogo en la cuenta nueva

```bash
BILLING_API_KEY=<clave de la cuenta NUEVA> uv run python scripts/sync_billing_catalog.py --dry-run
```

```bash
BILLING_API_KEY=<clave de la cuenta NUEVA> uv run python scripts/sync_billing_catalog.py --apply
```

El script es **idempotente por la clave del nivel**: ejecutarlo dos veces no
duplica precios. Escribe los `stripe_price_id` nuevos en `membership_tiers`.

**Lo ejecuta Luis, con sus claves.** Toca una cuenta con capacidad de cobro.

### 1b · Configurar la cuenta nueva (se pierde al migrar, y no avisa)

La cuenta nueva arranca con **los valores por defecto**, así que hay que volver
a poner lo que hace que la escalera exista:

| Ajuste | Por qué, y qué pasa si se olvida |
|---|---|
| Tras agotar reintentos, la suscripción va a **`unpaid`** | Stripe pone `unpaid` **solo si el panel lo dice** (verificado 2026-09-12). Con el valor por defecto, un impago salta de `past_due` a `canceled` y **el escalón intermedio de ADR-037 D6 no ocurre nunca** |
| **Smart Retries** encendido | Es la escalera de reintentos. Sin ella no hay reintentos que agotar |
| **Días de aviso de renovación** | Es lo que dispara `invoice.upcoming`, con lo que se cumple R5.6 |
| El **endpoint de webhook** registrado en Workbench, con los eventos de `contracts/webhook.md` | Sin el endpoint no llega nada |

> **Y una comprobación que solo aplica a una cuenta ajena**: el castigo de las
> 72 horas por no responder a `invoice.created` es **de la cuenta entera**, no
> de un endpoint —«includes handling **all** webhook endpoints configured for
> your account»—. Antes de cobrar con una cuenta que no es solo nuestra, hay que
> mirar qué otros endpoints tiene registrados y si responden.

La comprobación de arranque de la aplicación (T022) verifica el primero de estos
ajustes y avisa si falta. Los demás se comprueban a mano aquí.

### 2 · Apuntar la aplicación a la cuenta nueva

Rotar `BILLING_API_KEY`, `BILLING_PUBLIC_KEY` y `BILLING_WEBHOOK_SECRET`, con el
endpoint de webhook registrado en la cuenta nueva **antes** de rotar.

### 3 · Soltar las referencias viejas

```sql
UPDATE partner_subscriptions
   SET stripe_customer_id = NULL,
       stripe_subscription_id = NULL,
       state = 'canceled',
       state_changed_at = now();
```

**Lee esto antes de ejecutarlo.** Es seguro **porque**:

- Los tres campos son **referencias, no claves** (research §D5.1). Nada apunta a
  ellos.
- `state = 'canceled'` **no archiva nada** (§IV): el partner conserva
  teammates, historia y confirmaciones. Solo deja de reponerse el pool.
- **No toca `partner_wallets`.** El saldo se queda donde está. Si esta sentencia
  tocara el wallet, el runbook estaría mal.

> `state = 'canceled'` normalmente pone `purchased_expires_at` a 12 meses. **En
> una migración no debe hacerlo**: el partner no se fue, nos fuimos nosotros.
> La sentencia de arriba escribe la columna directamente y **no** pasa por el
> manejador de cancelación. Comprobarlo antes de ejecutar es parte del paso.

### 4 · Invitar a resuscribirse

Correo a cada partner con enlace directo a la página de pago, y **en la primera
línea: su saldo comprado sigue intacto**. Es lo que la gente va a preguntar.

La consola muestra el estado con el mensaje de la migración, no con el de
impago. Un partner al que le decimos «no has pagado» cuando el problema es
nuestro es un estado deshonesto (§V).

### 5 · Dejar la cuenta vieja abierta

**No se cierra.** Sus facturas son documentos fiscales que los partners y
Auphere pueden necesitar durante años. Se deja sin cobrar, accesible.

---

## Verificación posterior

| Comprobación | Cómo |
|---|---|
| **La suma de `purchased_remaining` es idéntica antes y después** | Consulta agregada, guardada antes de empezar. **Si no cuadra, se para todo** |
| Ningún partner perdió teammates | Recuento antes/después |
| Ninguna confirmación pendiente se invalidó | Recuento antes/después |
| El catálogo nuevo tiene cuatro niveles con precio correcto | Panel del proveedor |
| El webhook nuevo recibe y verifica firma | Un evento de prueba |
| Un partner puede resuscribirse de punta a punta | Recorrido real |

La primera es la que importa. Las demás son higiene; esa es la promesa.

---

## Reversión

Mientras no se haya cobrado nada en la cuenta nueva, se revierte rotando las
claves de vuelta. Las suscripciones viejas **siguen vivas en la cuenta vieja**
si no se cancelaron allí — **no las canceles en Stripe hasta que la cuenta nueva
haya cobrado con éxito al menos un ciclo completo.**

El paso 3 pone nuestro estado en `canceled`, que es recuperable con un `UPDATE`.
Cancelar en Stripe no lo es.
