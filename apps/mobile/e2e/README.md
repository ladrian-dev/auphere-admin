# Flujos de Maestro — spec 031

Contra la pila local con la semilla de la spec 030 (quickstart §3) y un build
de desarrollo instalado en el simulador o el emulador.

```bash
maestro test e2e/sign-in.yaml -e EMAIL=valeria@flor.test -e PASSWORD=…   # la persona de prueba (e2e/.env.e2e)
maestro test e2e/dynamic-tabs.yaml
maestro test e2e/send-flaky.yaml -e CONVERSATION_ID=<uuid de una conversación que atiende la persona>
```

La contraseña es la de la cuenta de prueba de la semilla; nunca una real.
`sign-in.yaml` ya no abre ningún navegador: la entrada es de la app (R1
enmendado). Google no se automatiza: su ventana es de Google.
`APP_ID` es `com.auphere.customers.dev` en un build de desarrollo.
