# MAPA — qué archivo abrir

> **En la versión abierta NO vienen** `panel_admin.py`, `api_web.py`, `launcher_api.py`,
> `launcher_contenido.py`, `ruleta.py`, `respaldo.py`, `npc_charla.py`, `geoip.py` ni `portero.py`:
> son la administración del servidor original (panel web, API de la página, launcher con ruleta,
> respaldos, prueba de carga, el portero de cuentas). Las filas de abajo que los nombran quedan como referencia. Los roles (GM, admin,
> streamer) salen de `gm.py`.


Este documento existe para no tener que leer el servidor entero antes de tocar una cosa.
Buscá tu tarea en la primera tabla y abrí sólo lo que dice.

## Si tu tarea es…

| tarea | abrí | y nada más |
|---|---|---|
| **un comando `FFxx` no anda / no sé quién lo atiende** | `despacho.py` | es la tabla `FFxx -> función`. 60 líneas. **Empezá siempre acá.** |
| **ver en vivo qué bytes cruzan de verdad** | `mitm.bat` → `../re2013/LEEME.md` | captura pasiva; el dump sale con el mismo formato que este log |
| las flechas de una canción | `notas.py` + `documentacion/RECETA_NOTAS_2013.md` | el formato del chart está medido del exe |
| importar canciones nuevas | `../importador2013/LEEME.md` | no toca el server |
| el picker de música sale vacío o de más | **primero fijate en qué CANAL estás** (ver abajo); después `notas.py` (`cargar`) y `myrecord.py` (LOOP A) | la lista sale de los `.bin` que existen |
| la ficha del jugador: monedas, apodo, ropa puesta, inventario | `myrecord.py` | es el `FF03`, el paquete más grande |
| misiones, grados, premios | `misiones.py` + `documentacion/mapeo_misiones.md` | |
| medallas, el récord del perfil (ganadas/perdidas) | `medallas.py` + `documentacion/MEDALLAS_Y_RECORD.md` | `.record` en el chat para ver/editar |
| la sala de conversación compartida (estancias, lista, movimiento, chat) | `charla.py` + `documentacion/SALA_DE_CHARLA_2013.md` | `CHARLA_COMPARTIDA` en `ajustes.py` |
| círculos (crear, pedir entrar, aceptar, echar, el mando; la pestaña de la Mensajería; donar) | `circulos.py` + `documentacion/CIRCULOS_HALLAZGOS.md` | `.circulo ayuda` en el chat; `.circulo sonda` (GM) |
| la tienda del círculo, su inventario, la marca | `circulo_tienda.py` + `documentacion/CIRCULO_EXE_TIENDA.md` | precios en `tablas-cliente/circleshop.xml` |
| la API de la WEB nueva (rankings, círculos, estado) | `api_web.py` + `documentacion/WEB_Y_PANEL_PLAN.md` | `http://127.0.0.1:48190/api/…` (`R2_API_PUERTO`; 0 = apagada) |
| el PANEL DE ADMINISTRACIÓN (salas, chat, conectados/IP, ban, EXP, Rcoin, apodo, clave, inventario) | `panel_admin.py` + `documentacion/PANEL_ADMIN_TRASPASO.md` | `/api/admin/…`; GM = `gm.txt`, ADMIN = `admin.txt`; su base, `panel.db` |
| ★ el PORTERO: las cuentas de R2Beat para OTROS juegos (EDA) — login, aprobados, pase firmado Ed25519, manifest sólo a aprobados | `portero.py` + `firma_ed25519.py` + `documentacion/PORTERO_CUENTAS.md` | PROCESO APARTE: `python -m servidor.portero` en `127.0.0.1:48195`; ⛔ `datos.db` sólo lectura; su base `portero.db` |
| el RESPALDO DIARIO de la base | `respaldo.py` + `documentacion/PENDIENTE_RESPALDO_Y_HISTORIAL.md` | `R2_RESPALDOS`, `R2_RESPALDO_HORA`, `R2_RESPALDO_DIAS`; `R2_RESPALDO=0` lo apaga |
| la PRUEBA DE CARGA de la sala de conversación (NPCs de la base local) | `npc_charla.py` | `.carga charla 30` en el chat (desarrollo, ⛔ sólo local) |
| nivel, exp, licencia, a qué canal entra | `progresion.py` + `documentacion/canales_matcher_findings.md` | |
| la tienda, comprar, equipar | `lobby_tienda.py` + `catalogo.py` | |
| crear/entrar/listar salas, el lobby | `lobby_salas.py` + `salas.py` | `salas.py` es el estado vivo |
| ⚔️ la CARRERA EN GRUPO / el 6vs6 (`.grupo`, `.grande`): la sala de 12 que arma el server | `grupo.py` + `salas.py` (`GRANDE_SALA`) + `documentacion/MODO_6VS6.md` | la dll: `grande.c` |
| la carrera, el chase, el cartel de resultado | `lobby_carrera.py` + `documentacion/HALLAZGOS_COOP.md` | |
| ⛔ LOCAL: los NPC que JUEGAN la carrera (su avance `FF4E 0x05` inventado, sus filas en el cartel y, en la carrera ítem, sus cajas e ítems `FF4E 0x01`) | `npc_carrera.py` | MODO_6VS6.md §16 |
| el cartel de resultado de la carrera de 12: la cola «C2» pegada al `FF28` (el contrato con `cartel12.c`) | `cartel12.py` | MODO_6VS6.md §17 |
| la tabla del sorteo de la caja «?» (la del CBT, R-coin apagado; GENERADA por `items_sorteo.py --datos`), con la que sortean los NPC que juegan | `items_tabla.py` | ITEMS_SORTEO.md |
| chat, perfil, amigos, el menú | `lobby_menu.py` | los comandos de prueba están en `chat.py` |
| la TIRA de anuncios de arriba del lobby (`FFBF`, `.tira`) | `tira.py` | `documentacion/TIRA_DE_ANUNCIOS.md` |
| «Enviar regalo» (`FF4F` cifrado + `FF53`) y «Mis preferidos» (`FF6F`/`FF70`/`FF71`) | `regalo.py` · `preferidos.py` | `documentacion/REGALO.md` · `REGALO_ACTIVO` |
| los 4 SETS del armario (`FF73`: guardar, cargar, la lista al entrar) | `conjuntos.py` | `documentacion/ARMARIO_CONJUNTOS.md` |
| «Restaurar» del armario / varias prendas de una (`FF7F`) | `lobby_tienda.h_ff7f_vestir_varios` + `catalogo.db_equip_varios` | `documentacion/ARMARIO_RESTAURAR.md` |
| la TRANSMISIÓN al espectador (`FF98`): los eventos de los corredores, descifrados, al que mira | `espectador_datos.py` | `documentacion/MODO_ESPECTADOR.md` §9 · `ESPECTADOR_DATOS` |
| «Ingreso Rápido» (`FF72`): una sala al azar según «Configuraciones de ingreso rápido» | `entrada_rapida.py` | `documentacion/ENTRADA_RAPIDA.md` · `ENTRADA_RAPIDA` |
| «Invitar a los del vestíbulo» (`FF52`) e «Invitar a un amigo a mi sala» (`FF40 0x07`) | `invitacion.py` | `documentacion/INVITAR_VESTIBULO.md` · `INVITAR_VESTIBULO` |
| «¿Quién te invitó?» (`FFE2`): el que invitó cobra Rcoin; la tabla `referidos` | `referido.py` | `documentacion/REFERIDO.md` · `REFERIDO_*` en `ajustes.py` |
| el PICKER de la sala: preferidas, «Mi record», popularidad, Aleatorio/TOP 20/NUEVOS 20 | `picker.py` + `documentacion/PICKER_SISTEMA.md` | `PICKER_*` en `ajustes.py`; el modo vive en `salas.SELECCION_SALA` |
| la PRESENTACIÓN PERSONAL y el cartel «¿Desea escribirla ahora?» (`FF94`, la letra del `FF03`) | `presentacion.py` + `documentacion/PRESENTACION_PERSONAL.md` | `PRESENTACION_*` en `ajustes.py` |
| ★ el LAUNCHER NUEVO (26-oct): su API (`/api/launcher/…`: entrar, personajes, ruleta, girar, público) · la RULETA (monedas gorila → Rcoin o ropa de Halloween, la paga el server al personaje elegido) · lo que muestra y se edita en el panel (noticias, torneo, supporters, la tabla de la ruleta) | `launcher_api.py` · `ruleta.py` (+ `ruleta_ropa.json`) · `launcher_contenido.py` | `pruebas/probar_ruleta_launcher.py` · `documentacion/LAUNCHER_NUEVO.md` |
| hasta 4 PERSONAJES por cuenta (la landing web y el selector del launcher): listar, crear, entrar con uno (o «a crear»: la creación nativa), borrar y las A/B/C de la creación (`FFF1`…`FFF5` del LoginServer); la tabla `cuenta_personajes` | `cuenta_personajes.py` | `pruebas/probar_cuenta_personajes.py` · `documentacion/SELECTOR_PERSONAJE.md` · repo Fuente `documentacion/LANDING.md` |
| guardar/leer personajes | `basedatos.py` | `chars_db.json` |
| el cifrado, los sobres `FF55`/`FF4E` | `cifrado.py` | |
| prender el server, puertos, listeners | `lobby.py` (`main`) y `../startserver.py` | |
| cambiar un número o una bandera | `ajustes.py` | ningún otro archivo tiene constantes |

