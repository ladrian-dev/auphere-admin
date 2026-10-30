# Apuntar temporalmente los webhooks de Instagram y Page a staging

**Decisión del owner (2026-10-30):** para probar y grabar, staging recibe los eventos reales de Instagram y Messenger.

**Lo hace el owner**, porque la app de Meta `957213733862330` es la misma para staging y producción.

## Por qué es seguro hoy

- Producción (`main` = `daf0ca15`) aún no tiene la spec 049: hoy descarta todos los eventos de `instagram` y `page`. Mientras dure el cambio, producción no pierde nada que use.
- **WhatsApp no se toca.** Cada número de WhatsApp lleva su propio destino (`override_callback_uri` por WABA), y el objeto `whatsapp_business_account` de la app debe quedarse como está.
- Staging ya responde en su URL y rechaza firmas o tokens falsos (verificado el 2026-10-30, T-WH-01…04).
- La firma de los eventos usa el secreto de la app, que es el mismo en los dos entornos, así que staging los acepta.

## Antes de empezar

- [ ] El despliegue de staging con los últimos cambios está terminado (te lo confirmo).
- [ ] Tienes a mano el **verify token de staging** (`NEXUS_META_WEBHOOK_VERIFY_TOKEN` del entorno de staging, en sus secretos).
  - Meta lo manda en la verificación, y staging solo responde si coincide.
  - No lo pegues en el chat.
- [ ] Apunta los valores actuales (la URL de producción y su token) para poder volver atrás.

## Pasos (App Dashboard → app «Auphere» → Webhooks)

1. Arriba, en el selector de objeto, elige **Instagram**.
   - Pulsa **Editar suscripción** (*Edit subscription*).
   - **URL de devolución de llamada:** `https://api.staging.auphere.com/webhook/meta`.
   - **Token de verificación:** el de staging.
   - Pulsa **Verificar y guardar**. Meta hace la verificación al momento; si falla, el token no coincide.
   - Comprueba que los 8 campos siguen suscritos (`messages`, `comments`, …).
2. Repite con el objeto **Page**: misma URL, mismo token. Comprueba que siguen sus 7 campos.
3. Mira que siga suscrito `messaging_policy_enforcement` en Page (pendiente de T050). Si no lo está, suscríbelo ahora.
4. **No toques** el objeto **WhatsApp Business Account**.

## Cuando termines

Avísame y compruebo que staging reciba los eventos. Para eso:
- conecto en staging la cuenta de Instagram y la Página de prueba, con tu autorización;
- mandas un DM de prueba;
- verifico en la bandeja y en los registros que llegó al cliente correcto.

## Para volver atrás

Mismos pasos, poniendo otra vez la URL de producción, `https://webhooks.auphere.com/webhook/meta`, con su verify token.

**Hay que hacerlo antes de promover la spec 049 a producción.** A partir de ese momento, producción necesita esos eventos y los reenvía a staging cuando son suyos.
