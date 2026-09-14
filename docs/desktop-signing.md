# La identidad de firma: rotación, revocación y quién manda

**Spec viva.** Describe lo que existe hoy para firmar la aplicación de
escritorio. Si cambias lo que describe, este documento va **en el mismo
commit**. Origen: `specs/008-empaquetado-firma-y-canal/` (R5.4, R5.5).

## Lo que hay

| Campo | Valor |
|---|---|
| Identidad | `Developer ID Application: FACELAD SpA (CBSWMG766P)` |
| Intermediario | **G2** (el defecto del portal era «Previous Sub-CA», que caduca el 2027-02-01) |
| Válido hasta | 2031-09-14 |
| Notarización | App Store Connect API key `NNFTSY329V`, acceso **Developer** |
| Dónde firma | Integración continua, `release-desktop.yml`, llavero temporal por ejecución |

## Quién puede revocar, y qué pasa si lo hace

**Puede revocar Facelad, no Auphere.** El Account Holder es Daniel Marquez; el
rol de Luis es App Manager en el portal y Admin en App Store Connect.

Y la distinción que importa, de la documentación de Apple:

- **Caducar no rompe nada** de lo ya firmado y distribuido.
- **Revocar sí**: una aplicación firmada con un certificado revocado **no se
  puede instalar, y no arranca aunque ya esté instalada**.

Ése es el argumento más fuerte a favor de un enrolamiento propio, y la razón de
que este documento exista en vez de ser un comentario en un YAML.

## Migrar al equipo de Auphere: qué cuesta

Cambiar de Team ID altera el *designated requirement*, así que **macOS trata la
aplicación como otra distinta**. En cascada:

- **Nadie se actualiza solo.** Squirrel rechaza la actualización; todos
  reinstalan a mano.
- **El llavero deja de ser legible** y la credencial de máquina se pierde:
  **cada partner vuelve a emparejar**.
- Se resetean el permiso de notificaciones y los grants de TCC.
- `userData` sobrevive, porque va por `productName`.

**Consecuencia operativa: migrar mientras el cohorte quepa en una llamada de
teléfono.** El coste escala con el número de instalaciones y hoy es casi cero.

## Rotar la identidad

1. Generar el CSR **en la máquina de destino** (la clave privada nunca se
   transfiere; un `.p12` sólo se mueve para respaldarlo, no para repartirlo).
2. Subirlo con la sesión del **Account Holder** — un Developer ID Application no
   lo crea ni un Admin. Con rol App Manager, «Certificates, Identifiers &
   Profiles» devuelve *Access Unavailable*.
3. **Elegir «G2 Sub-CA (Xcode 11.4.1 or later)» a mano.** El portal viene
   marcado por defecto en «Previous Sub-CA», y esos certificados caducan todos
   el 2027-02-01 sin importar cuándo se emitan. Es un clic y cuesta cuatro años.
4. Importar el `.cer`, exportar el `.p12`, y reemplazar `APPLE_CERT_P12_BASE64`
   y `APPLE_CERT_PASSWORD` en los secretos del repositorio.
5. Publicar una versión de prueba y **abrirla en un Mac limpio** antes de dar la
   rotación por buena.

Apple permite **cinco** Developer ID Application por cuenta, así que rotar no es
una operación de una sola bala.

## Si se pierde la máquina donde vive la clave

Mientras exista la copia sellada del `.p12` —fuera de GitHub, que es de sólo
escritura— no pasa nada: se importa en otra máquina o se usa desde la cadena,
que es donde de verdad se firma.

**Sin esa copia**, hay que pedirle a Facelad que emita otro certificado. No es
una llamada urgente porque las versiones ya publicadas siguen funcionando: lo
que se pierde es la capacidad de publicar **nuevas**.

## Qué no puede pasar nunca

- Material de firma en un commit. Lo impide el `.gitignore` y lo vigila
  `apps/desktop/tests/signing-material-never-committed.test.ts`, que pregunta a
  `git check-ignore` y no al fichero — hay reglas que se anulan entre sí, y de
  hecho aquí conviven una negación y estas exclusiones.
- Firmar fuera de la cadena. El disparo manual del workflow existe justo para
  que en un incidente nadie tenga la tentación.
