# Quickstart — spec 023

Qué se prueba en local con el proveedor simulado, y qué exige staging con
las cuentas reales.

## Prerrequisitos

- Stack local: `preview_start api` y `preview_start console` (ver memoria
  «Consola: stack local»). Partner `demo-audit`, cliente
  `panaderia-la-espiga` o uno nuevo con plantilla `barbershop_v1` y otro
  con `cobranza_v1`.
- La clave de Composio **no** está en local: en local los tres conectores
  no aparecen en el catálogo. Lo que se prueba en local es el filtro, las
  anotaciones, los nombres, la categoría y la recomendación, con el
  `FakeComposioClient`.
- Staging tiene la clave y las tres *auth configs* (`evidence/README.md`).

## En local — la suite

```bash
uv run --directory apps/api pytest \
  tests/unit/connectors/test_toolkit_allowlists.py \
  tests/unit/connectors/test_annotation_derivation.py \
  tests/unit/test_capability_names.py \
  tests/unit/test_connector_category.py \
  tests/unit/test_seed_templates_connectors.py \
  tests/integration/connectors/test_sync_allowlist.py \
  tests/integration/connectors/test_connectors_recommended.py -q
```

Lo que cada una fija:

| Test | Criterio |
|---|---|
| `test_toolkit_allowlists` | cada slug tiene prefijo, hint coherente y **nombre de negocio en los dos idiomas** (Requisito 3.2) |
| `test_annotation_derivation` | un slug de la lista toma sus anotaciones de la lista; `CALENDLY_CANCEL_EVENT` ya no está |
| `test_capability_names` | las 33 entradas nuevas se leen en `es` y `en` y no repiten la clave técnica |
| `test_connector_category` | `stripe → billing`, `calendly → booking`, `hubspot → crm` aunque el proveedor publique «otros»; `payments` y `commerce` ya no caen en «otros» |
| `test_seed_templates_connectors` | `barbershop_v1` recomienda `[agendapro, calendly]`, `cobranza_v1` `[amigable_cobro, stripe]`, `generic_v1` nada; un YAML sin bloque carga |
| `test_sync_allowlist` | el fake devuelve 3 slugs de la lista + 2 fuera: quedan 3 filas, `dropped_count=2`; uno de la lista que falta va en `missing` y, si tenía fila, pasa a `deprecated`; un toolkit sin lista sincroniza todo como hoy |
| `test_connectors_recommended` | `GET …/connectors` marca `recommended` según la plantilla del sector y `false` sin sector |

Consola:

```bash
cd apps/console && pnpm test -- connector-card
```

Fija: la tarjeta de `stripe` lee `connectors.desc.stripe` (no la reserva),
la insignia «Recomendado para tu sector» solo sale con `recommended: true`, y
`no-orphan-keys` pasa.

## En staging — con cuentas reales (cierre de la Historia 1)

1. **Confirmar los slugs en el panel** (una vez): en
   `dashboard.composio.dev/contacto_workspace/auphere/toolkits/{stripe,hubspot}`
   buscar cada slug de `TOOLKIT_ALLOWLISTS`; anotar en `evidence/` el que no
   exista y corregir la lista antes de seguir.
2. En un cliente de prueba, Conectores: **Stripe en «Cobros», Calendly en
   «Citas», HubSpot en «Clientes»**, cada uno con su frase (CE-004). Captura
   en español y en inglés.
3. Conectar Stripe con una cuenta en modo prueba. Al volver, Capacidades:
   12 capacidades de Stripe, ninguna con identificador técnico (CE-002), las
   8 de lectura encendidas y las 4 de escritura bloqueadas con la frase de
   siempre (CE-003). Mirar en la auditoría `connector.tools.synced`:
   `dropped_count` alto (≈ 414) y `missing` vacío.
4. En el Playground, preguntar por un cobro de la cuenta de prueba y pedir un
   enlace de pago que ya exista: el agente responde con el estado y el enlace
   sin que nadie haya abierto nada (CE-001).
5. Repetir 3 con Calendly (10) y HubSpot (11). `missing` vacío en los tres.
6. Cliente nuevo con `barbershop_v1`: Conectores marca Calendly y AgendaPro;
   con `cobranza_v1`, Stripe y Amigable Cobro (CE-005).

## Qué no se prueba aquí

- Shopify: fuera de la spec.
- Abrir una capacidad de escritura: sigue siendo de operador, por Admin.
