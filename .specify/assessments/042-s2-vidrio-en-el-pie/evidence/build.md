# Los builds del spike (T012)

Perfil `development-simulator` de `apps/mobile/eas.json`, compilado en EAS
con la cuenta de Luis (`lmatos`), proyecto `@lmatos/auphere-customers`.

| # | Id | Qué lleva | Resultado |
|---|---|---|---|
| 1 | `282cdcee-efc1-4c74-9e23-9208f346246e` | El código de `develop` + iteración 1, **sin** `expo-glass-effect` | FINISHED. Sirvió para T037 (capturas de Inicio) y dejó a la vista H14 |
| 2 | `0ba4ec04-5dd9-49fe-a9fd-a5d484df50d6` | Lo mismo + `expo-glass-effect` ~58.0.4 | FINISHED. Es el build del spike y de la iteración 2 |

- Logs: `https://expo.dev/accounts/lmatos/projects/auphere-customers/builds/<id>`.
- Imagen: la del alias `sdk-58`, `macos-tahoe-26.6-xcode-27.1`. El `Info.plist`
  del `.app` lo confirma: `DTXcode 2710`, `DTSDKName iphonesimulator27.1`.
- Se instala con `xcrun simctl install "SE 26" CustomersDev.app` (iPhone SE
  3.ª gen., iOS 26.0.1). El JS llega de Metro (`pnpm start`), así que las
  pantallas del spike no necesitan recompilar.
- **Disco.** Arrancar un segundo simulador («17 26») dejó el disco a cero: un
  simulador arrancado ocupa ~2,5 GB de datos, y el «iPhone 17» de serie que
  Maestro arrancó por error en la primera prueba, 4,5 GB. El spike se hace en
  «SE 26» solo; el iPhone 17 queda para las capturas de US4 cuando haya disco.
