# Research · línea base del panel antes de la 031

Capturas tomadas el 2026-10-18 en local (`develop` = `28a5b562`), 1440×900, tema claro:
`/tenants`, `/tenants/{id}` (Mouna), `/partners`, `/partners/{id}/wallet`.

## Crítica de diseño (método `/design:design-critique`)

### Impresión general

Paleta y tipografía editoriales con oficio, pero el panel se lee como un producto
distinto de la consola: controles hinchados, navegación sin jerarquía y fichas que no
cuentan lo que el operador necesita saber de un partner.

### Usabilidad

| Hallazgo | Severidad | Recomendación |
|---|---|---|
| Se aterriza en una tabla de 18 «tenants»; no hay vista de lo que necesita atención | 🔴 | Panel de inicio con métricas y «Necesita tu atención» |
| Sidebar plano de 6 entradas, mezcla inglés y español («Tenants», «Altas», «Auphere channels») | 🟡 | Grupos a la Chatwoot y todo en español |
| El listado de clientes no dice de qué partner es cada uno; sin búsqueda ni filtros | 🔴 | Columna de partner enlazada, búsqueda y filtros |
| La ficha de partner abre en «Keys»; contacto y facturación no se pueden editar | 🔴 | Resumen como primera pestaña, con edición |
| Saldo en créditos crudos (200.000.000) y recarga «Qty purchased» por defecto 1000 | 🔴 | US$ en todas partes (spec 033) |
| La ficha de cliente abre con «No se pudo calcular el estado» a toda anchura | 🟡 | Estado de error compacto en su tarjeta |
| Nueve pestañas en la ficha de partner y nueve en la de cliente | 🟡 | Agrupar: Resumen · Clientes · Equipo · Dinero · Configuración · Conocimiento · Auditoría |

### Jerarquía visual

- **Lo primero que se ve**: el título serif grande («Portafolio de agentes»), no un dato.
- **Lectura**: título → contador → tabla; ninguna cifra destaca lo urgente.
- **Énfasis**: el botón verde «Nuevo cliente» compite con el título; los estados
  («provisioning» en inglés) no destacan.

### Consistencia

| Elemento | Problema | Recomendación |
|---|---|---|
| Espaciado | `--spacing-7` = 48 px: botones y filas altos frente a la consola (32 px) | Tokens de `@nexus/ui` |
| Componentes | 22 copias de shadcn divergentes de `@nexus/ui` | Importar del paquete |
| Color | 49 colores por variable arbitraria, ~55 de la paleta de Tailwind | Utilidades de token y lint |
| Copy | Inglés y español mezclados («Keys», «Connectors», «Qty purchased») | Español |

### Accesibilidad

- **Contraste**: textos de estado en `--color-status-*` sólido sobre blanco no llegan a
  AA en tamaño pequeño; los tokens de `@nexus/ui` tienen pares `-text` para eso.
- **Objetivos táctiles**: suficientes (sobrados) por la escala inflada.
- **Lectura**: eyebrows `text-[10px]` mono en mayúsculas cuestan de leer.

### Lo que funciona

- Paleta de marca contenida y sin degradados; estados con punto de color.
- Migas y pestañas subrayadas sobrias; copy humano en los vacíos.

### Prioridades

1. **Un solo sistema de diseño** — arregla de raíz tamaños, color y modo oscuro.
2. **Panel + sidebar agrupado** — orienta al equipo en un vistazo.
3. **Fichas de partner y cliente que cuentan los hechos** — lo pidió el owner.
