# Checklist de calidad de la especificación: la aplicación se instala, y se arregla sola

**Propósito**: validar que la spec está completa antes de planificar
**Creada**: 2026-09-14
**Feature**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalle de implementación (lenguajes, frameworks, API)
- [x] Centrada en el valor y la necesidad de negocio
- [x] Legible por alguien que no programa
- [x] Todas las secciones obligatorias completas

> La spec no nombra `electron-builder`, ni S3, ni CloudFront, ni GitHub Actions
> en sus requisitos: dice «canal accesible por HTTPS y de solo lectura»,
> «cadena de integración continua» y «artefacto de instalación y de
> actualización». El **cómo** es del plan. Sí nombra el commit `e100564` y las
> rutas del repositorio en la sección de estado real, que es un contraste de
> hechos y no un requisito.

## Completitud de los requisitos

- [x] **No quedan marcas `[NEEDS CLARIFICATION]`** — las tres se cerraron el
      2026-09-14, y una cuarta decisión que la spec daba por resuelta se cerró
      con ellas:
      - R2.6 → **disparo manual de la cadena sí; subida directa al canal no**
      - R3.6 → **canal único, sin gradual**, con el contra registrado
      - R4.4 → **cañería puesta y apagada**, con preaviso y con avisar ≠ bloquear
      - R3.2 → **la barra gana un estado**: no había ninguno donde colgarlo
- [x] Requisitos comprobables e inequívocos (EARS, verbo normativo único)
- [x] Criterios de éxito medibles
- [x] Criterios de éxito sin tecnología dentro
- [x] Escenarios de aceptación definidos en las tres historias
- [x] Casos límite identificados — y el peor está nombrado: **una versión que
      rompe el puente saliente no se puede arreglar empujando nada**
- [x] Alcance acotado — «Fuera de alcance» separa explícitamente el
      emparejamiento sin código, que es otra superficie (§II)
- [x] Dependencias y supuestos identificados, incluido el riesgo de revocación
      de una identidad de firma que **no es nuestra**

## Preparación de la feature

- [x] Cada requisito funcional tiene criterios de aceptación
- [x] Las historias cubren los flujos principales (instalar · actualizar · dejar
      fuera una versión vieja)
- [x] La feature satisface los criterios de éxito declarados
- [x] No se filtra detalle de implementación a los criterios de éxito

## Puertas de la constitución

- [x] **Superficie declarada** (§II) — **nueva**, con la razón de por qué no
      cabe dentro de la actual y por qué se abre por su mitad barata
- [x] **Aislamiento** (§I) — ninguna de las 7 garantías se debilita; la prueba
      que la superficie nueva exige es de **integridad de artefacto**, y está
      declarada en R1.5, R3.4 y R3.5
- [x] **Medidor** — no consume modelo, reloj ni herramienta de pago; declarado
- [x] **Nota de KB** (§IX) — `[[teammates/14-mvp-y-fases]]` §1, más el assessment
- [x] **Licencias** (§VIII) — confirmado en el plan: **ninguna dependencia
      nueva**. `electron-builder` y `electron-updater` ya están (MIT), las
      herramientas de firma vienen con Xcode, y la acción de credenciales de AWS
      ya se usa en `deploy-prod.yml`
- [x] **Constitution Check completo** — las nueve filas en [plan.md](../plan.md),
      re-evaluadas tras el diseño

## Notas

- **El estado real contradice a los `tasks.md` y al propio assessment**, y la
  spec lo recoge en su tabla: `T057` de la 001 dice que la firma está bloqueada
  por certificados que **existen desde el 2026-09-13**, y los puntos 6 y 7 del
  assessment (pruebas en la tubería y comando único de verificación) **ya están
  resueltos**. Lo que falta es la cadena, sus secretos y el sitio donde publicar.
- `infra/terraform/40-releases/` **no contiene ningún `.tf`**: sólo un
  `prod.tfplan` binario de un módulo que nunca se versionó. R7 lo aborda.
- El bucket de releases **no se pudo verificar**: las credenciales de esta
  máquina son de la cuenta `831081046687` y producción es `793033583982`.
- **`/speckit-clarify` destapó un requisito que se apoyaba en algo que no
  existe.** R3.2 decía que la actualización se anunciaría «con los estados que
  la pantalla ya tiene»; los siete estados de la barra son todos de conexión y
  emparejamiento, y el commit rescatado sólo añade `liveCount` para que el
  actualizador sepa si hay sesiones vivas. La spec añade ahora **un** estado, y
  lo declara como superficie de interfaz nueva en vez de dejarlo aparecer en el
  plan.
- La decisión sobre la versión mínima **se buscó, no se recordó**: Slack
  (preaviso de seis meses, calendario publicado), Zoom (mínimo trimestral con 90
  días de aviso) y la práctica corriente en Electron (blando por defecto, bloqueo
  sólo por contrato roto o seguridad, nunca forzar el reinicio). De ahí salen
  tres criterios que el borrador no tenía: R4.5, R4.6 y R4.7.
