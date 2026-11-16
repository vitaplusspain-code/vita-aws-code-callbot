# Contrato de la API de avisos

Para quien programe el envío de avisos desde la web de VitaPlus. Un aviso hace que el callbot llame por teléfono al familiar de la persona y le lea un mensaje con el caso.

Hay dos formas de cuerpo. La de producción (la que debe usar el backend de VitaPlus) solo lleva el identificador de la alerta; la de demo (`persona_id` y `caso`) es temporal y desaparecerá tras la prueba de punta a punta. Solo se llama a una lista cerrada de teléfonos de prueba.

## Petición

```http
POST https://<api-id>.execute-api.eu-central-1.amazonaws.com/<stage>/avisos
Content-Type: application/json
x-api-key: <clave>

{"alert_id": "0b6f1c1e-4a52-4d0e-9d6a-1f2b3c4d5e6f"}
```

- **URL:** `<api-id>` y `<stage>` los da el despliegue (salida de la plantilla SAM del repo de infraestructura).
- **`x-api-key`:** obligatoria. La clave se entrega aparte, nunca por el repositorio. No la pongas en código que se ejecute en el navegador: la llamada debe salir del servidor de la web.
- **Límites de uso:** 1 petición por segundo y 20 al día por clave.

### Cuerpo de producción: `alert_id`

JSON con exactamente un campo, `alert_id`: el UUID de la alerta (formato 8-4-4-4-12; se acepta en mayúsculas). Cualquier otro campo se rechaza, y también mezclarlo con los de la demo. Tamaño máximo: 1024 bytes.

El callbot lee la alerta y decide solo si llama: la alerta debe estar abierta, ser reciente (por defecto, hasta 900 segundos de antigüedad; configurable), ser crítica o de una regla que siempre avisa, y la persona debe haber dado su consentimiento. Una misma alerta no llama dos veces al mismo familiar.

**Para no revelar nada, la respuesta es siempre la misma**: no se indica si la alerta existe, está cerrada, es antigua, no tiene consentimiento, ya se avisó o la llamada falló. Eso queda solo en los registros internos.

### Cuerpo de demo (temporal)

La demo solo funciona si el despliegue tiene `DEMO_ACTIVA=true`. Es temporal y está apagada por defecto: con la demo apagada, este cuerpo devuelve `400 aviso_invalido`, igual que cualquier aviso mal formado. La forma con `alert_id` no depende de este interruptor.

JSON con exactamente estos dos campos (cualquier otro campo se rechaza). Tamaño máximo: 1024 bytes.

| Campo | Tipo | Valores |
|---|---|---|
| `persona_id` | texto | De 1 a 40 caracteres: minúsculas, dígitos y guiones. En la fase 1, solo `demo-01`. |
| `caso` | texto | Uno de los casos de la tabla siguiente. |

| Caso | Qué le cuenta al familiar |
|---|---|
| `medicacion_7_dias` | El dispensador indica que la persona lleva siete días sin registrar la toma de su medicación. |
| `sin_actividad_hoy` | Hoy no se ha detectado actividad en casa de la persona. |
| `sueno_irregular` | Se ha observado un patrón de sueño irregular en la persona durante las últimas noches. |

Todos los mensajes se presentan como un asistente automático de VitaPlus, no dan consejos médicos, sugieren contactar con la persona y recuerdan llamar al 112 ante una urgencia. El familiar puede pulsar 1 para repetir el mensaje.

## Respuestas

Todas las respuestas son JSON (`Content-Type: application/json`).

### Aviso por `alert_id`: 202

```json
{"estado": "recibido"}
```

Significa solo que el aviso se ha recibido y procesado, no que se haya llamado. Es idéntico para cualquier desenlace.

### Demo: 200

```json
{"contact_id": "<identificador de la llamada en Amazon Connect>"}
```

Significa que Connect ha aceptado la llamada, no que el familiar haya contestado. Guarda el `contact_id`: sirve para localizar la llamada si hay que investigar algo.

### Errores del callbot

```json
{"error": {"codigo": "aviso_invalido", "mensaje": "El aviso no es válido."}}
```

El `mensaje` es siempre un texto fijo por código; nunca repite datos de la petición. Programa la web contra el `codigo`, no contra el texto.

| HTTP | `codigo` | `mensaje` | Cuándo | ¿Reintentar? |
|---|---|---|---|---|
| 400 | `aviso_invalido` | El aviso no es válido. | Cuerpo ausente, no es JSON, supera 1024 bytes, faltan o sobran campos, o un valor no es válido. | No: corrige la petición. |
| 400 | `persona_no_encontrada` | La persona indicada no existe. | El `persona_id` no corresponde a ninguna persona. | No. |
| 403 | `telefono_no_permitido` | No se permite llamar a ese teléfono. | El teléfono del familiar no está en la lista de teléfonos permitidos. | No. |
| 503 | `llamadas_desactivadas` | El servicio de llamadas no está activo. | Las llamadas están desactivadas a propósito. | Más tarde, cuando se reactive. |
| 500 | `error_base_datos` | No se pudo registrar el aviso. | Falló la base de datos antes de llamar (solo con `alert_id`). No se ha llamado. | **Sí**: es seguro reintentar. |
| 500 | `error_connect` | No se pudo iniciar la llamada. | Amazon Connect ha fallado o no ha respondido a tiempo. | **No automáticamente** (ver abajo). |
| 500 | `error_configuracion` | El servicio no está bien configurado. | Falta configuración en el despliegue. | No: avisa al equipo del callbot. |
| 500 | `error_interno` | Error interno. | Cualquier fallo inesperado. | No automáticamente. |

### Errores de API Gateway

Estos los devuelve API Gateway antes de llegar al callbot, con otro formato (`{"message": "..."}`):

| HTTP | Cuándo |
|---|---|
| 403 | Falta la cabecera `x-api-key` o la clave no es válida. |
| 429 | Se ha superado el límite por segundo o el cupo diario. |
| 502 / 504 | El callbot no ha respondido bien o a tiempo. |

## Reintentos

### Con `alert_id`

Reintentar es seguro. La llamada se reserva de forma atómica (reserva atómica en la base de datos antes de llamar), así que una misma alerta no llama dos veces al mismo familiar aunque la petición se repita. Puedes reintentar ante 429, 500, 502 y 504. El código `error_connect` no sale con `alert_id`: si falla el canal, la respuesta es el 202 de siempre y el fallo queda solo en los registros internos.

### Con la demo

En la demo **cada petición aceptada es una llamada**: no hay protección contra duplicados. Si una petición da `error_connect`, `error_interno`, 502 o 504, puede que la llamada se haya hecho igualmente. Antes de reintentar, compruébalo con el familiar o con el equipo del callbot; un reintento automático puede hacer sonar el teléfono dos veces (llamadas duplicadas).

## Probar en local

`events/aviso-alerta.json` (forma de producción, con un UUID inventado) y `events/aviso-demo.json` son eventos de ejemplo de API Gateway para `sam local invoke` (los pasos están en la guía de despliegue del repo de infraestructura). La clave que lleva es ficticia.
