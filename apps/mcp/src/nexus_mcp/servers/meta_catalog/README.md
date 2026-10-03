# meta_catalog — el catálogo del número, leído por el agente

Dos herramientas de solo lectura: `catalog.search_products` y
`catalog.get_product`. Leen el catálogo de Commerce Manager que la cuenta de
WhatsApp Business del número tiene enlazado (spec 022), con el token de ese
canal. Devuelven `retailer_id`, que es lo que `response.send_interactive`
espera en `products` para mandar la tarjeta nativa.

Qué canal: el de la conversación del cliente del turno (su última
conversación); si no hay cliente resuelto, el primer número vivo del negocio
con catálogo. Sin catálogo, `catalog_not_linked`, que el agente dice como «no
tengo catálogo para enseñarte». El token nunca sale del servidor.
