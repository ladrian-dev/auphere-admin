# Especificación: módulos — qué ve cada consola, y el Companion se enciende

**Rama**: `032-modulos-por-partner` · **Creada**: 2026-10-18 · **Estado**: Aprobada para plan

**Entrada**: owner, 2026-10-18 — «una visión que tengo dentro de la consola de Admin es
poder asignar qué servicios o vistas pueden tener nuestros partners o nuestros clientes en
sus consolas. Necesitamos tenerlo ordenado primero en la consola de super admin. Adicional
vamos a necesitar corregir el Companion para poder activarlo también». Decisión del mismo
día: el admin asigna y **la consola ya obedece** en esta ronda.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola y panel de operador |
| **Garantías de aislamiento tocadas** | Frontera partner A ↔ partner B: los módulos de A nunca aparecen en el principal ni en `/console/me` de B. `partners` no lleva RLS a propósito (la puerta de la consola la lee antes de que exista ámbito, igual que `console_enabled`). Barrido: `tests/isolation/test_partner_access_scope.py` |
| **Nota de KB que la justifica** | `[[ADR-045-modulos-por-partner]]` · `[[ADR-033-companion-de-consola]]` (CO-08 §10) |
| **Qué se mide** | Nada nuevo |

## Origen

- Los clientes ya tienen módulos (`panel · inbox · usage`, spec 030); los partners no:
  ven todo según el rol.
- `partners.companion_enabled` nace en `false` y **ningún endpoint ni pantalla lo
  enciende**: hacía falta SQL (`.specify/assessments/teammate-guia-de-auphere/intake.md`).

## Clarifications

### Session 2026-10-18

- Q: ¿Hasta dónde llega esta ronda? → A: **El admin asigna y la consola obedece** (owner).
- Q: ¿El Companion es un módulo? → A: **Sí**; encenderlo es marcar su módulo.
- Q: ¿Qué pasa con una sección no asignada? → A: Desaparece del menú y del buscador; su URL lleva al primer módulo. Ninguna pantalla «bloqueado» (§V).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Auphere elige las secciones de un partner (P1)

1. **Dado** un partner, **cuando** el operador abre Módulos, **entonces** ve una rejilla agrupada (Operar · Cuenta · Asistente) con lo que está encendido y un contador por grupo.
2. **Dado** el operador apaga Facturación y guarda, **cuando** el partner recarga su consola, **entonces** Facturación no está en su menú ni en ⌘K, y `/billing` lo lleva a su primer módulo.
3. **Dado** cualquier cambio, **cuando** se guarda, **entonces** la auditoría nombra al operador.

### Historia 2 — El Companion se enciende desde el admin (P1)

1. **Dado** un partner sin Companion, **cuando** el operador marca el módulo y guarda, **entonces** la burbuja aparece en la consola del partner para los roles que pueden usarla.

### Casos límite

- Consola encendida sin ninguna sección (o solo Companion): 422 `no_modules` y el formulario lo dice.
- Un partner sin secciones de menú en su principal se lee como consola apagada (`/no-access`).
- Con la consola apagada, las casillas siguen activas: la elección se aplica al encenderla.

## Requisitos *(obligatorio)*

### Requisito 1 — Catálogo y datos

1. El sistema DEBE declarar un único catálogo de módulos de partner: `panel, clients, usage, audit, knowledge, workstation, team, billing, keys, companion`.
2. El sistema DEBE guardar los módulos de cada partner en orden canónico y rechazar cualquier otro valor.
3. WHEN se despliega THEN cada partner DEBE conservar todas sus secciones, y el Companion donde ya estaba encendido.

### Requisito 2 — Escritura desde el admin

1. `GET/PUT /admin/partners/{id}/access` DEBEN leer y escribir consola encendida y módulos; el `PUT` DEBE exigir `X-Operator-Id` y auditar con el operador.
2. IF la consola queda encendida sin módulo de menú THEN el sistema DEBE responder 422 `no_modules`.
3. WHEN cambia el módulo `companion` THEN `companion_enabled` DEBE cambiar en la misma transacción.

### Requisito 3 — La consola obedece

1. `/console/auth/session` y `/console/me` DEBEN devolver los módulos del partner.
2. El menú del partner DEBE mostrar solo las entradas cuyo módulo está asignado **y** cuyo permiso tiene el rol.
3. WHEN un miembro abre una sección sin módulo THEN el sistema DEBE llevarlo a su primer módulo.
4. La paleta ⌘K NO DEBE ofrecer secciones sin módulo.
5. La burbuja del Companion DEBE montarse solo con el módulo `companion`.

## Criterios de éxito

- **CE-001**: encender el Companion de un partner es un clic en el admin, sin SQL.
- **CE-002**: apagar una sección la quita del menú, del buscador y de su URL en la siguiente carga.

## Fuera de alcance

- Que la API rechace las llamadas de un módulo no asignado (`require_module` en los routers) — siguiente spec; hoy la API ya acota por partner y por rol, y el módulo es un derecho de uso, no una frontera de aislamiento.
- Retirar la columna `companion_enabled` — cuando el módulo haya vivido un ciclo de despliegue.
- Módulos de cliente nuevos — siguen siendo `panel · inbox · usage` (spec 030).
