# Auditoría de seguridad (/cso): spec 069, app móvil

- **Fecha:** 2026-11-21
- **Alcance:** `git diff HEAD -- apps/mobile` y los archivos sin seguimiento de `git status --porcelain` (worktree `069-app-movil`, rama `069-la-app-con-el-diseno-nuevo`).
- **Modo:** diario, solo el diff, de solo lectura. No se tocó código, índice ni `node_modules`.

## Resumen

| Severidad | Número |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 0 |
| LOW | 5 |
| INFO | 3 (uno de ellos anterior a la 069 y fuera del diff) |

**Veredicto:** el modo demo no puede activarse en un build de tienda ni en una actualización OTA, no hay secretos en el diff y las tres dependencias nuevas no ejecutan scripts al instalarse. Ningún hallazgo bloquea el paso a tiendas.

## Hallazgos

| # | Sev | Fichero:línea | Hallazgo | Arreglo (una línea) |
|---|---|---|---|---|
| L1 | LOW | `apps/mobile/package.json:36` | `lucide-react-native` va como `^1.77.0`. Es la única dependencia nueva sin versión exacta; el lockfile fija 1.77.0, pero un `pnpm install` o `npx expo install` fuera de CI puede subir de minor a una release que nadie ha revisado. Lucide publica muy a menudo. | `"lucide-react-native": "1.77.0"`. |
| L2 | LOW | `apps/mobile/src/api/client.ts:31-33`, `src/api/sse.ts:121-125` | Que el negocio de ejemplo quede fuera del bundle depende de que cada `require("./demo")` siga dentro de `__DEV__ && DEMO`. Si mañana alguien añade un `import` estático de `@/api/demo/...` o quita el `__DEV__ &&`, ningún test ni lint falla, y los datos de ejemplo (con su sign-in que acepta cualquier credencial) entrarían en el bundle de tienda. | Regla ESLint `no-restricted-imports` para `@/api/demo*` y `./demo*` fuera de `src/api/demo/`, `client.ts`, `sse.ts` y `__tests__/`. |
| L3 | LOW | `apps/mobile/__tests__/version.test.ts:40-43` | El test lee el `env` tal cual de `preview`, `staging` y `production`, sin resolver `extends`: un `EXPO_PUBLIC_DEMO` puesto en `base.env`, o en las variables de entorno de EAS en expo.dev, pasaría el test. Hoy lo para la puerta de `__DEV__`, así que es una sola capa. | Resolver `base` + perfil en el test y comprobar también `APP_HELVENA`. |
| L4 | LOW | `apps/mobile/src/api/demo/data.ts:184,222,240,280,323,338,356,381,393,422`; `src/api/demo/reservas.ts:71-73` | Los nombres son ficticios, los correos terminan en `.test`, la URL de Instagram es `instagram.test` y los tokens se llaman `demo-…-not-a-real-secret`. Pero los teléfonos tienen formato de móvil español válido: los `+34 600 000 001–005` de la Bandeja, y cualquier `+34 600 000 0NN` que salga de `phoneOf` en Reservas. Tampoco consta que España reserve un rango para ficción. Además, `@sofi.herrera`, `@marta.gil`, `@carmen.ortiz`, `@ana.ruiz` y `@nuria.campos` son handles verosímiles. No comprobé si alguno existe. Si una captura de tienda sale del modo demo, podría atribuir conversaciones de una clínica dental a personas reales. | Usar handles con sufijo inequívoco (p. ej. `@sofia.ejemplo`) y números de un rango de ficción (Ofcom `+44 7700 900xxx`), o no usar el modo demo para capturas públicas. |
| L5 | LOW | `apps/mobile/package.json:7` (`@shopify/react-native-skia` y sus dependencias) | El motor de Skia llega como binarios precompilados en `react-native-skia-{android,apple-ios,apple-macos,apple-tvos}@154.0.0`, publicados desde `wcandillon/react-native-skia-binaries` (la cuenta personal de un mantenedor, no la organización de Shopify). Es código nativo dentro de la app firmada que no se puede revisar, y solo lo fija el `integrity` del lockfile. | Mantener la versión exacta y revisar el `integrity` de esos cuatro paquetes en el diff del lockfile en cada subida. |
| I1 | INFO | `apps/mobile/src/features/inbox/thread/comment-post.tsx:50` | `Linking.openURL(post.permalink)` sin comprobar el esquema. El permalink viene de la Graph API de Meta, a través de la API (`inbox_comment_post.py:69-95`), y es la publicación del propio negocio: hoy no lo controla un atacante. | Abrir solo si `post.permalink.startsWith("https://")`. |
| I2 | INFO | `apps/mobile/app.config.ts:46-47,131-147` | Helvena solo se incrusta con `APP_HELVENA=1` y los TTF presentes. La carpeta `assets/fonts/helvena/` está en `.gitignore:58`, no hay `.easignore` y la carpeta no existe en local, así que un build en la nube de EAS no puede llevarla. Queda abierto un build local de release con la fuente sin licencia: es un riesgo legal, no de seguridad. No hay descarga en tiempo de ejecución (`src/theme/fonts.ts:14`). | En `app.config.ts`, fallar si `helvena && variant !== "development"` hasta confirmar la licencia. |
| I3 | INFO | fuera del diff (`expo>@expo/cli`) | **Anterior a la 069.** `pnpm audit --prod` da 26 avisos: 9 high, 11 moderate y 6 low. Todos entran por `expo>@expo/cli` (node-forge ≤1.4.2, zod <4.6.6, glob, minimatch) o por la cadena de jest. Es herramienta de build, no va en el bundle, y la 069 no toca `expo`. **Ninguno** afecta a las tres dependencias nuevas ni a sus transitivas. | Tarea aparte: subir el parche del SDK cuando salga, o `overrides` de `node-forge>=1.4.3`. |

