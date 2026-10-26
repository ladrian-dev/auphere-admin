# Contrato — panel de operador (`/admin/*`)

Rutas del panel de operador de Auphere, con la identidad de operador de hoy
(ADR-034). Es la única superficie que enseña costes (requisito 54.11). Cada
escritura queda en la auditoría con la persona de Auphere y su motivo.

## 1. Catálogo de modelos

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /admin/models/deployments?status=&provider=&task=` | Despliegues con capacidades, residencia, retención, licencia, contrato, estado, retirada, cuota, precio vigente y certificaciones | 41.1 |
| `POST /admin/models/deployments` | Alta en `draft` | 41.1 |
| `PATCH /admin/models/deployments/{id}` | Editar; las capacidades y la región caducan las certificaciones (requisito 42.2) | 41.1 |
| `POST /admin/models/deployments/{id}/prices` | Precio nuevo con `valid_from` y fuente; si sube más de un 10 % el precio estimado de un agente, avisa a su partner antes de que entre en vigor | 41.8 |
| `POST /admin/models/deployments/{id}/activate` | Aplica las comprobaciones del requisito 41.2; `422` diciendo qué falta | 41.2 |
| `POST /admin/models/deployments/{id}/retire` | `{retire_after}`: avisa con 30 días o más y propone el sustituto a los agentes fijados | 41.7 |
| `POST /admin/models/deployments/{id}/unavailable` | El router deja de usarlo desde el siguiente turno | 41.9 |

## 2. Router

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /admin/router/taxonomy` | Taxonomía de tareas vigente y su versión | 40.1 |
| `GET /admin/router/profiles` · `PUT /admin/router/profiles/{profile}` | Política por tarea (`router-and-catalog.md` §3); exige `reason`; versión nueva desde el siguiente turno | 40.13, 54.2 |
| `POST /admin/router/preview` | `{tenant_id, agent_id, task, profile?}` → candidatos, descartes con motivo y cadena elegida, sin llamar a ningún modelo | 54.2 |
| `GET /admin/router/anomalies?since=` | Modelos de reserva, `no_model` y despliegues enfriados | 54.9 |

## 3. Certificación

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /admin/certifications?deployment=&task=&agent=` | Por clase y por agente: batería, fecha, notas y caducidad | 42.7, 54.3 |
| `POST /admin/certifications/runs` | `{deployment_id, tasks[] \| agent_ids[]}` → trabajo; lo paga Auphere, fuera de las partidas | 42.6 |
| `GET /admin/certifications/batteries` · `POST /admin/certifications/batteries` | Versiones de la batería común en español | 42.1 |

## 4. Constructor

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `POST /admin/builder/eval-runs` | Corre el banco de 100 descripciones | 54.4 |
| `GET /admin/builder/eval-runs` · `GET /admin/builder/eval-runs/{id}` | % que pasa el validador a la primera, % que pasa la batería del sector sin edición, p90 del borrador; comparación con la anterior | 54.4, CE-002, CE-003 |
| `GET /admin/sector-tests` · `PUT /admin/sector-tests/{sector}` | Las 12 pruebas por sector, con versión | 54.10 |

## 5. Partners y clientes

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `PUT /admin/partners/{id}/build-budget` | Tope mensual de «Construcción y pruebas» | 46.5, 54.5 |
| `GET/PUT` de `api/admin/partner_models.py` (existe) | Modelos permitidos al partner (`partner_model_allowlist`), con su pantalla en `partners/[id]/models` | 54.5 |
| `PUT /admin/partners/{id}/account-currency` | Cambio de moneda de la cuenta, con conversión y asiento | 43.1 |
| `POST /admin/partners/{id}/console-v2/dry-run` | Migración en modo ensayo → informe: batería por agente y audiencia por número, antes y después | 55.4 |
| `POST /admin/partners/{id}/console-v2/enable` · `/disable` | Activa con el informe sin diferencias; desactivar devuelve la consola de hoy hasta que el partner confirme el reparto | 55.2, 55.5 |
| `PUT /admin/clients/{tenant_id}/sovereign` | Restricción soberana `{enabled, reason}` | 54.6 |
| `GET /admin/partners/{id}/build-budget/requests` | «Pedir ampliación» recibidas | 46.5 |

## 6. Canales e integraciones

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /admin/whatsapp/login-beta/countries` · `PUT /admin/whatsapp/login-beta/countries/{iso2}` | Activar o quitar la beta por país; rechaza los países de la UE y del EEE | 31.5, 54.7 |
| `GET /admin/catalog/channels` · `GET /admin/catalog/integrations` | Catálogos, con «Próximamente» y «Pendiente» (que también ve el catálogo de canales de la consola de partners, constitución 1.2.0) y el esquema de ajustes de cada integración | 36.2, 54.8 |

## 7. Anomalías y conciliaciones

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /admin/ledger/reconciliation?date=` | Cuadre diario de cuentas, bolsas y gasto, con las diferencias | 43.9 |
| `GET /admin/channels/meta-reconciliation?date=` | Mensajes entregados por Meta frente a guardados, por canal | 2.6 |
