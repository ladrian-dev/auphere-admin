# Contratos

**Esta spec no añade ni cambia ningún endpoint.** Esa es su característica más
importante y por eso el contrato se escribe: para que quede dicho, y para que
`/speckit-analyze` pueda comprobarlo.

## Lo que la consola consume, y de dónde

Todo existe ya. La columna «desde» dice qué spec lo trajo.

| Lectura | Endpoint | Desde | Quién lo usa ahora |
|---|---|---|---|
| Ficha del cliente | `GET /console/clients/{ref}` | 017 | Resumen (bloque «¿atiende?») |
| Consumo de un cliente | `GET /console/usage?client={ref}&days=30` | 004 · 016 | Resumen (bloque «¿cuánto consume?») |
| Estadísticas de conversación | `GET /console/clients/{ref}/conversations/stats?days=30` | CP-16 | Resumen (bloque «¿cómo va?») |
| Canales del cliente | `GET /console/clients/{ref}/channels` | CP-12 | Resumen y pantalla de Canales |
| Conectores del cliente | `GET /console/clients/{ref}/integrations` | 016 | Resumen y pantalla de Conectores |
| Capacidades del cliente | `GET /console/clients/{ref}/capabilities` | 017 | Pantalla de Habilidades |
| Datos del cliente | `PATCH /console/clients/{ref}` | CP-11 | Edición desde el Resumen |

## Contrato de interfaz que sí se define

El único contrato nuevo es **de componente**, no de red: el patrón de catálogo
que las tres pantallas comparten.

```
CatalogBrowser
  entrada:
    elementos      lista de {id, nombre, descripción, categoría, activo, estado}
    categorías     orden y etiqueta de cada grupo
    textos         qué se llama «activo» en esta pantalla, qué dice el vacío
    estado inicial búsqueda, pestaña y filtro leídos de la dirección
  salida:
    pinta          buscador · pestañas · filtro · grupos · contador · vacíos
    delega         qué se pinta dentro de cada elemento, y qué pasa al pulsarlo
```

**Lo que este contrato prohíbe**: que el componente sepa qué es una habilidad,
un conector o un canal. En cuanto lo sepa, deja de servir para los tres.

## Cómo viaja el estado

Búsqueda, pestaña y filtro van en la dirección de la página (R4.4), igual que
`?all=1` en Capacidades desde la spec 017: así un enlace se puede compartir y
volver atrás hace lo que el partner espera.

```
/clients/{ref}/capabilities?q=cita&ver=activas&cat=appointments
```

## Redirecciones que esta spec crea

Permanentes, porque las direcciones viejas están en correos y marcadores.

| De | A | Por qué |
|---|---|---|
| `/clients/{ref}/settings` | `/clients/{ref}` | Los datos del cliente se editan en el Resumen |
| `/clients/{ref}/agent/settings` | `/clients/{ref}/agent` | Los ajustes son parte del agente |

Las de la spec 017 (`/tools` y `/skills` → `/capabilities`) **siguen en pie**.
