# Lista de comprobación de publicación

## Código
- [ ] `pnpm check` y `pnpm build` en verde en `apps/amacrux-event`.
- [ ] `git status` limpio en la rama `DEMO-AMACRUX-EVENT`; PR abierto si procede.

## Vercel (un proyecto por entorno)
- [ ] Nuevo proyecto → importar `ladrian-dev/auphere-admin`.
- [ ] **Root Directory: `apps/amacrux-event`** (crítico; si no, Vercel construye la raíz y falla).
- [ ] Framework Next.js autodetectado; install/build los declara `vercel.json`.
- [ ] Rama de producción: `DEMO-AMACRUX-EVENT` (o `main` tras fusionar).
- [ ] Variables (Production): `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_DEMO_MODE=false`, `NEXT_PUBLIC_ANALYTICS`, `NEXT_PUBLIC_PLAUSIBLE_DOMAIN` (si aplica), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `LEADS_TO` (Amacrux y Auphere, separados por comas), `LEADS_FROM`.
- [ ] Probar `https://<dominio>/api/health` → `mode: "live"`, `storage: true`, `email: true`.
- [ ] Dominio y certificado. Probar `https://<dominio>/api/health` → `mode: "live"`.

## Supabase
- [ ] Proyecto creado y `supabase/migrations/0001_leads.sql` ejecutado en el SQL Editor.
- [ ] Enviar un lead de prueba y verlo en Table Editor → `leads_panel`; reenviar el mismo y comprobar que no se duplica.
- [ ] Borrar los leads de prueba (`delete from public.leads where lower(email) = lower('…')`).

## Resend
- [ ] Dominio del remitente verificado (SPF/DKIM) o, para pruebas, `onboarding@resend.dev`.
- [ ] Clave de API con permiso de envío, creada solo para este proyecto.
- [ ] Enviar un lead de prueba y confirmar recepción en `LEADS_TO`.

## Marca y textos
- [ ] Revisar con Amacrux los `TODO_COMERCIAL` (`docs/TODO-COMERCIAL.md`).
- [ ] Política de privacidad validada (responsable y contacto).

## QR
- [ ] Generar el QR con la URL de campaña (`docs/EVENT-GUIDE.md`) y probarlo con dos celulares distintos.
- [ ] Imprimirlo con margen y tamaño suficiente para la pantalla del evento.

## Después del evento
- [ ] Exportar los leads del buzón y borrar los de prueba.
- [ ] Revisar el embudo (analítica) y anotar aprendizajes en la KB.
