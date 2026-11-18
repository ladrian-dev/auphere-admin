# Contrato — «Cómo habla» y la regla de idioma del turno

Enmienda `specs/047-la-fabrica-de-agentes/contracts/agent-spec.schema.json`
(requisito 16.1) y la línea de idiomas del bloque de operación.

## AgentSpec: `voice`

```jsonc
"voice": {
  "languages": ["es", "en"],     // 1–5, únicos; el primero es el principal
  "languages_limited": true,     // NUEVO, opcional. Omitido = false = sin límite
  "tone": "…", "register": "tu", "greeting": "…"
}
```

- `languages_limited` es `boolean`, no es obligatorio y no tiene valor por defecto
  en el JSON Schema. La ausencia significa «sin límite».
- `test_agent_spec_contract.py` ata el modelo Pydantic y el JSON Schema: los dos
  cambian en el mismo commit.

## La regla de idioma del turno

- **Dónde va:** es un mensaje `{"role": "system"}` propio, el **último** de los de
  sistema: después de la directiva del turno y antes del historial y del mensaje del
  cliente (`_build_handler_messages`). Sale del bloque de operación.
- **En qué idioma:** inglés, como el resto de instrucciones de operador. El cliente
  final nunca lo ve.
- **Cuándo:** va en todos los turnos, también en una versión sin `policies.console`
  (D4). El probador de la consola usa el mismo pipeline.

Los dos textos están probados en staging, con 2 llamadas por caso, también contra un
prompt que dice «Never answer in English» (`research.md` §1, segunda ronda).

**Sin límite** (por defecto):

```text
Reply language (set by the business; it overrides every instruction above about the reply language, including any 'always reply in …' or 'never answer in …'): reply in the language of the customer's latest message. If you cannot tell which language it is, keep the language of the conversation; at its start, use {primary}.
```

**Con límite**:

```text
Reply language (set by the business; it overrides every instruction above about the reply language, including any 'always reply in …' or 'never answer in …'): you only answer in {allowed}. If the customer writes in one of them, reply in it; otherwise reply in {primary}. If you cannot tell which language it is, keep the language of the conversation; at its start, use {primary}.
```

`{allowed}` son los códigos separados por «, » (por ejemplo `es, en`).

## La reescritura del evaluador

`_RETRY_SYSTEM_TEMPLATE` termina con: `Keep the language of the reply you are rewriting.`

## Lo que la consola enseña en «Cómo habla» (1.8)

| Estado | Texto |
|---|---|
| Sin límite | «Contesta en el idioma del cliente. Si no lo sabe, en {principal}.» |
| Con límite | «Solo en: {lista}. Si le escriben en otro, en {principal}.» |

El interruptor dice «Responder solo en estos idiomas» y empieza apagado.
