# Validación de la 008

Cómo se comprueba que esto funciona. **Lo único que de verdad lo demuestra es un
Mac que nunca ha visto el proyecto**, y por eso el paso 3 no se puede sustituir
por ningún test.

## 0 · Antes de nada: la identidad de firma

```bash
security find-identity -v -p codesigning | grep "Developer ID Application"
ls -l ~/.appstoreconnect/private_keys/
```

Esperado: la identidad de FACELAD SpA y la clave `.p8`. **Si falta el `.p12`
exportado, la cadena no se puede construir** (research D2) — y eso no lo arregla
escribir código.

## 1 · Las pruebas del cliente rescatado

```bash
cd apps/desktop && pnpm test
```

Esperado: verde, incluidas las de la política de actualización que trae
`e100564`. **Van antes de construir nada**: firmar una aplicación cuyas pruebas
nadie corre es firmar a ciegas (R6.2).

## 2 · Construir y firmar en local, una vez

```bash
cd apps/desktop && pnpm build && pnpm dist
```

Y comprobar el resultado, que es lo que nadie hace y donde está el error clásico:

```bash
codesign --verify --deep --strict --verbose=2 "dist/mac-arm64/Auphere.app"
spctl --assess --type execute --verbose "dist/mac-arm64/Auphere.app"
xcrun stapler validate "dist/Auphere-<versión>-arm64.dmg"
```

Esperado: cadena hasta la raíz de Apple, `flags=0x10000(runtime)`, `accepted`, y
el sello grapado. **`hardenedRuntime` sin los permisos correctos no falla al
construir: falla al abrir**, así que esto no vale como prueba de que arranca.

## 3 · El Mac limpio — y esto no se puede automatizar

Copiar el `.dmg` a una máquina que nunca ha visto el proyecto, abrirlo,
arrastrar, abrir la aplicación.

Esperado: **arranca al primer intento, sin aviso de desarrollador no
identificado y sin tocar la terminal** (CE-001). Si aparece cualquier diálogo del
sistema, la cadena no está lista, por muy verde que esté todo lo demás.

## 4 · El canal

```bash
curl -I https://updates.auphere.com/desktop/latest-mac.yml
curl -s https://updates.auphere.com/desktop/latest-mac.yml | head
```

Esperado: `200` sobre HTTPS y **sin cabecera de autenticación** — R2.3, ningún
secreto en el cliente.

Y lo que importa de verdad, que es lo que **no** se puede hacer:

```bash
aws s3 cp cualquier-cosa.zip s3://<bucket>/desktop/   # DEBE fallar
```

Con las credenciales de una persona, esto tiene que dar `AccessDenied`. Si sube,
R2.2 no se cumple y da igual todo lo demás.

## 5 · La actualización, de punta a punta

1. Instalar la versión N en el Mac limpio.
2. Publicar N+1 por la cadena.
3. Dejar la aplicación abierta con **una tarea esperando confirmación**.

Esperado: descarga sola, la barra dice **que espera y por qué**, y **no** se
instala. Al resolver la confirmación y cerrar, se aplica.

## 6 · Lo que tiene que fallar

```bash
# Un paquete manipulado
cp Auphere-N+1.zip roto.zip && printf 'x' >> roto.zip
```

Esperado: el actualizador lo rechaza por la firma (R3.5).

Y con un binario sin firma de distribución (un `--dir` local), el actualizador
**no le pide nada al canal**, ni siquiera con un paquete ya descargado (R3.4).
Comprobar en los registros que no hay ninguna petición saliente.

## 7 · La versión mínima

Con un mínimo declarado por encima de la versión instalada, el latido responde
con **código y motivo legibles**, y la barra lo nombra. Sin mínimo declarado —el
estado del primer despliegue— el latido no rechaza nada.

## 8 · Lo que corre la tubería, entero

```bash
./scripts/verify.sh
```

No la mitad, y **leyendo la cola en crudo**. Ha roto la tubería dos veces por
mirar sólo una parte.

## 9 · La infraestructura

```bash
cd infra/terraform/40-releases && terraform plan
```

**Leer el plan entero antes de aplicar.** Si aparece algo que nadie pidió, parar
y preguntar. Y comprobar que `NEXUS_DEVICE_TOKEN_SECRET` existe en el almacén de
secretos **antes** de aplicar nada de `20-services`: está declarada desde hace
tiempo y el día que alguien aplique infraestructura, ECS aborta el arranque si
falta.
