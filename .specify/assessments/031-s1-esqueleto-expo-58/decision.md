# Decision Gate: spike S1 — Expo SDK 58

- **Slug**: 031-s1-esqueleto-expo-58
- **Decided**: 2026-10-20
- **Verdict**: **go con el SDK 58**, sin bajar a 57.0.30. Pendiente de
  confirmar en dispositivo lo que solo se ve allí (lista abajo).
- **Artifacts reviewed**: [`intake.md`](./intake.md), `apps/mobile`,
  `./scripts/verify.sh mobile`.

## Lo comprobado

| Pregunta | Resultado | Evidencia |
|---|---|---|
| Instala y resuelve en el workspace anidado | Sí | `pnpm --dir apps/mobile install --frozen-lockfile`; el workspace raíz no cambia |
| Tipos | Sí, con `strict` y `noUncheckedIndexedAccess` | `tsc --noEmit` limpio; los nombres de SF Symbols y Material Symbols se comprueban al compilar |
| Empaquetado JS para las dos plataformas | Sí | `expo export --platform android --platform ios`: dos bundles Hermes de 4,7–4,8 MB |
| Build nativo de Android | **Sí**: `assembleDebug` (arm64) en 7 min, instalado y arrancado en el emulador | El primer intento enseñó que el SDK 58 exige `compileSdk 37`; el segundo se cortó por disco lleno; `expo-doctor` cazó que faltaba `expo-font`, par de `expo-symbols` |
| La ventana segura en Android | Se abre (Custom Tab) y cancelarla vuelve a la app con su mensaje | `evidence/capturas/` |
| Pruebas | jest-expo 58 + Jest 30 + RNTL 14 (render asíncrono) | 104 pruebas en verde. El doble oficial de reanimated 4 no carga en Jest: se usa uno mínimo propio (`test/reanimated.ts`) |
| Lint | ESLint 9 | La 10 rompe `eslint-plugin-react` (lo trae `eslint-config-expo`) |

## Pendiente en dispositivo (bloquea el piloto, no el código)

- [ ] Xcode 26.4+ en la máquina de build (o EAS) y un build de desarrollo en
      un iPhone.
- [ ] Liberar disco (≥ 10 GB) y terminar el build de Android en el emulador.
- [ ] La vuelta de la ventana segura por esquema propio con un código real (Android: la apertura y la cancelación ya están vistas).
- [ ] Aviso real de APNs `time-sensitive` (necesita el App ID con su capacidad
      y la clave `.p8`, T004) y de FCM a `waiting_v1` (necesita Firebase).
- [ ] `NativeTabs`: quitar un módulo en el admin y volver al primer plano.
- [ ] «Tomar el control» a 60 fps en un Android de gama media.
- [ ] `eas build` desde el workspace anidado, con la cuenta de FACELAD.

## Por qué no 57.0.30

Nada de lo comprobado lo pide. Bajar costaría React 19.2 vs 19.3 sin ganar
nada que hoy falle, y obligaría a rehacer las versiones fijadas en el lockfile.