## Controles comprobados (no son hallazgos)

- **El modo demo nunca se activa en un build de tienda ni en una OTA.** Comprobado leyendo el código, sin ejecutar nada.
  - `demoOf` exige `__DEV__` (`src/config.ts:42-46`), y `demo-mode.test.ts` cubre que `demoOf("1", false)` sea `false`.
  - `publicApi` (`client.ts:184`) y `upload` (`client.ts:210`) usan `DEMO`, que ya incluye `__DEV__`.
  - Ningún perfil de `eas.json` define `EXPO_PUBLIC_DEMO`, y `app.config.ts` no lee esa variable: solo lee `EAS_PROJECT_ID`, `EAS_OWNER`, `APP_VARIANT`, `APP_HELVENA` y `GOOGLE_SERVICES_JSON`.
  - Los únicos usos de `api/demo` fuera de su carpeta son los dos `require` protegidos.
- **Fuera del bundle de release: esperado, pero no verificado con un `expo export`.** Al no haber `metro.config.js`, aplica el transformador de Expo (`@expo/metro-config` 58.0.16). Ese transformador aplica `constantFoldingPlugin` cuando `!options.dev` (`transform-worker/metro-transform-worker.js:367,403`), antes de recoger dependencias (`:442`). Con `__DEV__` en `false`, el `require("./demo")` desaparece del bundle.
- **Sign-in de ejemplo.** `routes.ts:162-180` acepta cualquier credencial, pero solo en memoria y en desarrollo. Sus tokens (`routes.ts:47`) no son secretos reales.
- **Sin secretos en el diff.** Busqué AKIA, `sk-`, `ghp_`, `xox*`, claves privadas, JWT, `NEXUS_ADMIN_TOKEN`, `EXPO_TOKEN` y `SENTRY_AUTH_TOKEN` en el diff (sin el lockfile) y en los archivos nuevos: nada. Solo aparecen contraseñas de prueba en `__tests__/demo-router.test.ts:175,331`. `.npmrc` no lleva tokens y `.env*` está ignorado.
- **Cadena de suministro.**
  - Licencias: MIT y MIT/ISC, leídas en `docs/licenses/app-movil-069.md`.
  - Scripts de instalación: no hay `preinstall`, `install` ni `postinstall` en los tres paquetes ni en sus transitivas (`css-select@5.2.2`, `css-tree@1.1.3`, `react-native-skia-*@154.0.0`, `canvaskit-wasm@0.41.0`, `react-reconciler@0.31.0`). `install-skia*` son scripts manuales, no de ciclo de vida. Además, `pnpm-workspace.yaml:11` (`onlyBuiltDependencies: []`) bloquea cualquier script de build de dependencias.
  - Versiones resueltas (`pnpm list`): `react-native-svg` 15.16.0, `@shopify/react-native-skia` 2.14.0 y `lucide-react-native` 1.77.0.
- **Pantallas de entrada.**
  - `src/auth/*` no cambia.
  - El sign-in mantiene `secureTextEntry` y `autoComplete="current-password"`, y `EntryField` los pasa al `TextInput` (`entry-field.tsx:31,78`).
  - «¿Olvidaste tu contraseña?» sigue respondiendo lo mismo exista o no la cuenta (`sent_if_known`). La espera de 30 s (`forgot-password.tsx:17`) es solo de UX: el límite real lo pone el servidor, por email (`apps/api/.../console/password_reset.py:68-134`).
- **Fotos de contacto.**
  - `avatarUrl` siempre apunta a `API_URL` (`v13-bandeja.ts:51-58`): el bearer nunca sale hacia terceros.
  - Todas las fotos se pintan con `Avatar`, que usa `cachePolicy="memory"` (`ui/bits.tsx:58`): nada de los clientes finales va a disco.
  - En modo demo, `has_avatar` es `false` (`demo/inbox.ts:244,304`).
- **Aislamiento.** Las llamadas nuevas no envían `tenant_id` (`v13-ajustes.ts:21-23`).

## Límites de esta auditoría

- **Lockfile.** `apps/mobile/pnpm-lock.yaml` no se pudo leer porque los permisos de la sesión lo deniegan. Las versiones se confirmaron con `pnpm list` y `node_modules/.pnpm`. **No se revisaron** los hashes de `integrity`, el diff del lockfile ni si contiene URLs con credenciales.
- **Capturas.** De las 35 PNG que había en `evidence/` al cerrar el informe se vieron 5 (entrar, ajustes, bandeja, conversación en espera y reservas del día). Todas muestran el negocio de ejemplo. La afirmación «sin datos personales reales en las capturas» vale solo para esa muestra.
- **Fases omitidas:**
  - 2: no hay historial que revisar, porque el diff no está confirmado.
  - 4-6: el diff no toca CI, infraestructura ni webhooks.
  - 7: la app no construye prompts, y los mensajes se pintan como `Text`.
  - 8: no hay skills en el diff.
  - 14: no se escribió el JSON de `.gstack/`, porque la tarea solo permite escribir este fichero.
- **Pasos de la skill no ejecutados:** el preámbulo, la telemetría, las *learnings* y las preguntas interactivas. La verificación de cada hallazgo es mía, no de verificadores independientes.

---

*Esta herramienta no sustituye una auditoría de seguridad profesional. /cso es un primer pase asistido por IA que detecta patrones de vulnerabilidad comunes; no es exhaustivo, no garantiza la ausencia de fallos y puede dar falsos negativos. Para sistemas en producción con datos personales o pagos, contrata una auditoría o un pentest profesional.*
