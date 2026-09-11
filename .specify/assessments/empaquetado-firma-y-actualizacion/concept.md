# Concept: la cadena de distribución de la aplicación

- **Slug**: empaquetado-firma-y-actualizacion
- **Fecha**: 2026-09-11
- **Apetito**: `medium` — una spec, sin segundo frontend y sin plataforma nueva.
  Lo que la hace mediana y no pequeña es que toca secretos, integración continua
  y una superficie de confianza.

## La forma

Una sola cadena, que corre igual en una máquina y en integración continua:

```
construir  →  firmar (hardened runtime + permisos)  →  notarizar  →  grapar  →  publicar
```

Y en la app, dos piezas: el actualizador (comprueba, descarga, aplica al salir)
y la puerta de versión mínima en la plataforma.

## Las tres decisiones que no son técnicas

### D1 · Dónde vive el canal

| Opción | A favor | En contra |
|---|---|---|
| **Almacenamiento en AWS con CDN delante** | Donde ya vive todo; control del acceso; encaja con el despliegue existente | Hay que montarlo |
| Releases de GitHub | Gratis y en cinco minutos | En repositorio privado obliga a incrustar un token **dentro del binario del cliente**: un secreto en la máquina de cada partner |
| Servir desde la API | Un sitio menos | Mezcla el plano de datos con la distribución de binarios; el ALB no es un CDN |

**Recomendación: la primera.** La segunda se descarta por el token, no por el
precio.

### D2 · Cuándo se aplica una actualización

Descargar en segundo plano y aplicar **al salir**. Nunca reiniciar sola.

Esta app no es un editor de texto: puede tener una tarea en `esperandote` y un
comando corriendo en la máquina del partner. Reiniciar en medio deja un asiento
de auditoría abierto y una persona sin saber qué pasó con lo que pidió. La
pantalla ya sabe nombrar estados; «hay una versión nueva, se instala al cerrar»
es uno más y no un diálogo que interrumpe.

Con despliegue por porcentaje, porque el puente es saliente: si una versión lo
rompe, no hay forma de empujar el arreglo.

### D3 · Quién firma

Integración continua, con la identidad guardada como secreto y un llavero
temporal por ejecución. Firmar desde el portátil de alguien hace que la cadena
dependa de esa máquina y de ese llavero.

Consecuencia que hay que aceptar: **el certificado pasa a ser un secreto de
producción**, con su rotación y su revocación. Va en la spec, no en un `README`.

## Alcance

**Dentro**: macOS (arm64 e Intel), firma, notarización, grapado, DMG para la
primera instalación y ZIP para actualizar, canal de publicación, actualizador en
la app con su estado en pantalla, versión mínima exigible en la plataforma,
icono de aplicación, y la cadena en integración continua desde un tag.

**Y lo primero de todo, antes de firmar nada**: que la integración continua
ejecute las pruebas de `apps/desktop` y de `packages/companion-ui`. No es
alcance prestado: no tiene sentido construir una cadena que empaqueta y firma
una aplicación cuyas pruebas nadie corre al fusionar. Son dos trabajos nuevos en
`ci.yml` y media hora; el orden importa porque la cadena de firma se va a colgar
de ese mismo fichero.

**Fuera**: Windows (se dice cuándo), App Store, la edición sobre KiroCrew,
telemetría, y actualizaciones diferenciales (el ZIP completo basta a este
tamaño).

## Lo que se reutiliza

- La app ya se identifica con su versión en el latido y en el agente de usuario:
  la puerta de versión mínima no necesita cañería nueva.
- La pantalla ya tiene estados honestos donde colgar «hay una versión nueva».
- El despliegue a AWS ya existe y ya guarda secretos de producción.

## Riesgos

| Riesgo | Qué lo contiene |
|---|---|
| El canal de actualización como vía de ejecución remota en la máquina del partner | La firma se verifica antes de aplicar; publicar exige pasar por la cadena; el canal es solo lectura para todo el mundo menos la cadena |
| El certificado se pierde o se filtra | Copia sellada fuera de la cadena; revocación documentada; rotación probada una vez |
| Se firma con `hardenedRuntime` sin permisos y la app no arranca | Es el primer error esperado; hay una prueba de humo que abre el `.app` firmado antes de publicar |
| Una versión rompe el puente y deja máquinas fuera | Despliegue por porcentaje y una versión anterior siempre disponible en el canal |
| El diálogo de permisos del sistema aparece sin contexto la primera vez | La pantalla que declara el directorio lo explica antes |
| Se empaqueta una versión con la aplicación rota porque nadie corre sus pruebas | Los dos trabajos nuevos de integración continua, **antes** que la cadena de firma |
| Alguien verifica en local lo que conoce y la tubería descubre el resto | Un solo comando de verificación, usado por la persona y por la tubería |
