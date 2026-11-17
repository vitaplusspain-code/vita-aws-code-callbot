# Flujo de Connect: check-in diario con la persona mayor

Flujo que ejecuta Amazon Connect cuando el lanzador (`handlers/lanzar_checkin.py`) pide la llamada con `StartOutboundVoiceContact`. Fija la voz y deja la conversación en manos del bot de Lex V2 `vita-dev-callbot-checkin` (alias `vita-dev-callbot-checkin-activo`, idioma `es_ES`), que a su vez la deja en manos de la Lambda `vita-dev-callbot-conversacion`. Cuando el bot cierra la conversación, el flujo cuelga.

La llamada solo lleva un atributo de contacto, `call_id` (`$.Attributes.call_id`), un UUID sin datos personales. El flujo lo pasa a la sesión de Lex con la misma clave, `call_id`, y la Lambda lo lee de `sessionAttributes` (`adapters/lex.py`). El flujo no contiene nombres ni datos de personas: solo un «Hola, le llama el asistente automático de VitaPlus.» inicial y el cierre fijo de error.

Hay dos formas de crearlo. Las dos dan el mismo resultado. Los nombres de menús y opciones de la consola pueden variar un poco según la versión de Connect.

## Antes de empezar

- El stack de Frankfurt está desplegado y el bot está asociado a la instancia (`DESPLIEGUE.md` del repo de infra, apartado 10.3, pasos 3 y 4).
- Ten a mano el ARN del alias: es el output `CheckinBotAliasArn` del stack `vita-dev-callbot-checkin`. Tiene la forma `arn:aws:lex:eu-central-1:<cuenta>:bot-alias/<id-bot>/<id-alias>`.

## Opción A: importar `flujo-checkin.json`

El JSON no lleva el ARN del alias: en su lugar tiene el marcador `SUSTITUIR_ARN_ALIAS_BOT_CHECKIN`, para no guardar en el repo el número de cuenta.

1. Haz una **copia local** de `connect/flujo-checkin.json` fuera del repo (por ejemplo, en el escritorio; si la dejas dentro, llámala `connect/flujo-checkin.local.json`, que git ignora) y, en la copia, sustituye `SUSTITUIR_ARN_ALIAS_BOT_CHECKIN` por el ARN del alias. No guardes el ARN en el repo.
2. En la consola de Connect de la instancia `vita-dev-callbot` (eu-central-1), ve a **Routing → Flows**.
3. Si el flujo `vita-dev-callbot-flujo-checkin` ya existe, ábrelo e importa encima: se sustituye y **el identificador no cambia**, así que el parámetro `ConnectFlujoCheckinId` no necesita cambios. Si no existe, crea uno nuevo de tipo *Inbound flow* (en la consola sale como *Contact flow (inbound)*; en la API, `CONTACT_FLOW`), el mismo tipo que el del aviso, y llámalo `vita-dev-callbot-flujo-checkin`.
4. En el desplegable junto a **Save**, elige **Import (beta)** y selecciona la copia del paso 1.
5. Abre el bloque **Get customer input** y comprueba que en la pestaña de Amazon Lex sale el bot `vita-dev-callbot-checkin` con el alias `vita-dev-callbot-checkin-activo`. Si sale vacío o con error (por ejemplo, porque importaste el JSON sin sustituir el marcador), elige ahí el bot y el alias en los desplegables.
6. Guarda y publica.
7. Copia el identificador del flujo: es la parte final de su ARN, en la pestaña **Details**. Es el parámetro `ConnectFlujoCheckinId` del stack de Irlanda (`DESPLIEGUE.md`, 10.3, paso 6).

El JSON sigue el *Flow language* de Connect (versión `2019-10-30`) y lo comprueba `tests/test_flujo_checkin.py`.

**Problema conocido de las posiciones:** al importar `flujo-aviso.json` (08/11) los bloques salieron amontonados, porque el editor ignoró `Metadata.ActionMetadata.*.Position`. Este JSON usa el mismo formato, así que lo normal es que pase lo mismo. Es solo la colocación en el editor y no afecta a la llamada: arrastra los cuatro bloques para verlos. Si la importación fallara, usa la opción B.

## Opción B: crearlo a mano

Crea un *Inbound flow* vacío con el nombre `vita-dev-callbot-flujo-checkin` y añade estos cuatro bloques:

