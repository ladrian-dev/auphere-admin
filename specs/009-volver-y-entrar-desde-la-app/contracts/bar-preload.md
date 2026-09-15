# Contrato — el `preload` de la barra pasa de seis funciones a ocho

**Enmienda** a [`specs/002-identidad-app-escritorio/contracts/desktop-bar.md`](../../002-identidad-app-escritorio/contracts/desktop-bar.md),
que es el documento que manda. Ese contrato se actualiza **en el mismo commit**
que el código; esto explica el porqué.

## Lo que se añade

```ts
window.auphere = {
  getState(): Promise<BarState>;
  onState(cb: (s: BarState) => void): () => void;
  pair(code: string): Promise<void>;
  unpair(): Promise<void>;
  pickDirectory(clientRef: string): Promise<void>;
  openInBrowser(url: string): Promise<void>;
  // ── spec 009 ──────────────────────────────────────────────────────────
  showApp(): Promise<void>;          // vuelve a la pantalla del equipo
  redeemCode(code: string): Promise<void>;  // canjea el código; el resultado llega por onState
};
```

Canales IPC: `bar:showApp` y `bar:redeem`.

## Por qué la lista crece, cuando ya se dijo que no una vez

`bar.ts:125` rechazó añadir `checkForUpdate` con este argumento: «habría ampliado
la única superficie de la aplicación que tiene `preload` —una lista cerrada de
seis funciones— y el botón no lo justifica».

**La diferencia es que allí había un segundo camino y aquí no.** El actualizador
iba a coger la versión nueva solo en cuatro horas; el botón era un atajo. La barra
no puede cambiar de superficie ni entregar un código sin un canal al principal, y
no hay nada esperando a hacerlo por ella.

## Las cinco propiedades que la lista conserva

1. **Sigue siendo cerrada y declarada.** Ocho, escritas aquí y en el contrato de
   la 002, con un test que falla si aparece una novena.
2. **La vista de la consola sigue sin `preload`.** Nada de esto le da un canal a
   la página cargada (spec 002, R3.5).
3. **Ninguna devuelve un secreto.** `redeemCode` entrega ocho caracteres y recibe
   un estado. El token no cruza el `preload` en ninguna dirección — quien habla
   con la plataforma es el principal, igual que con `pair`.
4. **`showApp` no acepta a dónde ir.** Sólo sabe volver. Una `showSurface(name)`
   parametrizada daría a la barra la capacidad de navegar, que es más de lo que
   hace falta.
5. **El texto del `preload` sigue sin `login`, `session`, `cookie` ni `token`**
   (`no-own-auth.test.ts:38`), y no por esquivar el test: la aplicación sigue sin
   tener autenticación propia. Lo que entrega es un código tecleado por una
   persona.

## Acciones de la barra

`BarAction` pasa de cuatro a cinco:

```ts
type BarAction =
  | "introducir_codigo" | "directorios" | "desemparejar" | "actualizar"
  | "volver_a_la_app";   // spec 009
```

**`volver_a_la_app` es ortogonal a los siete estados de conexión**, como `update`:
depende de qué superficie se ve, no de si la máquina está emparejada. Por eso
**no** entra en `actionsFor(state)`, que decide a partir de `status` — y en
particular **no** la filtra el `if (!state.encryptionAvailable) return []`: volver
no guarda nada, y encerrar a alguien en la consola por un llavero bloqueado sería
un castigo sin causa (R2.4).

`BarState` gana un campo:

```ts
/** Qué superficie se ve. Ausente = la pantalla del equipo (§V: la ausencia
 *  se diseña — sin consola delante no hay nada que ofrecer). */
surface?: "console";
```
