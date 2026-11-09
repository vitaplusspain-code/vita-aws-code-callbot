# Flujo de Connect: aviso al familiar

Flujo que ejecuta Amazon Connect cuando la Lambda pide una llamada con `StartOutboundVoiceContact`. Primero saluda y pide al familiar que confirme que es él pulsando 1. Solo entonces le cuenta el motivo, que puede repetir pulsando 1, y cuelga (decisión 37).

La Lambda manda las dos partes ya preparadas, en SSML, en dos atributos de contacto:

- `saludo` (`$.Attributes.saludo`): solo nombra al familiar y pide pulsar 1. No dice nada de la persona mayor ni del motivo.
- `detalle` (`$.Attributes.detalle`): el motivo del aviso, el 112 y cómo repetirlo.

El flujo no contiene textos de casos ni datos de personas, salvo las dos despedidas fijas.

Hay dos formas de crearlo. Las dos dan el mismo resultado. Los nombres de menús y opciones de la consola pueden variar un poco según la versión de Connect.

## Opción A: importar `flujo-aviso.json`

1. En la consola de Connect de la instancia `vita-dev-callbot` (eu-central-1), ve a **Routing → Flows**.
2. Si el flujo `vita-dev-callbot-flujo-aviso` ya existe, ábrelo e importa encima: se sustituye y **el identificador no cambia**, así que la plantilla SAM no necesita cambios. Si no existe, crea uno nuevo de tipo *Inbound flow* (en la API, `CONTACT_FLOW`) y llámalo `vita-dev-callbot-flujo-aviso`.
3. En el desplegable junto a **Save**, elige **Import** y selecciona `connect/flujo-aviso.json`.
4. Guarda y publica.
5. Si es nuevo, copia el identificador del flujo: es la parte final de su ARN, en la pestaña **Details**. Es el parámetro `ConnectContactFlowId` de la plantilla SAM.

El JSON sigue el *Flow language* de Connect (versión `2019-10-30`) y lo comprueba `tests/test_flujo_connect.py`. Al importarlo, los bloques pueden salir amontonados: es solo la colocación en el editor, no afecta a la llamada. Si la importación fallara, usa la opción B.

**Importante:** el flujo y la Lambda van juntos. Esta versión lee `saludo` y `detalle`; la anterior leía `mensaje`. Si solo cambia una de las dos piezas, la llamada sale muda: el bloque no encuentra su atributo y cuelga. No se filtra nada, pero la API responde 200 y nadie se entera. Cambia las dos en este orden, y en el mismo orden si hay que volver atrás:

1. Apaga las llamadas: despliega con `LlamadasActivas=false` (la API responde 503).
2. Importa y publica el flujo.
3. Despliega la Lambda nueva, todavía con las llamadas apagadas.
4. Enciende las llamadas (`LlamadasActivas=true`) y haz una llamada de prueba a un número de la lista blanca.

## Opción B: crearlo a mano

Crea un *Inbound flow* vacío con el nombre `vita-dev-callbot-flujo-aviso` y añade estos seis bloques:

| # | Bloque | Configuración | Salidas |
|---|---|---|---|
| 1 | **Set voice** | Idioma: español (España). Voz: **Lucia**. Activa la sustitución del estilo de habla y elige el motor **Neural**, sin estilo. | Success → 2. Error → 6. |
| 2 | **Get customer input** (saludo) | Texto a voz definido **dinámicamente** e interpretado como **SSML**, con el atributo definido por el usuario **`saludo`** (`$.Attributes.saludo`). DTMF: tiempo de espera de **8** segundos y una condición **1**. | Pressed 1 → 3. Timeout → 5. Default → 5. Error → 6. |
| 3 | **Get customer input** (detalle) | Igual que el 2, con el atributo **`detalle`** (`$.Attributes.detalle`). | Pressed 1 → 3 (vuelve a sí mismo). Timeout → 4. Default → 4. Error → 6. |
| 4 | **Play prompt** | Texto a voz definido a mano, interpretado como texto: `Gracias. Hasta luego.` | Success → 6. Error → 6. |
| 5 | **Play prompt** | Texto a voz definido a mano, interpretado como texto: `No hemos recibido la confirmación. Disculpe las molestias. Hasta luego.` | Success → 6. Error → 6. |
| 6 | **Disconnect / hang up** | Sin configuración. | — |

El punto de entrada va al bloque 1. Guarda, publica y copia el identificador como en la opción A.

## Por qué está hecho así

- **La voz se fija lo primero.** Si no, Connect usa Joanna (inglés de EE. UU.) y leería el castellano con acento inglés. Si la voz falla, el flujo cuelga en lugar de leer el mensaje con una voz equivocada.
- **Lucia con el motor neural.** Es una voz femenina de castellano de España que admite los motores *standard*, *neural* y *generative*. Las voces neural y standard son gratuitas dentro de Connect (la generativa se paga aparte), y la neural admite lo que usa nuestro SSML: `<speak>` y `<prosody rate="90%">`. La generativa solo admite `<prosody>` alrededor de frases completas y no se ha probado.
- **Primero se confirma la identidad.** Quien coge el teléfono puede no ser el familiar. El saludo solo dice que hay un aviso para él; el motivo, que puede ser un dato de salud, solo se cuenta si pulsa 1. Al detalle no se llega por ningún otro camino, y un test lo comprueba. Pulsar 1 no prueba quién es; más adelante se podría pedir el DNI y validarlo contra la base de datos.
- **Cada parte va en su propio *Get customer input*.** Así el familiar puede pulsar 1 mientras suena, sin esperar a que termine. En el detalle, el 1 lo repite; la repetición no tiene límite, pero exige que alguien pulse cada vez.
- **Si no pulsa nada en 8 segundos** o pulsa otra tecla: tras el saludo se despide sin dar detalles; tras el detalle se despide y cuelga. Si falta un atributo o el SSML no es válido, el bloque toma la salida *Error* y cuelga sin decir nada: es un fallo de la Lambda, no del familiar.
- **Límite de texto.** Connect admite hasta 3000 caracteres facturables (6000 en total) por texto a voz; con más, el bloque toma la salida *Error*. Cada parte ronda los 200-350 caracteres y un test comprueba que quedan muy por debajo con nombres de longitud máxima.

## Referencias (documentación de Amazon Connect y Amazon Polly)

- Flow language: *Example flow*, *MessageParticipant*, *GetParticipantInput*, *UpdateContactTextToSpeechVoice*.
- Guía de administración de Connect: bloques *Set voice*, *Get customer input* y *Play prompt*; *SSML tags supported by Amazon Connect*; *Add text-to-speech to prompts*; *Import/export flows*.
- Amazon Polly: *Available voices*, *Supported SSML tags* y *Controlling volume, speaking rate, and pitch*.
