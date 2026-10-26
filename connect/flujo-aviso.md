# Flujo de Connect: aviso al familiar

Flujo que ejecuta Amazon Connect cuando la Lambda pide una llamada con `StartOutboundVoiceContact`. Lee al familiar el mensaje del caso, permite repetirlo pulsando 1 y cuelga.

La Lambda manda el mensaje ya preparado, en SSML, en el atributo de contacto `mensaje`. El flujo no contiene textos de casos ni datos de personas: solo lo lee como `$.Attributes.mensaje`.

Hay dos formas de crearlo. Las dos dan el mismo resultado. Los nombres de menús y opciones de la consola pueden variar un poco según la versión de Connect.

## Opción A: importar `flujo-aviso.json`

1. En la consola de Connect de la instancia `vita-dev-callbot` (eu-central-1), crea un flujo nuevo de tipo *Inbound flow* (en la API, `CONTACT_FLOW`).
2. Usa la opción de importar flujo del editor y elige `connect/flujo-aviso.json`.
3. Nómbralo `vita-dev-callbot-flujo-aviso`, guárdalo y publícalo.
4. Copia el identificador del flujo (la parte final de su ARN, visible en la información adicional del flujo). Es el parámetro `ConnectContactFlowId` de la plantilla SAM.

El JSON sigue el *Flow language* de Connect (versión `2019-10-30`) y lo comprueba `tests/test_flujo_connect.py`. Si la importación fallara, usa la opción B.

## Opción B: crearlo a mano

Crea un *Inbound flow* vacío con el nombre `vita-dev-callbot-flujo-aviso` y añade estos cuatro bloques:

| # | Bloque | Configuración | Salidas |
|---|---|---|---|
| 1 | **Set voice** | Idioma: español (España). Voz: **Lucia**. Activa la sustitución del estilo de habla y elige el motor **Neural**, sin estilo. | Success → 2. Error → 4. |
| 2 | **Get customer input** | Texto a voz definido **dinámicamente** e interpretado como **SSML**, con el atributo definido por el usuario **`mensaje`** (`$.Attributes.mensaje`). DTMF: tiempo de espera de **8** segundos y una condición **1**. | Pressed 1 → 2 (vuelve a sí mismo). Timeout → 3. Default → 3. Error → 4. |
| 3 | **Play prompt** | Texto a voz definido a mano, interpretado como texto: `Gracias. Hasta luego.` | Success → 4. Error → 4. |
| 4 | **Disconnect / hang up** | Sin configuración. | — |

El punto de entrada va al bloque 1. Guarda, publica y copia el identificador como en la opción A.

## Por qué está hecho así

- **La voz se fija lo primero.** Si no, Connect usa Joanna (inglés de EE. UU.) y leería el castellano con acento inglés. Si la voz falla, el flujo cuelga en lugar de leer el mensaje con una voz equivocada.
- **Lucia con el motor neural.** Es una voz femenina de castellano de España que admite los motores *standard*, *neural* y *generative*. Las voces neural y standard son gratuitas dentro de Connect (la generativa se paga aparte), y la neural admite lo que usa nuestro SSML: `<speak>` y `<prosody rate="90%">`. La generativa solo admite `<prosody>` alrededor de frases completas y no se ha probado.
- **El mensaje va en el propio *Get customer input*.** Así el familiar puede pulsar 1 mientras suena, sin esperar a que termine, y el bloque vuelve a empezar. La repetición no tiene límite, pero exige que alguien pulse cada vez.
- **Si no pulsa nada en 8 segundos** o pulsa otra tecla, se despide y cuelga. Si el atributo `mensaje` falta o el SSML no es válido, el bloque toma la salida *Error* y cuelga sin decir nada: es un fallo de la Lambda, no del familiar.
- **Límite de texto.** Connect admite hasta 3000 caracteres facturables (6000 en total) por texto a voz; con más, el bloque toma la salida *Error*. Los mensajes actuales rondan los 350 caracteres y un test comprueba que quedan muy por debajo con nombres de longitud máxima.

## Referencias (documentación de Amazon Connect y Amazon Polly)

- Flow language: *Example flow*, *MessageParticipant*, *GetParticipantInput*, *UpdateContactTextToSpeechVoice*.
- Guía de administración de Connect: bloques *Set voice*, *Get customer input* y *Play prompt*; *SSML tags supported by Amazon Connect*; *Add text-to-speech to prompts*.
- Amazon Polly: *Available voices*, *Supported SSML tags* y *Controlling volume, speaking rate, and pitch*.
