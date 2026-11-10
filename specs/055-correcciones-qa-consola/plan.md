# Plan de implementación: Correcciones de QA de la consola

**Rama**: `055-correcciones-qa-consola` | **Fecha**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Entrada**: la spec aprobada por el owner el 2026-11-05. Se corrige y se prueba en local con el partner de pruebas, y se sube a `develop` ya corregido.

## Resumen

Seis cortes que se pueden entregar por separado, de menor a mayor:

1. **Marcas (H3):** cada sección avisa al índice cuando cambia su estado.
2. **Ejemplos (H4):** una función pura decide cómo se añade el ejemplo a la descripción.
3. **«Señal» (H5):** etiqueta, ayuda y lo que lee el agente.
4. **Moneda (H2):** dos campos al crear, listas en Datos básicos, sin CLP inventado, y los servicios siguen a la moneda del negocio, con confirmación.
5. **Recuperar con invitación (H1):** si no hay cuenta y sí invitación viva, se reenvía en segundo plano, con la misma respuesta. Se comprueba además que el panel invita al crear.
6. **Categorías (H6):** una columna opcional en el servicio, en las dos pantallas, en la ficha exportada y en lo que lee el agente.

Las decisiones técnicas, con su porqué, están en [research.md](research.md).

## Contexto técnico

**Lenguaje**: Python 3.14 (API y worker), TypeScript con Next.js (consola)

**Dependencias**: FastAPI, SQLAlchemy y Alembic; React y `@nexus/ui`. **Ninguna nueva**

**Almacenamiento**: PostgreSQL con RLS. Una migración aditiva, `0220`: [data-model.md](data-model.md)

**Pruebas**: pytest (`apps/api/tests`, con `tests/isolation/`), vitest en la consola, `./scripts/verify.sh`

**Plataforma**: API en AWS y consola en Vercel. En local: `preview_start api` y `console`, partner `demo-audit`

**Restricciones**:
- «Recuperar» no puede distinguir ningún caso ni por el cuerpo ni por el tiempo.
- La app móvil sigue funcionando: `ServiceOut` y los ajustes de Reservas solo ganan campos opcionales.
- Nada toca «Autprod Staging», Meta Review Demo ni Jemma's Hair.

**Alcance**: unos 10 ficheros de API, unos 12 de consola, 1 migración

## Comprobación de la constitución

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto | ☑ | `tests/isolation/test_055_services_currency_category.py`: moneda y categorías no cruzan clientes. El partner de un reenvío sale de la invitación |
| II | Corte por superficie | ☑ | Superficie `0`, sin abrir ninguna |
| III | Lo leído es dato | ☑ | La categoría pasa por `_line`, como el nombre del servicio. Test con una categoría con forma de instrucción |
| IV | Acción consecuente con humano y auditoría | ☑ | Cambiar la moneda pide confirmación y queda auditado con cuántos servicios cambian. El reenvío queda auditado con actor de sistema |
| V | La pantalla no miente | ☑ | Es el motivo de H1, H2 y H3. Sin moneda no se inventa una |
| VI | Por API `console.*` | ☑ | No se navega nada; las pruebas locales son del desarrollador |
| VII | Test primero | ☑ | Cada corte empieza por su test: [tasks.md](tasks.md) |
| VIII | Licencias | ☑ | Sin dependencias nuevas |
| IX | La KB es dueña del porqué | ☑ | Sin nota: el encabezado de la spec lo dice y el owner aprobó la spec así |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantías 1 y 9, y la regla de que «Recuperar» no distingue | T040 y T041 |
| **Licencias** | Ninguna dependencia nueva | No aplica |
| **Medidor** | Nada que gaste saldo. Un correo más cuando se reenvía una invitación | No aplica |

## Estructura

### Documentación

```text
specs/055-correcciones-qa-consola/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/console-api.md
├── checklists/requirements.md
└── tasks.md
```

### Código

```text
apps/api/alembic/versions/0220_service_category.py
apps/api/src/nexus_api/
├── db/models/reservation.py                     # category
├── api/console/
│   ├── password_reset.py                        # reenviar si no hay cuenta
│   ├── team.py                                  # el envío pasa a invitation_reissue
│   ├── business.py, schemas_business_sections.py # confirmación, moneda, categoría
│   └── lite/reservas.py, reservas_schemas.py    # moneda y categoría
└── services/
    ├── invitation_reissue.py                    # nuevo
    └── business/
        ├── services_catalog.py                  # moneda conocida, repreciar, categoría
        ├── profile_edits.py                     # cambiar moneda repreciando
        ├── client_spec.py                       # category en la ficha
        └── compilation.py                       # etiqueta y categoría
apps/console/src/
├── components/business/sections/                # índice, datos básicos, servicios, políticas
├── components/builder/                          # builder-new, builder-model
├── components/clients/                          # «Más ajustes»
├── components/reservas/                         # modal y lista de servicios
├── lib/backend/                                 # tipos
└── i18n/lanes/                                  # textos
specs/047-la-fabrica-de-agentes/evidence/prototipo/agente.md  # §3.1
```

**Decisión de estructura**: se quedan los módulos actuales. Solo es nuevo `invitation_reissue.py`, porque `password_reset.py` no debe saber de los dos tipos de invitación.

## Lo que el plan añade y la spec no pedía

| Añadido | Por qué | Alternativa descartada |
|---|---|---|
| `currency_set` en los ajustes de Reservas | El modal tiene que saber si pedir la moneda, y `currency` debe seguir siendo texto para la app móvil | Hacer `currency` opcional rompe el tipo que usa la app |
| Bajar a una moneda sin decimales redondea | 15,50 USD no existe en CLP. Se redondea al entero más cercano y el aviso lo dice | Rechazar el cambio dejaría sin salida al negocio |
| La consola lite no edita la categoría | Su API de servicios es otra y no renombra servicios. Enseña los grupos y conserva la categoría | Llevarla a la lite es trabajo aparte, y nadie lo ha pedido |

El último punto corrige el supuesto de la spec, ya actualizado.
