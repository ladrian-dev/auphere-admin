# Crítica final del panel — después de las specs 031–034

Recorrido en local el 2026-10-19 (rama `032-modulos-por-partner`, que contiene 031, 034 y
033), 1440×900 claro y oscuro, 375×812 claro. Método `/design:design-critique`, contra la
línea base de [`research.md`](../research.md).

## Impresión general

El panel se lee como la consola: mismos tokens, controles de 32 px, tipografía Inter y
modo oscuro. Abre en un Panel que dice qué espera al equipo; las fichas de partner y
cliente cuentan sus hechos antes de cualquier pestaña.

## Lo que cambió frente a la línea base

| Hallazgo de la línea base | Estado |
|---|---|
| Se aterrizaba en una tabla de «tenants» | ✅ Panel con cifras y «Necesita tu atención» |
| Sidebar plano y en dos idiomas | ✅ Panel · Gestionar · Plataforma · Instancia, en español, contador de tickets, ⌘K |
| Clientes sin partner, sin búsqueda | ✅ Columna de partner enlazada, búsqueda y tres filtros |
| Ficha de partner abría en «Keys», sin edición | ✅ Resumen editable, Equipo, Módulos, Dinero, Configuración |
| Saldo en créditos y recarga en «tokens» | ✅ US$ en todas partes; recarga con confirmación e idempotencia; «¿cuadra el libro?» |
| 22 copias de primitivas y escala inflada | ✅ `@nexus/ui`, lint sin avisos |
| Agente: una página de 5–7 pantallas | ✅ Prompt · Runtime · Versiones · Evals |

## Usabilidad pendiente

| Hallazgo | Severidad | Recomendación |
|---|---|---|
| Un cliente sin nombre en datos de demo se lista como «Sin nombre» | 🟢 | Dato, no interfaz |
| La pestaña Configuración agrupa límites, modelos y claves en una columna larga | 🟡 | Sub-secciones como en Agente si crece |
| Roles de operador: todos ven todo | 🟡 | Spec «Operadores» |

## Accesibilidad

- Contraste: textos de estado con los pares `-text` de los tokens (AA).
- Las casillas de Módulos llevan nombre accesible propio; el formulario anuncia el error
  con `role="alert"`.
- Los botones que son enlaces declaran `nativeButton={false}`.

## Lo que funciona

- La rejilla de Módulos se lee como la de funciones de Chatwoot: grupos, contador y filtro.
- La conciliación del libro dice, en una frase, si el dinero cuadra.