| # | Bloque | Configuración | Salidas |
|---|---|---|---|
| 1 | **Set voice** | Idioma: español (España). Voz: **Lucia**. Activa la sustitución del estilo de habla y elige el motor **Neural**, sin estilo. | Success → 2. Error → 4. |
| 2 | **Get customer input** (Lex) | Texto a voz definido a mano, interpretado como texto: `Hola, le llama el asistente automático de VitaPlus.` Pestaña **Amazon Lex**: bot `vita-dev-callbot-checkin`, alias `vita-dev-callbot-checkin-activo` (o el ARN del alias). **Atributos de sesión**: `call_id` = valor dinámico, atributo definido por el usuario `call_id` (`$.Attributes.call_id`); `x-amz-lex:audio:start-timeout-ms:*:*` = `6000`; `x-amz-lex:audio:end-timeout-ms:*:*` = `1200`. **Intents**: añade `Conversacion`. Sin *Initialize bot with message*. | Conversacion → 4. Default → 3. Timeout → 3 (si sale). Error → 3. |
| 3 | **Play prompt** | Texto a voz definido a mano, interpretado como texto: `Lo siento, ha habido un problema y no puedo seguir hablando ahora. Si necesita ayuda urgente, llame al 112. Si piensa en hacerse daño, llame al 024. Hasta mañana.` | Success → 4. Error → 4. |
| 4 | **Disconnect / hang up** | Sin configuración. | — |

El punto de entrada va al bloque 1. Guarda, publica y copia el identificador como en la opción A.

## Cómo arranca la conversación

**El bot no puede hablar primero en una llamada de voz.** La documentación del *Flow language* lo dice expresamente en `ConnectParticipantWithLexBot`: `LexInitializationData` («Initialize bot with message») «is only supported for Chat channel today. The Voice channel is not supported». En voz, Lex solo actúa cuando la persona dice algo. Por eso:

1. Connect fija la voz y entra en el bloque de Lex, que dice el «Hola, le llama el asistente automático de VitaPlus.» del flujo. Es una invitación a hablar para quien coge el teléfono y espera en silencio. Se puede interrumpir hablando (*barge-in*), así que un «¿Diga?» dicho a la vez también vale.
2. Lo primero que diga la persona («¿Diga?», «¿Sí?», «Hola, ¿quién es?») llega a Lex. Si encaja con las frases de ejemplo del intent `Conversacion` («hola», «sí», «dígame»…), entra en él; si no, entra en `FallbackIntent`. Los dos llaman a la Lambda.
3. La Lambda ve que la sesión aún no tiene estado (`core/conversar.py`, `hay_estado`) y responde el primer turno: el saludo con el nombre y la identificación como asistente automático, más la primera pregunta. Antes pasa esa primera frase por el detector de riesgo.
4. A partir de ahí la Lambda pide el slot `respuesta` en cada turno (`ElicitSlot`) y, al terminar, cierra con `Close` y el intent `Conversacion` en `Fulfilled`, con la despedida, el aviso del 112 o el cierre de error como último mensaje.
5. Connect toma la salida **Conversacion** y cuelga. **No hay despedida en el flujo:** la Lambda siempre cierra con un mensaje (`adapters/lex.py` no deja un cierre mudo), así que otra frase aquí se oiría repetida.

No hace falta un intent de inicio: cualquier primera frase llega a la Lambda, y la Lambda empieza la conversación cuando no hay estado.

## Ramas de error y sin respuesta

Todas van al bloque 3, que dice el mismo cierre de error que la Lambda (`TEXTOS[Trato.USTED].cierre_error`, en `core/checkin_guion.py`; un test comprueba que coinciden), menciona el 112 y el 024, no nombra a nadie, y cuelga:

- **Error:** falla el bloque (por ejemplo, el alias no existe o no está asociado a la instancia) o el intent no queda cumplido.
- **Default:** el bot devuelve el control con un intent que no es `Conversacion` (por ejemplo, `FallbackIntent` cerrado sin pasar por la Lambda).
- **Timeout:** según la documentación, solo salta con el temporizador de chat (`LexTimeoutSeconds`), que este flujo no usa. Se conecta igual por si acaso.

Si falla el bloque de la voz, se cuelga sin decir nada: leer el castellano con la voz por defecto (Joanna, inglés de EE. UU.) sería peor.

## Por qué está hecho así

