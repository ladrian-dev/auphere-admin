# Revisión de seguridad (T187) · 2026-10-28

Revisión de solo lectura de todo lo que la rama `047-la-fabrica-de-agentes-impl`
cambia respecto a `origin/develop` (lo commiteado, lo pendiente y lo nuevo), con el
método de la skill `security-review` de Claude Code: solo hallazgos explotables con
confianza ≥ 0,8, de gravedad alta o media. Los skills `/cso` y
`tenant-security-audit` que nombra la tarea no están instalados en esta sesión:
esta revisión los sustituye y conviene repetirlos antes de producción si existen.

**Resultado: ningún hallazgo alto ni crítico.**

## Qué se revisó y por qué aguanta

- **Rutas de la consola del partner**: todas pasan por `client_scope`,
  `agent_in_path`, `any_agent` o `agent_scope` (o `resolve_mapping` +
  `tenant_scoped_session`); cada id del camino o del cuerpo se vuelve a comprobar
  contra el cliente; `job_tenant()` (SECURITY DEFINER) solo devuelve el
  `tenant_id` y la propiedad del partner se comprueba antes de leer.
- **Papeles**: saltar la puerta exige owner o admin en la API y en el trabajo de
  publicar; escribir dinero exige `usage:write`.
- **Dinero**: las tablas del partner con RLS por `app.partner_id`; las bolsas
  con la del cliente vía `as_client`; asignar, rellenar y confirmar el reparto no
  pasan de `assignable()`; mover y bajar, no más de lo que hay.
- **Lite y app**: `lite_scope` ata el cliente de la membresía; cada id se
  comprueba contra él; los avisos filtran por cliente.
- **Admin**: los routers nuevos llevan `require_admin_token` y las escrituras
  `require_operator`; cada acción de servidor del panel llama a
  `requireOperator()`.
- **Migraciones 0175–0202**: tablas del cliente con ENABLE + FORCE RLS
  canónica; las del partner con su política por `partner_id`.
- **SSRF**: toda lectura de una web (la del negocio, sus redes, las fuentes, la
  relectura semanal y el conocimiento por URL) pasa por `assert_public_url`, que
  resuelve el host, exige direcciones globales y vuelve a validar cada
  redirección a mano.
- **Webhook de Meta**: la firma HMAC se comprueba antes de enrutar, también en
  `account_update`; el cliente sale del número firmado.
- **Herramientas del agente**: `reception.handoff` toma conversación y cliente
  del contexto del turno; el destino tiene que estar en la lista publicada de
  Recepción, ser del mismo cliente y estar vivo; los saltos tienen tope.

## Por debajo del umbral

1. **Mover un número en «A todos» a un agente de solo administradores** no
   repetía la comprobación de «A todos». **Corregido**: responde 409
   `audience_admin_only_template` (`channel_config.move_channel`), con prueba.
2. **DNS rebinding** en `services/knowledge_indexer.py` (anterior a la 047): se
   resuelve el host y la conexión lo vuelve a resolver. Lo leído nunca se
   devuelve tal cual. Arreglo propuesto: fijar la IP validada o negar rangos
   privados en la salida.
3. `reception/tools.py` usa la última conversación del cliente en lugar de la del
   turno: queda dentro del mismo cliente y se valida contra su lista.
4. `load_seed_template` une un nombre sin sanear a una ruta (anterior a la 047):
   solo `.yaml` con `safe_load` y claves obligatorias.

## Encontrado por la regresión, ya corregido

- Pausar o reanudar un número tiraba la caché antes del commit.
- `GET …/channels/diagnostics` quedaba tapado por `…/channels/{channel_id}`.
- El simulador llamaba al modelo sin la clave virtual del partner.
- Anterior a la 047, sin tocar: `/admin/tenants/{id}/conversations/stream` queda
  tapado por `/admin/tenants/{id}/conversations/{conversation_id}`.
