# Contrato: el canal de versiones

**Este contrato describe una superficie de confianza nueva.** Lo que está aquí no
es una convención de nombres: es lo que impide que alguien ponga un binario
delante de los partners.

## Las cuatro reglas del canal

1. **Solo lectura para todo el mundo.** Se sirve por HTTPS y **sin credenciales**:
   ningún secreto viaja dentro del binario del cliente (R2.3).
2. **Escribe una sola identidad**, la de la cadena, y sólo sobre el prefijo del
   canal. No es la misma identidad que despliega la plataforma: un rol que puede
   publicar versiones no puede tocar los servicios, y al revés.
3. **Publicar es añadir.** El índice pasa a apuntar a la versión nueva; los
   paquetes anteriores **se quedan**. Es la única marcha atrás que existe cuando
   el puente es saliente y no se puede empujar nada.
4. **Todo lo publicado pasó por la cadena.** Un artefacto que no salga de ahí no
   entra, ni en una emergencia: para eso está el disparo manual de la cadena.

## Lo que el cliente comprueba, y en qué orden

El orden **es** la política, y está escrito en `update-policy.ts`:

```
¿este binario lleva nuestra firma de distribución?
    no  → no se pregunta nada al canal.  FIN.
    sí  → ¿hay versión nueva?
              sí → descargar (sin preguntar, sin interrumpir)
                   → ¿hay trabajo vivo?
                         sí → ESPERAR, y decirlo
                         no → instalar al salir
```

**La primera rama falla cerrada**: un binario sin firma de distribución sigue
diciendo que no aunque ya haya un paquete descargado en el disco. Y la
comprobación de la firma del paquete la hace el sistema operativo, no nosotros:
lo que el cliente hace es **no llegar a pedir** lo que de antemano no puede salir
bien.

## La puerta de versión mínima

Vive en el latido (D6), que es lo único que corre solo y cada poco.

| Situación | Respuesta |
|---|---|
| Sin mínimo declarado | El latido sigue como hoy. **Es el estado del primer despliegue** |
| Versión ≥ mínimo | El latido sigue como hoy |
| Versión < mínimo | Negativa con **código y motivo legibles**, en el mismo idioma que `device_archived` y `pairing_required` |

**Avisar y bloquear son dos cosas distintas** (R4.6): una versión vieja pero
admisible recibe un aviso y **sigue funcionando**. Sólo la que cae por debajo del
mínimo se rechaza, y el mínimo se reserva a que el contrato del puente se haya
roto o a un problema de seguridad (R4.7).

**Y nunca sin avisar antes** (R4.5). El patrón de la industria es preaviso
largo y calendario conocido —Slack seis meses, Zoom noventa días— y la razón es
la misma aquí: una máquina que se queda fuera sin aviso es un partner que llama
sin saber qué le ha pasado.

## Los dos estados nuevos de la barra

| Estado | Cuándo | Qué dice |
|---|---|---|
| Actualización lista | Hay versión descargada y nada vivo | Se instalará al cerrar |
| Actualización esperando | Hay versión descargada y hay sesión viva o aprobación pendiente | Espera, **y por qué** |

Cuando no hay ninguna versión esperando, **la barra no dice nada**: ni indicador
apagado ni texto explicando lo que no hay. La ausencia se diseña (§V).
