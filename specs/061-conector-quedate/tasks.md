---

description: "Tareas de la spec 061: conector de Quédate (enmienda del 2026-11-16)"
---

# Tasks: Conector de Quédate

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/tools.md](contracts/tools.md), [contracts/admin-api.md](contracts/admin-api.md)

**Reglas**: cada tarea cita sus requisitos. Test primero (§VII). Aislamiento en T010–T014. Sin dependencias nuevas. Sin commits: los hace Luis.

> La implementación del 2026-11-13 (registro con `/register` y clave por persona) se sustituye entera por esta. Reutiliza la conexión, la tabla (sin credencial), el panel y la comprobación de clave.

## Fase 1: Base

- [x] T001 Modelo `CustomerConnectorAccount` sin `credential`, con FK a `tenants` y FK compuesta a `customers`. _Requisitos: 6.1, 6.2_
- [x] T002 Migración 0233 rehecha:
  - la tabla sin credencial;
  - el conector `lodging` sin autoactivación;
  - las 27 filas de `tool_catalog` desde la instantánea;
  - el valor por defecto deshabilitado;
  - el vocabulario: `linked`, `link_failed` y `external_write_unconfirmed`.

  Antes, deshacer la 0233 vieja en la base local. _Requisitos: 1.5, 6.1, 3.11_
- [x] T003 Semilla con `api_key` (secreta) y `environment` (opcional), y las traducciones de la consola. _Requisitos: 1.1, 1.2_
- [x] T004 `base_client.request(files=…)` para multipart, retrocompatible, con su test. _Requisitos: 3.8, 4.2_

## Fase 2: Aislamiento, en rojo

- [x] T010 RLS del vínculo entre tenants. _Requisitos: 6.1_
- [x] T011 Dos clientes del mismo negocio: con el turno de B, ninguna herramienta de la persona llama a Quédate sobre el anfitrión o los anuncios de A. _Requisitos: 3.9, 4.5, CE-004_
- [x] T012 Barrido de argumentos: solo `register_me.email`, `create_host.email` y `create_host.phone` del eje. Ninguna herramienta acepta cliente, tenant, conversación ni clave, y las de la persona no aceptan `host_id`. _Requisitos: 3.9, 6.5, CE-002_
- [x] T013 Barrido de fugas: la clave del cliente no aparece en salidas, registros, auditoría ni errores, y no hay datos personales en registros ni en auditoría. _Requisitos: 1.6, 6.4, CE-003_
- [x] T014 Cascada por cliente final y por tenant (la del tenant, en `test_22`). Sin cliente en el turno, las herramientas de la persona se niegan. Con el partner sin acceso, se niegan las 27. _Requisitos: 6.1, 6.3_
- [x] T015 `test_51` (+3 entradas razonadas, techo 31) y `test_44` (familia `quedate`). _Requisitos: 6.5_

## Fase 3: Cliente, catálogo y públicas

- [x] T020 Contrato:
  - cada petición coincide con su ruta y su método;
  - los cuerpos solo llevan campos del contrato;
  - las públicas van sin clave y las del agente con la del cliente;
  - el entorno elige la base.

  _Requisitos: 1.2, 2.*_
- [x] T021 `client.py`, `errors.py` y `schemas.py`, y el catálogo con sus públicas, recortes incluidos. _Requisitos: 2.*_

## Fase 4: La persona

- [x] T030 Pruebas del alta:
  - vincula;
  - no repite;
  - un correo tomado vincula el anfitrión si es de la clave;
  - el teléfono sale del cliente;
  - exige confirmar el correo;
  - sin respuesta, audita;
  - un 403 marca revisión.

  Y de la cuenta, el enlace reutilizado, la subida de KYC con fotos elegidas y los anuncios: pertenencia, sin reintento, solo `pending_approval` y `hidden`. _Requisitos: 3.*, 4.*_
- [x] T031 `accounts.py`, `photos.py` y las 9 herramientas de la persona más `recent_photos`. _Requisitos: 3.*, 4.*, 6.*_

## Fase 5: Equipo

- [x] T040 Pruebas y las 11 herramientas de equipo: paginación, filtro por anfitrión, nunca `published`, y un 403 como «la clave no lo alcanza». _Requisitos: 5.*_
- [x] T041 Registro (`registry.py`, recuento) y nombres de capacidades. _Requisitos: 2.*_

## Fase 6: Conexión y panel

- [x] T050 `key_check` con `GET /agent/hosts?per_page=1` en el entorno de la conexión, con sus pruebas (unit e integración). _Requisitos: 1.3, 1.4_
- [x] T051 Panel: el bloque «Anfitriones vinculados». _Requisitos: 7.1_

## Fase 7: Cierre

- [x] T060 Pasada real contra dev con la clave de Luis, fuera de la suite: alta, enlace, anuncio, fotos, revisión y ocultar. _Requisitos: CE-006_
- [x] T061 Docs (`docs/admin.md` y `docs/console.md`), la KB y el ADR enmendado. _Requisitos: todos_
- [x] T062 Verificación:
  - `verify.sh lint` y `js`;
  - MCP, worker y API tocada;
  - `tests/isolation/` completa;
  - `/cso`;
  - buscar los prefijos de las claves en el repo, la KB y la memoria.

  _Requisitos: todos_
- [x] T063 Guion de commits rehecho. _Requisitos: —_

## Fase 8: Lo que encontró staging (2026-11-17)

- [x] T064 `quedate` en `_EVERY_INTENT_TOOLKITS` del pipeline, con su prueba en `apps/worker/tests/unit/test_intent_tool_filter.py`. _Requisitos: 3.12_

