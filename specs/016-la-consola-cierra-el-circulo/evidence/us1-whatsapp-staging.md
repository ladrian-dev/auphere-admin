# US1 · WhatsApp desde la consola — pendiente de staging

**Local (2026-09-23)**: sin `NEXUS_META_APP_ID` ni `NEXUS_META_CONFIG_ID_*`,
Canales muestra la nota «El número lo conecta Auphere» sin botón (ausencia
diseñada, R1.3). Cubierto por `whatsapp-connect.test.tsx` y por el test de
`shell-detect` (la ruta «continuar en el navegador» apunta a esta misma página).

**Staging (pendiente)**: requiere las claves de Meta en Vercel y un número de
prueba. Recorrido a documentar aquí con capturas:

1. Canales → «Conectar WhatsApp» → ventana de Meta → volver.
2. Tarjeta del número activa; toast «Número … conectado. El cliente ya está
   activo y atendiendo» si el partner auto-activa y hay agente publicado.
3. Ficha «Listo para atender»; onboarding «Conecta un canal» hecho;
   `tenants.status = active`.
4. Un segundo cliente con el mismo número → «Ese número ya está conectado en
   otro cliente. Nada ha cambiado.»