## El orden de la cadena

Cada módulo sólo puede usar los de **más arriba**. Si te encontrás necesitando algo de
más abajo, la función está en el lugar equivocado.

```
ajustes        los números y las banderas. No importa nada del server.
registro       el log y el modo paso a paso
cifrado        el framing FFxx y los sobres FF55 / FF4E
basedatos      chars_db.json: personajes, inventario, equipo
catalogo       tienda y cosméticos: shop_lt, wing.txt, face.txt
progresion     exp, nivel, licencia, banda de canal
notas          los charts del FF57                        ← autónomo, no depende del lobby
misiones       las 19 misiones, premios y grados
medallas       el récord (ganadas, perdidas, 97%, allcombo) y las 24 medallas — se cuenta al cobrar
circulos       el círculo (clan): crear/unirse/echar por `.circulo` (la web del original), el GuildInfo (FF40 0x21)
circulo_tienda la tienda del círculo (FFD9), su inventario (FFD7/FFDA) y la marca (FFDF) — se paga con el dinero del círculo
api_web        la API de la web (HTTP en 127.0.0.1, su hilo): lecturas + lo de la web, siempre por las funciones del juego
panel_admin    el PANEL: todo /api/admin/*; escucha el chat público y la IP (`oir`, desde lobby) y escribe en SU panel.db;
               mide el TIEMPO DE JUEGO (`actividad`), anota la BITÁCORA (`carreras_log`, `sesiones`, `campanas`), los REPORTES de cada FF28 con sus marcas de pillo (`reportes`) y los PERMISOS de cada GM (`permisos`)
launcher_api   ★ /api/launcher/* (dentro de api_web, con `Authorization: Bearer`): la cuenta, sus personajes, la ruleta
portero        ★ PROCESO APARTE (no lo importa lobby): cuentas de R2Beat → pases firmados para EDA; datos.db sólo lectura
firma_ed25519  la firma Ed25519 (RFC 8032) en Python puro, para el portero
ruleta         la RULETA del launcher: monedas gorila → Rcoin o ropa (ruleta_ropa.json); `ruleta_giros` en datos.db
launcher_contenido  lo que muestra el launcher (noticias, torneo, supporters, la tabla de la ruleta): tabla `launcher_contenido`
respaldo       el RESPALDO DIARIO de datos.db + panel.db (copia de SQLite, se abre y se cuenta, gzip, rota); lo arranca api_web
npc_charla     NPCs para la prueba de carga de la charla: entran/caminan/hablan/se van por los caminos de verdad (⛔ local)
charla         la SALA DE CONVERSACIÓN compartida (tipos 5..10) y la del CÍRCULO (12, una por círculo): estancias, lista armada una vez, FF0E, FF23, FF08
picker         el PICKER: preferidas (FF137/138/13A), Mi record (FF139), popularidad (FF13B), el sorteo de las maneras de lista
presentacion   la presentación personal: el FF94 (registrar/editar/la letra de «Buscar amigos») y lo que va en FF03/FF77
myrecord       el FF03 (la ficha del jugador)
paquetes       los armadores FFxx sueltos
salas          salas, mesas, ocupantes y los lugares de charla
carrera        modo de sala (FF4B), canciones del chase, cartel de resultado
autoplay_gm    `.autoplay`: el server le prende al GM el autoplay escondido del cliente
chat           los comandos de prueba que se escriben en el chat
lobby          la conexión, el reparto de comandos y el arranque
  lobby_menu · lobby_salas · lobby_carrera · lobby_tienda    los handlers, por tema
despacho       la tabla FFxx -> handler
```

