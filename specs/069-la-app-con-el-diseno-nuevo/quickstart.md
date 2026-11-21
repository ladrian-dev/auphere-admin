# Cómo probar la 069 (Luis, mañana)

Todo está en el worktree `.claude/worktrees/069-app-movil`, rama `069-la-app-con-el-diseno-nuevo`. **No hay commits**: el guion `commits.sh` y los parches de respaldo `snap-*` están en `.claude/commits/069/` del checkout principal, fuera del worktree a propósito.

## 1. Android, en el emulador (lo más rápido: ya está instalado)

El build de desarrollo 1.3.0 está instalado en el AVD `Pixel_9`.

1. Si el emulador no está abierto, lánzalo:

   ```bash
   ~/Library/Android/sdk/emulator/emulator -avd Pixel_9
   ```

2. Arranca Metro con el negocio de ejemplo (Clínica Brisa, sin servidor):

   ```bash
   cd .claude/worktrees/069-app-movil/apps/mobile && EXPO_PUBLIC_DEMO=1 APP_VARIANT=development pnpm start
   ```

   En la terminal de Metro, pulsa `a` (o abre «Customers Dev» en el emulador).

   Si Expo dice que el puerto 8081 está ocupado, es un Metro que quedó abierto: ciérralo, o acepta otro puerto y elige ese servidor en el cliente de desarrollo.

3. Entra con cualquier correo y cualquier contraseña. Hay tres casos especiales:
   - la contraseña `error` da el error de credenciales;
   - un correo que empiece por `partner@` lleva a la pantalla de cuenta de partner;
   - a los 3 s de entrar, llega una conversación nueva de Instagram (Nuria Campos), con su animación;
   - Reservas va con la hora real de Santiago de Chile: por la mañana en España allí es de madrugada, así que todas las reservas de hoy salen por venir.

   La app del emulador está en español (idioma por app). Para verla en inglés: Ajustes del sistema → Aplicaciones → Customers Dev → Idioma.

## 2. Android contra staging, con tu cuenta

```bash
cd .claude/worktrees/069-app-movil/apps/mobile && EXPO_PUBLIC_API_URL=https://api.staging.auphere.com EXPO_PUBLIC_CONSOLE_URL=https://console.staging.auphere.com APP_VARIANT=development pnpm start
```

## 3. iOS, en el simulador

El build de desarrollo ya está instalado en el iPhone 13 (iOS 26.0). Para rehacerlo, lo que también abre el simulador:

```bash
cd .claude/worktrees/069-app-movil/apps/mobile && APP_VARIANT=development npx expo run:ios
```

Con Metro en modo ejemplo (paso 1.2), abre la app desde el simulador; si no conecta sola, este enlace la lleva a Metro:

```bash
xcrun simctl openurl booted "exp+auphere-customers://expo-development-client/?url=http%3A%2F%2F127.0.0.1%3A8081"
```

- **Abre el enlace solo con la app cerrada.** Abrirlo con la app ya arrancando la recarga a mitad de arranque, y en este simulador eso la tira casi siempre (ver `log.md`, «La caída de las categorías de avisos»).
- La app está en español por idioma de app. Para verla en inglés: Ajustes → Apps → Customers Dev → Idioma.
- **Si deslizar una fila desde la derecha no responde**, es el botón flotante «Tools» del cliente de desarrollo, que tapa el borde: escóndelo desde el menú de desarrollo (⌃⌘Z en el simulador).

## 4. Helvena (cuando confirmes la licencia)

1. Copia los tres archivos al proyecto:

   ```bash
   mkdir -p .claude/worktrees/069-app-movil/apps/mobile/assets/fonts/helvena && cp ~/Downloads/"Helvena Font File"/TTF/Helvena-{Regular,Medium,Semibold}.ttf .claude/worktrees/069-app-movil/apps/mobile/assets/fonts/helvena/
   ```

2. Haz un build nuevo con el interruptor encendido (Android; en iOS, lo mismo con `run:ios`):

   ```bash
   cd .claude/worktrees/069-app-movil/apps/mobile && APP_HELVENA=1 APP_VARIANT=development npx expo run:android
   ```

Sin el interruptor, los títulos salen con la fuente del sistema y el mismo tamaño.

## 5. Lo que hay que mirar

- Inicio, Bandeja (deslizar, buscar, filtros por canal), una conversación (tomar el control y devolver), Contacto, Corregir, Reservas (día, semana, mes, cuadrícula, nueva, mover y cancelar), lista de espera, Consumo, Ajustes y Entrar (el líquido).
- Modo oscuro, con el ajuste del sistema del emulador.
- Texto grande y «Quitar animaciones».
- TalkBack: deslizar una fila tiene sus acciones, y «Deshacer» dura 20 s con el lector activo.
- La revisión de calidad y qué se hizo con cada hallazgo: `revision.md` y la tabla de `log.md`.

## 6. Lo que no se hizo esta noche

Ver `log.md`, sección «No verificado».
