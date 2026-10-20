# Para agentes que trabajen en apps/mobile

Expo/React Native (SDK 58). Antes de tocar nada, lee `docs/app-movil.md` y la
spec 031; la spec viva manda.

## Expo cambia en cada SDK: no te fíes de lo que recuerdas

Antes de escribir código que toque una API de Expo, EAS o React Native:

1. Mira la versión de `expo` en `package.json`.
2. Lee la documentación de esa versión: `https://docs.expo.dev/versions/v<major>.0.0/`
   o el índice `https://docs.expo.dev/llms.txt`.
3. Deja que `pnpm typecheck` valide: los tipos de los módulos son la verdad.

## Reglas de esta app

- Instala con `npx expo install <paquete>` (elige la versión compatible con el
  SDK) y lee su licencia antes (constitución §VIII; tabla en `research.md`).
- Nada de hex: el color sale de `useTheme().colors` (`tokens.gen.ts`).
- Las palabras de la consola salen de `src/i18n/lite.gen.ts`; las propias, de
  `src/i18n/app.{es,en}.ts`. Nunca las dupliques.
- Las rutas son de expo-router en `src/app/`; lo demás vive fuera.
- Antes de dar algo por hecho: `pnpm verify` (o `./scripts/verify.sh mobile`
  desde la raíz).