## Dos reglas que ya costaron caro

**1 · No reasignes un nombre que otros módulos importan.** `from .x import NOMBRE` copia
el **nombre** apuntando al mismo objeto. Reasignarlo (`NOMBRE = otra_cosa`) sólo cambia tu
copia; los demás siguen viendo la vieja, sin ningún error. Si tenés que actualizar una
lista o un dict compartido, **mutalo** (`X[:] = ...`, `X.clear()` + `X.update(...)`), o
mejor: guardalo privado y exponé funciones, como hace `notas.py`.

Esto rompió tres cosas distintas, todas en silencio:

- `OWNED_SONGS_2013` → el picker llegaba sin una sola canción
- `NOTES_MAP` → el log decía `SIN MAPA` en las 814 canciones (las notas iban bien)
- la misma trampa, con el agravante de correr `lobby.py` como script y tener dos copias
  del módulo vivas a la vez

**2 · El picker de ENTRENAMIENTO depende del CANAL, no de lo que mandes.** Es el "picker
de práctica" y está filtrado por la categoría de licencia del jugador: sólo la categoría
**13 = LIBRE** libera el guard `[player+0x6d98]` y muestra el catálogo entero. En cualquier
otro canal ves un subconjunto y parece que el server manda de menos.

`0x58CEF0` traduce el byte del `FFC9` a categoría: `1/8→3` novato · `2/3→0` estrella ·
`4/5→1` luna · `6/7→2` sol · **cualquier otro → 13**. Por eso `LIBRE_TIER_BYTE = 9`.
Palancas ya hechas: el canal `Libre` (puerto 48085), `FORZAR_CANAL_LIBRE` en `ajustes.py`,
y el comando `.libre` del chat.

