# Cargas de webhook de Meta (spec 050)

Formas oficiales de Meta (`developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/*`) recortadas, con datos ficticios. Las pruebas las firman con `sign_meta_request(app_secret, body)`.

- WABA `102290129340398`, número `+34 600 00 00 01` (`phone_number_id` `106540352242922`).
- Persona con teléfono y BSUID: `34611000001` / `ES.100000000000000001`. Persona solo con BSUID: `ES.200000000000000002`.

Las pruebas de `apps/channels` y de `apps/api` las leen por ruta (`META_WEBHOOK_FIXTURES / "<nombre>.json"`).