- **El `call_id` va como atributo de sesión.** `LexSessionAttributes` admite claves y valores estáticos o dinámicos; aquí la clave es fija (`call_id`) y el valor, el atributo de contacto `$.Attributes.call_id`. Los atributos de sesión que devuelve la Lambda tienen prioridad sobre los del flujo, y la Lambda devuelve siempre el `call_id`.
- **Tiempos de voz desde el primer turno.** La Lambda fija 6000 ms de silencio inicial y 1200 ms de fin de frase para el slot `respuesta` (`TIEMPOS_VOZ`), pero Connect avisa de que, si los atributos los pone la Lambda, se usan los valores por defecto (3000 y 600 ms) hasta que se la invoca. El primer turno aún no tiene intent ni slot, así que el flujo pone los mismos valores con el comodín `*:*`. Un test comprueba que coinciden con los de la Lambda.
- **Lucia con el motor neural**, como en el flujo del aviso. Los mensajes del bot los sintetiza Lex con su propia voz (`VoiceSettings` del bot, también Lucia neural, en `template-frankfurt.yaml`); la voz del flujo se oye en el «Hola, le llama el asistente automático de VitaPlus.» y en el cierre de error.
- **Se identifica desde la primera frase** (decisión 9), sin decir el nombre: quien coge el teléfono puede no ser la persona mayor, y si nadie habla se oye igualmente que es un asistente automático. El nombre lo dice la Lambda en su primer turno.
- **Grabación y registros apagados.** El flujo no tiene bloques de grabación (*Set recording and analytics behavior*) ni de registro (*Set logging behavior*), y un test lo comprueba. Lo que dice la persona mayor son datos de salud: no actives la grabación ni los registros del flujo en la instancia. Si algún día se activan para otros flujos, añade aquí un bloque que los apague.
- **Sin SSML en los mensajes del bot.** La Lambda manda `PlainText`; que Connect reproduzca SSML del bot está sin verificar.

## Sin verificar (comprobar en la primera llamada real)

- **Que el `sessionId` de Lex sea el `ContactId` de Connect.** La documentación oficial no lo dice: la de Lex V2 describe `sessionId` sin mencionar Connect, y la de Connect no documenta qué valor usa (en la tabla `bot_conversations` del *data lake*, `bot_session_id` y `contact_id` son columnas distintas, sin decir si coinciden). Solo lo afirman fuentes no oficiales para voz (un blog de diciembre de 2022 y respuestas en re:Post); en chat, otra respuesta de re:Post dice que Connect usa el `participantId`. La Lambda depende de ello (`contacto_id` en `adapters/lex.py`): si no coincide, la conversación cierra con el texto de error. En la primera llamada, compara el `session_id` del log de `vita-dev-callbot-conversacion` con el `ContactId` que guarda el lanzador.
- Que el comodín `*:*` de los tiempos de voz se aplique al primer turno, cuando aún no hay intent.
- Que el `FallbackIntent` pueda pasar a `Conversacion` con la respuesta de la Lambda (`ElicitSlot` sobre otro intent).
- Qué hace Lex si la persona no dice nada tras el «Hola, le llama el asistente automático de VitaPlus.» (en voz no hay salida *Timeout*): lo esperable es que el bot vuelva sin intent y el flujo tome **Default** o **Error**, es decir, el cierre fijo.
- Si salta un contestador, su mensaje llega a Lex como si fuera la persona, y la Lambda saludaría con el nombre. La detección de contestadores de Connect parece ligada a las campañas salientes (no comprobado); queda para el piloto.
- Las posiciones de los bloques al importar (ver arriba).

## Referencias (documentación de Amazon Connect y Amazon Lex V2)

- Flow language: *ConnectParticipantWithLexBot* (`https://docs.aws.amazon.com/connect/latest/devguide/participant-actions-connectparticipantwithlexbot.html`), *Example flow*, *MessageParticipant*, *UpdateContactTextToSpeechVoice*.
- Guía de administración de Connect: *Get customer input* (`https://docs.aws.amazon.com/connect/latest/adminguide/get-customer-input.html`), *How flow blocks use Amazon Lex session attributes*, *Bot analytics data in the analytics data lake*.
- Lex V2: *Interpreting the input event format* (`https://docs.aws.amazon.com/lexv2/latest/dg/lambda-input-format.html`), *Configuring timeouts for capturing user input*.
- No oficial: *Call Lex Intent From Amazon Connect Without User Input* (yottabrain.org, 24/12/2022), sobre el `ContactId` como `sessionId`.