Está desarrollado en `documentacion/canales_matcher_findings.md` §7.

⚠ **Antes de medir cualquier cosa del picker, fijá el canal.** Cambiar de canal es
re-loguear, así que se cambia solo entre pruebas sin que te des cuenta — y ahí cualquier
otra variable que estés midiendo (tamaño del paquete, cantidad de canciones) da resultados
que parecen limpios y no significan nada. Pasó el 2026-09-02: se "midió" un tope de 2193 B
en el `MyRecord` que no existe.

**3 · Una canción en el picker sin chart mata al cliente.** El handler `FF57`
(`0x5D01F0`) baja el contador de pedidos pendientes aunque el `result` no sea 1, y al
llegar a cero corre `0x56E080` con los vectores vacíos: el proceso se auto-mata, sin
excepción, sin log y sin crashdump. Por eso el picker se arma con los `.bin` que
realmente existen y nunca con una lista escrita a mano.

## Antes de dar por buena una modificación

```bash
python pruebas/huella.py
```

Llama a los 23 armadores de paquetes con entradas fijas y compara los bytes contra la
referencia. Si cambiaste el formato a propósito, `--guardar` regraba la referencia; si
no, algo se rompió. Regrabarla "para que pase" es tirar la red de seguridad.

```bash
python pruebas/dependencias.py --imports
```

Dice qué nombres usa cada módulo y de dónde salen, con las líneas de `import` ya armadas.
Sirve para mover una función de lugar sin adivinar a quién le va a faltar.

## Estado del orden (2026-09-02)

`lobby.py` era un archivo de **1776 líneas con ocho temas adentro**. Salieron `notas`,
`misiones`, `myrecord`, `carrera`, `chat`, la parte de `progresion` y los lugares de
charla (a `salas`). Quedó en **707 líneas** y ahora es una sola cosa: la conexión, el
reparto de comandos y el arranque.

**Ya no queda ni un `from .x import *`.** Cada archivo abre con la lista de lo que usa y
de dónde sale, así que para entender un módulo alcanza con leer su cabecera.

Lo que **falta**:

- `ajustes.py` son 1408 líneas, 1046 de ellas comentarios. Mucho de eso es historia del
  reversing que le corresponde a `documentacion/`, no a un archivo de constantes.
- `lobby_salas.py` (49 nombres de afuera) y `lobby_tienda.py` (48) siguen siendo los que
  más tiran de todo el resto; probablemente les sobre alguna responsabilidad.
- Los handlers se llaman `h_21_ff28`: el número del medio es el orden que tenía la rama
  en el `if/elif` original y hoy no significa nada.
