# Paridad — tres conectores más

Qué hace hoy Conectores y Capacidades con un conector que llega del
proveedor de consentimientos, y qué le pasa a cada parte aquí.
**Nada se retira.** Google Calendar, Google Sheets, Notion, Gmail y Outlook
siguen exactamente igual: sin lista cerrada, con todas sus herramientas y la
heurística de hoy.

| Lo que hacía | Aquí |
|---|---|
| El catálogo lee las *auth configs* del proveedor y proyecta cada una como conector `oauth_composio` | Igual |
| Conectar abre el consentimiento firmado; al volver, sincroniza | Igual |
| La categoría sale de la etiqueta del proveedor; «payments» y «commerce» caen en «otros» | **Cambia** para `stripe`, `calendly` y `hubspot`: categoría fija por toolkit. Para el resto, igual, con dos familias de palabras más (`payment…` → Cobros, `commerce…` → Tienda) |
| La tarjeta describe el conector con `connectors.desc.<slug>` o la frase de reserva | Igual; tres frases más |
| Sincronizar trae **todas** las herramientas del toolkit y las gatea por la tabla de pistas y la heurística | **Cambia** solo para los tres: se filtra a la lista cerrada y las pistas salen de la lista. Los demás toolkits, igual |
| Lo desconocido nace bloqueado; lo que lee nace encendido al conectar | Igual |
| Capacidades enseña una herramienta sin nombre de negocio con su nombre técnico | Igual (regla «nada desaparece por no estar traducido»); los 33 slugs de los tres tienen nombre |
| «Recomendada para tu sector» en Capacidades, según `tools_required` de la plantilla | Igual |
| La tarjeta de conector no tiene «recomendado» | **Nuevo**: insignia «Recomendado para tu sector» según `connectors.recommended` de la plantilla |
| `CALENDLY_CANCEL_EVENT` en la tabla de pistas (slug que no existe) | **Se retira** junto con las otras tres pistas de Calendly: la lista cerrada las sustituye. No es una función que se pierda: nunca casó con nada |
