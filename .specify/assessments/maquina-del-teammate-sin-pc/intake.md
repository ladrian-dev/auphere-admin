# Idea Intake: una máquina para el teammate cuando el portátil está apagado

- **Slug**: maquina-del-teammate-sin-pc
- **Created**: 2026-09-20
- **Source**: sesión del 2026-09-20. Luis: «quizás añade una investigación para
  asignar una pequeña Virtual Machine (considerando la infra que tenemos hoy) y el
  agente pueda ejecutar acciones sin necesidad de que la pc esté encendida (cuando
  tengamos la app móvil) así podamos tener un ecosistema bien definido» · KB previa:
  [[teammates/02-ambiente-del-agente-vm]], [[teammates/14-mvp-y-fases]] §5 (beta 5),
  [[teammates/08-coste-y-precio]], [[teammates/09-seguridad-y-compliance]] §3
- **Type**: spike acotado → evaluación (la KB ya decidió que se hace; lo que falta es
  **con qué y cuánto** sobre la infraestructura de hoy)

## Qué se pide

Un sitio donde el trabajo del teammate siga cuando el portátil del partner está
cerrado. Hoy, cuando la máquina no está presente, lo correcto es que las herramientas
locales **desaparezcan del catálogo** en vez de fallar — y eso ya está diseñado. Pero
el resultado para el partner es que no se hace nada.

Con app móvil eso pasa de incómodo a incoherente: aprobar desde el iPhone una acción
que necesita un portátil encendido en otra habitación no es un ecosistema, es un
recordatorio.

## Lo que la KB ya decidió, y no se reabre

Del 2026-08-27 y del recorte del 2026-08-30:

- **Híbrido PC + VM**, con el PC primero. Confirmado y ordenado.
- **Una VM por partner, compartida por todos sus teammates.**
- Es la **superficie 2**, con precio de entrada propio: contrato `SandboxProvider`
  con dos implementaciones, `AgentHomeStore` en S3 con versionado, suspensión con
  checkpoint, reloj de máquina dentro del medidor, ADR de VM compartida y un test de
  aislamiento nuevo.
- **Regla dura: ninguna credencial de cliente final entra nunca en esa máquina.**
- La estimación que hay escrita es **~121 USD/mes/partner de máquina encendida**, y
  es la cifra que mató la idea de meterla en la beta.

## Qué ha cambiado desde entonces, y por eso se reabre

1. **La infraestructura ya no es la que se evaluó.** Producción es AWS, cuenta
   `793033583982`, región `eu-south-2`, con ECS y cinco servicios corriendo. La KB
   original pensaba la VM antes del corte. Hay que rehacer el número contra Fargate,
   y contra lo que ya se paga.
2. **El coste está bajo vigilancia.** Hubo un plan de costes en septiembre y se apagó
   Container Insights por ~106 USD/mes «y nada lo leía». Meter 121 USD/mes/partner
   sin discutirlo contradice esa decisión.
3. **La mitad local no está entregada.** El puente existe pero el teammate no lo
   alcanza (bug B4). Encender la nube antes de que funcione lo local sería construir
   la segunda mitad de un puente cuya primera mitad nadie ha cruzado.

## Lo que hay que investigar, no dar por hecho

- **Qué forma toma la máquina sobre lo que ya tenemos**: tarea Fargate por partner
  bajo demanda, un pool compartido con aislamiento por contenedor, Firecracker, o
  algo gestionado. Con precio real por hora **y** por partner inactivo, que es donde
  se va el dinero.
- **Cuánto tiempo está encendida de verdad.** La cifra de 121 USD supone reloj
  continuo. Si el trabajo desatendido son diez minutos por la noche, el modelo es
  otro y la respuesta puede ser «se enciende para la tarea y se apaga».
- **Qué se lleva el partner a esa máquina.** En su portátil el valor era que su
  ambiente ya está montado: sus repos, sus CLI, sus credenciales de git. En la nube
  eso hay que reconstruirlo — y la regla de no meter credenciales de cliente final
  limita cuánto. **¿Qué trabajo tiene sentido ahí que no lo tenga en el portátil?**
  Si la respuesta es «poco», la conclusión honesta de esta evaluación es *kill*.
- **Persistencia entre tareas**: `AgentHomeStore` en S3 con versionado, o disco
  efímero y todo desde cero cada vez.
- **Residencia de datos.** La KB la dejó libre para el MVP. Con clientes europeos y
  datos de salud de por medio, `eu-south-2` deja de ser una casualidad afortunada y
  pasa a ser un requisito que conviene escribir.
- **Cómo lo ve el partner.** Hoy hay «tu máquina». Con dos, la interfaz tiene que
  decir **dónde** corre cada cosa y por qué, sin inventar vocabulario nuevo.

## La relación con el móvil

Luis lo ata a la app móvil, y el orden importa: el móvil (superficie 0, barato) gana
valor **después** de que el teammate ejecute, porque entonces hay mucho que aprobar.
La máquina en la nube es la superficie 2, la más cara de todas. **El móvil no
necesita la VM para existir**, y conviene no atarlos: si se atan, el proyecto barato
hereda el calendario del caro — que es exactamente el error que la KB ya cometió una
vez y corrigió por escrito.

## Superficie de confianza

`2`, entera y sin descuento. Abre además la combinación que la KB marcó como
peligrosa: navegador y ejecución encendidos a la vez sin las guardas es *«la
superficie completa de inyección de prompt apuntando a una máquina real»*.

## Fuera de alcance

La app móvil en sí (superficie 0, evaluación aparte) y controlar el escritorio (`3b`).
