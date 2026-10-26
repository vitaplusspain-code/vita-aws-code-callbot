# Contrato de la API de avisos

Para quien programe el envío de avisos desde la web de VitaPlus. Un aviso hace que el callbot llame por teléfono al familiar de la persona y le lea un mensaje con el caso.

Fase 1: solo existe la persona `demo-01` y solo se llama a una lista cerrada de teléfonos de prueba.

## Petición

```http
POST https://<api-id>.execute-api.eu-central-1.amazonaws.com/<stage>/avisos
Content-Type: application/json
x-api-key: <clave>

{"persona_id": "demo-01", "caso": "medicacion_7_dias"}
```

- **URL:** `<api-id>` y `<stage>` los da el despliegue (salida de la plantilla SAM del repo de infraestructura).
- **`x-api-key`:** obligatoria. La clave se entrega aparte, nunca por el repositorio. No la pongas en código que se ejecute en el navegador: la llamada debe salir del servidor de la web.
- **Límites de uso:** 1 petición por segundo y 20 al día por clave.

### Cuerpo

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

### Éxito: 200

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

## Reintentos: cuidado con las llamadas duplicadas

En la fase 1 **cada petición aceptada es una llamada**: no hay protección contra duplicados. Si una petición da `error_connect`, `error_interno`, 502 o 504, puede que la llamada se haya hecho igualmente. Antes de reintentar, compruébalo con el familiar o con el equipo del callbot; un reintento automático puede hacer sonar el teléfono dos veces.

## Probar en local

`events/aviso-demo.json` es un evento de ejemplo de API Gateway para `sam local invoke` (los pasos están en la guía de despliegue del repo de infraestructura). La clave que lleva es ficticia.
