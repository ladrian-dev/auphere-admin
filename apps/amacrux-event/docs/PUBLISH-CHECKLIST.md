# Lista de comprobación de publicación

## Código
- [ ] `pnpm check` y `pnpm build` en verde en `apps/amacrux-event`.
- [ ] `git status` limpio en la rama `DEMO-AMACRUX-EVENT`; PR abierto si procede.

## Vercel (un proyecto por entorno)
- [ ] Nuevo proyecto → importar `ladrian-dev/auphere-admin`.
- [ ] **Root Directory: `apps/amacrux-event`** (crítico; si no, Vercel construye la raíz y falla).
- [ ] Framework Next.js autodetectado; install/build los declara `vercel.json`.
- [ ] Rama de producción: `DEMO-AMACRUX-EVENT` (o `main` tras fusionar).
- [ ] Variables (Production): `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_DEMO_MODE=false`, `NEXT_PUBLIC_ANALYTICS`, `NEXT_PUBLIC_PLAUSIBLE_DOMAIN` (si aplica), `RESEND_API_KEY`, `LEADS_TO=contacto+event@auphere.com`, `LEADS_FROM`. Supabase y el webhook se quedan vacíos.
- [ ] Probar `https://<dominio>/api/health` → `mode: "live"`, `email: true` (`storage: false` y `sheet: false` son lo esperado hoy).
- [ ] Si `/api/health` dice `misconfigured`, falta una variable: en producción ya no cae en demo en silencio.
- [ ] Dominio y certificado. Probar `https://<dominio>/api/health` → `mode: "live"`.

## Supabase (apagado hoy)
No se configura: la decisión vigente es correo como único destino. El código y la
migración se quedan en el repo por si se enciende más adelante.

## Resend
- [ ] Dominio del remitente verificado (SPF/DKIM) o, para pruebas, `onboarding@resend.dev`.
- [ ] `LEADS_FROM` sin tildes ni caracteres no ASCII en el nombre visible: Resend rechaza el envío. Si `/api/health` dice `misconfigured` con todas las variables puestas, es esto.
- [ ] Clave de API con permiso de envío, creada solo para este proyecto.
- [ ] Enviar un lead de prueba y confirmar recepción en `contacto+event@auphere.com`.
- [ ] En ese correo: comprobar que están las cinco secciones y que la fila CSV del final se pega bien en la hoja (40 columnas, sin descuadres).
- [ ] Responder al correo y comprobar que el `replyTo` lleva a la persona, no al remitente.

## Marca y textos
- [ ] Revisar con Amacrux los `TODO_COMERCIAL` (`docs/TODO-COMERCIAL.md`).
- [ ] Política de privacidad validada (responsable y contacto).

## QR
- [ ] Generar el QR con la URL de campaña (`docs/EVENT-GUIDE.md`) y probarlo con dos celulares distintos.
- [ ] Imprimirlo con margen y tamaño suficiente para la pantalla del evento.

## Después del evento
- [ ] Exportar los leads del buzón (la fila CSV de cada correo) y borrar los de prueba.
- [ ] Revisar el embudo (analítica) y anotar aprendizajes en la KB.
