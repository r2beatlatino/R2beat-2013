# -*- coding: utf-8 -*-
"""ajustes — los números y banderas que se tocan: puertos, canales, flags de sonda

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
# server_login2013.py — LoginServer + LobbyServer mínimos para R2Beat 2013.
#
# Implementa la secuencia de FASE 2 (re/FASE2_login_response.md), byte-exacta:
#
#   Cliente -> Login  :  FF 01 0C 00 <usn:u32><vcode:u64>      (CmdLogin req)
#   Login   -> Cliente:  RESP-1  (CmdLogin status=0)           <- desbloquea
#   Cliente -> Login  :  FF 02 00 00                           (pide lista de lobbies)
#   Login   -> Cliente:  RESP-2  (CmdLobbyServerList, 1 entry -> nuestra Lobby)
#      => el cliente CONECTA la Lobby a la IP:puerto de la entrada
#   Cliente -> Lobby  :  FF 01 02 00 04 00                     (CmdCheckVer ver=4)
#   Lobby   -> Cliente:  RESP-3  (FF 01 01 00 00, ACK status=0)
#      => tras el OK el cliente ENVIA por si mismo (0x5C68B0) el "login a la Lobby"
#         (opcode a afinar en vivo; aqui SOLO lo logueamos, es el siguiente eslabon)
#
# Framing (FASE 0):  [magic:u8][cmd:u8][len:u16 LE][payload]   len = tam del payload.
#   magic 0xFF = cmd normal ; magic 0xFE = cmd + 0x100.  Sin cifrado de transporte.
#
# Diseno: reactivo puro (el cliente habla primero, nunca mandamos handshake cmd 0x00).
#   Dos listeners en hilos: Login :48004 y Lobby :48005. Cada conexion parsea frames
#   completos de su buffer y despacha por (rol, cmd). Todo se loguea hex en ambos
#   sentidos -> sirve de oraculo junto al listener probe_login.py y a Frida trace_wire.py.
#
# CORRER:  python server_login2013.py           (Ctrl+C para parar)
#   No necesita admin (bind en 0.0.0.0). El cliente (R2Beat_local.exe, IP parcheada a
#   192.168.1.60) conecta solo cuando se lanza con  SN 192.168.1.60 48004 notoken.
#   ⚠ La IP es DHCP y cambia: si el cliente no conecta, verificar `Get-NetIPAddress` y
#   re-parchear el exe (foff 0x484D00) + este LOBBY_IP. Ver re/patch_ip.py.

# =================================================================================================
# ⛔⛔⛔ QUÉ ES "EL REFERENTE" — LEER ANTES DE USARLO COMO PRUEBA DE NADA
# =================================================================================================
# En este repo, en los comentarios y en `documentacion/CAPTURA_2026-09-02_GAMEPLAY.md`, se llama
# **el REFERENTE** al server de `<IP del referente>`, del que hay una captura de 5,2 MB con una sesión
# entera jugada contra él.
#
#   ⚠⚠ **ES OTRO SERVER PRIVADO, IGUAL QUE EL NUESTRO. NO es el oficial, NO es "el server real",
#      y NO es la verdad.** Lo aclaró anonimo03 el 2026-09-09 porque la etiqueta se estaba usando mal
#      — en 16 comentarios decía literalmente "el server real", y con eso cualquiera (yo incluido)
#      lo toma por autoridad.
#
#   ★ PARA QUÉ SIRVE: es **evidencia de lo que el cliente ACEPTA y DIBUJA**. Si algo funciona
#     allá, el cliente lo tolera. Nada más que eso.
#   ⛔ PARA QUÉ NO SIRVE: para decidir qué está BIEN. Ese server puede tener el código mal y andar
#     igual — está lleno de code caves — y el cliente perdona mucho.
#
#   ⇒ REGLA: **cuando el referente contradice al exe, manda el exe** (`taller/re2013/disasm.py`).
#     Y una decisión suya (qué valor mete en un campo) **no funda nada**: ubica el campo, no lo
#     define. Ya nos pasó con el `byMode = 0x10` del `FF4B`, donde el equivocado resultó ser
#     nuestro disector y no él — así que tampoco sirve para acusarlo de apuro.
# =================================================================================================

import socket, struct, threading, datetime, sys, os, time, json, random
import re                                                 # wing.txt (tabla de alas del cliente)
from . import shop_catalog                                       # Fase 0: catalogo de tienda (fuente de verdad)

# ★★★ LA CARPETA DE VERDAD, CAPTURADA ANTES DEL DISFRAZ — 2026-09-16.
#   La línea de abajo le pisa el `__file__` a este módulo para que finja ser el monolito viejo
#   (`server_login2013.py`, en la raíz) y las rutas relativas salgan de ahí. Es un puente de
#   compatibilidad de cuando se partió el monolito, y lo hacen NUEVE módulos.
#   ⚠ El precio es que `dirname(__file__)` **miente**: parece decir «la carpeta servidor/» y en
#     realidad devuelve la raíz. Ya me hizo leer mal el código una vez, buscando dónde vivían los
#     charts.
#   ⇒ Acá se guarda la buena ANTES de pisarla, para lo que sí vive junto al código.
_DIR_SERVIDOR = os.path.dirname(os.path.abspath(__file__))

__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original

# --- Config: donde vive NUESTRA Lobby (lo que anunciamos en RESP-2) ---
BIND_IP    = "0.0.0.0"
# ★★★ `R2_PUERTOS` — CORRE ESTE SERVER AL LADO DE OTRO SIN PISARLO (2026-09-05).
#   En el VPS ya vive el server del CBT en 48004/48005/48015/48025/48035. Para probar el nuestro
#   ahí **antes del switch** hace falta que use otros puertos, y no alcanza con mover el de login:
#   los CANALES son puertos propios y el cliente los saca del `FF02` que arma este mismo server.
#   ⇒ Un solo desplazamiento se aplica al login Y a los diez canales, así el cliente sigue solo.
#      `R2_PUERTOS=1000` -> login 49004 · canales 49005, 49015, …, 49095
#   ⚠ El cliente conecta al login por LÍNEA DE COMANDOS; los del lobby los aprende del FF02. Por
#     eso desplazar acá alcanza y no hay que tocar el cliente ni el launcher.
PUERTO_OFF = int(os.environ.get("R2_PUERTOS") or 0)
# ★ `R2_LOGIN_PUERTO` (26-sep): el login por separado de los canales. El exe entra SIEMPRE por el
#   48004 (el argv3 del launcher no es el puerto de conexión), pero los canales los anuncia el
#   server ⇒ con `R2_LOGIN_PUERTO=48004 R2_PUERTOS=1000` corre al lado de otro server que ocupa
#   los canales 48005… (el del cliente coreano) y el cliente 2013 igual lo encuentra.
LOGIN_PORT = int(os.environ.get("R2_LOGIN_PUERTO") or (48004 + PUERTO_OFF))
LOBBY_PORT = 48005 + PUERTO_OFF
# ⛔ El default apuntaba a `D:\R2Beat\…` — la carpeta del proyecto viejo, que en el VPS no existe.
#   `startserver.py` ya fija `R2_LOG`, así que sólo mordía a quien importara el paquete a mano…
#   y ahí escribía en la carpeta de sólo consulta (pasó: correr `pruebas/simular_cartel.py`
#   escribía en D:). Ahora el default cae al lado de este proyecto.
LOG        = os.environ.get("R2_LOG") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "servidor.log")

# ★★ 2026-08-06 — `R2_PUBLIC_IP`: LA IP QUE SE ANUNCIA CUANDO EL SERVER ESTA DETRAS DE NAT.
#   En el VPS de Oracle la instancia NO ve su IP publica: `getsockname()` (y `get_local_ip()`)
#   devuelven la PRIVADA de la VCN (10.0.x.x) porque el mapeo publico->privado lo hace la nube.
#   Anunciar esa privada en el RESP-2 manda al cliente a una direccion que no existe para el.
#   Con esta variable puesta, GANA sobre `getsockname()`. En local se deja sin definir y todo
#   sigue como estaba (cada cliente recibe la punta del host por la que llego).
PUBLIC_IP  = os.environ.get("R2_PUBLIC_IP") or ""

# ★★ 2026-08-06 — SESIONES (solo en el server publico; en local queda apagado).
#   El cliente 2013 manda `[usn:u32][vcode:u64]` en el FF01, y los dos salen de SU LINEA DE COMANDOS
#   (argv[1] y argv[2]). O sea que el launcher puede loguear por HTTPS, recibir el par y pasarselo:
#   el `vcode` funciona como TOKEN DE SESION de 64 bits y el server lo valida.
#   Sin esto, cualquiera que corra el exe a mano entra como el usn que se le antoje.
#   `R2_SESIONES` = ruta del json que escribe la API  ->  {"<usn>": {"vcode": N, ...}}
#   ★★★★★ EL LOGIN NATIVO (2026-09-05). Lo de arriba describía el mecanismo, pero estaba APAGADO:
#   `SESIONES_FILE` venía vacío ⇒ `sesion_valida` decía que sí a cualquiera. Ahora apunta al
#   archivo de ESTE proyecto, y lo escribe nuestro propio `launcher2013.py`.
#   Cómo funciona, de punta a punta:
#       1. el launcher sortea un `vcode` de 62 bits y lo anota en `sesiones.json`
#       2. lanza el juego con  `<exe> <usn> <vcode> <puerto> test:<ip>`
#       3. el juego manda `FF01 [usn:u32][vcode:u64]`  (12 bytes, sin usuario ni clave)
#       4. el server valida el par contra el archivo
#   ⚠ Si el archivo NO EXISTE se sigue dejando pasar a todos, para no romper el arranque a mano
#     del exe. En cuanto el launcher lo crea, la validación pasa a ser real. El log dice en qué
#     modo está en cada arranque.
# ★ 16-oct · SÓLO PRUEBAS: las canciones del cooperativo FIJAS («7603,7603,7603»), para que el panel QA juegue perfecto
#   con su plan (`_trabajo/qa/planes/`). Sin la variable (prod), el sorteo de siempre.
# ★ 16-oct · EL AVISO DEL NUEVO ANFITRIÓN (FF9B + FF13) TAMBIÉN EN CARRERA (anonimo03: «se rompe el cooperativo si un jugador
#   se sale» · «el gorila ya no se activa, lo pasan»). En el COOPERATIVO el gorila lo maneja el cliente del ANFITRIÓN
#   (MODO_COOPERATIVO_MAPA_CLIENTE.md §4); si se iba en carrera, el aviso se difería hasta volver a la sala («en el CBT eso
#   tumbaba al cliente») y los que quedaban seguían con el master del que ya no estaba ⇒ nadie manejaba al gorila.
#   MEDIDO con 6 clientes del 2013 (COOP_SE_VA_EL_ANFITRION.md): el FF13 en carrera no tumba a nadie y el cliente lo
#   pasa al juego (cGame::poner_master, vtable +0x30) ⇒ minijuego y CAPTURA. Lo de «tumbaba» era del cliente 2011.
#   R2_ANFITRION_EN_CARRERA=0 vuelve a lo de antes (diferido).
ANFITRION_AVISO_EN_CARRERA = os.environ.get("R2_ANFITRION_EN_CARRERA", "1") != "0"
CHASE_CANCIONES_PRUEBA = [int(x) for x in (os.environ.get("R2_CHASE_CANCIONES") or "").split(",") if x.strip().isdigit()]
SESIONES_FILE = os.environ.get("R2_SESIONES") or ""   # lo fija `startserver.py`; ver `sesion_valida`

# ── ★★ CUANTAS SESIONES VIVAS POR CUENTA (2026-09-12) ───────────────────────────────────────────
#   ⛔ Con UNA sola, abrir un segundo cliente de la misma cuenta **invalidaba al primero**, y el
#     primero se caia recien al CAMBIAR DE CANAL (que revalida) -> "estancado en cambio de canal".
#   ★ anonimo03 abre varios clientes de la misma cuenta para probar: es el caso normal aca, no un abuso.
#   ⚠ Acotado a proposito: sin tope, un launcher en bucle haria crecer la lista para siempre.
SESION_VIVAS = 4

SESION_TTL_H = 12                       # horas que vale un vcode antes de caducar

# ★★ TOLERANCIA `+10` — la trampa más cara del CBT, traída por las dudas.
#   Allá está MEDIDO que el cliente le SUMA 10 al token en cada re-login (`0x56FCB0`:
#   `add [config+0x1C8], 0xA`; en producción se vio 192 -> 202 -> 212 -> 222). Validando por
#   igualdad exacta, el primer login entra y **todo cambio de canal se rechaza** — y acá hay 8
#   canales, o sea que los re-logins son moneda corriente.
#   ⏳ EN EL CLIENTE 2013 NO ESTÁ CONFIRMADO: busqué ese `add …, 0xA` en todo el `.text` del
#     prístino y aparece UNA sola vez, en un offset que no tiene nada que ver. Puede que este
#     binario no lo haga, o que lo codifique distinto.
#   ⇒ Se acepta `vcode + 10*n` con `n` acotado. Si el cliente no suma, `n` es siempre 0 y esto no
#     cambia nada; si suma, no nos come el bug. Cuesta cero y evita un fallo intermitente.
#   Para MEDIRLO: entrá, cambiá de canal y mirá los 12 bytes del 2º `FF01` en el log.
SESION_PASO   = 10                      # de a cuánto puede crecer el vcode entre re-logins
SESION_PASOS_MAX = 64                   # cuántos re-logins se toleran antes de pedir otro launcher

# ============================================================
# ★★★ CANALES (2026-07-30) — LA ESCALERA REAL, SACADA DEL EXE
# ============================================================
# El cliente 2013 conoce **8 canales** y un filtro "todos". Los nombres son literales del
# binario (widgets del .rui):  Button_channel_{rookiechobo, rookie, starchobo, star,
# moonchobo, moon, sunchobo, sun} + Button_channel_all.  "chobo" (초보) = NOVATO.
#
# Quién puede entrar a cuál lo decide `0x486E90` = GetMyChannelCode(), que devuelve un
# CÓDIGO 1..8 mirando, EN ESTE ORDEN, las licencias y recién al final el nivel:
#     [player+0x8bb] -> 7   |  [player+0x83f] -> 6  |  [player+0x747] -> 5
#     ítem 0x0D      -> 4   |  ítem 0x0A      -> 3
#     nivel < 4      -> 8   |  nivel 4..10    -> 1  |  nivel >= 11 -> 2
# `0x5BA9B0` traduce ese código a un BIT del filtro de la lista de salas [obj+0x30]:
#     código 8->bit0  1->bit1  2->bit2  3->bit3  4->bit4  5->bit5  6->bit6  7->bit7
# y los bits, en ese orden, son los 8 botones de arriba. De ahí sale la escalera.
#
# ★ El `cat` (E7 de la entrada de RESP-2) NO es un número libre: `0x5C4C00` lo traduce por
#   un switch a un par (tier1 -> entrada+1, tier2 -> entrada+0x34), y `0x4A5F60` elige la
#   entrada a la que CONECTAR buscando la que matchea el código del jugador:
#     código 8 -> (t1=3,t2=7) · 1 -> (3,0) · 2 -> (*,2) · 3 -> (0,0)
#     código 4 -> (*,3)       · 5 -> (1,0) · 6 -> (*,4) · 7 -> (2,0)
#   ⇒ hay UN cat por canal, y es el de la tabla de abajo. Un cat que no matchea ningún
#   código = canal al que ese jugador no puede entrar.
#
# Como el CBT, cada canal es un PUERTO propio (48005 + i*10).
# (cat, tier1, tier2, código, clave del exe, nombre visible, puerto)
CANALES_2013 = [
    # ★ RESTAURADO 2026-07-31 para una prueba. Historia corta: se sacó de la lista y con una cuenta
    #   de nivel 1 el cliente **aterrizó en "Novato" pero NO marcó ningún canal** — como si quisiera
    #   mandarte a un canal que ya no está. Encaja con que `0x486E90` (el cálculo de banda del propio
    #   cliente) devuelva **banda 8 = Novato Principiante** cuando el nivel es **< 4**, y con el cartel
    #   del `string_lt/system.csv`: *"Solo usuarios de hasta el nivel 3 pueden ingresar al Canal
    #   Principiantes"*. ⇒ el canal existía en el diseño y cubre justo los niveles 1-3.
    #   ✅ DECIDIDO 2026-07-31: **se queda en la lista**, renombrado a **"Principiante"** (que además es
    #     como lo llama el propio cliente en `string_lt/system.csv`, línea 112). Sacarlo NO servía: el
    #     cliente lo sigue pidiendo mientras el nivel sea < 4 y queda apuntando a un canal inexistente.
    #   ⏳ Lo que SÍ queda por resolver es que desde acá se pueda llegar al canal **Libre** (tarea #22):
    #     en un server chico este canal está vacío y el jugador nuevo queda encerrado sin poder subir
    #     de nivel. ⚠ El original lo prohibía a propósito ("Libre desde el nivel 4"): es una desviación
    #     deliberada, no un bug a corregir.
    # ★★★★ SALA DE CHARLA — VA PRIMERA Y ES UNA SOLA (corregido 2026-08-05 contra un video del
    #   juego ORIGINAL que encontró el usuario). El orden y el nombre del retail eran:
    #       Sala de Charla · Principiantes · Novato · Novato estrella · Estrella ·
    #       Novato lunar · Luna · Novato solar · Sol · Libre
    #   ⛔ ANTES estaba MAL de tres formas, y las tres eran inferencias nuestras, no mediciones:
    #     1) iban DOS canales ("Conversación 1" y "2"). Salió de leer en la doc que la UI
    #        `createroom_chatroom.rui` tiene `Image_channel01`/`Image_channel02` y deducir "elige entre
    #        dos canales propios". El video muestra UNO. Los dos `Image_channel` serán otra cosa.
    #     2) iban AL FINAL de la lista, y en el retail va PRIMERA.
    #     3) el nombre llevaba tilde y el cliente la renderiza como `?` ("Conversaci?n").
    #        "Sala de Charla" es el nombre real y además esquiva el problema de codificación.
    #   ⚠ NO es un canal de juego: al elegirlo el cliente abre la pantalla de opciones (Multi juego),
    #     no la lista de salas. Eso lo hace el `cat 0x03` y es correcto.
    (0x03, 5, 0, 0, "chat",        "Sala de Charla",      48095),
    # ⚠⚠ EL 8 NO ES «UN CANAL MÁS» — medido en el exe el 2026-09-17. En la escala de licencias
    #   del cliente el **8 es la MÁS BAJA** (el que todavía no tiene ninguna), y está fuera de
    #   orden: la escala real es **8 < 1 < 2 < 3 < 4 < 5 < 6 < 7**. Por eso `0x484A00` lo trata en
    #   dos líneas aparte antes de comparar con `>=`, y por eso una sala con banda 8 **la ve todo
    #   el mundo** y **no dibuja ícono** (el sprite sólo existe para 1..7).
    #   ⇒ Si algún día se usa este `code` como banda de sala, tenerlo presente.
    #     Ver `documentacion/LICENCIA_DE_SALA_Y_SU_ICONO.md`.
    (0x63, 3, 7, 8, "rookiechobo", "Principiante",        48005),
    (0x01, 3, 0, 1, "rookie",      "Novato",              48015),
    (0x04, 0, 2, 2, "starchobo",   "Novato Estrella",     48025),
    (0x0F, 0, 0, 3, "star",        "Estrella",            48035),
    (0x05, 1, 3, 4, "moonchobo",   "Novato Luna",         48045),
    (0x0C, 1, 0, 5, "moon",        "Luna",                48055),
    (0x07, 2, 4, 6, "sunchobo",    "Novato Sol",          48065),
    (0x08, 2, 0, 7, "sun",         "Sol",                 48075),
    # ★★ CANAL LIBRE / TODOS (2026-07-30). Sale de la doc del CBT (`server-clean`, build_ff13_libre):
    #    allá el status **0x09** daba `campoA = 0xC` = CANAL LIBRE y liberaba el guard `[player+0x6d98]`
    #    = el selector de licencia de la sala de práctica (o sea: el picker SIN filtro de licencia).
    #    En el 2013 el mismo `cat 0x09` da **tier1 = 13**, y 13 no lo matchea NINGÚN código (1..8) ni el
    #    fallback por banda de `0x486F90` (que devuelve 0..3) ⇒ **se LISTA pero nunca se auto-elige**,
    #    que es justo lo que se quiere de un canal libre. `code=0` acá = "ningún código lo reclama".
    (0x09, 13, 0, 0, "all",        "Libre",               48085),
    # ★★ SALA DE CONVERSACIÓN (2026-08-05). El botón "Sala de Conversación" del menú "Multi juego"
    #    estaba APAGADO porque no publicábamos ningún canal de charla.
    #    MEDIDO (ver `docs\CANALES_ESPECIALES.md`): **`cat 0x03` -> tier1 = 5, tier2 = 0**, y el handler
    #    del FF02 deja `[roommgr+0x16E5] = 1` = "este canal es de charla". Con tier1 en [5..12]
    #    `0x4873F0` permite entrar **sin condiciones** (ni banda ni nivel), que es lo propio de una
    #    sala de charla.
    #    Van DOS porque la UI `createroom_chatroom.rui` tiene `Image_channel01`/`Image_channel02` con
    #    sus checks ⇒ la pantalla elige entre dos canales propios.
    #    `código = 0` (como Libre) = ningún código de nivel/licencia los reclama ⇒ **se listan pero el
    #    cliente NUNCA aterriza solo acá**; se entra únicamente por el botón.
    #    ⚠ Nadie duplica `cat` con los otros 9: el 0x03 estaba libre.
]
# ⛔⛔ DESCARTADO 2026-07-31: `cat 0x03` (tier1 = 5) para que "Principiante" pudiera entrar a Libre.
#   La idea venía de `0x4873F0`, cuya PRIMERA instrucción permite sin condiciones cualquier
#   `tier1` en [5..12] — y `0x03` es el único `cat` del FF02 que cae ahí. El permiso FUNCIONÓ (el
#   jugador de nivel 1 conectó a :48085), pero **`tier1 = 5` no es "un canal permisivo": es un canal
#   de tipo SALA DE CONVERSACIÓN**. El cliente no abre la lista de salas: abre el menú de charla.
#   Encaja con `createroom_chatroom.rui` (`Image_channel01/02`) del barrido de paks, y con el
#   `[roommgr+0x16E5] = 1` que ese `cat` setea en el handler del FF02.
#   ⇒ **No hay ningún `cat` que dé un canal NORMAL con `tier1` en [5..12]**: los que produce el FF02
#     son {0,1,2,3,5,13} y el único de la franja es el de charla. La vía server-side está agotada.
#   ⚠ Lección de método: se dio por resuelto mirando el LOG (conectó al puerto correcto) sin mirar
#     la PANTALLA. El puerto era el correcto y la experiencia no.
# ★★★ 2026-07-31 — LIBRE PASA A `cat 0x03` (tier1 = 5) PARA QUE ENTRE TAMBIÉN "PRINCIPIANTE".
#   Medido: con `cat 0x09` (tier1 = 13) el clic llegaba hasta la 3ª guarda y ahí moría —
#   `0x4A1D20` -> `default` -> `0x4873F0(player, 13)` devolvía 0 con una cuenta de nivel 1.
#   Leyendo `0x4873F0` quedó claro por qué, y es una sola línea:
#       cmp bl,0xd / jne .. / cmp al,8 / setne al    ⇒ para LIBRE: **permite a TODA banda MENOS la 8**
#   O sea que el cartel del `system.csv` ("Libre desde el nivel 4") está implementado como
#   "cualquiera menos Principiante", porque `0x486E90` da banda 8 justo cuando el nivel es < 4.
#   ★ LA SALIDA, en la PRIMERA instrucción de esa misma función:
#       mov bl,tier1 / sub al,5 / cmp al,7 / jbe -> `mov al,1; ret`
#     ⇒ **cualquier `tier1` entre 5 y 12 se permite SIN mirar banda ni nivel.** `cat 0x03` da tier1=5.
#   ⚠ `cat 0x03` además hace `[roommgr+0x16E5] = 1` en el handler del FF02 — efecto NO identificado.
#     Si aparece algo raro en el lobby, éste es el primer sospechoso.
#   ⚠ El "libre" de verdad (picker sin filtro) NO depende de esto: lo da el `FFC9` al conectar a
#     :48085, vía `0x58CEF0`. Cambiar el `tier1` no debería tocarlo — a verificar en pantalla.
#   ⏳ Y de paso quedó el muro entero al descubierto, por si sirve:
#       tier1=3 + tier2=7  -> exige nivel < 4  Y banda 8   (= Principiante)
#       tier1=3 + tier2!=7 -> exige nivel < 11 Y banda 1   (= Novato)
# ★★★ VUELTA A `cat 0x09` (2026-07-31, tras arreglar la guarda del socket de login).
#   `0x09` -> tier1 = **13** = la categoría LIBRE de verdad (`0x58CEF0`: cualquier byte no reconocido
#   -> 13). `re/canales_matcher_findings.md` §7 tiene la observación clave, hecha en su momento:
#       cat 0x09 (tier1=13) -> se veía **BLANCO / disponible**   ·   cat 0x01 (tier1=3) -> **GRIS**
#   ⛔⛔ POR QUÉ SE HABÍA ABANDONADO, Y POR QUÉ ESE DESCARTE NO VALÍA:
#     aquella corrida concluyó "con 0x09 el clic no hace nada" — pero en ESE momento **el clic no
#     hacía nada en NINGÚN canal**, porque lo mataba la guarda `[[0x9D43D8]+0x20420]` (= socket de
#     login abierto), que recién se arregló hoy. La medición estaba contaminada.
#     Y el razonamiento que la reemplazó se apoyaba en el comparador `0x4874E0`… que el propio §7
#     documenta como **NO LLAMADO** al abrir el diálogo ni al clickear. Doble motivo para revisarlo.
#   ⇒ con la guarda ya baja, `0x09` es el candidato correcto: es el único que el cliente pinta como
#     disponible, y es la categoría que de verdad significa LIBRE.
#
# ★ Historia de los otros dos intentos de hoy (para no repetirlos):
#   · `cat 0x01` -> (tier1,tier2) = (3,0). SE VE en la lista, pero al clickearlo sale
#     **"No puede ingresar a este servidor con su nivel"** (cartel 242): el `tier2 = 0` cae en el
#     **default** de `0x4A1D20` = `0x4873F0(player, tier1)`, y con tier1 = 3 (novato) contra la banda
#     del jugador el chequeo falla.
#   · ⛔ `cat 0x47` -> (0,6). El `tier2 = 6` es "permite siempre" en `0x4A1D20`… pero **DESAPARECE DE
#     LA LISTA** (medido). El alta sí ocurre (la rama llama a `0x4A9750` como todas), así que el canal
#     se registra pero el diálogo del lobby NO lo dibuja. Coherente con que la ruta que exige
#     `tier2 = 6` sea la de **OTRA pantalla** (la de CircleBattle, `0x4E11A0`), no la de este selector.
#     ⇒ **`tier2 = 6` NO sirve para un canal del lobby.** No reintentar con 0x48/0x49: misma rama.
#   · ✅ `cat 0x0F` -> (0,0) = la MISMA pareja que "Estrella". Se dibuja (tier2 = 0) y para entrar pide
#     lo mismo que Estrella, que es la banda MÁS BAJA de las clickeables ⇒ lo alcanza cualquiera de
#     estrella para arriba. Es lo más permisivo que se puede sin salir de las categorías que el
#     diálogo muestra.
#   ⚠ Va ÚLTIMO a propósito: comparte (0,0) con "Estrella" y el auto-selector del login toma el
#     PRIMERO, así que nadie aterriza en Libre sin pedirlo.
#   ⚠ El "libre" de verdad NO lo da la categoría: lo manda el server al conectar a :48085, con el
#     `FFC9` fuera de 1..8 -> `0x58CEF0` devuelve categoría 13 = LIBRE (picker sin filtro de licencia).
#   ⏳ ABIERTO: un jugador en banda NOVATO (3) sigue sin poder entrar a Libre.
# ★★★ POR QUÉ EL "LIBRE" LLEVA `cat 0x01` Y NO `0x09` (medido 2026-07-30, tras ver que el clic NO hacía NADA):
#   El botón de la lista de canales pasa por el comparador **`0x4874E0(banda_jugador, tier1_canal, 0)`**:
#       banda == tier1        ->  0  OK (tu propio canal)
#       banda == 3            -> -1  NO (el novato no sale de novato)
#       tier1 == 3            ->  1  OK ★ un canal con tier1=3 lo puede clickear CUALQUIERA
#       tier1  < banda        ->  1  OK (se puede BAJAR de banda)
#       tier1  > banda        -> -1  NO (nunca se sube)
#   y la banda del jugador (`0x4855B0`) SOLO puede ser 0,1,2,3. El `cat 0x09` da **tier1 = 13**, siempre
#   mayor que cualquier banda ⇒ **rechazado por construcción**: se lista pero el clic no hace nada y no
#   sale ni un paquete. ⇒ el canal "para todos" tiene que llevar **tier1 = 3** (`cat 0x01`).
#   ⚠ Va ÚLTIMO a propósito: comparte (3,0) con "Novato" y el auto-selector del login toma el PRIMERO.
#   El estado LIBRE de verdad se lo manda el server al conectar a su puerto: `FFC9` con un byte fuera
#   de 1..8 -> `0x58CEF0` devuelve la categoría 13 = LIBRE (el mismo 13, pero por la vía que sí funciona).
#
# ★★★ QUÉ ES EL `tier2` (`[entrada_canal+0x34]`) — TABLA COMPLETA (2026-07-31, del switch `0x4A1D20`).
#   NO es un número redundante: es el **TIPO de canal**, y decide QUÉ REQUISITO se te pide para entrar.
#   `0x4A1D20` es un `switch (tier2 - 1)` con 6 casos; el `default` cubre el resto:
#       tier2 = 1  ->  `0x487260(player, 0x3F)`  = exige un ÍTEM; si no lo tenés, cartel 243
#       tier2 = 2  ->  `0x486E90(player) == 2`   = exige CÓDIGO 2
#       tier2 = 3  ->  `0x486E90(player) == 4`   = exige CÓDIGO 4
#       tier2 = 4  ->  `0x486E90(player) == 6`   = exige CÓDIGO 6
#       tier2 = 5  ->  chequeos de CÍRCULO/CLAN (`0x49F7C0`/`0x49F7E0`) + `0x4872F0(player, tier1)`
#       tier2 = 6  ->  `mov al,1; ret`           = ★ SIEMPRE PERMITIDO, sin mirar licencia ni nivel
#       default    ->  `0x4873F0(player, tier1)`; si falla, cartel 242
#   ⇒ El `tier2` que sale de cada `cat` (ver tabla de arriba) NO se puede elegir libremente: viene
#     pegado al `cat` por el switch `0x5C4C00`. Los tier2 alcanzables hoy son {0,1,2,3,4,6,7};
#     **el 5 NO lo produce ningún `cat`** — coherente con que el 5 sea el tipo CLAN, que en el retail
#     probablemente se publicaba por otra vía (o no se usaba en esta build).
#   ⚠ `cat 0x47/0x48/0x49` dan `(tier1, tier2) = (0,6) (1,6) (2,6)` = canales SIN NINGÚN requisito.
#     Tentador para "abrir todo", pero ojo: saltea también el muro de banda que hoy nos protege.
#
# ★ Y de paso quedó claro el MURO REAL de Luna/Sol: la banda sale de `0x486F90` -> `0x4855B0`, que mira
#   un word de flags (>=0x100 -> 2 sol · >=0x10 -> 1 luna · si no 0 estrella) armado con los bytes
#   `[+0x83F]` y `[+0x747]` del blob de ítems/licencias del jugador. Sin esos flags la banda es 0 y los
#   canales Luna/Sol NO se pueden clickear. Escribir ese blob = lo que falta para la licencia REAL.
MULTICANAL = True                 # False = volver a la entrada única histórica (48005, cat 0x63)
CERRAR_LOBBY_EN_SWITCH = True     # ★★★ cerrar el socket del LOBBY al recibir el `FF3D` de cambio de
                                  #   canal. El cliente NO cierra solo: se queda en "conectando" hasta
                                  #   que la conexión vieja se cae. Ver el comentario en `handle_inner`.
CERRAR_LOGIN_TRAS_HANDOFF = True  # ★★★ cerrar el socket de LOGIN al terminar el handoff al lobby.
                                  #   Es lo que baja el flag `[[0x9D43D8]+0x20420]` del cliente, que
                                  #   `0x4A7020` exige en 0 para dejarte CAMBIAR DE CANAL. Ver el
                                  #   comentario largo en `handle_login` (cmd 0x02). False = volver
                                  #   al comportamiento viejo (login abierto, clic de canal muerto).
CANAL_PUERTOS = [c[6] for c in CANALES_2013]
# ★ El desplazamiento de puertos (`R2_PUERTOS`) se aplica también a los CANALES, y acá — no en la
#   tabla de arriba — para que la tabla siga leyéndose con los puertos "de verdad".
#   Sin esto, mover sólo el login serviría de nada: el cliente entra por el login y después salta
#   al puerto del canal que le dice el `FF02`, que sale de esta misma lista.
if PUERTO_OFF:
    CANALES_2013 = [c[:6] + (c[6] + PUERTO_OFF,) for c in CANALES_2013]

CANAL_POR_PUERTO = {c[6]: c for c in CANALES_2013}
CANAL_POR_CLAVE  = {c[4]: c for c in CANALES_2013}

# ── Tabla NIVEL↔EXP: se LEE DEL EXE (99 u32 en el VA 0x8782A0 = file offset 0x476EA0) ──────────
#   nivel = cuántos umbrales son <= exp. Es la MISMA tabla que usa el cliente para dibujar la barra,
#   así que server y cliente no pueden discrepar. Detalle: re/nivel_exp_umbrales.md
# ⛔⛔ ESTO APUNTABA A `D:\R2Beat\client\…` (2026-09-05). El server leía la TABLA DE NIVELES del
#   exe que vive en el proyecto VIEJO — la carpeta que es de sólo consulta y que en el VPS no
#   existe. Andaba de casualidad, en esta máquina.
#   ⇒ Y el fallo era SILENCIOSO del peor modo: sin ese archivo `cargar_umbrales_exp` deja la tabla
#     vacía y **todos los jugadores quedan en nivel 1**, con un `⚠` en el log y nada más.
#   Ahora apunta al prístino NUESTRO, que viaja en el repo. Comprobado: la tabla de los 99
#   umbrales es **byte-idéntica** en los dos (los parches no la tocan).
#   ⚠ UN SOLO `dirname`: arriba de este archivo, `__file__` se re-apunta A LA RAÍZ del proyecto
#     (ver la nota de la línea 37). Con dos, esto saldría de la carpeta.
EXE_CLIENTE   = os.environ.get("R2_EXE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "R2Beat", "R2Beat.exe.pristino")
# ★★ 2026-08-06 — LA TABLA SE MOVIÓ +8 CON LA BUILD DE SEPTIEMBRE Y FALLABA EN SILENCIO.
#   `0x476EA0` (VA 0x8782A0) era el offset de la build de MAYO. En la de septiembre la tabla está
#   en **`0x476EA8` (VA 0x8782A8)** — exactamente **+8**, el mismo corrimiento que tuvo la IP
#   horneada (0x484D00 -> 0x484D08) entre las dos builds.
#   Leyendo 8 bytes antes, el primer u32 era 0xFFF7A19C ⇒ el `all(v[i] < v[i+1])` daba False…
#   y la función **no logueaba nada** en ese caso ⇒ la lista quedaba vacía y `nivel_de_exp`
#   devolvía **1 para todo el mundo**, sin una sola línea de aviso. Ahora avisa siempre.
#   ★ DESEMPATE (0x476EA4 también pasa el test de "creciente", así que el test no alcanza): con
#     `0x476EA8` salen EXACTOS los cuatro números medidos EN PANTALLA el 2026-07-11 —
#     L1=500 · L30=348681 · L60=5289931 · L99=1431689882, y `exp 20000 -> nivel 5` con la barra
#     20000/21564. Con 0x476EA4 daba nivel 6 y ningún hito coincidía.
#   ⚠ Un offset fijo se rompe con cada recompilación. Por eso ahora, si el ancla no está donde se
#     espera, se BUSCA por contenido y se avisa en el log.
EXP_UMBRALES_OFF = 0x476EA8
ANCLA_UMBRALES   = struct.pack("<5I", 500, 3000, 7000, 11400, 16240)   # los 5 primeros umbrales

# ── ★ LICENCIA DERIVADA DEL NIVEL (bandas de canal) ───────────────────────────────────────────
# Calca el espíritu del muro de canal del CBT (Estrella 1-30 / Luna 31-60 / Sol 61+) pero abierto
# a los 8 escalones reales del 2013. (nivel_desde, clave del canal, byte de licencia del FFC9)
#   El byte del FFC9 va a [cRoom+0x9512]: 1=novato · 2/3=estrella · 4/5=luna · 6/7=sol.
#   ★★ Y el 3er valor es `LICENSE_VAL` = el u32 **@19 del MyRecord -> cfg+0x664**. Ese era el HUÉRFANO:
#      estaba clavado en 1000000 (=SOL) desde 2026-07-11, sin relación con el nivel. No es cosmético:
#      **`0x486E90` mira la licencia ANTES que el nivel**, así que una licencia mentida cambia tu CÓDIGO
#      de canal después de que llega el MyRecord, y el gate `0x4A1D20` (el que abre la escena de
#      MULTIJUGADOR) compara ese código contra el `tier2` del canal ⇒ **con la licencia mal, el botón
#      Multi deja de cambiar de escena, sin cartel de error.** Medido 2026-07-30.
#      Calibración conocida (probe 2026-07-11): 0 = sin licencia (el código sale del NIVEL) · 1 = estrella
#      · 1000000 = sol. ⏳ Luna y Sol-novato SIN CALIBRAR: valores de abajo = primera aproximación.
# (nivel_desde, clave del canal, byte de licencia del FFC9, LICENSE_VAL del MyRecord)
#   ⚠⚠ MEDIDO 2026-07-30: **el canal se elige ANTES de que llegue el MyRecord**, así que la licencia
#      @19 NO puede decidir a qué canal entrás — eso lo hace siempre el NIVEL. Y peor: si después la
#      licencia cambia el código, deja de coincidir con el `tier2` del canal al que ya entraste y el
#      gate del Multi te rechaza. ⇒ **la licencia @19 se manda en 0 (sin licencia)**: el código del
#      cliente queda siempre el del nivel, coherente con el canal, y la banda visible la ponen el
#      FFC9 y el NOMBRE del canal (que los elige el server). Es el muro server-side del CBT.
# (nivel_desde, clave del canal, byte de licencia del FFC9, LICENSE_VAL del MyRecord)
# ★★★ NIVELES REALES (2026-07-31): salen del propio cliente, del campo **+0x04 de cada misión** de
#   licencia (ver MISIONES_2013 más abajo). No son invento nuestro: el texto de cada misión los
#   imprime con `%d` ("- R2Beat carreras de nivel %d o superior"). Antes teníamos 21/31/46/61/81
#   inventados; los verdaderos son 20/30/40/60/70. `rookiechobo`/`rookie`/`starchobo` NO tienen misión
#   propia (no hay misión de "Novato Estrella"), así que esos tres siguen siendo estimación.
BANDAS_LICENCIA = [
    (1,  "rookiechobo", 1, 0),          # ⏳ estimado — sin licencia, el codigo lo pone el NIVEL (<4 => 8)
    (4,  "rookie",      1, 0),          # ⏳ estimado — sin licencia -> nivel 4..10 => codigo 1
    (11, "starchobo",   2, 0),          # ⏳ estimado — sin licencia -> nivel >=11 => codigo 2
    (20, "star",        3, 1),          # ✅ nivel del cliente (misión "LICENCIA Estrella"); licencia 1 -> :48035
    (30, "moonchobo",   4, 1),          # ✅ nivel del cliente ("Licencia Canal Novato Lunar")
    (40, "moon",        5, 2),          # ✅ nivel del cliente (misión "LICENCIA Luna");  licencia 2 -> :48055
    (60, "sunchobo",    6, 2),          # ✅ nivel del cliente ("Licencia Canal Novato Sol")
    (70, "sun",         7, 4),          # ✅ nivel del cliente (misión "LICENCIA Sol");   licencia 4 -> :48075
]
CANAL_FORZADO = None              # p.ej. "moon" para forzar Luna ignorando el nivel

# ★★★★★ EL ÍCONO DE CANAL EN LA LISTA DE SALAS — 2026-09-17, pedido de anonimo03.
#   El `L` de la fila del `FF6E` (offset 21+n) es **el código de canal que exige la sala**, y hoy
#   va clavado en 0 ⇒ ninguna sala muestra su canal.
#
#   ★ Lo dice el exe, no el referente. `0x49E44D` pasa el `L` por `0x484A00(L, mi_licencia)` y si
#     devuelve 0 **la sala no se agrega a la lista**:
#         if (L == 0)  return 1          ; sala sin restricción: la ve cualquiera
#         if (mi == 8) return (L == 8)   ; si YO soy 8, sólo veo las de 8
#         if (L == 8)  return 1          ; las de 8 las ve cualquiera
#         return (mi >= L)
#   ★★ Y los valores son **los `code` de `CANALES_2013`**: 0 libre · 1 rookie · 2 starchobo ·
#     3 star · 4 moonchobo · 5 moon · 6 sunchobo · 7 sun · 8 rookiechobo. Encaja con el exe por
#     los dos extremos (el 0 y el 8 los ve cualquiera, que es Libre y Principiante) y con el
#     censo del referente, que usa {0,1,3,4,5,6,7} y trata el 8 aparte.
#
#   ⚠⚠ ES UN FILTRO, NO SÓLO UN DIBUJO. Un `L` más alto que la licencia del que mira **le
#     esconde la sala**. Por eso: el valor sale del canal donde se creó la sala (que es el puerto
#     por el que entró su dueño, o sea gente que ya tiene esa licencia), y las salas sin canal
#     anotado quedan en 0 = visibles para todos.
#   ⇒ Si aparecen salas invisibles, ésta es la perilla.
#   ✅ PRENDIDA — el ícono aparece. Medido en vivo con anonimo03 el 2026-09-17: con `L=3` sale una
#     estrella amarilla pegada al «No.» de la sala.
#   ★★ Y el valor es **la banda que eligió el anfitrión** (`DIFICULTAD_SALA` / `dificultad_de`),
#     no el canal donde se creó: *"si el master lo tiene seleccionado en sol, afuera sale el icono
#     de sol en X sala"*. El dato ya lo teníamos; faltaba publicarlo.
#   ⏳ Y queda pendiente lo que pidió anonimo03 para después: el mismo byte **filtra** (`0x484A00`
#     esconde las salas que piden más licencia que la tuya), y él quiere que cualquiera pueda
#     entrar igual. Si molesta, se parchea esa función para que devuelva siempre 1: el ícono se
#     sigue dibujando y el filtro se cae.
#
# ★★★★★ LOS DOS CRITERIOS DE ACEPTACIÓN, dichos por anonimo03 y que NO se negocian:
#
#   1. **Al crear la sala, el ícono de la lista tiene que ser IGUAL a la licencia del creador.**
#      ✅ Hecho: el valor sale del `FFC9` que el propio server le manda al entrar a la sala (que
#         es su licencia, ver `lobby_salas`), y se anota ahí mismo. No se deduce del `exp` — se
#         probó y daba distinto de lo que muestra el picker.
#
#   2. **CUALQUIER usuario, incluso un novato, tiene que PODER VER la sala.** Lo que no debe poder
#      es ENTRAR: ahí va un popup de «no tenés la licencia necesaria». anonimo03: *"en el original
#      cualquiera podía ver X sala con X licencia; solamente si no tenías la licencia, al hacer
#      clic no podías entrar"*. Y su objetivo final va más lejos: *"queremos que las salas se
#      listen todas para todos… luego lo modificaremos para que de todas formas puedan entrar"*.
#      ⏳ PENDIENTE, y NO es `0x484A00` como creíamos. El filtro que esconde salas es **el panel
#         «Configuraciones de ingreso rápido» del propio cliente**: nos manda su máscara de
#         licencias en el `FF6E` C2S (2º byte de `filtros=3f 1f 01 01`: `7f`=siete marcadas,
#         `1f`=cinco) y **filtra él, localmente**. El server manda la sala igual — está en el log.
#      ⚠ Y de ahí sale la pregunta que decide todo, hoy en manos del agente: **¿el cliente filtra
#        por el MISMO campo que dibuja el ícono?** Si están acoplados, no hay forma server-side de
#        tener el ícono sin el filtro, y ahí sí hará falta el parche. Si son campos distintos, se
#        arregla sin tocar el binario.
#   ⛔⛔ APAGADA (2026-09-17) — y NO porque el ícono no funcione: funciona, anonimo03 lo vio.
#     Es que **el ícono y el candado son EL MISMO BYTE**, y la licencia del jugador la calcula el
#     cliente de su experiencia con **techo 2** (el sistema para otorgarla está sin conectar en el
#     exe). ⇒ Con `L ∈ 3..7` la sala **no la ve NADIE, ni su creador**. Prenderla hoy es dejar
#     salas invisibles.
#   ⇒ Se prende junto con el parche de 7 bytes que está medido en
#     `documentacion/LICENCIA_DE_SALA_Y_SU_ICONO.md` §6. Con ese parche, `L ∈ 1..7` dibuja el
#     ícono y ya no esconde nada: los dos criterios de anonimo03 cumplidos a la vez.
#   ★ Mientras tanto el dato NO se pierde: la banda de la sala se anota igual (ver
#     `lobby_salas`), y el **filtro por licencia** de abajo la usa. Sólo no viaja en el `L`.
#
# ⛔⛔⛔ CORRECCIÓN 2026-09-17 (tarde) — **EL PÁRRAFO DE ARRIBA ES FALSO Y EL PARCHE NO HACE FALTA.**
#   anonimo03 se negó a aceptar el negativo (*"no tomaremos ese camino; si hay forma serverside, sólo
#   no la conocemos"*) y tenía razón. Lo medido ese mismo día, en `LICENCIA_DE_SALA_Y_SU_ICONO.md`
#   **§5-ter**:
#     · el techo 2 **no existe**: `0x4884D0` prende el flag de la licencia **sin comprobar nada**,
#       y la función que se había analizado (`0x4885D0`) escribe **otro bit** — el 2, no el 1;
#     · el server ya tiene el cable: el bucle de nibbles del **campo E del login** (`0x48AC20`)
#       otorga el requisito `0x0100` con `nibble2 = 1` ⇒ **`mi` sube de 2 a 6** y con eso las
#       salas de banda 1..6 **se ven y dibujan su ícono**;
#     · y `cuenta+0x664` —que se había dado por muerto— lo **carga desde el paquete** el handler
#       `0x5E2D80`, que es la vía de las tres licencias restantes.
#   ✅ PRENDIDA (2026-09-17, «dale, implementalo entero»). Va junto con las dos perillas de abajo:
#     `LICENCIA_CLIENTE_AL_TOPE` sube el `mi` del cliente a 6, y `GATE_LICENCIA_AL_ENTRAR` pone el
#     popup del lado del server. Las tres son **un solo cambio**: prender ésta sola vuelve a
#     esconder salas. La prueba `probar_filtro_licencia.py` §4 no deja que se separen.
FF6E_CANAL_EN_LA_LISTA = True

# ★★★★★ EL TOPE DEL `L` QUE PODEMOS PUBLICAR — 6, y el 6 no es arbitrario.
#   `0x484A00` esconde la sala si `L > mi`, y el `mi` más alto que el server puede darle al cliente
#   es **6**: se otorga con el requisito `0x0100` (record 17), que es el único de los cinco de
#   licencia que el bucle de nibbles del login sabe armar (`nibble2 = 1`). Los otros cuatro piden
#   `0x0F01/0x0F02/0x0F04/0x0010`… y de ésos sólo `0x0010` sale de un nibble, pero da `mi = 4`.
#   ⇒ Una sala de banda **7 (sol)** con `L = 7` sería invisible para todos. Se publica con `L = 0`:
#     **se ve, pero sin ícono**. Es la única de las ocho que queda sin dibujo, y es preferible a
#     que desaparezca. ⏳ Sale del todo el día que se decida el parche de la §6.
#   ⚠ Medido y descartado: por `FF125` no se puede: las cinco misiones de licencia tienen
#     **mid = 0 en el propio cliente** (arg8 del ctor `0x492990`) y `0x489AE0` devuelve 0 con mid 0.
FF6E_CANAL_TOPE = 7                # ★ con el parche ya no hay tope: las siete se dibujan

# ★★★★★ EL FILTRO POR LICENCIA — «que funcione el botón de filtrar» (2026-09-17).
#   anonimo03 lo pidió con sus palabras: *"la sala desaparece como si hubiera usado el botón filtrar,
#   cuando no debería ocurrir eso **al menos que use la función filtrar**"*.
#   ★★ Y el cliente **ya nos manda su elección** en el último byte del `FF6E` C2S (la máscara de
#     las 7 casillas de licencia, `panel+0x466C`) **esperando que filtremos nosotros**. Nunca la
#     miramos: es una función nuestra que faltaba, no un parche.
#   ⚠ Rinde poco hasta que esté el parche: con licencia 2 el panel sólo deja tocar 1 o 2 casillas.
#     Se implementa igual porque es el comportamiento correcto y no cuesta nada.
#
# ⛔⛔ Y ESA MISMA TARDE ESTO ESCONDIÓ SALAS — el bug que anonimo03 vio: *"luna ya no ve la sala de
#   sol"*. Filtrábamos por los siete bits, pero el cliente **no le deja marcar** las casillas por
#   encima de su licencia (`0x4A1D2F`) ⇒ los bits altos vienen apagados SIEMPRE, y no son una
#   elección del jugador. El log lo decía: `mascara 0x1F: 1 sala(s) -> 0`.
#   ⇒ Arreglado en `lobby_salas._tope_de_casillas`: el filtro sólo mira los bits que el jugador
#     PUDO marcar. Con eso vuelve a valer lo que él recuerda del original: *"yo era luna y podía
#     ver las salas de sol, pero no podía entrar"*.
#   ★ Y cuando `mi` suba (ver el bloque de arriba), el tope sube solo y el filtro rinde de verdad.
FF6E_FILTRA_POR_LICENCIA = True

# ★★★★★ SUBIRLE AL CLIENTE SU PROPIA LICENCIA, PARA QUE VEA TODAS LAS SALAS — 2026-09-17.
#   El cliente esconde de la lista toda sala cuya banda sea mayor que **su** licencia (`0x484A00`),
#   y esa licencia se la calcula solo, de la experiencia, con tope 2 mientras no tenga marcado el
#   flag de ninguna misión de licencia. Por eso una sala de luna o de sol no la veía nadie.
#
#   ★★ LA VÍA ES NATIVA Y YA LA TENÍAMOS TENDIDA: el **campo E del login** lleva tres nibbles, y el
#     bucle `0x48AC20` del cliente hace `for i=1..n: otorgar(i << 4*grupo)`. Con `nibble2 = 1`
#     otorga el requisito `0x0100` —y **nada más**, es una sola vuelta— que es justo el del record
#     17 ⇒ `0x4863C0` pasa a devolver **6**.
#   ★★★ Y `0x4884D0`, que es quien prende el flag, **no comprueba nada**: ni nivel, ni los campos
#     que se creían necesarios. Ver `documentacion/LICENCIA_DE_SALA_Y_SU_ICONO.md` §5-ter.
#
#   ⚠ NO TOCA LA BASE. El nibble se sube **en el paquete**, no en `mision_nibbles`, así que
#     `paquetes.mision_para_icono` sigue leyendo el avance real del jugador ⇒ **el ícono de
#     licencia que se le ve al lado del nombre en la sala no cambia**. Son dos paquetes distintos
#     (login vs `FF0C`) y no se pisan. La prueba `probar_filtro_licencia.py` §5 lo vigila.
#   ⚠ Efecto visible aceptado: en el panel de misiones le va a figurar «Licencia Canal Novato Sol»
#     como hecha. Es cosmético y es el precio de que la lista de salas funcione.
#   ⚠ Y el popup «Su nivel no es adecuado» **deja de salir solo** (`0x4A84BD` usa la misma función)
#     ⇒ lo pone el server, abajo. Las dos perillas van juntas.
#
# ⛔⛔⛔ APAGADA EL MISMO DÍA, DESPUÉS DE PROBARLA. Y el motivo es la parte que importa:
#   anonimo03, luna, diez minutos después de prenderla: *"al ver mi info salgo como **novato sol**, al
#   canal que estoy cayendo es novato sol — yo era luna XD"*.
#   ★ `0x4863C0` **no es «la licencia para la lista de salas»**: es la licencia del jugador a secas,
#     y la consultan **más de veinte sitios**. Uno es `0x4A1640`, el gate de canales, cuya rama pide
#     `licencia == 6` ⇒ el cliente lo manda —y lo deja entrar— a NOVATO SOL.
#     Acá arriba el costo estaba anotado como «cosmético». Estaba mal medido: se contaron los tres
#     llamadores de `0x484A00` y no los veinte de `0x4863C0`, que era el que se estaba tocando.
#   ★★★ Y la razón de fondo, que agota la vía nativa: **el login sólo sabe pronunciar 2 de las 5
#     licencias.** Estrella, luna y sol piden `0x0F01/0x0F02/0x0F04` —dos nibbles a la vez— y el
#     bucle `0x48AC20` otorga de a un nibble. **No existe la combinación que diga «luna».** Por eso
#     al luna le tocó «novato sol»: es el escalón más alto que el login SABE decir.
#   ⇒ Se resolvió con los **tres parches** de `herramientas/aplicar_parches.py` (8 bytes), que no
#     tocan `0x4863C0` ni `0x484A00` ⇒ la licencia del jugador queda intacta.
#   ⏳ Si algún día se quiere volver a esto: sirve, pero sólo para un server donde a nadie le
#     importe que su licencia mostrada suba un escalón.
LICENCIA_CLIENTE_AL_TOPE = False   # ⛔ APAGADA: le corría la licencia a todo el mundo (ver arriba)

# ★★★★★ EL POPUP DE «NIVEL NO ADECUADO», AHORA DEL LADO DEL SERVER — 2026-09-17.
#   Al subirle el `mi` al cliente, éste deja de frenar la entrada él mismo. Lo frenamos nosotros, y
#   **con el popup ORIGINAL**: la tabla de respuestas del `FF11` (medida del disasm el 2026-08-05,
#   está en `lobby_salas.h_18_ff11`) tiene **`0x15` -> popup id 84 «Su nivel no es adecuado para
#   esta sala.»**. O sea que el jugador ve exactamente el mismo cartel de siempre.
#   ⇒ Se cumplen los dos criterios de anonimo03 a la vez: **ve la sala con su ícono**, y **si no tiene
#     la licencia, no entra y le sale el cartel**.
#   ★ La comparación replica `0x484A00` tal cual, incluido que el **8 es la licencia más baja** y
#     que `L = 0` y `L = 8` los ve (y entra) cualquiera.
#
# ⛔ APAGADA — y no por un problema: **es lo que anonimo03 eligió**, textual:
#   *"7 bytes, aceptar que cualquiera entre a cualquier sala"*. Es su objetivo declarado desde la
#   primera sesión del tema: *"luego lo modificaremos a nuestro antojo para que de todas formas
#   puedan entrar a cualquier sala de X licencia"*.
#   ⇒ El tercer parche (`0x0A78C5`) ya saltea el popup en el cliente, así que el candado del server
#     sería un rechazo que el jugador no entendería: ve la sala, hace clic, y lo echamos nosotros.
#   ★ El código de `_alcanza_la_licencia` **queda**, con su prueba: es la única réplica fiel de
#     `0x484A00` que tenemos, y devolver el candado es prender esta perilla y sacar ese parche.
#     Los tres parches son independientes a propósito, justamente para poder hacer eso.
# ★★ 29-sep — LA CONTRASEÑA DE SALA. anonimo03: *"que sólo funcione para los id de GM o streamers"*.
#   Los roles salen de los mismos archivos que el panel (`admin.txt`, `gm.txt`, `streamers.txt`,
#   vía `panel_admin.rol_de`). Al que no tiene rol la sala se le crea ABIERTA y se le avisa por chat.
#   Vaciarla (`()`) = nadie puede poner clave.
CLAVE_DE_SALA_ROLES = ("admin", "gm", "streamer")
GATE_LICENCIA_AL_ENTRAR = False    # ⛔ APAGADA a pedido: «que cualquiera entre a cualquier sala»
           # "L" · "A_alto" · "C" · "D" · "H" · "I"
# ★★★ CANAL LIBRE, SERVER-SIDE, UN BYTE (2026-07-30). `0x58CEF0` traduce el byte de licencia del FFC9
#   a CATEGORÍA de canal:  1/8 -> 3 novato · 2/3 -> 0 estrella · 4/5 -> 1 luna · 6/7 -> 2 sol ·
#   **cualquier otro -> 13**. Y 13 es el MISMO tier1 que produce el `cat 0x09` = LIBRE.
#   Es el mismo mecanismo del CBT ("status NO en {1..7} => campoA 0xC = canal libre", allá 12, acá 13),
#   pero allá hubo que cablearlo en el exe y **acá alcanza con mandar el FFC9 con un 9**.
#   En el CBT el canal libre liberaba el guard del picker de práctica (selector de licencia en sala).
# ★★★ MISIONES → LICENCIA (2026-07-30, pista del usuario CONFIRMADA en el código).
#   `FF81` (handler `0x5E30A0`) es el paquete de MISIONES/tutorial, y en `0x5E31A0` escribe
#   **`[player+0x335]` = progreso de misión**. Y el bucle que otorga licencias (`0x489103`) tiene una
#   rama: **si la máscara de la licencia está en {6,7,8}, se otorga cuando `mascara <= [player+0x335]`**.
#   ⇒ en el retail parte de la escalera de licencias se gana POR MISIONES, no por nivel.
#   Respuesta S->C (14B, mismo layout que el CBT): [A:u8][selector:u8][f3:u32][f4:u32][f5:u32]
#   con selector=0 y f3!=0 el cliente hace `[player+0x335] = A`.
PROBE_MISION_OFF = False          # ★ sonda de una corrida para ubicar el byte de mision
MISION_GRUPO = 0                  # nibble al que suma cada misión completada (0=grupo 1)
MYREC_MISION_OFF = None           # ⚠ APAGADO. 2079 es el offset que consume el read que alimenta
                                  #   [player+0x335], y el volcado del buffer del cliente CONFIRMA
                                  #   que nuestro 08 llega ahí... pero [player+0x335] termina en 242.
                                  #   Falta una medición más antes de dejarlo prendido: esa zona de la
                                  #   cola es la misma donde vive la biseccion de PUNTOS DE DESCANSO
                                  #   (REST_TEST/TAIL_U32_DELTAS) y no conviene escribirla a ciegas.
                                  #   Valor viejo (medido, sin confirmar el efecto): 2079           # ★ offset del byte de PROGRESO DE MISIÓN dentro del payload del
                                  #   MyRecord, MEDIDO con re/trace_myrec_mision.py. ⚠ el cursor del
                                  #   ring es ACUMULATIVO y el handler arranca en 4 (cabecera), así
                                  #   que el absoluto 2083 = **relativo 2079**. El valor sale de la
                                  #   DB: chars_db.json -> char["mission"], igual que el CBT
                                  #   (allá era el campo #64 -> player+0x331).
MISION_PROGRESO = 0               # ⚠ APAGADO: el push funciona pero llega TARDE (ver abajo) y sus

LIBRE_TIER_BYTE = 9               # byte del FFC9 fuera de 1..8 -> categoría 13 = LIBRE
FORZAR_CANAL_LIBRE = False        # True = mandar al jugador al canal LIBRE (se puede togglear con `.libre`)
LICENCIA_EN_LOGIN = True
MURO_POR_CANJE_DE_CAT = True 

LICENCIA_VAL_FIJA = None

# ★★ 2026-07-31: la MÁSCARA de licencia sale SÓLO de la DB (ganada por misión). NUNCA del nivel.
#   Las filas 20/30/40/60/70 de BANDAS_LICENCIA traen LICENSE_VAL 1/1/2/2/4, pero esos niveles son el
#   **requisito** de las misiones "LICENCIA Estrella/Luna/Sol" (campo +0x04 de la tabla del cliente),
#   NO una promoción automática. Derivar la máscara de ahí REGALABA la licencia al cruzar el nivel y
#   dejaba la misión correspondiente sin sentido (ya la tenías antes de hacerla).
#   ⚠ Esto NO toca la BANDA de canal: por nivel 20 la banda sigue siendo 'star' y el muro la alcanza
#     por canje de cat. Si se quiere que la banda TAMBIÉN espere a la misión, es otra perilla.
LICENCIA_SOLO_POR_MISION = True

# ★ licencia GANADA -> (clave de canal, byte del FFC9). En el retail la licencia la dan las MISIONES
#   (FF111), no el nivel: si el personaje ya ganó una, MANDA ESA y el nivel pasa a ser el respaldo.
LICENCIA_A_CANAL = {4: ("sun", 7), 2: ("moon", 5), 1: ("star", 3)}

# ★ Cats que el cliente entiende pero que NO son de la escalera (por si hacen falta):
#   0x03 -> (5,0) y ADEMÁS prende roommgr+0x16E5 = 1  (huele a canal de TORNEO: el exe tiene
#           "tournament channel lobby" en los textos de reglas)
#   0x47/0x48/0x49 -> (0/1/2, 6)   ·   0x1E -> lo agrega por OTRA función (0x4A94B0)
#   0x3D/0x3E/0x3F/0xA1/0xA2/0xA3 -> se PARSEAN pero NO se agregan a la lista (ocultos)

# --- Challenge del CmdLogin de la Lobby (handler cliente 0x5E2560) ---
# El cliente exige, en su cmd 0x02 de respuesta:  A ^ 0xCACB1112 == f(cfg),
# donde f(cfg)=0x485670 normalmente devuelve el token anti-tamper [cfg+0x90].
# => A = TOKEN_CFG90 ^ 0xCACB1112.  TOKEN_CFG90 se lee en vivo con Frida
# (re/read_token.py). Hipotesis inicial barata: token=0 -> A=0xCACB1112.
# Un challenge equivocado NO desconecta: solo dispara el dialogo de error del
# cliente ("LobbyServer : <CmdLogin> - ERROR"), asi que es seguro iterar.
CHALLENGE_XOR = 0xCACB1112
TOKEN_CFG90   = 0x44159589        # <-- [cfg+0x90] capturado por Frida EN EL HOST (re/read_token.py)
                                  #     => A = 0x44159589 ^ 0xCACB1112 = 0x8ede849b
# ★★★★★ 2026-08-05 — ESE NUMERO NUNCA FUE UNA CONSTANTE: VIENE DENTRO DEL PAQUETE DEL CLIENTE.
#   La hipotesis de arriba decia "constante entre sesiones, a validar", y quedo sin validar un año
#   porque el proyecto NUNCA corrio fuera de esta PC. La VM fue el primer testigo independiente y la
#   rompio: le mandabamos el `A` del host, el cliente lo rechazaba, y sacaba
#   "Imposible conectarse con el servidor. Redireccionando a otro servidor."
#
#   El server del CBT ya lo hacia bien y era cuestion de copiarlo (`server-clean.py`, cmd 0x02):
#       nic = <u32 del cliente> ^ 0xCCCCCCCC ;  respuesta = nic ^ 0xCACB1112
#   Los 4 bytes viajan en el FF02 de la lobby, justo ANTES de la MAC. No los veiamos porque el log
#   corta el payload a 48 bytes y caen mas alla.
#
#   ✅ VERIFICADO con los payloads reales de hoy, dos coincidencias exactas:
#       host  crudo=0x88D95945 -> nic=0x44159589 (== el TOKEN_CFG90 de arriba) -> A=0x8EDE849B (== el
#             que el server venia mandando, o sea el host no cambia en nada)
#       VM    crudo=0xC004A7E5 -> nic=0x0CC86B29 -> A=0xC6037A3B  (le mandabamos el del host)
#
#   ⇒ TOKEN_CFG90 queda SOLO como red de emergencia por si el payload no calza. Si se usa, el log
#     lo grita: fuera de esta maquina va a fallar.
CHALLENGE_XOR_CLIENTE = 0xCCCCCCCC     # con esto ofusca el cliente su challenge

# --- Cifrado del LOBBY (FF55/FF56) — CONFIRMADO = esquema 2011 (ver FASE4) ---
# El bloque de 256B que mandamos en RESP-4 es la tabla `pwd` que el cliente carga en
# el EncryptManager (+0x100). Con pwd=CEROS el cifrado se reduce a  out[i] = rv ^ plain[i]
# (rv = key & 0xFF). Verificado descifrando el wire real. B (RESP-4) y USN (RESP-1) = 0
# => key_base = (B+USN) = 0 => rv = counter. Contadores C->S y S->C separados (el cliente
# usa [sess+0x21b5c] para enviar, [sess+0x21b60] para recibir; ambos arrancan en 0).
PWD = bytes(256)                  # tabla de cifrado (ceros; = el bloque de RESP-4)
KEY_BASE = 0                      # (B + USN) con nuestros RESP-1/RESP-4 = 0
# ★ El `B` que mandamos en el RESP-4. La clave del cliente es `key_base = B + USN`, así que con B=0
#   la clave ES el USN -> **una clave por cuenta**, que es como el juego fue diseñado. Se lleva en
#   `st.key_base`, NO en esta constante, porque con varios jugadores cada conexión tiene la suya.
LOBBY_B = 0
PASO_HANDSHAKE = os.environ.get("R2_PASO", "") == "2"

# ============================================================
# Capa de cifrado del LOBBY (FF55/FF56) + MyRecord  (FASE 4)
# ============================================================
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL SOBRE `0x4E` — LA CAPA DE JUEGO (desensamblado + verificado 2026-08-05)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# El `0x4E` **no es un paquete de carrera**: es un SOBRE CRIPTOGRÁFICO que lleva otro comando
# adentro (handler `0x5E4BE0` -> descifra -> re-despacha por la misma tabla `0x203E8 + cmd*0x10`).
# El que viaja adentro es el inner **`0x26`**, y ése sí es el sincronismo de la carrera.
#
# ── Cifrado (`0x5C44D0`): XOR, **14 bytes FIJOS**, ignora el `size` declarado ──
#     dst[0:4]   = src[0:4]   ^ key        dst[8:12]  = src[8:12] ^ key
#     dst[4:8]   = src[4:8]   ^ key        dst[12:14] = src[12:14] ^ (u16)key
#     key = ([CNetwork+0x21B58] + [cfg+0x7C]) ^ contador   = (B + USN) ^ contador
#   O sea **la MISMA fórmula del FF55**: `key_base ^ contador`. Y el `B` no se escribe nunca ⇒ 0.
#
# ⚠⚠⚠ EL CONTADOR ES **COMPARTIDO** con el FF55 (medido: `0x4E`, `0x4F` y `0x55` usan todos
#   `[+0x21B60]` al recibir y `[+0x21B5C]` al mandar). ⇒ cada `0x4E` que entra o sale **corre el
#   mismo contador que el FF55**. Ésta es la explicación del viejo "salto de 20" que obligó a poner
#   una ventana de resync de 4096: no era ruido, eran los cientos de `0x4E` de la carrera.
#
# ── Segunda ofuscación, **sólo en el C->S** (`0x5C8730`) ──
#     wire_sub = sub ^ (u8)magic ^ 0xCA      wire_A = A ^ magic ^ 0xEF      wire_B = B ^ magic ^ 0xAB
#   con `magic` = el del FF25 LOADGAME. El handler S->C (`0x5CE9F0`) **NO des-ofusca**: usa los
#   valores crudos ⇒ es ASIMÉTRICO. El server des-ofusca lo que recibe y **releva EN CLARO**.
#
# ── Formatos ──
#     C->S: [FF][26][0A 00] [00][sub:u8][A:u32][B:u32]     = 14 B (el 00 inicial es constante)
#     S->C: [FF][26][09 00]     [sub:u8][A:u32][B:u32]     = 13 B, **sin** el 00
#
# ✅ VERIFICADO contra los 16 paquetes capturados en la partida de hoy: los 16 descifran a la
#    cabecera exacta `ff 26 0a 00`, y adentro aparecen los dos slots (2 y 3) y una serie de
#    flotantes crecientes (61, 176, 262, 345, 828, 895, 961) = la posición en la pista.
# ⚠ La regularidad "byte4 = complemento del byte0" que se vio primero NO era un checksum: los
#   bytes 0 y 4 del texto claro son `0xFF` y `0x00`, así que **asomaba la clave por los dos lados**.
FF4E_LARGO = 14                        # el cifrado es de 14 B fijos, pase lo que pase

# Offset del char_count en el MyRecord (reversado con trace Frida: read n=29, ra=0x5edb00).
MR_CHARCOUNT_OFF = 69
# ★ OWNED SONGS/STAGES del picker (MyRecord FF03). Loops del handler 0x5ED3C0 hallados por disasm+trace:
#   LOOP A (0x5edbfc): [u16 count] + u16 songid × count      (off 92 tras la lista de chars) = SONGS
#   LOOP B (0x5edc8b): [u16 count] + (u16 stageid)(u8 flag) × count                          = STAGES
# Calca CBT #32/#34 (server-clean.py). IDs reales del cliente 2013 = rnr_script.pak (music_lt/stage_lt).
# ★ IDs REALES extraidos de rnr_script.pak del cliente 2013 (music_lt.txt/stage_lt.txt, r2unpak).
#   50-55 = mission01-06.xml (canciones de MISION, filtradas del picker de sala -> NO usar).
#   Canciones REALES (no-mission, con File): 816. Stages validos (sin placeholder 100-103 ni centinela 25): 17.
# ★★★★★ 2026-09-01 — VACIADA. El picker no ofrece ninguna canción: es el punto de partida
#   para importar las del CBT. La lista original (769) está en
#   legacy/musica-2013-quitada/OWNED_SONGS_2013.json
#   ⚠ NO volver a llenarla con ids que no estén en el `music_lt` del cliente: el cliente
#     escupe "<CmdMyRecord> - Music Not Found:NNNN" por cada una y termina CRASHEANDO
#     (c0000005 en 0x005552C7). Medido el 2026-09-01 con 769 ids fantasma.
OWNED_SONGS_2013 = []
   # ★ FALLBACK. En el arranque lo REEMPLAZA la lista `owned_songs` de notes_map_2013.json = las 802
    #   canciones del 2013 que hoy tienen chart .bin en el CBT (ver la sección NOTAS más abajo). Esta lista
    #   literal quedó de cuando el índice se creía compartido: ofrecía 769 y 451 daban el chart equivocado.
# ★★ 2026-09-07 — +5 PISTAS DEL CBT: 58 Glitch Land · 63 ESTADIO PERU BOLIVIA · 66 Pista de Miku ·
#   94 AKB48 · 99 Abismo sin fin. Las eligió el usuario del catálogo con preview que arma
#   `pistas_del_cbt.py`, y las trajo `importar_pistas.py` (fondo + obstáculos + entrada <Bg> +
#   previews). Conservan su id original: el 2013 los tenía libres, así que no hubo que renumerar.
#   ⚠⚠ EL ORDEN IMPORTA Y ES ÉSTE: **primero el cliente, después esta lista**. El aviso de arriba
#     sobre las canciones vale igual acá — ofrecer un id que el `stage_lt.txt` del cliente NO tiene
#     es pedirle al cliente que cargue una pista inexistente. Si algún día se saca una pista del
#     cliente, se saca de acá PRIMERO.
#   ⚠ El `flag=0` es el mismo que el resto: no hay pistas "de pago" en este server.
OWNED_STAGES_2013 = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 19, 21, 22,
                     58, 63, 66, 94, 99]                # 23 stages validos (u16 stageid, u8 flag=0)
#   ★ 16-oct: + la 22 «Abismo semi oscuro», del muse (`herramientas/importar_semioscuro.py`; su versión de 12 la armó
#     `pista_ancha.py 22`). Es la 99 con las luces del camino: mismo track y obstáculos, otras texturas.

# ★ LAS PISTAS QUE TRAEN OBSTÁCULOS PROPIOS: `rnr_script/stage/backNNN.txt` en el `rnr_script.pak` del
#   cliente (contado el 2026-10-08). `.obstaculos N` sólo acepta éstas: pedirle al cliente un archivo que no
#   tiene es el mismo error que las canciones fantasma. Ver `documentacion/PISTA_OBSTACULOS_VICTORIA.md`.
OBSTACULOS_2013 = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 19, 20, 21,
                   22, 25, 58, 63, 66, 94, 99, 100, 101, 102, 103)
# ★ 09-nov — LOS «ALEATORIOS» SALEN SÓLO DE LAS PISTAS QUE SE CORREN. anonimo03 (lo reportaron jugadores): *«el modo
#   aleatorio está metiendo obstáculos que existen pero que no fueron integrados… casi no se usan»*. El sorteo era
#   sobre las 31 de arriba, y 9 (13, 17, 18, 20, 25, 100..103) traen `backNNN.txt` pero NO son ninguna pista que se
#   pueda elegir: restos del cliente que nadie armó para jugar. `.obstaculos N` y la ventana siguen aceptando las 31.
OBSTACULOS_DEL_SORTEO = tuple(o for o in OBSTACULOS_2013 if o in OWNED_STAGES_2013)

# ★ «ALEATORIA» (la pista 0, «Random» en `stage_lt.txt`) SE SORTEA EN CADA CARRERA (2026-10-08). anonimo03: *"que sirva
#   aleatoria"*. Hasta hoy el 0 se perdía en `seleccion_de` (`0 or DEFAULT_ROOM_MAP`) y se corría SIEMPRE la 11.
#   Las del sorteo: las que el cliente tiene, menos la 0 misma. Ver `salas.pista_de_carrera`.
PISTAS_DEL_SORTEO = tuple(p for p in OWNED_STAGES_2013 if p != 0)

# ── NOTAS (FF57 GET_NOTE_DATA) ──
# No tenemos charts propios: servimos los .bin del proyecto CBT-2011. Cada {songid}.bin =
# [BloqueA: count:i32 + count×(marker:i32,bpm:f32)] + zlib(notas 6B [Coord:u16][Kind:u8][Level:u8][Fx:u16]).
# El cliente NO infla el BloqueA (lee count crudo) y solo infla el B. Formato = ground-truth CBT (mismo engine).
#
# ★★ EL ÍNDICE NO ES COMPARTIDO (2026-07-29). Antes se asumía "mismo music_lt lineage => mismo songid",
#   y era cierto hasta que el IMPORT MASIVO del CBT (~2500 canciones, julio 2026) RENUMERÓ su music_lt.
#   Medido: de los 822 songids reales del 2013, 451 tenían .bin PERO era el chart de OTRA canción
#   (id 109 = "Beach Love" acá, "Sea Love" en el CBT) y otros 350 quedaban sin notas existiendo el chart.
#   Fallo SILENCIOSO: no crashea, simplemente las flechas no casan con la música. Ver memoria
#   r2beat-bin-indice-cruzado. FIX = traducir songid-2013 -> songid-CBT por el `File` del music_lt (la ruta
#   del .xml del chart: único en los dos catálogos y estable entre builds; el nombre NO sirve porque el
#   Latino traduce, y el Level tampoco porque se rebalanceó). Mapa en notes_map_2013.json.
#   ⚠ REGENERAR con  python server\gen_notes_map.py  cada vez que el CBT importe música o renumere.
# ★★★ 2026-07-31: LOS CHARTS SON NUESTROS, YA NO SE LEEN DE PROD (pedido del usuario).
#   Hasta hoy esto apuntaba a `D:\R2Beat\server\notes`, que es **la carpeta de notas de PRODUCCIÓN
#   del CBT (la del VPS)**: cualquier trabajo nuestro sobre charts podía romper el CBT en vivo.
#   Ahora el 2013 tiene su PROPIA copia (3550 .bin, 15 MB, verificada por md5), y prod queda
#   read-only para nosotros. ⚠ El precio es que la copia **no se actualiza sola**: cuando el CBT
#   importe música nueva hay que re-sincronizarla Y regenerar el mapa:
#       cp -r D:/R2Beat/server/notes/. "<proyecto 2013>/server/notes/"
#       python server\gen_notes_map.py
# ★★ VIVEN DENTRO DE `servidor/` desde el 2026-09-16 (antes estaban en la raíz). Pedido de anonimo03:
#   *"la carpeta notes debería vivir dentro de la carpeta server"*. Y no es sólo orden — el
#   documento de deploy tiene un capítulo que se llama **«lo que NO es .py y se olvida solo»**
#   justo porque el server leía datos de AFUERA de la carpeta que se sube. Adentro, esa clase de
#   error desaparece: se sube `servidor/` y va todo.
#   ⚠ Van con `_DIR_SERVIDOR`, no con `__file__`: acá arriba a `__file__` se lo disfraza de
#     monolito y apunta a la raíz. Ver la nota del principio del archivo.
#
# ⛔⛔⛔ Y LA RED, QUE ACÁ NO ES OPCIONAL — si el server no encuentra los charts, el cliente
#   **se auto-mata sin excepción ni log** al pedir una canción (el `FF57`, ver CHART_TECHO_4096).
#   O sea: el peor síntoma posible, provocado por el orden de un deploy.
#   Prod todavía los tiene en la RAÍZ. Si algún día se suben estos `.py` antes de mover los datos
#   —o si alguien vuelve atrás sólo el código— esta lista lo salva. Se va cuando prod esté migrado.
def _primero_que_exista(*rutas):
    for r in rutas:
        if os.path.exists(r):
            return r
    return rutas[0]        # el de `servidor/`, para que el error diga dónde DEBERÍA estar


_RAIZ_PROY = os.path.dirname(_DIR_SERVIDOR)
NOTES_DIR_2013 = _primero_que_exista(os.path.join(_DIR_SERVIDOR, "notes"),
                                     os.path.join(_RAIZ_PROY, "notes"))
NOTES_MAP_FILE = _primero_que_exista(os.path.join(_DIR_SERVIDOR, "notes_map_2013.json"),
                                     os.path.join(_RAIZ_PROY, "notes_map_2013.json"))

# ── MONEDA del MyRecord (rcoin/cash/seed) ──────────────────────────────────
# Viven en el PREFIJO de 69 bytes (hoy todo ceros). Los u32 del prefijo (por myrec_reads.txt):
#   off 1,5,9,13,19,23,28,36,40,46,51,55,59,65   (los u8/u16 son gender/strlens/counts -> NO tocar)
# Cual u32 es rcoin/cash/seed = PENDIENTE (FASE4 §3.1). Modo PROBE = centinela 1000000+off en cada
# u32 -> abrir tienda y leer que numero sale de rcoin/cash/seed (los 2 ultimos digitos = el offset).
PROBE_CURRENCY = False                # probe HECHO 2026-07-10: rcoin=@9, cash=@13 (seed no esta en el prefijo u32)
STORE_MAP = False                     # 1-login: centinela 0xF0000000|offset en CADA u32 escalar -> Frida escanea
                                      #   los destinos en memoria (re/trace_storemap.py). Anula currency/license/probe.
# ✅ PROBE APODO HECHO 2026-07-11: los 4 strings del prefijo (probe ALFA/BETA/GAMA/DELTA) ->
#   @27 = APODO (nick), @44 = GREMIO/círculo (guild). @45 y @63 = sin uso (vacíos).
#   Ahora build_prefix() sirve nick+guild desde la DB (char["nick"]/char["guild"]).
# ✅ STORE-MAP HECHO 2026-07-10: prefijo -> struct cfg contigua. record@off -> cfg:
#   @1=cfg+0x652 @5=+0x656 @9=+0x65a(RCOIN) @13=+0x65e(CASH) @19=+0x664(LICENCIA) @23=+0x668
#   @28=+0x66d @36=+0x675 @40=+0x679 @46=+0x67f @51=+0x684 @55=+0x688 @59=+0x68c @65=+0x692
#   Cola (rest points @1693 etc.) NO guarda crudo (se transforma). Seed = NO viene del MyRecord (otro paquete).
PREFIX_U32_OFFS = (1, 5, 9, 13, 19, 23, 28, 36, 40, 46, 51, 55, 59, 65)

# ★★★★★ SONDA FINA DEL PREFIJO (2026-09-02) — para encontrar la MONEDA GORILA.
#   El problema: la caja del gorila ya reparte la moneda y el server la PERSISTE
#   (`monedas_gorila` en la DB), pero el contador de la sala y el diálogo "Intercambio de Coin
#   de Gorila" siguen mostrando **0**: nunca se la contamos al cliente. Y la captura del server
#   de referencia no lo resuelve, porque en esa sesión el jugador tenía 0 monedas — todos los
#   campos candidatos viajan en cero y no se distinguen entre sí.
#   ⇒ mismo método con el que se encontraron rcoin=@9 y cash=@13, pero **sin romper el login**:
#   `PROBE_CURRENCY` reemplaza el prefijo entero por ceros+centinelas y se pierden apodo y
#   gremio; esto, en cambio, deja el prefijo REAL y sólo pisa los u32 que siguen sin mapear,
#   cada uno con un número reconocible a simple vista.
#   Uso: poner el dict, entrar UNA vez, mirar el contador de moneda gorila (arriba a la derecha
#   de la sala, o "Mi Coin" en el diálogo de intercambio) y ver qué número salió. Ese número
#   dice el offset. Después se vacía el dict y se sirve ahí `monedas_gorila` de la DB.
#   ⚠ Si el contador sigue en 0 con la sonda puesta, el dato NO viaja en el prefijo del
#     MyRecord y hay que buscarlo en otro paquete (candidatos del corpus: FF51 -> 5 B,
#     FF137 -> 2 B, FFAF -> 6 B; los tres se contestan hoy con ceros).
#   ✅ NO HIZO FALTA: la moneda gorila apareció comparando los MyRecord de la captura entre sí
#      (ver MONEDA_GORILA_ITEM). Queda la herramienta lista para el próximo campo huérfano.
SONDA_PREFIJO = {}                    # {offset: valor} — vacío = apagada

# ★★★★★ LA MONEDA GORILA = EL ÍTEM 540 DEL INVENTARIO (2026-09-02, sacado de la captura).
#   Cómo se encontró, porque el método vale más que el dato: el contador salía 0 aunque el
#   server ya persistía `monedas_gorila`. En la captura del server de referencia hay CINCO
#   MyRecord de la misma cuenta en distintos momentos; comparándolos byte a byte, entre logins
#   cambian **exactamente 3 bytes**: los de `@9 rcoin`... y un u16 en `cola+55` que va
#   **1 → 2 → 6 → 6**, monótono creciente y de a poco. El usuario lo describió igual: "tenía 3 o
#   5 y subía de a una cuando tenía suerte con las cajas".
#   Y al parsear la cola con nuestra propia estructura, ese u16 NO es un campo suelto: es el
#   **`count` de la 5ª entrada de la lista #37 de inventario**, cuyo `item_id` es **540**. El
#   `shop_lt.txt` lo confirma sin lugar a dudas:
#       <Item ShopIndex="0509" Index="540" Name="Monedas Gorila" ItemEffect="1444" ...>
#   ⇒ la moneda gorila no es una moneda aparte: es un ÍTEM, y la cantidad viaja en el `count`
#     de su entrada del inventario — el mismo campo que nosotros mandábamos siempre en 0.
#   ⚠ Ese `count` NO es "cargas" en general: está medido que para el Auto Impulsor (1000999)
#     mandar 30 ahí no mostró cargas. Por eso se llena SÓLO para este ítem.
MONEDA_GORILA_ITEM = 540
GENDER_OVERRIDE = None                # None = deriva de char_id (bit0). 0/1 = fuerza gender byte @0 (flag GACHA, NO visual)
CHARID_OVERRIDE = None                # None = char de DB. 130900=♂/130901=♀ @71 = GENERO VISUAL (confirmado 2026-07-10)
WORN_PREPEND_CHARID = True            # ★ vestido-en-login: worn=[char_id]+ropa (char_id como slot-1 cuerpo). Guía CBT.
POPULATE_INVENTORY = True             # ★ poblar loop de inventario del MyRecord (0x5edf34->0x48ffb0): registra
                                      #   ítems -> setea slots worn + inventario. Sin esto: render default + inv vacío.
# ★ formato REAL del ítem del loop de inventario (0x5eddd0): 11 bytes = [item_id:u32][F2:u32][F3:u8][F4:u16]
#   (medido con trace_reads: off1691 read(4)+off1695 read(4)+off1699 read(1)+off1700 read(2)).
#   F2 = marca permanente 0xeeffcbb8 (igual que 0x580580 en creación). F3/F4 = 0 (ítem nuevo -> 0x5c5890
#   devuelve -1 y registra sin importar F4). Ítem se registra vía 0x48ffb0 -> slot worn + inventario.
INV_F2 = 0xEEFFCBB8                    # duración/permanente
INV_F3 = 0
INV_F4 = 0
# ★ Fase B DISCOVERY: al comprar NO persiste (ítem sigue comprable en toda duración) y loguea el código de
#   período bien grande. Comprá el MISMO ítem en 7d/30d/permanente para mapear período->duración. Apagar tras mapear.
DISCOVER_DURATION = False             # ★ apagar tras mapear período->duración (Fase B mapeada 2026-07-11)
REFRESH_AFTER_BUY = True              # ★ tras comprar, reenviar MyRecord (FF03) para refrescar el panel de
                                      #   inventario en vivo (si no, el ítem auto-equipado no aparece hasta reloguear).
RESYNC_VENTANA = 4096                 # ★ cuantos contadores adelante se buscan al re-sincronizar el
                                      #   FF55 entrante (ver decrypt_container). Solo se paga en el fallo.
# ★★★★★ EL FF4E NO SE ADIVINA: SE DESPEJA — 2026-09-09.
#   ⛔ EL AGUJERO, medido en prod: **1364 sobres FF4E tirados de 4516 (~30 %)**. El FF4E es la capa
#     de JUEGO (posición, ítems, combo, el mono), así que perder 3 de cada 10 explica de una sola
#     vez el jugador que se ve congelado, el ítem que se activa tarde y la carrera que no cierra.
#     No es un bug del modo gorila: es de la carrera, y ahí se nota más porque todos tienen que
#     coincidir sí o sí.
#
#   ★ POR QUÉ FALLABA. El contador es UNO SOLO para todo lo que el cliente manda —lo tocan
#     **166 funciones** del exe— y se le desacomodó al server. `descifrar_ff4e` lo buscaba
#     probando `RESYNC_VENTANA` contadores **hacia adelante**. La huella del log dice que el
#     desacomodo **pasa los 4096**:
#         atraso 0..4095  -> se recupera, y LOGUEA `FF4E resync`
#         atraso 4096+    -> se pierde TODO y no loguea ni uno   <- prod: CERO resyncs
#     Y el `decrypt_ff55` no puede ayudar: con `PWD` en ceros valida **un solo byte**, así que da
#     por buenos **16 contadores** por ventana y nunca fija mejor que "módulo 256" (por eso todos
#     sus saltos de resync son < 256; el mayor medido fue 254).
#
#   ★★ EL ARREGLO. El sobre es XOR y los 4 primeros bytes del texto claro se conocen SIEMPRE
#     (`FF 26 0A 00`), así que la clave sale de una resta y el contador con ella:
#         clave = payload[0:4] XOR b"\xFF\x26\x0A\x00"   ;   ctr = clave XOR key_base
#     Un paso, exacto, y **sin ventana que se quede corta**. Medido en `probar_contador_compartido`:
#     0 perdidos con huecos de 1 hasta 50 millones, y ~3.290x más barato que el barrido.
#     De paso repara al FF55, que comparte el contador y solo no puede acomodarlo.
#
#   ⚠ LO QUE ESTO NO ARREGLA: **qué abre el hueco la primera vez**. Sigue abierto. El despeje no
#     lo necesita —el sobre siguiente vuelve a poner el reloj en hora solo— pero hay que buscarlo.
#   ⚠ Y el precio: el despeje **no valida nada** (la cabecera sale por construcción). Por eso el
#     contador solo se mueve si el salto es sensato; ver `FF4E_SALTO_MAXIMO`.
FF4E_DESPEJA_LA_CLAVE = True          # False = volver al barrido de antes (el interruptor ES el snapshot)
FF4E_SALTO_MAXIMO = 1 << 20           # si el contador despejado salta más que esto, se descifra igual
                                      #   pero NO se mueve el reloj: un sobre roto no nos desacomoda.
# ★★★★★ Y EL FF55 TAMPOCO ADIVINA — 2026-09-09, después de medirlo en prod.
#   ⛔ EL PROBLEMA. `decrypt_container` buscaba el CONTADOR entre 4096 candidatos, y **no puede
#     acertar**: el cifrado es `out[i] = pwd[i%256] ^ pwd[rv] ^ rv ^ plain[i]`, o sea que lo único
#     que interviene es **`rv`, de 8 bits**. Medido: para el contador 1000, descifran igual de bien
#     el 232, 488, 744, 1000, 1256, 1512… — **256 candidatos**, y el verdadero es indistinguible.
#     El barrido se quedaba con el más bajo ≥ `base+12`, y de ahí los aterrizajes en múltiplos de
#     256 que mataban al FF4E (que sí necesita el contador entero).
#
#   ★ LA HUELLA que lo delató, en prod: cadenas donde **cada resync arranca justo donde aterrizó el
#     anterior** y salta lo mismo:
#         RESYNC del contador: 14344 -> 14599 (salto de 254)
#         RESYNC del contador: 14599 -> 14854 (salto de 254)
#         RESYNC del contador: 14854 -> 15109 (salto de 254)
#     Entre uno y otro el reloj no avanza bien ni una vez ⇒ no hay ninguna fuga: **el rescate
#     acierta mal y su propio error obliga al siguiente**. Y se descartó con número la hipótesis
#     de que se escaparan sobres sin contar: líneas `?? cmd` en todo el log, **0**.
#
#   ★★ EL ARREGLO: resolver **`rv`** (256 valores, exhaustivo y exacto) en vez de adivinar el
#     contador entre 4096. El claro empieza SIEMPRE con `FF 56`, así que se prueban los 256 `rv` y
#     se exige que los DOS bytes den — con `PWD` en ceros queda uno solo. Descifrar deja de
#     depender del contador, y el contador deja de moverse a los saltos: avanza de a uno, y si el
#     byte bajo no coincide se corrige **dentro de su bloque de 256** (nunca más de 255).
#     ⇒ Ningún salto de 256. El FF4E sigue siendo el único que fija el contador de verdad.
#
#   ⚠ ESTO TOCA EL CAMINO DEL LOGIN ENTERO. Si se rompe, no entra nadie. Prueba propia:
#     `pruebas/probar_cifrado_del_lobby.py`.
FF55_DESPEJA_LA_CLAVE = True          # False = volver al barrido del contador (rollback sin git)
# ★★★★★ LA CONSOLA DE GM DEL CHAT — CERRADA POR DEFECTO (2026-09-09).
#   ⛔ EL AGUJERO: `comando_chat` es la consola de desarrollo del proyecto (`.npc`, `.cartel`,
#     `.salas`, `.map`, `.chase`, `.lic`, `.obs`) y **NO tenía ningún control**: cualquier jugador
#     que escribiera un mensaje empezado con `.` la tenía entera. En producción, desde siempre.
#     Lo pidió anonimo03: *"en prod quedó prendido el comando `.npc`, necesitamos apagarlo"*.
#     ⚠ Y `.npc` era el menos grave. `.cartel` saca el cartel de resultado **a media carrera**,
#       `.salas N` le inventa salas a TODO el canal, y `.map` fija la pista del próximo START.
#
#   ★ QUIÉN PUEDE, y por qué así:
#     · `R2_CONSOLA_GM` sin definir  -> **CERRADA** (lo que corre en prod)
#     · `R2_CONSOLA_GM=1`            -> abierta a todos (lo que usa el LOCAL, donde todas las
#                                       cuentas son de anonimo03 y la consola es la herramienta)
#     · `R2_CONSOLA_GM=7,42`         -> abierta sólo a esos `usn`
#   ⚠⚠ EL DEFAULT ES EL CERRADO A PROPÓSITO. Si algún día se despliega sin la variable, queda
#     cerrada — no abierta. Es la lección del `gender`: un default cómodo se vuelve el bug.
#
#   ★ SALVO `.oscuro`, que NO es de desarrollo sino del juego: lo pidió anonimo03 —*"el único que
#     debería quedar para todos los master es `.oscuro`"*— y ya se controla solo (adentro chequea
#     `anfitrion_de` y contesta "solo el anfitrion"). Y `.ayuda` va con él, para que el anfitrión
#     tenga cómo enterarse de que existe.
_CONSOLA_GM_CFG = (os.environ.get("R2_CONSOLA_GM") or "").strip().lower()
CONSOLA_GM_TODOS = _CONSOLA_GM_CFG in ("1", "on", "si", "sí", "todos", "true")
CONSOLA_GM_USNS = {int(_x) for _x in re.split(r"[,\s]+", _CONSOLA_GM_CFG) if _x.isdigit()}
# ★ `pd` entró acá el 2026-09-14: es del JUEGO, no de desarrollo — el anfitrión elige con qué
#   tabla de puntaje juega su sala (`.pd on/off`). Se controla solo por dentro, igual que
#   `.oscuro`: si el que escribe no es el anfitrión, contesta "solo el anfitrion" y no hace nada.
#   ⚠ La perilla de GM que ANTES vivía en `.pd` (inventar milésimas para probar el cartel) sigue
#     existiendo en `.milesimas` / `.decimales`, y ésa sí pide ser GM.
CONSOLA_SIN_GM = ("oscuro", "abismo", "pd", "score", "marcador", "reset",
                  # ★ `.obstaculos` (08-oct): cada jugador elige los SUYOS (ver salas.ELECCION_JUGADOR)
                  "obstaculos", "obstaculo",
                  "ayuda", "help", "?",
                  # ★ `.circulo` (24-sep): reemplaza a la web de los círculos. Cada subcomando se
                  #   controla solo (líder / jefe); la `sonda` pide GM por dentro. `circulos.py`.
                  "circulo", "círculo")   # los que NO piden ser GM
# ★★★ EL TERCER NIVEL: LOS COMANDOS DE OPERACIÓN (2026-09-14).
#   Hasta hoy había UNA sola puerta: o tenías la consola entera, o nada. Y como `.oscuro` y `.pd`
#   no son de desarrollo sino del juego, había que irlos metiendo a mano en la lista de arriba —
#   una lista de excepciones que iba a crecer hasta volverse un lío.
#
#   ⇒ Tres niveles, que es como lo tenía el CBT y por el mismo motivo
#     (`taller/estudio/J-operacion/06-comandos-gm.md`):
#
#       jugador / anfitrión   `CONSOLA_SIN_GM`  — del JUEGO. Se controlan solos por dentro
#                                                 ("solo el anfitrion") y van en prod.
#       GM                    `COMANDOS_GM`     — de OPERACIÓN. Piden estar en `gm.txt`.
#                                                 Van en prod, restringidos.
#       desarrollo            todo lo demás     — `.npc`, `.cartel`, `.salas`, `.map`, `.pulso`…
#                                                 Piden `R2_CONSOLA_GM`, que prod NO define.
#
#   ★★ Y LOS DOS EJES SON DISTINTOS A PROPÓSITO, que es la parte que se entiende mal:
#     `gm.txt` dice **QUIÉN**, `R2_CONSOLA_GM` dice **QUÉ ESTÁ CONSTRUIDO**. Un comando de
#     operación tiene que existir en producción y estar restringido; uno de desarrollo
#     directamente **no tiene que existir ahí**. Por eso ser GM NO abre los de desarrollo.
COMANDOS_GM = ("rate", "rates", "gm",
               # ★★ LOS ANUNCIOS — el `.gm1/.gm2/.gm3` del CBT (2026-09-15, pedido de anonimo03).
               #   Van acá y NO en `CONSOLA_SIN_GM` por lo obvio (hablarle a todo el server no es
               #   del jugador) y NO en desarrollo porque **tienen que existir en prod**: son la
               #   herramienta de operación para "reinicio en 10 minutos".
               "aviso", "anuncio", "gm1", "gm2", "gm3", "horn", "notice",
               # ★ la TIRA de anuncios del lobby (29-sep, `tira.py`): también es de operación
               "tira",
               "cartelgm", "csonda",
               # ★ SONDA DE LA CAMPANA (2026-09-15). El cartel del bono se leyó del cliente pero
               #   NO está confirmado en pantalla, y barrer subtipos reiniciando el server es
               #   como perdimos media tarde con el cartel de GM. Con esto se barre en vivo.
               "campana",
               # ★ `.autoplay` (2026-09-24): el autoplay escondido, prendido desde el server. Es una
               #   trampa a propósito, para probar bonos: por eso es de GM. Ver `AUTOPLAY_GM`.
               "autoplay",
               # ★ `.record` (2026-09-24): ver y EDITAR los contadores de las medallas, y la sonda
               #   del perfil. Edita la base: por eso es de GM. Ver `RECORD_Y_MEDALLAS`.
               "record")
# ★★ 04-oct — LOS STREAMERS TAMBIÉN ANUNCIAN. anonimo03: *"que los streamers también puedan usar el comando
#   .gm1 .anuncio"*. Son de `COMANDOS_GM` y se abren ADEMÁS a los de `streamers.txt` (el mismo archivo del
#   panel, `panel_admin.streamers`). ⚠ Sólo esos DOS, a propósito: `.aviso` (mismo comando que `.anuncio`),
#   `.gm2`/`.gm3`, `.tira` y `.rate` siguen siendo sólo de GM. Para darles otro, se agrega acá.
COMANDOS_STREAMER = ("gm1", "anuncio")

# ★★★★★ EL CARTEL DE GM (`FF46`) — ver el comentario grande en `chat.py`.
#   El itemcode es el que `rnr_script/notice.xml` usa para elegir el dibujo del cartel:
#       0         «공지사항»    aviso común
#       1         «작은 확성기»  megáfono chico
#       2         «큰 확성기»    megáfono grande
#       10000002  «GM 공지»     ★ el de GM — imgindex 20 = `gm_megaphone.spr`
#   ⚠ Que cada uno se vea distinto es lo ESPERADO, no lo medido: el CBT tenía tres colores y acá
#     hay tres dibujos. Se afina jugando, con `.horn <itemcode> <texto>`.
GM_NOTICE_ITEMCODE = {"gm1": 0, "gm2": 1, "gm3": 10000002}

# ⚠⚠ ARRANCÓ EN `False` A PROPÓSITO, y no era timidez: el layout estaba leído del disasm y **no
#   visto en pantalla**, y en este cliente un paquete mal armado no se queja — MATA al que lo
#   recibe (el `Ani` de 16 bytes ya nos tiró clientes). Un broadcast sin confirmar habría sido
#   tirar a TODO el server de una sola vez. Y de hecho el primer intento (`FF46`) **sí** tiró el
#   cliente de anonimo03: el freno hizo exactamente su trabajo.
#
# ▶ EN `True` DESDE EL 2026-09-15. anonimo03: *"el anuncio sólo lo veo yo, lo ideal es que sea
#   global"*. Ya no hay nada que confirmar: el cartel se vio en pantalla, y resultó ser el MISMO
#   `FF40 [0x12]` que mandamos para el cartel de pareja **desde hace días** — su riesgo no es
#   nuevo, es el que ya corríamos. Y el megáfono de los jugadores usa ese mismo camino a todos.
#   ★ `.aviso` NO depende de esto: es chat común y no puede romper nada.
GM_AVISO_A_TODOS = True

# ⛔⛔⛔ EL `FF46` QUEDA APAGADO — 2026-09-15, DESPUÉS DE TIRARLE EL CLIENTE A ANONIMO03.
#
#   Lo que pasó, en el log de local:
#       18:39:19   .gm1 'probando'  ->  FF46 mandado (sólo a él)
#       18:40:00   RX FF9E len=270 : 00 f3 1a 00 ... 74 8b 82 ...   ← punteros de Windows
#       18:40:00   cliente cerro
#   Ese "FF9E" **no es un paquete**: son 270 bytes de MEMORIA del cliente escupidos al morir.
#   41 s después del único paquete raro que le mandamos.
#
#   ★★★ Y LA CAUSA MÁS PROBABLE ES UN BYTE QUE FALTA. El cartel de pareja, que dibuja lo mismo, es:
#       FF40 [0x12][u32][str n1][str n2][u8 FLAG]     ← termina en un flag
#   y nuestro FF46 mandaba
#            [0x01][u32][str n1][str n2]              ← ⛔ SIN ese byte
#   ⇒ el cliente lee un campo que no está. Es **el mismo molde del `Ani` de 16 bytes**, que ya
#     nos tiró clientes: un paquete que "casi" tiene el layout no da error, corrompe y mata.
#
#   ⇒ NO se vuelve a prender hasta tener el paquete MEDIDO (no deducido). Con esto en `False`,
#     `.gm1/.gm2/.gm3/.horn` contestan que están apagados y **no mandan nada**.
#   ★ `.aviso` sigue andando: es chat común y no depende de esta perilla.
GM_CARTEL_FF46 = False

# ★★★★★ EL MEGÁFONO DE LOS JUGADORES — `FF40` sub `0x0B` (2026-09-15, pedido de anonimo03:
#   *"para los usuarios intentemos hacer funcionar los megafonos"*).
#   El cliente lo tenía entero —los ítems están en el catálogo y la tienda los vende— y el pedido
#   caía en «FF40 SIN handler». Medido con anonimo03 usándolos:
#       0b 01 00 00 00 [len][texto]    megáfono chico   (item 1)
#       0b 02 00 00 00 [len][texto]    megáfono grande  (item 2)
#       0b c8 00 00 00 [len][texto]    «agregar amigos» (item 200)
#   ⇒ el `u32` es el ID DEL ÍTEM, el mismo número con el que `notice.xml` elige el dibujo del
#     cartel. Ver `lobby_social.h_ff40_megafono`.
#   ⚠ El ítem SE GASTA. Un megáfono que no se consume es munición infinita.
# ★★★★★ LA TIENDA ABRE LOS PACKS — 2026-09-15, lo cazó anonimo03 comprando.
#   Compró *"5 megáfonos de agregar amigos"* y le quedó el **pack** (`486`, PackIndex=200,
#   PackCount=5) en vez de 5 unidades del `200`. Los que le había plantado a mano eran el `200`
#   suelto y ésos SÍ funcionaban: *"no están funcionando como los que plantaste"*.
#   ★ Y el log lo confirma por AUSENCIA: con el pack, al intentar usarlo **el cliente no manda
#     nada**. No lo considera usable.
#   ⚠⚠ Esto CONTRADICE una conclusión nuestra del 2026-07-31 (`catalogo.desempacar_pack`:
#     *"la compra siempre guardó el pack crudo, y es lo correcto"*). No era falsa: era PARCIAL —
#     vale para el auto impulsor, que se usa **siendo** un pack con cargas. Por eso esto es una
#     perilla: si algún pack se rompe al abrirlo, se apaga y vuelve el comportamiento viejo.
TIENDA_ABRE_PACKS = True

# ★★★★★ LAS FAMILIAS QUE SE GUARDAN CON CARGAS — 2026-09-15, lo separó anonimo03 comparando:
#   el pack de 5 mostraba su número bien, *"pero los otros 2 se muestran como si fuera un ítem
#   activado sin cargas"*. Ésos los había comprado SUELTOS, y a un ítem suelto lo guardábamos sin
#   `cant` — o sea con CERO usos. El pack andaba sólo porque el `PackCount` le ponía el número.
#   ⇒ Comprar un consumible suelto es comprar **una carga**. Y con eso, comprar otro SUMA, que es
#     lo que pidió: *"debería poder comprar más y acumular cargas tal cual hace el de 5"*.
#
#   ⚠⚠ LA LISTA ES CORTA Y EXPLÍCITA A PROPÓSITO. *"No vestible"* NO alcanza como regla: las
#     cápsulas del gacha tampoco son vestibles, tienen su propio camino y ya andan. Se agregan
#     familias **a medida que se prueben en pantalla**, no por deducción — que es el error que
#     ya cometí cuatro veces hoy.
#   ★ Las candidatas obvias para el día que se prueben: `coupon_buff` (Coin Up / EXP Up) y
#     `gift_levelup`. Hoy NO están: nadie las miró.
FAMILIAS_CON_CARGAS = ("megaphone",)

# ★★★★★ EL MyRecord MANDA LAS CARGAS DE LOS CONSUMIBLES — 2026-09-15, lo vio anonimo03 comprando:
#   *"al comprar no lista directamente cuántos usos tiene, ni el de 5 ni los otros 2 que compré
#   y son de 1 carga"*. El `count:u16` de la lista #37 iba **0 para todos** salvo la moneda
#   gorila, así que el cliente nunca sabía cuántos usos tenía nada.
#   ★ El dato ya se calculaba (`inv_cant`) y su propio comentario decía dónde iba. Faltaba usarlo.
#   ⚠ La ropa no se toca: no tiene cargas y no entra en `inv_cant`.
#   ⚠⚠ Un `count` de 0 el cliente lo lee como **1** (`0x5ED3D9: test ax,ax / jne / mov eax,1`),
#     así que un consumible agotado NO se apaga mandando 0: hay que sacarlo de la lista.
MYRECORD_MANDA_CARGAS = True

# ★★★★★ UN `FF69` POR CADA CONSUMIBLE AL ENTRAR — 2026-09-15, lo midió anonimo03 con dos capturas:
#   *"cuando lo uso por primera vez recién marca el contador de usos; sin usarlo, la primera
#   vista sale sin número"*. Al USAR le mandamos un FF69 y ahí aparece; al ENTRAR sólo le llega
#   el MyRecord y no aparece.
#   ⇒ **El cliente dibuja la cantidad desde el `FF69`, no desde el `count` del MyRecord.**
#   ★ Es la misma conclusión que ya estaba escrita para el saldo de monedas gorila
#     (`MONEDA_GORILA_POR_FF69`); lo que no sabíamos es que valía para TODOS los consumibles.
#   ⚠ Es idempotente (el FF69 FIJA, no suma), así que mandarlo de más no infla nada — a
#     diferencia del `count` del MyRecord, que el cliente ACUMULA.
FF69_CARGAS_AL_ENTRAR = True

MEGAFONO_ACTIVO = True
MEGAFONO_LARGO_MAX = 120          # ★ tope del texto: el cliente deja escribir, nosotros acotamos

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ LAS CAMPANAS — `FFA8` (2026-09-15, pedido de anonimo03: *"vamos a mapear otro item,
#   campanas de plata"*). Ver `documentacion/CAMPANAS.md`.
#
#   C2S  `FFA8 [u32 item][f32 x][f32 z][f32 rot]`   ← medido con anonimo03 tocándola:
#        `30 01 00 00 | 00 00 c8 c2 | 00 00 0c c3 | db 0f 49 40`
#        = ítem 304, parado en (-100, -140), mirando a π.
#   ★ Las tres coordenadas salen de `0x443BC0`, que le pregunta al mundo dónde estás y manda
#     (x, z, rot) — la altura NO viaja. Para nosotros son informativas: el cartel no las usa.
#
#   ★★ QUÉ HACE EL ÍTEM — no hay que adivinarlo, lo dice el propio cliente (texto 553/638):
#        «¡Hoy es su día de suerte! ¿Desea hacer sonar la campana? …
#          TODOS LOS USUARIOS EN LA SALA RECIBIRÁN EL BONO RCOIN.»
#     y alrededor están las tres reglas, también escritas:
#        640 «sólo puede usarse en la sala de juego»          ← la comprueba el CLIENTE
#        642 «los espectadores pueden usar la campana»        ← la comprueba el CLIENTE
#        639 «otro usuario ya hizo sonar la campana; intente  ← ★ ÉSTA ES NUESTRA
#             nuevamente luego de jugar un juego»
#
#   ⚠ El texto 639 dice «luego de jugar un juego», no «luego de N minutos»: la campana se
#     rehabilita **cuando la sala juega una canción**, no por reloj. Por eso el candado se abre
#     en el arranque de la carrera y no con un timer.
# ═════════════════════════════════════════════════════════════════════════════════════════════════
CAMPANA_ACTIVA = True

# ★ El cliente normaliza CUALQUIER variante a cuatro ítems canónicos. La receta está en
#   `0x430420`: pregunta `0x444060` («¿es de oro?») y `0x444080` («¿es de plata?») y después
#   arma el id con aritmética —
#        oro:   0xB5 + 2*(plus)   -> 181 / 183
#        plata: 0x130 - 7*(!plus) -> 297 / 304
#   que son exactamente los cuatro del `shop_lt`. O sea que el cliente ya sabe que son la misma
#   familia; nosotros sólo repetimos su tabla.
CAMPANAS = {
    181: ("oro",   False),
    183: ("oro",   True),
    297: ("plata", False),
    304: ("plata", True),
    774: ("oro",   True),      # «Campana de Oro S»  (ShopIndex 0600, de temporada)
    775: ("plata", True),      # «Campana de Plata S»
    778: ("oro",   True),      # «Campana de Oro Luminoso+»  (159b, 05-nov, ocultas: ver CAMPANA_PROPIAS)
    783: ("plata", True),      # «Campana de Plata Celeste+»
}

# ★★ LAS CAMPANAS CON MODELO PROPIO — 2026-11-05, pedido de anonimo03 con el diseño de su amigo: *"no reemplazarán,
#   se crearán como ítems nuevos, Show=0, mismo funcionamiento, única diferencia: pagarán un 50 % más"*.
#   {itemcode: factor del premio}. Dos diferencias con las de arriba, y nada más:
#     · se PLANTAN y se ANUNCIAN con SU código, no con el canónico (183/304). El cliente elige la malla por el
#       código (`0x444260` -> emoticon2 -> effectid -> roomfx), así que con el canónico saldría la campana vieja;
#       y el cartel lo elige `notice.xml` por el mismo código (ahí están los fondos nuevos).
#     · el consuelo, el gordo y el techo se multiplican por el factor.
#   ⚠ El `Hit` del final («fulano recibió N») el cliente lo cablea a 181/297: ése sale con el cartel de siempre.
#   Ver `documentacion/CAMPANAS_PLUS_NUEVAS.md` y `taller/campanas_plus/`.
CAMPANA_PROPIAS = {778: 1.5, 783: 1.5}

# ★★★★★ EL BONO — **LO DESCRIBE EL PROPIO ÍTEM**, y lo señaló anonimo03: *"su bono viene descrito
#   en el item"*. Está en `string_lt/item.csv`, indexado por el `ItemEffect` del `shop_lt`:
#
#     700  Campana de Oro    «…todos los jugadores recibirán Rcoin de Bono. (Max 5.000 Rcoin)»
#     701  Campana de Oro+   «… (Max 10.000 Rcoin)»
#     904  Campana de Plata  «Si hace sonar la campana de plata Y COMIENZA EL JUEGO, todos
#                             reciben bonus en RPOINTS. (Máximo 20.000 Rpoints)»
#     905  Campana de Plata+ «… (Máximo 40.000 Rpoints)»
#
#   ★★★ TRES COSAS QUE ESE TEXTO RESUELVE, y que yo había puesto mal:
#     1. **El oro paga Rcoin y la plata paga RPOINTS.** No es la misma moneda.
#     2. **Se paga «y comienza el juego»**, no al tocar la campana. anonimo03 lo vio antes que yo:
#        *"el cartel de quién recibió el bono salió antes; éste recién debe salir al final"*.
#     3. Los números son **máximos**, no fijos: el original repartía «hasta» eso.
#
#   ⚠⚠ Y HAY UNA CONTRADICCIÓN QUE **NO SE RESUELVE SOLA**: el texto 643 que dibuja el cliente
#     dice *«%s ha recibido %d de RCoin»* incluso para la plata, mientras que la descripción del
#     ítem dice Rpoints. Dos fuentes del mismo juego, distintas. Acá se sigue **la descripción
#     del ítem** (es la que promete el ítem al comprarlo) y queda la perilla para darlo vuelta
#     con una palabra.
#   ⚠ Ojo: `rpoint` se guarda en la base pero **el server no se lo manda al cliente en ningún
#     paquete** (ver `basedatos.db_add_rpoint`). O sea que hoy el bono de plata se acredita y no
#     se ve hasta que eso se cablee. El de oro sí se ve.
#   ⛔⛔ Y ACÁ ME EQUIVOQUÉ, CON LA RESPUESTA YA ESCRITA EN ESTE REPO. Puse la plata a pagar en
#     la columna `rpoint`… que **no la lee nadie**. Lo dijo anonimo03 de una línea: *"rpoint es EXP
#     corazón, lo pagamos en el modo gorila"*.
#     ★ Y `lobby_carrera` lo tiene documentado desde el **2026-09-10**, con el disasm y todo: el
#       «Rpoint» del juego es la EXPERIENCIA (`[jugador+0x2D0]`, que el 2019 llama `CmdSyncExp`),
#       y la columna `rpoint` quedó como resto muerto de cuando se guardaba ahí por error.
#     ⇒ Mismo bug, seis días después, en el mismo archivo. La nota estaba a cuarenta líneas de
#       donde escribí el mío.
CAMPANA_MONEDA = {"oro": "rcoin", "plata": "exp"}

# ★★★★★ EL BONO ES UN **RENGLÓN DEL CARTEL DE RESULTADO**, no un paquete suelto — 2026-09-15.
#   Lo dijo anonimo03 viendo que no se pagaba: *"es un bonus como el de pareja, o como el de joya de
#   amistad, pero ligado a la presencia del ítem en la sala"*. Y tenía el nombre esperándonos en
#   `rnr_script/bonus.xml`:
#
#       <bonus bonustype="67" type="3" … comment="플래티넘벨">     플래티넘벨 = «Platinum Bell»
#
#   ★★ Y el `type` de esa misma tabla cierra la discusión de la moneda. El comentario de arriba
#     del archivo dice: `type : 1-알코인, 2-allcombo, 3-알포인트, 4-대회보너스`
#     o sea **1 = Rcoin · 3 = Rpoint**. La campana de plata es `type="3"` ⇒ **Rpoint**, que es
#     exactamente lo que promete la descripción del ítem. Dos archivos distintos del cliente,
#     la misma respuesta.
#
#   ★★★★★ Y EL DEL ORO APARECIÓ EN **OTRA COPIA DEL MISMO ARCHIVO** — 2026-09-16. En el
#     `bonus.xml` del 2013 la entrada 55 está **sin comentario**; en el de la versión de Steam,
#     la misma entrada dice:
#
#         <bonus bonustype="55" type="1" x="640" y="-40" … comment="골든벨">   골든벨 = «Golden Bell»
#
#     y nuestra 55 tiene `type="1" x="640" y="-40"` **idénticos**: es la misma entrada, sin la
#     etiqueta. El cruce es sólido porque los dos archivos coinciden también en el 67
#     (플래티넘벨) y en el 71/72 (단짝, el amigo del alma), que ya teníamos confirmados.
#   ★ Y su `type="1"` = 알코인 = **Rcoin**, que es justo lo que promete la descripción del ítem
#     del oro. Dos archivos y dos versiones distintas diciendo lo mismo.
#   ⇒ Lección barata: **cuando un archivo del cliente no dice algo, buscar la MISMA tabla en las
#     otras copias antes de darlo por perdido.** Este repo tiene diez `rnr_script` guardados.
CAMPANA_BONUSTYPE = {"plata": 67, "oro": 55}

# ★ El techo que promete el ítem. Es DATO, no perilla: no se toca sin volver a leer `item.csv`.
CAMPANA_BONO_MAX = {
    ("oro",   False): 5000,
    ("oro",   True):  10000,
    ("plata", False): 20000,
    ("plata", True):  40000,
}

# ★★★★★ CÓMO SE REPARTE EL BONO — 2026-09-15, **dictado por anonimo03 de memoria del juego real**:
#
#     «sobre la cantidad, que sea 3000 4000 3500 *para los que no ganaron el bono*, y debemos
#      distinguir entre campana de plata normal y la plata+, que sólo ésta lleva el premio gordo,
#      y el premio gordo debe ir desde 25000 30000 35000 hasta 40000, siendo el drop rate más
#      común 25000 y el más raro 40000»
#
#   ⇒ Son DOS cosas distintas, no una:
#       · **el bono de consuelo**: lo cobra TODO el que jugó, siempre. Una banda chica.
#       · **el premio gordo**: UNO solo, y **sólo con la «+»**. Escalonado y con pesos.
#
#   ★★ Y con eso la «+» deja de ser «el doble del techo» (que era mi lectura literal de la
#     descripción) y pasa a ser **otra cosa**: la normal no tiene premio gordo. La descripción
#     del ítem no lo dice; el que jugó, sí. Cuando el dato de la cabeza de anonimo03 y mi lectura del
#     archivo se contradicen, gana el que jugó — el archivo dice el techo, no el reparto.
#
#   ⏳ EL ORO ESTÁ **DERIVADO**, no dictado: mismas proporciones sobre su propio techo (5.000 y
#     10.000 Rcoin, contra los 20.000/40.000 Rpoint de la plata). Nadie lo probó todavía.
# ★ El consuelo: **valores cerrados**, no un número cualquiera. anonimo03: *"usá cerrados 2500 3000
#   3500 4000, no uses valores como 2534 3152"*. Lo que se sortea es CUÁL de los cuatro, no un
#   número dentro de una banda — que es lo que hacía antes y se veía a la legua.
CAMPANA_BONO_BASE = {
    ("plata", False): (2500, 3000, 3500, 4000),    # ★ dictado
    ("plata", True):  (2500, 3000, 3500, 4000),    # ★ dictado
    ("oro",   False): (500, 750, 1000, 1250),      # ⏳ derivado, sin probar
    ("oro",   True):  (500, 750, 1000, 1250),      # ⏳ derivado, sin probar
}

# ★ El premio gordo: `(monto, peso)`. **Sólo las «+»**, y **es del que tocó la campana**.
#   anonimo03: *"el premio mayor se lo llevará el que toca la campana, los valores altos; los demás
#   sí, entre los valores bajos"*. El peso es la frecuencia — «el más común 25000, el más raro
#   40000».
CAMPANA_GORDO = {
    ("plata", True): ((25000, 50), (30000, 27), (35000, 15), (40000, 8)),   # ★ dictado
    # ★ Bajado a pedido de anonimo03 (2026-09-16) para poder abaratar el ítem: *"bajale un poco el
    #   gordo y conservá ese rango de precios para oro"*. Con el gordo en 10.000 el precio no
    #   podía bajar de ahí sin volverse un cajero — el que la toca la recuperaba él solo.
    #   ⇒ Techo 6.000 ⇒ la «Oro+» puede costar 7.000 en vez de 12.000 y sigue sin ser farmeable.
    ("oro",   True): ((3000, 50), (4000, 27), (5000, 15), (6000, 8)),
}

# ⏳ Los pesos exactos (50/27/15/8) son NUESTROS: anonimo03 dio el orden («25000 el más común, 40000
#   el más raro»), no la tabla. Es una curva decreciente razonable y nada más que eso.

# ★★★★★ **SÓLO LA «+» SACA EL CARTEL DEL BONO** — el del FINAL de la partida, no el del principio.
#   ⛔ Le leí mal la corrección a anonimo03 y apagué el que no era. Él dijo *"sólo las campanas+ se
#     anuncian con cartel"*, yo apagué el aviso de «fulano hizo sonar la campana», y tuvo que
#     aclarármelo: *"con los anuncios me refería a los anuncios de BONOS AL TERMINAR LA PARTIDA,
#     no a los anuncios iniciales de campanas tocadas — esos no tenían que quedar tapados"*.
#   ⇒ Tocar una campana **se anuncia siempre**, normal o «+».
#     Lo que sólo tiene la «+» es el **premio gordo** y el cartel del ganador al terminar.
#   ★ Y eso le da sentido a la diferencia entre las dos: la «+» no es «lo mismo pero el doble»,
#     es **la que reparte el premio gordo**.
CAMPANA_SOLO_PLUS_ANUNCIA = True

CAMPANA_BONO = dict(CAMPANA_BONO_MAX)    # el techo, para no pasarse nunca del que promete el ítem

# ★ Una campana por sala hasta que la sala JUEGUE (texto 639). Apagalo para poder probar en
#   cadena sin tener que jugar una canción entre tiro y tiro.
CAMPANA_UNA_POR_SALA = True

# ⛔⛔ ACÁ VIVIÓ `CAMPANA_MYRECORD_TRAS_USAR` (2026-09-17) — un MyRecord de ~6 KB después de cada
#   campanazo, para que el contador bajara en pantalla. **Se cayó el mismo día**: no arreglaba
#   nada y el que sí arregla es el `FF6A`. Queda la lección, que es lo que vale:
#     · el `FF69` **no asigna** un contador: `0x48F350` BORRA la fila del inventario y la vuelve a
#       crear. Al llegar a 0 eso resucita el ítem con 0 cargas, y el cliente lee 0 como 1
#       (`0x5ED3D9`) ⇒ queda dibujado y clickeable. Era nuestro propio fantasma.
#     · el `FF69` repinta con `mov ecx,[0x9314C4]` = **cLobby, clavado**: en una sala repinta el
#       panel del lobby. Por eso parecía "no redibujar nada". **Es un paquete de lobby.**
#     · ⛔ el parser del MyRecord **ACUMULA** las cargas (`0x48F3E0`: `rec.count = viejo + count`).
#       Hoy no se nota porque los `FF69` de refresco las re-asignan detrás — o sea que el `FF69`
#       está TAPANDO ese bug. ⚠ Si algún día se saca un `FF69` de refresco, hay que mirar si deja
#       un MyRecord suelto acumulando. Deuda anotada, no tocada.
#   ⇒ El mecanismo bueno está en `lobby_campana._avisar_cuantas_quedan`.

# ★★★★★ LOS DOS PAQUETES QUE FALTABAN — 2026-09-17. Pedido de anonimo03: *"empecemos con que baje,
#   y sigamos con que el ítem se desliste al tener 0 cargas — en el juego original el ítem
#   aparecía en el inventario sólo al tener cargas; al terminarse desaparecía"*.
#
#   El camino: el cliente 2019 nombra SIETE comandos de ítem y nosotros usábamos uno solo.
#   `taller/_analisis/reg19b.json` los numera, y los que ya mandábamos confirman el mapeo
#   (105=0x69 CmdGetItemCount ✔ · 168=0xA8 CmdUse ✔ · 169=0xA9 CmdGoldenBell ✔):
#
#        62 = 0x3E   CmdDelInventoryItem      <- BORRA el ítem de la lista
#       106 = 0x6A   CmdDecreaseItemCount     <- BAJA el contador
#
#   ★★ Y sus handlers RX ya existen en el exe 2013, los dos de cuatro bytes pelados:
#
#       FF6A  0x5D0F30 : lee [u32 item] -> `0x48FDA0` sobre el inventario  (Decrease)
#       FF3E  0x5CE940 : lee [u32 item] -> `0x48F870` sobre el inventario  (Del)
#
#   ⚠⚠ POR QUÉ EL `FF69` NO SERVÍA, que es la parte que costó: su handler (`0x5D0E00`) llama a
#     `0x48F5E0` = **SetInventory**, que ASIGNA el dato pero el redibujo que hace después es
#     sobre `[0x9314C4]` — el objeto del PANEL, que en la sala está cerrado. Los otros dos
#     trabajan sobre `[0x9314E0]`, el inventario que sí se ve. Tres funciones, el mismo objeto de
#     datos, y sólo dos repintan.
#   ⇒ Es otra vez [[leer-al-consumidor]]: teníamos bien medido QUÉ contesta el `FF69` y nunca
#     preguntamos si era el paquete que el cliente usa para CAMBIAR la lista. No lo es.
#
#   ★ El orden importa: primero el `FF6A`/`FF3E` (que repintan), y DESPUÉS el `FF69` con el
#     número real. Así el dibujo lo pone el que sabe repintar y el valor exacto lo fija el que
#     no se desincroniza — el `FF6A` resta 1, no asigna, así que solo se iría de menos.
CAMPANA_DESCUENTA_EN_PANTALLA = True

# ★★★★★ LAS CAMPANAS TIENEN SUS PROPIOS COMANDOS — y los nombres los puso el CLIENTE 2019.
#   ⛔ Primero mandé el cartel por el `FF40` sub `0x3A`: salió **«Círculo <cuenta_admin> llegó al nivel
#     1»** (es el aviso del círculo). Después por el `FF40 0x12` del megáfono, con el itemcode de
#     la campana: ahí sí salió **el cartel correcto, pero con los datos mal** — el número de sala.
#   ★★★★★ La respuesta estaba en el cliente 2019, que trae su tabla RX **con los nombres**
#     (`taller/_analisis/reg19b.json`). Ahí las campanas tienen SIETE comandos propios:
#
#         0xA8  CmdUse                  <- el que RECIBIMOS. «usé este ítem», no «la campana»
#         0xA9  CmdGoldenBell           0xC3  CmdPlatinumBell          plantar la campana
#         0xAA  CmdGoldenBellNotifer    0xC4  CmdPlatinumBellNotifer   el cartel
#         0xB4  CmdGoldenBellHit        0xC5  CmdPlatinumBellHit       «fulano cobró N Rcoin»
#
#   ⇒ El cartel de la campana **nunca fue el del megáfono**. Ése dibujaba porque el `u32` cae en
#     la misma tabla de `notice.xml`, pero le faltan los campos (la sala) y le sobra el texto.
#   ★ En el 2013 los cinco handlers existen y encajan: A9->0x5D6AD0, C3->0x5DD200 (idénticos
#     salvo `push 0x47`='G' contra `push 0x50`='P'), AA=C4->0x5DD2C0, B4->0x5D79F0, C5->0x5DD350.
#
#   ⏳ El `u32` del final del `spawn` va a un global (`[0x9314C0+0x13038]`) y no sabemos qué es.
#     Arranca en 0; la sonda `.campana` lo barre sin reiniciar.
CAMPANA_SPAWN_EXTRA = 0

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ⏳ EL SYNC DE POSICIONES — `FFF5` (2026-09-16, pedido de anonimo03 «si es que es fácil»)
#
#   ⛔ EL SÍNTOMA: *"cuando alguien entra a la sala, éste no mira las posiciones pasadas de los
#     usuarios hasta que se muevan … el que entra ve las campanas una encima de la otra"*.
#   ★ Y la causa está medida: `0x444260` **NO usa las coordenadas que mandamos** en el `plantar`.
#     Las pide él, con `0x595070(&vec, slot, &rot)`, a un mapa **suyo** de asiento -> posición. Si
#     ese mapa está vacío —y en el que recién entra lo está— devuelve `(0,0,0)` y **todas las
#     campanas caen en el mismo punto**. (Comprobadas las DOS ramas de `0x444260`: ninguna usa el
#     vec3 del cable.)
#
#   ★★★ EL VEHÍCULO EXISTE y el 2019 le puso nombre: `FFF5` = **`CmdCurrentActionObject`**.
#         S2C   FFF5 [u8 count] + count × [u8 slot][f32][f32][f32][u8 acción]
#       El handler (`0x5DB900`) limpia el mapa, mete una entrada por cada uno y lo cierra.
#
#   ⚠⚠ LO QUE FALTA ES EL DATO, y eso sí está medido: **el cliente nunca nos manda su posición**.
#     En una sesión entera lo único de alta frecuencia que sale de la sala es `FF00` (vacío, 38
#     veces) y `FF3D` (UN byte, 53). Ni un stream de movimiento. O sea que un sync de verdad hoy
#     no se puede armar: no tenemos de dónde sacar dónde está cada uno.
#
#   ⇒ SALVO PARA UNO: **el que tocó la campana**. Su `FFA8` trae `(x, z, rot)` — exactamente los
#     tres floats que el `FFF5` quiere. Así que del único jugador cuya posición importa para este
#     bug, sí la sabemos. Eso es lo que hace esta perilla.
#   ⏳ Es un EXPERIMENTO: el orden de los tres floats y el byte de acción salen del desensamblado,
#     no de una captura. Si los avatares aparecen en lugares raros, se apaga y listo.
SYNC_POSICION_AL_ENTRAR = True
SYNC_POSICION_ACCION = 0        # ⏳ el u8 del final; sin medir, arranca en 0

# ⏳⏳ EL ITEMCODE DEL CARTEL: ¿el «+» o el base? — 2026-09-15, sin resolver.
#   anonimo03, con el cartel en pantalla: *"sale en texto del cartel de plata «la campana de oro»
#   cuando toqué la de plata"*. O sea que **el DIBUJO salió bien (plata) y el TEXTO salió mal
#   (oro)**: son dos búsquedas distintas dentro del cliente y sólo una acertó.
#     · el dibujo sale de `notice.xml` por itemcode -> 304 = imgindex 19 = plata ✅
#     · el texto sale de la LETRA (`byte [edi+9]`), y `edi` lo reescribe `0x430420` con
#       aritmética (`0xB5 + 2*plus` si «es de oro») antes de buscar. Ahí se perdió.
#   ★ La pista que sí es dura: **el propio cliente, en su `Hit`, cablea siempre el código BASE**
#     — `push 0xB5` (181, no 183) y `push 0x129` (297, no 304). Nunca usa el «+».
#   ⇒ Con `True` mandamos el base (lo que hace el cliente). Con `False`, el «+».
#     Se confirma en pantalla con `.campana cartel 297` contra `.campana cartel 304`.
CAMPANA_CARTEL_BASE = True

# ★★★★★ CONSUMIBLES SUELTOS **POR ÍTEM**, no por familia — 2026-09-15.
#   Las campanas son `coupon_buff` en el `shop_lt`, la misma familia que los cupones de Coin Up y
#   EXP Up. Y `coupon_buff` está FUERA de `FAMILIAS_CON_CARGAS` a propósito: *"se agregan familias
#   a medida que se prueben en pantalla, no por deducción"*.
#   ⇒ Meter la familia entera para que anden las campanas sería exactamente el atajo que esa nota
#     prohíbe: arrastraría los cupones de EXP, que nadie miró y que se compran por DURACIÓN
#     (P30), no por cargas. Así que se abren **los seis ítems medidos y nada más**.
#   ★ El síntoma que arregla, del log de anonimo03 de las 21:13:52:
#         FF2A BUY item=304 fam=coupon_buff -> result=2   («ya lo tenés»)
#     Los packs (x5 / x10) sí entraban, porque el pack se abre por otro camino. La campana
#     suelta no se podía comprar dos veces.
#   ★ + el Cupón Coin Up (1200033): se gasta de a una carga por carrera (ver `CUPONES_PREMIO`).
#     Sin esto, comprarlo SUELTO lo guardaba sin cargas (los packs sí, por su PackCount).
ITEMS_CON_CARGAS = tuple(CAMPANAS) + (1200033,)

# ★★★★★ LOS SEIS SOSPECHOSOS DEL AVISO DE GM — 2026-09-15. Ver `documentacion/AVISO_DE_GM.md`.
#
#   La idea de buscarlos fue de anonimo03: *"revisar en el exe y comparar con el 2019, quizá está
#   señalado así como los ítems de usuario, los comandos de game master"*. Y lo estaba: el
#   cliente 2019 lleva los nombres de sus comandos como cadenas, y ahí aparece
#   **`CNetwork::CmdSystemNotice`**, cuyo handler (`0x00D304E0`) lee:
#
#       1 byte          un tipo
#       2 bytes         ★ EL LARGO DEL TEXTO (u16)
#       <ese largo>     ★ EL TEXTO
#
#   ★★★ Un largo de DOS bytes es **texto libre y largo** — justo lo que el `FF46` no podía llevar.
#
#   ⚠ Los nombres NO están en el binario del 2013, así que no se cruza por nombre. Se cruza por
#     **firma**: barriendo sus 241 handlers en busca de *"el largo de un string sale de un u16"*
#     quedan 13, y estos SEIS están pegados en memoria — y justo al lado del `FF97` (Notice, la
#     hora del server, `0x5C5710`). Toda esa zona del binario es la de los avisos.
#
#   ⇒ Se prueban UNO POR UNO con `.avisogm <n> <texto>` y Frida enganchado. El que lea
#     `[u8][u16][texto]` es el bueno. Es medición, no deducción — que es el error que ya cometí
#     tres veces hoy con este mismo asunto.
GM_CANDIDATOS = (
    (0xAD,  0x5C5810),
    (0xCF,  0x5C58B0),
    (0x107, 0x5C5900),
    (0x110, 0x5C5970),
    (0x134, 0x5C5980),
    (0x142, 0x5C59C0),
)

# ★★★ LOS RATES DE EVENTO — los mueve un GM con `.rate exp 2.0` (2026-09-14)
#   Multiplican lo que paga UNA carrera, para todo el server. Es la "happy hour" de siempre.
#
#   ⚠⚠ ARRANCAN EN 1.0 Y NO SE GUARDAN EN NINGÚN LADO: si el server se reinicia, vuelven a 1.0.
#     Es a propósito y es el default seguro — un multiplicador que sobrevive a un reinicio que
#     nadie recuerda es como se termina pagando el triple durante una semana sin que nadie sepa
#     por qué. Si algún día se quiere que duren, que sea una decisión explícita, no un descuido.
#
#   ⚠ El tope existe para que un dedo pesado no rompa la economía: `.rate exp 200` sería un
#     error de tipeo de `20.0`, y con 200 una sola canción daría más que una semana de juego.
_RATES = {"exp": 1.0, "coin": 1.0}
RATE_MIN, RATE_MAX = 0.0, 10.0
RATE_NOMBRES = {"exp": "experiencia", "coin": "monedas"}


def rate_de(que):
    """El multiplicador vigente. 1.0 si no se tocó, o si el nombre no existe."""
    return float(_RATES.get(str(que).lower(), 1.0))


def poner_rate(que, valor):
    """Fija un multiplicador. Devuelve el valor guardado, o `None` si el nombre no existe.

    ⚠ Se ACOTA en vez de rechazar: un GM que escribe `.rate exp 200` quiso decir mucho, y
      contestarle "error" sin hacer nada lo deja sin saber cuánto es el máximo. Se le pone el
      tope y se le dice cuál fue.
    """
    k = str(que).lower()
    if k not in _RATES:
        return None
    _RATES[k] = max(RATE_MIN, min(float(valor), RATE_MAX))
    return _RATES[k]


def rates():
    """Copia de todos los multiplicadores, para mostrar. ⚠ Copia: que nadie los mueva por afuera."""
    return dict(_RATES)

NPC_IN_ROOM = False                   # ★★ 2026-08-05: las salas nacen VACIAS, como en el CBT. Estuvo en True
                                      #   mientras el NPC era la unica forma de tener un 2º ocupante para reversar
                                      #   el START; con dos jugadores de verdad ese relleno ESTORBA (el invitado
                                      #   se sentaba encima del fantasma). Se invocan a mano: `.npc 1` / `.npc full`.
GHOST_SLOTS = [3]                     # ★ slots de los NPC. Default = 1 (el historico PROBADO en gameplay);
                                      #   para mas, `.npc N` / `.npc full` en el chat — asi el default
                                      #   nunca mete una variable nueva en una medicion. NO hay "comando de spawn": los jugadores de una sala
                                      #   son las ENTRADAS del FF0C USERLIST, asi que "spawnear" = agregar un
                                      #   ocupante mas a esa lista (+ su FF17 de LISTO). El host ocupa el 2 y el
                                      #   slot_mask 0x3F abre los slots 0-5 => libres 0,1,3,4,5 = hasta 5 NPC.
                                      #   ⚠ el reparto de EQUIPOS por slot todavia NO esta mapeado (pendiente #10):
                                      #   con host=2 y NPC=3,4,5 el equipo puede quedar 1v3.
GHOST_SLOT  = GHOST_SLOTS[0]          # compat: el 1er NPC (el que ya existia)
HOST_SLOT   = 2                       # slot del host: lo fija CREATEROOM client-side (me+0x40=2 si roomtype!=6).
# ★★ CAPACIDAD QUE MUESTRA LA GRILLA — MEDIDA CON DOS PUNTOS (2026-08-05):
#       G = 14  ->  la lista dice 8       G = 6  ->  dice 0
#   ⇒ **lo que se muestra es `G − 6`**, o sea `G = 6 + capacidad`.
#   ★ Eso explica el `6 + 8` que estaba escrito literal y que nadie sabía por qué: no era un número
#     mágico, era la fórmula a la vista. Lo que se había perdido era el motivo.
#   ⏳ ¿Y por qué 8 y no 6? La sala tiene 6 ASIENTOS (el loop del FF13 es fijo de 6). La sospecha
#     —del usuario, sin confirmar— es que los 2 de más sean los ESPECTADORES, que encajaría con el
#     "[N]" del corchete que ya tenemos medido como un contador aparte.
FF6E_CAPACIDAD = 6 + 6                # 6 asientos reales -> la grilla dice 6
FF0C_DISTINTIVO = 0xFF                # ★ Byte del distintivo del asiento en el FF0C. **0xFF = ninguno**
                                      #   (es el valor con el que el propio cliente lo pre-carga antes
                                      #   de leerlo). Mandar 0 pedía el distintivo nº 0 de la lista.
# ★★★ EL FF4B SÓLO CUANDO EL MODO CAMBIA DE VERDAD (2026-09-03).
#   El `FF4B` es **el único paquete que abre el cartel "el modo de juego ha cambiado"** (la otra
#   vía, la silenciosa, es `0x53ACF0`/`0x529EB0`). Y ese cartel está bien: avisa a los que ya
#   están adentro que el anfitrión tocó la configuración.
#   ⛔ Lo mandábamos también AL ENTRAR, desde el handler del `FF13`, que corre para todos. Así
#      que al que se unía le salía "el modo de juego ha cambiado a…" apenas entraba, sin que
#      nadie hubiera cambiado nada. Reportado por el usuario.
#   MEDIDO: el server de referencia manda **3 `FF4B` en toda una sesión**, y en las **8 entradas
#   a sala del corpus no hay ni uno**. El modo del que entra le llega por la entrada de la lista
#   de salas (`FF6E`), no por un `FF4B`.
#   ⚠ RIESGO CONOCIDO al apagarlo: había una nota diciendo que el `FF4B` es lo que hace que el
#     applier del cliente **redibuje los paneles de los asientos**. Si al entrar los asientos se
#     ven mal (paneles corridos o sin color), es esto: volver a poner `True` y buscar otra vía.
FF4B_AL_ENTRAR = False

FF4B_REPETIR_AL_CREAR = True          # ★ Repetir el FF4B una vez, ya dentro de la sala, para que los
                                      #   asientos de equipo queden bien DESDE LA CREACIÓN. No saca
                                      #   ningún cartel (el aviso de cambio de modo está gateado por
                                      #   que el modo CAMBIE). Ver el bloque en handle_inner().
FFBD_ANTES_DEL_FF4B = False           # ⛔ PROBADO Y DESCARTADO (2026-08-05, en pantalla).
                                      #   La idea era imitar el camino manual (FFBD concedido -> FF4B)
                                      #   para que el applier redibujara los slots de equipo al CREAR.
                                      #   RESULTADO MEDIDO: **abre el diálogo de configuración de sala
                                      #   apenas se crea** — el FFBD no es un "habilitador" silencioso,
                                      #   ES la orden de abrir esa ventana. Queda como negativo honesto:
                                      #   el layout hay que arreglarlo por otro lado (hay un agente
                                      #   buscando qué función redibuja los asientos).
FF4E_LOG = False                      # ★ True = loguear CADA sobre 0x4E que sale. Son cientos por
                                      #   carrera: sirve para depurar el relevo, ahoga el log si queda
                                      #   prendido. Los que ENTRAN se loguean igual, pero muestreados.
CRUDOS_MUESTRA = 8                    # ★ cuántos ejemplares de cada frame suelto sin handler se loguean
                                      #   ENTEROS antes de pasar a contarlos. 8 alcanza para ver qué
                                      #   campos varían y cuáles no, que es lo que descifra el layout.
# ★★★ SUBS DEL `FF4E` QUE SE LOGUEAN **SIEMPRE**, salteando el muestreo de arriba (2026-09-07).
#   POR QUÉ EXISTE: el `FF4E` entra muestreado (los primeros 8 y después uno cada 200), y eso
#   alcanza para descifrar un layout pero **esconde los eventos raros**, que son justo los que
#   interesan. Se descubrió queriendo verificar el `sub = 0x32`: en el log de una carrera de jefe
#   entera había 60 líneas de `FF4E` y ninguna era la que hacía falta.
#     0x32 = ★ "mi combo llegó a un múltiplo de 40" (`0x5050E7`). En modo jefe es LA señal con la
#            que el server tiene que decidir cuándo mandar el `FF176` del impulsor: el cliente,
#            en jefe, no carga la barra solo (sale en `0x504F85`).
#            Sus cuatro compuertas (`0x5050B4`..`0x5050D4`): no tener el efecto 0x19 · ser EQUIPO
#            (bit 0x04) · ser VELOCIDAD (bit 0x02) · NO ser relevo (bit 0x40). El jefe (`0x2017`)
#            pasa las cuatro — verificado en el disasm.
#     0x01 = ★ "se aplicó un efecto", y el DATO trae **cuál** (`0x50A490` -> anunciador con
#            eventId 1). Por acá pasa el uso de ÍTEMS: el despachador de acciones `0x50C9B0`
#            atiende la acción `0xC8` = usar ítem (`0x50CAEE`), y las acciones de efecto
#            terminan en `0x50A490`.
#            ⚠⚠ Y por acá pasa TAMBIÉN el disparo del impulsor del jefe. Por eso **no se puede
#               cargar a ciegas con cada `0x01`**: sería el impulsor recargándose a sí mismo.
#               Hay que ver primero QUÉ id de efecto trae cada cosa — para eso se loguea.
#   Poner () para volver al muestreo puro.
FF4E_SUBS_SIEMPRE = (0x32, 0x01)
# ★ 14-oct · EL GLOBO DEL COMBO (anonimo03: «el que espera su tramo o ya corrió no ve los combos del de su equipo»): la dll
#   (globo_combo.c) del que corre manda su combo por el FF4E con un sub NUESTRO, `A = 0x4743_00_asiento` ('GC'),
#   `B = combo`. El juego no lo atiende (cae en el «default»): un cliente sin la dll lo ignora. Se releva SÓLO a los
#   sentados de una sala de RELEVO (al espectador no: re-juzga las teclas, ya tiene el combo); los NPC que corren
#   mandan el suyo (npc_carrera.py). Ver documentacion/RELEVO_12.md «el globo del combo».
FF4E_SUB_GLOBO = 0x70
FF4E_FIRMA_GLOBO = 0x47430000
# ★ 14-oct · LA CALCULADORA DEL ESPECTADOR (documentacion/PAQUETES_ESPECTADOR.md): 0x71 = las notas (hasta 4 por paquete),
#   0x72 = la BASE (7 partes cada 8 s). Sólo a los ESPECTADORES. Junto con el 0x70 son «cosméticos»: no los atiende el
#   juego, no se anotan en el log, se reenvían SÓLO si el destino puede recibir YA (nunca se espera a nadie) y cada
#   conexión tiene un tope (lo de más se tira).
FF4E_SUB_CALC = 0x71
FF4E_SUB_CALC_BASE = 0x72
FF4E_COSMETICOS = (0x70, 0x71, 0x72)
FF4E_COSMETICOS_POR_S = 12          # el tope por conexión (ráfaga: el doble)
FF23_SLOT_AL_FRENTE = True            # ★ FF23 (movimiento en sala): ¿el S->C lleva el slot del emisor
                                      #   antepuesto? True = sí (como el CBT). ⚠ SIN CONFIRMAR en el
                                      #   2013: allá el C->S mide 11 y acá 12, así que la analogía no
                                      #   cierra sola. Si el avatar remoto no se mueve o salta a
                                      #   coordenadas absurdas, probar False. Ver el handler del 0x23.
FF28_WINTEAM = 0                      # ★ byte0 del cartel FF28 = EQUIPO GANADOR. El cliente lo compara con el
                                      #   suyo -> GANASTE/PERDISTE. Valor del 2013 sin confirmar (0 = 1er intento);
                                      #   si sale "perdiste" con el 1º puesto, probar 1 / 2. NO afecta que el
                                      #   cartel APAREZCA, solo el cartelito de victoria.
FF13_SENTINEL  = False                # ★ FF13 ROOMINFO: True = cada u8 del prefijo lleva su propio OFFSET como
                                      #   valor (diagnostico: descubrir QUE offset alimenta me+0x41). Ver build_ff13_2013.
                                      #   ⚠ apagar despues de medir (mete basura en campos sin mapear).
FF139_SENTINEL = False                # ★ FF139 PlayData: True = mandar centinelas por campo (diagnostico Frida del
                                      #   mapeo arg<->campo + valor del gate 0x5BA510); False = layout real (song).
# ★ START de partida en sala (cadena FF24->FF25->FF24). El botón START manda C->S FF24[00]; el server responde
#   S->C FF25 LOADGAME [magic:u32][map:u16][flag:u8][songs:u16..] (handler recv 0x5EB030) -> el cliente carga y
#   manda C->S FF25 -> el server responde S->C FF24 GO [count:u8][final:u8] (recv 0x5CE930) -> arranca la carrera.
DEFAULT_ROOM_MAP  = 11                # pista/stage por defecto (FF1B manda el elegido)
# ★ El mapa que pone `.oscuro` sin argumentos: 99 = "Abismo sin fin", una de las 5 traídas del CBT
#   el 2026-09-07. Es un ajuste y no un número suelto en `chat.py` para que cambiarlo sea una línea.
#   ⚠ Tiene que estar en `OWNED_STAGES_2013` o el comando lo rechaza — y hace bien: ofrecer un
#     stage que el cliente no tiene es el mismo error que las canciones fantasma, que crasheaban.
MAPA_OSCURO       = 99
DEFAULT_ROOM_SONG = 4017             # cancion por defecto (FF139/FF1C mandan la elegida)
FF25_SENTINEL = False                 # ★ FF25 LOADGAME: True = centinelas (diag); False = magic/map/song reales.
# ★ EXPERIMENTO: el cliente lista en el panel de inventario SOLO los ítems in_use=0; los in_use=1 (equipados)
#   los pone en el char pero NO en el panel. Para que un ítem equipado ADEMÁS figure en el panel, probamos
#   emitirlo 2 veces: in_use=1 (renderiza) + in_use=0 (lista). "dup" = probar; "single" = comportamiento previo.
WORN_PANEL_MODE = "dup"
# ★ Fase B DEBUG formato de fecha: mapa item_id -> wire end_time forzado (para descifrar el layout que muestra
#   el cliente). Cada probe activa UN bit-group distinto, año fijo 2030(0x7EE) de referencia. {} = desactivado.
DEBUG_ENDTIME_MAP = {}                # {} = desactivado (formato descifrado: display lee word[+0x20]/byte[+0x22]/
                                      #   byte[+0x23] del struct de item de 0x34B; decode en cadena de 0x48ffb0; +54 compensa)
# ★ RCOIN CON EL QUE ARRANCA UN PERSONAJE. 65.000 a pedido del usuario (2026-09-05).
#   ⚠ Es el DEFAULT de `db_get_rcoin` (`ch.get("rcoin", RCOIN)`), o sea que se lo lleva el que
#     todavía no tiene saldo propio — no le regala nada al que ya venía jugando. Para darle a los
#     que YA existen: `python pruebas/dar_rcoin.py --a-todos 65000`.
#   ⛔ El 32562 original no era un número elegido: era el saldo de una cuenta de captura.
RCOIN = 65000
CASH  = 258780

# ★★★ ¿EL SERVER DESCUENTA AL COMPRAR? (2026-09-05, a pedido del usuario)
#   Hasta hoy NO: `h_35_ff2a` y `h_36_ff50` contestaban éxito y devolvían el saldo **sin tocar**.
#   O sea que la tienda entera era decorativa: se podía comprar todo con cualquier saldo.
#   En False vuelve a ese comportamiento (útil para probar items sin quedarse sin plata).
COBRAR_COMPRAS = True
SEED  = 0
COIN_OFF = 9                          # rcoin = u32 @ off 9 (confirmado: centinela 1000009 salio en rcoin)
CASH_OFF = 13                         # cash  = u32 @ off 13 (centinela 1000013 salio en cash)
SEED_OFF = None                       # seed NO esta en el prefijo u32 (probe1 mostro 0) -> vive en la COLA

# ── SEED (vive en la COLA del MyRecord, no en el prefijo) ──
# Probe de cola: centinela 7000000+offset en cada u32 escalar de la cola (offsets del mapa myrec_reads.txt,
# relativos a tail_start=1687): u32 @ 1693,1697,1701,1705,1712,1724,1728,1736 -> deltas 6,10,14,18,25,37,41,49.
PROBE_SEED = False                    # <- probe de seed completo (los 8 u32). Usar REST_TEST para bisecar.
TAIL_U32_DELTAS = (6, 10, 14, 18, 25, 37, 41, 49)
SEED_DELTA = None                     # <- delta (offset-1687) del seed, rellenar tras el probe
# BISECCION "puntos de descanso" (vive en la cola). REST_TEST = deltas de cola a poner en centinela;
# si el popup de descanso APARECE, el campo esta en ese subconjunto. Deltas -> offsets: 6->1693,10->1697,
# 14->1701,18->1705,25->1712,37->1724,41->1728,49->1736.
REST_TEST = None                      # CONFIRMADO 2026-07-10: puntos de descanso = @1693 (delta 6). Probe apagado.
REST_OFF  = 1693                      # ✅ puntos de descanso = u32 @1693 (delta 6 desde tail_start)

# ── LICENCIA (sol) — BISECCION del campo grade/tier en el prefijo ──
# Con todos los u32 del prefijo en ~1000000 salio SOL. Candidatos (sin rcoin@9/cash@13): 12 u32.
# LICENSE_TEST = lista de offsets del prefijo a poner en LICENSE_VAL (valor-gatillo). Biseccion: prender
# la mitad -> ¿sol? -> el culpable esta en esa mitad. Repetir hasta 1 offset. Luego fijar LICENSE_OFF.
LICENSE_TEST = None                     # CONFIRMADO 2026-07-10: licencia = @19. Fijo permanente abajo.
LICENSE_VAL  = 1000000                  # 2026-07-11: 0 => NOVATO ESTRELLA (la mas baja); 1 => estrella; 1000000 => SOL.
LICENSE_OFF  = 19                       # ✅ campo licencia = u32 @19 (-> cfg+0x664)

# ── LICENCIA/TIER del objeto PLAYER (FFC9) — lo que falta para el nombre del canal ──
# El FFC9 (handler 0x5D8490) lee 1 byte -> [0x9314c0]+0x9512 (setter 0x58EDF0) = valor de licencia/tier
# del player + refresco de UI. Es el equivalente 2013 del player+0x6d36 del CBT (1=novato, 2/3=estrella,
# 4/5=luna, 6/7=sol). El @19 del MyRecord es OTRO campo; el ícono/nombre del canal sale de ESTE. Calibrar
# el byte en vivo (empezamos en 1 = novato estrella).
SEND_FFC9_LICENSE  = True
# ★ FF49 = la lista de personajes + SelectByKey. Es lo que deja VÁLIDO el índice `word[G+0x8C]` que
#   el handler del MyRecord chequea contra el tamaño de la lista. Es la VÍA HONESTA del parche de
#   2 bytes `mov ecx,0xFFFF -> mov ecx,0` (en el CBT ese parche se pudo quitar con esto). Ver build_ff49().
SEND_FF49_LISTA    = True
# ★ cuántas INSTANCIAS de cada lugar especial se publican en el FF65 (el panel 'Libre 0/1/2…').
#   El nº visible es `A & 0x7FF`, así que 3 -> Libre 0, Libre 1, Libre 2. Sirve para que el jugador
#   se pueda mudar si la instancia por defecto se llena.
# ⚠ 2026-08-05: con 3 instancias y el layout [count:u16]{[A:u16][ocupantes:u8]} el cliente MUERE
#   al abrir la lista (reset TCP, sin registro en el visor de eventos). El layout del FF65 no está
#   bien medido todavía. **0 = no contestar el FF65** (el panel queda vacío, pero nada crashea).
INSTANCIAS_LUGAR   = 0   # extras además de la instancia actual (0 = sólo la actual, prueba del agente)
# ★ Los lugares PERSISTENTES que se crean al arrancar. Los tipos salen de la tabla horneada en
#   `cChatRoom.cpp`: 5 = Conversación Libre, 6..10 = los cinco grupos de país, 12 = charla de
#   círculo. El 11 (casa de un jugador) NO va acá: se crea sola la primera vez que alguien entra.
TIPOS_LUGAR_CHARLA  = (5, 6, 7, 8, 9, 10, 12)
INSTANCIAS_LUGAR_N  = 3          # Libre 0, Libre 1, Libre 2 (y lo mismo por cada tipo)
# los números que el CLIENTE pide desde cada botón (medidos del disasm): tipo -> nº
DESTINOS_HORNEADOS  = ((5, 965), (6, 966), (7, 967), (8, 968), (9, 968), (10, 969), (12, 970))
# ★★ LA SALA DE CONVERSACIÓN COMPARTIDA (24-sep) — `charla.py`, `documentacion/SALA_DE_CHARLA_2013.md`.
#   Tipos 5..10 (Libre + los 5 grupos de país) y, abajo, el círculo (12). Mi Sala (11) no pasa por acá.
CHARLA_COMPARTIDA = True         # False = como antes: cada uno solo en su copia de la sala
CHARLA_ESTANCIAS  = 4            # estancias por tipo, numeradas 1..N (el nº visible = A & 0x7FF)
CHARLA_FF0C_REAL  = True         # el ocupante con el armador de las salas de carrera (un paquete c/u);
                                 #   False = el multi-ocupante viejo `build_ff0c_2013`
# ★★ LA SALA DEL CÍRCULO (tipo 12, 25-sep) — también por `charla.py`, pero con UNA estancia POR
#   CÍRCULO: el nº 970 es el mismo para todos, así que la clave es el círculo del que entra
#   (`(12, circulo_id)`), no el número. Cada uno cae en la de SU círculo: no hace falta filtro.
CIRCULO_SALA_COMPARTIDA = True   # False = como antes: cada uno solo en su copia
CIRCULO_SALA_CAPACIDAD  = 30     # `circleroom.xml`: 30 de base (40 con el ítem 474, todavía no)
CIRCULO_SALA_NUMERO     = 0      # el nº del `A` que vuelve: el título lo arma el CLIENTE con
                                 #   `"%s%d"` (círculo + nº, SIN espacio, `0x5CD675`) ⇒ con el 970
                                 #   del botón se leería «Pinguinos970»; con 0, «Pinguinos0», como
                                 #   «Libre 0» (anonimo03, 25-sep). Acá el nº NO elige renglón: para el 12
                                 #   el panel marca el 0 y después BUSCA el renglón con ese nº
                                 #   (`0x585AD0` + `0x58D990`) ⇒ ningún nº puede marcar uno vacío
LICENSE_TIER_BYTE  = 6                  # 2026-07-25: 6 = SOL (1=novato, 2/3=estrella, 4/5=luna, 6/7=sol)


FF49_RANURAS = 11          # el registro del cliente mide 0x30 = key(4) + 11 dwords

# ★★ 2026-08-06 — CON QUÉ NACE UNA CUENTA NUEVA (pedido para el server de pruebas).
#   Los cinco campos son una COPIA EXACTA de los de `testest` (usn 3), que es un personaje que se
#   juega todos los días: exp 1.899.989 = **nivel 50** (es justo el umbral de ese nivel, o sea que
#   subió ahí) y licencia 1 = banda **Estrella**.
#   ⚠ Por qué van los tres campos de misión y no sólo `exp`+`licencia`: la licencia NO se deriva del
#     nivel (`LICENCIA_SOLO_POR_MISION`), la da la misión. Dejar `licencia=1` con el progreso de
#     misiones en cero sería un estado que NUNCA existe jugando — y los estados inventados son los
#     que después aparecen como "bugs raros". Copiando el conjunto entero, la cuenta nueva arranca
#     en una situación que ya sabemos que el cliente maneja bien.
#   Para volver a que nazcan vírgenes (nivel 1, sin banda): poner  CUENTA_NUEVA = {}
#   ★ 2026-08-06 (ii) — la licencia pasó de 1 (Estrella) a **3 = Estrella|Luna**, para que las
#     cuentas nuevas nazcan igual que las que ya se pasaron a Luna a mano. Va el 3 y no el 2 porque
#     a Luna no se llega sin la Estrella: el 2 solo sería un estado que jugando no existe.
#     Las misiones de licencia NO se marcan por el nibble — las marca el bucle del login leyendo
#     `[player+0x664]`, que sale de este mismo campo ⇒ con el 3 aparecen hechas las dos.
#   ★ 2026-09-05 — NACEN EN **NIVEL 5** Y CON **65.000 RCOIN**, a pedido del usuario.
#     El 16240 no es un número redondo: es el UMBRAL EXACTO del nivel 5 en la tabla que el propio
#     exe trae (`cargar_umbrales_exp`: 500 · 3000 · 7000 · 11400 · **16240** · 21564 …). Poner un
#     número "lindo" cerca daría nivel 4 y nadie entendería por qué.
#     ⚠ La `licencia` NO se tocó: sigue en 3 (Estrella|Luna). Nivel y licencia son cosas
#       distintas — el nivel sale de la exp y la licencia de las misiones — así que una cuenta
#       nueva es nivel 5 con banda Luna. Si se quiere que también arranque sin licencia, es este
#       campo, no la exp.
#   ★★ 2026-09-29 — NACEN SIN LICENCIA Y SIN MISIONES, a pedido de anonimo03 (*"debería empezar
#     estrella verde nivel 5"*): la licencia 3 las hacía nacer LUNA (la luna azul al lado del
#     apodo) con «Licencia Estrella» y «Licencia Luna» ya cumplidas a nivel 5. Con 0 el ícono sale
#     del nivel (nivel 5 = Novato) y cada licencia se gana jugando su misión, como en el original.
#     ⛔ Y la plantilla vieja traía además `mision_nibbles [4,0,0]` (= Tutorial, Ritmo, King y
#     Anillo hechas, que nunca se jugaron) y los ids 1 y 2, que no son misiones. Se va todo.
#     ⚠ Las cuentas YA creadas con la plantilla vieja siguen como están: esto es sólo al nacer.
CUENTA_NUEVA = {
    "exp":             16240,            # ★ el umbral exacto del NIVEL 5 (antes 1899989 = nivel 50)
    "rcoin":           65000,            # ★ para que pueda comprar y probar que el server descuenta
    "licencia":        0,                # ★ 29-sep: sin licencia (era 3 = Estrella|Luna -> 'moon')
    "mission":         0,
    "mision_nibbles":  [0, 0, 0],
    "misiones_hechas": [[], [], []],
    "misiones_grado":  {},
}

# ★★★ TABLA DE MISIONES DEL CLIENTE (2026-07-31) — volcada del propio exe, no adivinada.
#   `re/trace_misiones_tabla.py` + `re/trace_misiones_nombres.py`. El disasm de `0x48A5E0` (la función
#   que el handler del FF125 usa para resolver el id que le mandamos) reveló que NO traduce nada:
#   **recorre el vector de 19 structs de 124 B y compara `byte [ebp+0x79]`**, devolviendo `word [ebp]`.
#   O sea cada misión lleva DENTRO su id y su máscara. Del volcado salieron además:
#       +0x02 = capítulo (1..6)   ·   +0x04 = NIVEL REQUERIDO   ·   +0x0C.. = nombre/objetivo/premio
#   (id, máscara, nivel, nombre)  — id 0 = el cliente no la resuelve por FF125 (llegan por otra vía)
MISIONES_2013 = [
    ( 10, 0x0001,  0, "Tutorial (control basico)"),
    (100, 0x0002, 15, "Ritmo de la competencia"),
    (120, 0x0003, 20, "Batalla con King"),
    (  0, 0x0004, 25, "Anillo del Amor"),
    ( 20, 0x0005,  4, "Tutorial (repetir nivel 4+)"),
    ( 30, 0x0006,  0, "¡Repasemos! obstaculos basicos"),
    ( 40, 0x0007,  0, "¡Repasemos! obstaculos avanzados"),
    ( 50, 0x0008,  0, "Velocidades normal/alta/super"),
    ( 60, 0xF001,  5, "Tutorial movimientos basicos"),
    ( 70, 0xF002,  5, "Tutorial recoger estrellas"),
    ( 80, 0xF004, 10, "Tutorial terremotos"),
    ( 90, 0xF008, 10, "Tutorial modo item"),
    (  0, 0x0F01, 20, "LICENCIA Estrella"),
    (  0, 0x0010, 30, "Licencia Canal Novato Lunar"),
    (  0, 0x0020, 30, "Nuevos retos"),
    (  0, 0x0030, 40, "Revancha con King"),
    (  0, 0x0F02, 40, "LICENCIA Luna"),
    (  0, 0x0100, 60, "Licencia Canal Novato Sol"),
    (  0, 0x0F04, 70, "LICENCIA Sol"),
]
MASCARA_DE_MISION = {m[0]: m[1] for m in MISIONES_2013 if m[0]}
NOMBRE_DE_MISION  = {m[0]: m[3] for m in MISIONES_2013 if m[0]}

# ★★★ DE DÓNDE SALE EL "HECHA" DE CADA MÁSCARA — leído del bucle `0x4890D0` (corre en el login).
#   El bucle recorre las 19 entradas y tiene EXACTAMENTE TRES reglas, ninguna más:
#     · `mask > 0xF000`            -> `test [player+0x320], mask`   (0xF001/2/4/8 = los 4 tutoriales)
#     · `mask - 6 <= 2` (6,7,8)    -> `mask <= [player+0x335]`      (las LECCIONES de la escuela)
#     · `mask - 0xF01 <= 3`        -> `test [player+0x664], mask`   (0x0F01/02/04 = LICENCIAS)
#   Todo lo demás (1..5, 0x10/0x20/0x30, 0x100) sólo lo puede otorgar el bucle de NIBBLES `0x48B720`,
#   que hace `for i=1..n: otorgar(i)`, `otorgar(i<<4)`, `otorgar(i<<8)` — o sea el nibble es un
#   **avance lineal**, no una cantidad de misiones sueltas.
#   ⇒ La cadena de historia del grupo 1 son las máscaras **1..4**, y sus niveles lo confirman
#     (Tutorial 0 → Ritmo 15 → King 20 → Anillo 25). Grupo 2: 0x10 (30) → 0x20 (30) → 0x30 (40).
#     Grupo 3: 0x100 (60).
#   ⚠ La máscara 5 ("Tutorial repetible nivel 4+") es la única huérfana: no tiene regla propia y
#     marcarla exigiría n0=5, que arrastraría 1..4 como hechas. Se deja SIN persistir a propósito
#     (es un reto repetible, no un eslabón de la historia). A verificar en la corrida con cuenta nueva.
LECCIONES = {6, 7, 8}                    # -> [player+0x335]

# ★★★ PREMIOS DE MISIÓN — de los SCRIPTS DEL PROPIO CLIENTE (2026-07-31), no inventados.
#   `rnr_script/mission/<MÁSCARA>.txt` (desempacado con tools/unpackers/R2PAK-1.10.0.113) es el XML
#   original de cada misión — hay **uno por máscara**, lo que confirma de nuevo la tabla de máscaras:
#       <Mission Char Name Title Stage Music Count Item="..." Succ="..." Fail="...">
#   · `Item=` es el **ítem premio** · el `Succ` coreano de la 1 dice literal `5000 알코인 획득!`
#     (= "¡5000 Rcoin obtenidos!") · los EXP salen del texto español que ya teníamos del exe.
#   ⚠ Las que NO tienen `Item=` y premian "Set Avatar" (máscaras 1 y 5) **no traen el set en el
#     cliente**: el cliente sólo REPORTA qué recuadro elegiste (`premio` del FF125) y dibuja imágenes
#     estáticas. Qué ropa hay detrás de cada recuadro es dato de SERVER — abajo, SETS_PREMIO_MISION.
# máscara: {rcoin, exp, item, dias, nota}
#   `item`: id suelto (se ajusta el género con ajustar_genero_item) **o** dict {0: id_H, 1: id_M}
#           cuando la pareja NO se deduce cambiando el 2º dígito.
#   `dias`: duración del premio en ítems. El texto de cada misión la dice (30d los sets avatar,
#           3d/7d los accesorios); si falta, PREMIO_SET_DIAS.
PREMIOS_MISION = {
    0x0001: {"rcoin": 5000, "nota": "Tutorial — '5000 알코인 획득!' en el Succ coreano; rank S = set a elección"},
    0x0005: {"rcoin": 5000, "nota": "Tutorial repetible — mismo script (5.txt == 1.txt)"},
    0x0002: {"item": 600008, "dias": 7, "nota": "Ritmo de la competencia — Item= del script; texto: Accesorios(7dias)"},
    0x0003: {"nota": "Batalla con King"},
    0x0004: {"exp": 2500, "item": 30009,  "nota": "Anillo del Amor — Item= + '2500 EXP' del texto del cliente"},
    0x0020: {"exp": 3000, "item": 830009, "nota": "Nuevos retos — vara de Marie"},
    0x0030: {"exp": 4000, "item": 910003, "nota": "Revancha con King — Guantes del King"},
    # ★ El script coreano de la 6 NO trae `Item=`; el cliente sólo dice "Rank S – Accesorios(3dias)".
    #   El accesorio concreto lo eligió el usuario. ⚠ La pareja H/M de este ítem **no se deduce
    #   cambiando el 2º dígito** (910061 vs 920060, difieren también en el último) — por eso va
    #   explícita: con la heurística se habría calculado 920061, que no existe.
    0x0006: {"item": {0: 910061, 1: 920060}, "dias": 3,
             "nota": "¡Repasemos! básicos — Anillo Luz (H)/(M), 3 días"},
    # ★ Tampoco trae `Item=`; el cliente sólo dice "Rank S – Cirugia Plastica(3dias)" = cambio de
    #   CARA (familia wardrobe_face). La eligió el usuario. ⚠ Pareja H/M explícita: los ids no se
    #   deducen entre sí (1010042 vs 1020043, difieren en el último dígito) y además son ids de 7
    #   dígitos, donde ajustar_genero_item ni siquiera aplica (sólo toca los de 6).
    0x0007: {"item": {0: 1010042, 1: 1020043}, "dias": 3,
             "nota": "¡Repasemos! avanzados — cara Incubus niño / Succubus niña, 3 días"},
    # ★ La 8 tampoco trae `Item=` (8.txt sólo tiene Stage/Music/Count/Tempo); el cliente dice
    #   "Rank S – Mascota(30dias)". La mascota la eligió el usuario. NO lleva pareja H/M: los ids de
    #   la familia `pet` son 6xxxxx (2º dígito 0) y ajustar_genero_item los deja intactos a propósito.
    #   ⚠ Se eligió una con precio `P30` en shop_lt por prolijidad (garantiza que en el juego original
    #   existía como mensual), pero NO es una restricción técnica: la caducidad la pone el server
    #   (`caduca = now + dias*86400` en entregar_premio_mision) y no pasa por el catálogo —
    #   `shop_catalog.duration_days` sólo interviene en la COMPRA de tienda. 600007 = Mong.
    0x0008: {"item": 600007, "dias": 30,
             "nota": "Velocidades normal/alta/super — Mong (mascota), 30 días"},
    # ★ Grupo 0xF00X (`add_1..add_8.txt`): NINGUNO trae `Item=` de premio — los `Item=` de add_8.txt
    #   son MissItem/UseItem del bloque <AI> y el <Item Coord Type> de pista, o sea objetos DENTRO de
    #   la carrera. Premio del texto del cliente; el ítem lo eligió el usuario.
    #   ⚠ Par H/M EXPLÍCITO: 910214 / 920210 no se deducen cambiando el 2º dígito (el último difiere).
    0xF001: {"item": {0: 910214, 1: 920210}, "dias": 7,
             "nota": "Tutorial 1-1 'Buenas habilidades básicas' — Vara de Luz (H)/(M), 7 días"},
    # ⚠ Par H/M EXPLÍCITO otra vez (1010515 / 1020516: ids de 7 dígitos, donde ajustar_genero_item ni
    #   siquiera aplica, y además el último dígito difiere). En shop_lt sólo tienen precio `P365` y
    #   son `Cash="1"` — irrelevante para el premio: la caducidad la pone el server.
    0xF002: {"item": {0: 1010515, 1: 1020516}, "dias": 7,
             "nota": "Tutorial 1-2 'Estrellas en mi corazón' — cara Ojos de estrella (H)/(M), 7 días"},
    # ★★ PRIMER PREMIO POR CANTIDAD, no por duración: el cliente dice "Auto Booster(30EA)".
    #   Se eligió el PACK de 30 (`1200099`, ItemEffect 17, `PackCount="30"`, `PackIndex="1000999"`)
    #   en vez de mandar el impulsor suelto con `cant=30` en el FF126: así la cantidad la resuelve el
    #   propio cliente con el `PackCount` del catálogo (`word [item+0xC4]`) y no dependemos de que el
    #   campo `cant:u16` del FF126 funcione — que sigue sin medirse.
    #   ⚠ `dias: 0` = PERMANENTE (en la tienda su único período es `P`). Es consumible, no vestible.
    #   Sin género: id de 7 dígitos, `ajustar_genero_item` no aplica.
    0xF004: {"item": 1200099, "dias": 0,
             "nota": "Tutorial 1-3 'Gorilla Molesto' — Pack de Auto Impulsor x30, permanente"},
    0xF008: {"item": 1200099, "dias": 0,
             "nota": "Tutorial Final 'RCarrera de Picnic' — Pack de Auto Impulsor x30, permanente"},
}
# ★ NUESTRA tabla: qué ropa entrega cada recuadro del cartel de rank S.
#   El cartel es un SPRITE (medido con `re/trace_premio_sets.py`: al abrirse NO se consulta ningún id
#   de ítem nuevo, sólo las prendas que el jugador ya lleva puestas) ⇒ el cliente no sabe qué ropa hay
#   detrás de cada recuadro, sólo manda un número. Las claves de esta tabla son la POSICIÓN VISUAL
#   1..4 de izquierda a derecha; el número del wire se traduce con RECUADRO_DESDE_WIRE (ver abajo).
#   Los nombres los identificó el usuario mirando el cartel; los ids salen del catálogo (shop_lt.txt).
#   ★★ EL CARTEL MUESTRA SETS DISTINTOS SEGÚN EL GÉNERO ⇒ la tabla va por género, no se puede
#      derivar uno del otro cambiando dígitos (son conjuntos completamente distintos).
#      Género = `char_id & 1`  →  **0 = hombre · 1 = mujer** (medido: 130900 = H, 130901 = M).
SETS_PREMIO_MISION = {
 0: {  # ───── HOMBRE ─────────────────────────────────────────────────────────────────────
    1: [210530,   # Sombrero Kiel
        310533,   # Chaleco Kiel a Cuadritos
        410462,   # Jeans Negros Kiel
        510401],  # Zapatos Kiel Style
    2: [210054,   # Sombrero Armeni
        310051,   # Traje Armeni
        410035,   # Pantalon Armeni
        510046],  # Zapatos Armeni
    3: [210055,   # Cabello Michael
        310061,   # Chaqueta Michael
        410063,   # Jeans Michael
        510024],  # Maclow Blancos — no hay "Zapatos Michael" en el catálogo; los eligió el usuario
    4: [210319,   # Rua Desgreñado
        310335,   # Skull Callejero Rua
        410304,   # Jeans Rua con Tirantes
        510254],  # Zapatos Rua Skull
 },
 1: {  # ───── MUJER ──────────────────────────────────────────────────────────────────────
    1: [220038,   # Anillo Channil
        320057,   # ★ Camiseta Channil   (la prenda que identificó el usuario)
        420039,   # Falda Channil
        520047],  # Tacones Channil                      ← set COMPLETO y exacto
    2: [220486,   # ⏳ Corte Emo Negro Evisen  (no hay pelo "Evisen Puntos"; es el Evisen más cercano)
        320481,   # ★ Blusa Evisen Puntos
        420445,   # ⏳ Mini Falda Evisen
        520360],  # ⏳ Zapatos de Cuero Evisen
    3: [220435,   # Gorrita Rosa
        320462,   # Sttraples Priamvera con Lazo  (el typo es del catálogo, no del usuario)
        420428,   # Minifalda Azul
        520343],  # Zapatos Durazno   ← las 4 identificadas por el usuario en el juego
    4: [220550,   # Colitas Gemelas Kiel
        320534,   # ★ Chaleco kiel Caqui
        420496,   # Shorts de Jean Kiel
        520408],  # Zapatos Kiel                         ← línea Kiel femenina completa
 },
}
PREMIO_SET_DIAS = 30             # "Set Avatar(30dias)" según el texto de la misión

# ⚠ SETS_PREMIO_MISION es el cartel de la MISIÓN 1 (máscaras 1 y 5, que comparten script). Si otra
#   misión muestra recuadros DISTINTOS, hay que ponerlos acá o entregaríamos los de la misión 1.
#   {máscara: {género: {recuadro: [item_id, ...]}}}
SETS_POR_MISION = {}

# ★★★ EL NÚMERO DEL WIRE **NO ES** EL ÍNDICE DEL RECUADRO — el cliente lo REMAPEA antes de mandarlo.
#   Hallado en el emisor del `FF125` (`0x5D9F71`), que elige entre DOS tablas según `[player+0x80]`:
#       mov al, byte [ecx+0x80] ; test al,al ; jne <tabla B>      ; ecx = player
#     tabla A:  1→4 · 2→1 · 3→2 · 4→3          (0x5D9F84..0x5D9FA7)
#     tabla B:  1→1 · 2→4 · 3→3 · 4→2          (0x5D9FA9..0x5D9FB8)
#   `[player+0x80]` = **GÉNERO** (deducido, no verificado por xref): con esa lectura las 4 corridas
#   observadas encajan exactamente y sin ella ninguna encaja —
#     hombre  recuadro 2 → wire 1 ✓ · recuadro 3 → wire 2 ✓   (tabla A)
#     mujer   recuadro 2 → wire 4 ✓                           (tabla B)
#   ⚠ Esto explica el desconcierto anterior: el mismo "elegí el set 2" mandó **1** con personaje
#     hombre y **4** con personaje mujer. La hipótesis del índice 0-based encajaba de casualidad con
#     la tabla A (2→1, 3→2 se parecen a "restar uno") y se rompió al cambiar de género.
#   Acá va la tabla INVERSA: wire -> posición visual del recuadro.
RECUADRO_DESDE_WIRE = {
    0: {4: 1, 1: 2, 2: 3, 3: 4},     # hombre (inversa de la tabla A)
    1: {1: 1, 4: 2, 3: 3, 2: 4},     # mujer  (inversa de la tabla B)
}

# ★★★ GRADO POR MISIÓN + REPLAY (2026-07-31) — resuelve DOS cosas de un saque.
#   El handler RX del `FF125` (`0x5DA100`) hace tres cosas con la respuesta de 2 bytes `[id][grado]`:
#       esi = 0x48A5E0(player, id)      -> máscara de esa misión (busca por `byte [ebp+0x79]`)
#       si grado != 0: 0x488FD0(player, esi)   -> ★ OTORGA la máscara, DIRECTO
#       0x48A530(player, esi, grado)           -> ★ `byte [ebp+0x78] = grado`  (el GRADO de la misión)
#   ⇒ `+0x78` = grado · `+0x79` = id, pegados en el struct.
#   ★★ Y ese handler es RX: **el server puede mandar `FF125` cuando quiera**, no sólo contestarlo.
#      Mandando uno por misión hecha al entrar al lobby se restaura el estado COMPLETO — y encima
#      otorga la máscara **exacta**, sin pasar por el nibble.
#   Eso arregla las dos limitaciones que teníamos:
#     · la **máscara 5** (misión id 20) no tenía forma de persistir: el nibble sólo la alcanzaría
#       arrastrando las máscaras 1..4 como hechas. Con el replay se otorga sola.
#     · el **grado** (S/A/B/C…) se perdía en cada relogin: la misión volvía a verse sin nota.
#   ⚠ SIN VERIFICAR todavía que el cliente acepte un `FF125` no solicitado en ese momento del flujo.
REPLAY_MISIONES = True            # mandar un FF125 por misión hecha al entrar al lobby
# ★★ 2026-07-31: NIBBLE RETIRADO. El campo E del RESP-1 va en 0 y toda la persistencia la hace el
#   replay. Motivo: el nibble otorga las máscaras **1..n en fila**, o sea SOBRE-MARCA — haciendo sólo
#   la de máscara 3 quedaban "hechas" también la 1 y la 2, misiones que el jugador nunca jugó. El
#   replay otorga la máscara EXACTA (`0x488FD0`) y encima restaura el grado.
#   ⚠⚠ LÍMITE CONOCIDO: el replay se apoya en `0x48A5E0(id)`, que **devuelve 0 si el id es 0**. En el
#   volcado del cliente hay 5 misiones jugables con `+0x79 == 0` — Anillo del Amor (0x0004), Licencia
#   Canal Novato Lunar (0x0010), Nuevos retos (0x0020), Revancha con King (0x0030) y Licencia Canal
#   Novato Sol (0x0100). A ésas el replay NO las puede restaurar. Tampoco las manejábamos antes: al
#   completarse mandarían `FF125` con A=0 y el server ya avisa `⚠ id 0 NO está en MISIONES_2013`.
#   Son de nivel 25+, así que se resuelven cuando se llegue — y ahí se verá qué id mandan de verdad.
#   Poner en False para volver al nibble (queda todo el código intacto).
MISIONES_POR_REPLAY = True
ORDEN_GRADOS = "SABCDEF"          # de mejor a peor; lo que no esté en la lista se considera lo peor

# ★★★ FF126 = EL CARTEL DE PREMIO SE POBLA CON ESTO (S→C). Handler cliente `0x5DA160` (cmd 294).
#   Sin él, el recuadro "Recompensa de misión" sale VACÍO — que es el bug que reportó el usuario
#   comparando nuestro cartel con un video del juego original, donde sale el ícono del ítem y el texto
#   "¡Felicidades! Has obtenido [Incubus niño] por tu logro!".
#   WIRE (leído entero del disasm, incluido el contador del bucle en 0x5DA327):
#       [A:u8][exp:u32][rcoin:u32][cantidad:u8]
#         × cantidad:  [item_id:u32][end_time:u32][tipo:u32][cant:u16]
#   Qué hace el cliente:
#     · `exp`   != 0 -> lo suma vía 0x486020/0x486000
#     · `rcoin` != 0 -> `[player+0x2d8] = ([player+0x2d8]^0x1FEF + rcoin)^0x1FEF`  (SUMA, no pisa)
#     · por ítem: si `tipo & 0xFFF` es 0 ó 3000 -> lo resuelve con `0x511D80` (el MISMO lookup que la
#       compra del FF50), multiplica `cant` por el PackCount (`word [item+0xC4]`) y lo agrega.
#   ⚠ Se manda con **exp=0 y rcoin=0 a propósito**: la entrega real ya la hace el server contra la DB
#     (y el saldo viaja en el MyRecord). Si además los mandáramos acá, el cliente los sumaría de nuevo
#     y quedarían contados dos veces hasta el próximo MyRecord. Acá el FF126 se usa sólo para POBLAR
#     EL CARTEL. Migrar la entrega entera a este paquete es la tarea aparte.
#   ⏳ El byte A no se identificó (se lee pero no se le vio uso); va en 1.
FF126_TIPO_ITEM = 0                # `tipo & 0xFFF` ∈ {0, 3000} = rama de ítem de catálogo

# ★★★ FF63 = FIN DE CANCIÓN — EL PAGO NATIVO DE EXP + RCOIN (2026-07-31)
#   Estaba en `re/FASE0_dispatcher_wire.md` como "fin cancion 🔶" y en `rx_table_2013.md` con handler
#   de RECEPCIÓN `0x5E5CD0` ⇒ es BIDIRECCIONAL, como el FF125: el cliente reporta el fin de la canción
#   y **se queda esperando** que el server le diga cuánto ganó. Sin respuesta el cliente se cuelga
#   (medido: al terminar la misión 60 quedó girando; el `FF3D` a 60/s NO era el síntoma, viene desde
#   el login).
#   Qué hace el handler RX (disasm `0x5E5CD0`), con las auxiliares confirmadas:
#       0x486020  get EXP   -> `[player+0x2d0] XOR 0x1fef`
#       0x486000  set EXP   -> `[player+0x2d0] = v XOR 0x1fef`
#       0x485d30  get NIVEL -> recorre la tabla `0x8782a0` hasta `exp < tabla[i]` (tope 100)
#     · lee 4 campos con `0x67CFE0`: u8 + 3×u32 = **13 bytes**
#     · exp += campo3, recalculando el nivel ANTES y DESPUÉS -> `setne bl` = **subiste de nivel**
#     · `[player+0x2d8] (rcoin) += campo4`, también XOR `0x1fef`
#   ★★ Dato transversal: **el cliente guarda exp y rcoin OFUSCADOS con XOR `0x1fef`** (anti-cheat).
#   ⚠ Los offsets salen de leer los `lea` con la trampa del `push size` ANTES del `lea dst`
#     (`lea [esp+N]` apunta a `esp0+N-4`). Por eso existe FF63_PROBE.
#   ✅ MEDIDO 2026-07-31 con FF63_PROBE=(1234, 777): el `FFAB` que el cliente manda justo después
#      llegó con **43339**, y nuestra DB tenía **42562** => 43339-42562 = **777** = el rcoin de la
#      sonda. ⇒ **`u32 @ 0x09` = RCOIN, confirmado por medición.** (El campo de exp sigue apoyado
#      sólo en el disasm: no se reporta por el cable.)
#   ★★★ Y ESO RESUELVE LA DUDA DEL `FFAB`: el cliente cobró los 777 del FF63 y DESPUÉS mandó el FFAB
#      con su saldo nuevo — o sea **el `FFAB` es una RECONCILIACIÓN de saldo, no un premio**. El
#      "Rank Basico – Rcoin" de las misiones se paga por `FF63`. Sumar rcoin al recibir un `FFAB`
#      atribuyéndolo a `st.ultima_mision` era estructuralmente incorrecto: de ahí los falsos
#      positivos ("la misión 2 con S cobró el set Y 5000") y los FFAB con `misión 0` al entrar al
#      lobby. ⇒ MIGRAR el pago en moneda de FFAB a FF63.
FF63_PROBE = None                 # (1234, 777) fue la corrida que MIDIÓ el rcoin. None = pago real
# ⏳ HOY EL FF63 PAGA 0. Su función crítica —destrabar al cliente— ya la cumple así. El pago de
#   verdad queda pendiente por un problema de ATRIBUCIÓN, no de formato: el `FF63` llega ANTES que el
#   `FF125`, así que en el momento de contestarlo el server todavía no sabe qué misión terminó
#   (`st.ultima_mision` es la ANTERIOR — el mismo error de modelo que teníamos con el FFAB). Para
#   pagar el "Rank Basico – Rcoin" por acá hay que saber qué misión arrancó: el `FF63` de arranque
#   (b0=0) NO trae id, así que el candidato es recordar la última misión LANZADA, no la última
#   completada. Ver tarea #18.
FF63_RESPONDER = True             # False = volver a dejarlo sin contestar (para reproducir el cuelgue)

# ============================================================
# Fase B: DURACIÓN / EXPIRY del inventario
# ============================================================
# Un ítem del inventario puede ser int plano (legacy = permanente) o dict {"id":int,"exp":int} donde
# exp = timestamp UNIX de expiración (0 = permanente). El cliente muestra días restantes = (exp-now)/86400;
# el centinela 0xEEFFCBB8 (=año 2097) es "permanente". Ver docs/PLAN_TIENDA.md §5.
PERM_SENTINEL = 0xEEFFCBB8

# ★ SONDA 2026-07-31: poblar la 2ª lista del MyRecord (`0x5EDF34`) con los packs y su PackCount, a
#   ver si es la lista de CONSUMIBLES y el `u16` son las cargas. Poner en False para volver al
#   comportamiento histórico (2ª lista vacía). Ver la nota larga en build_myrecord.
#   ⛔ MEDIDO 2026-07-31 = **NEGATIVO**. Se mandaron los 2 packs con su PackCount
#   ([(1200002,100),(1200099,30)]); la sonda salió bien formada y la cola quedó intacta, pero los
#   packs siguieron **sin responder al clic** (ni un `FF1A`). ⇒ la 2ª lista, POBLADA ASÍ, no es lo que
#   habilita el uso. Tampoco duplicó ítems (aunque `0x48FFB0` sea la misma rutina que la #37).
#   ⚠ El negativo descarta ESTA forma de poblarla (id + PackCount), no la lista entera: el `u16`
#   podría ser otra cosa (un slot, un tipo, un índice) y entonces habría que medirlo con centinela.
INV_LISTA2 = False

DATE_WIRE_OFFSET_DAYS = 54            # ★ el cliente 2013 muestra (fecha_codificada − 54 días). Medido con 4

# ★ Fase A: familias que ocupan UN slot único (equipar reemplaza la prenda de ese slot).
#   fullset/couplelook ocupan varios slots -> por ahora NO persistimos (eco visual solo). pet/aura/skin: 1 slot.
_MULTISLOT_FAMILIES = {"fullset", "wardrobe_couplelook"}

# ── MODO DE SALA (FF10) ────────────────────────────────────────────────────
# ★ CODIFICACION COMPLETA, medida el 2026-07-29 creando una sala por combinacion (6 capturas, con
#   una prediccion acertada -> modelo verificado). El dialogo del 2013 tiene 4 selectores (el CBT
#   solo tenia 2). Wire: [flags:u8][namelen:u8][name][c0][c1][colab][jefe]
#     flags bit0 0x01 = VELOCIDAD (en 0 = ITEM) · bit1 0x02 = EQUIPO · bit4 0x10 = RELEVO (implica equipo)
#     colaboracion -> flags=0x00 y cola[2]=1     ·   jefe -> flags=0x00 y cola[3]=1
#     (en colaboracion/jefe los selectores equipo/velocidad quedan SIN efecto -> flags=0)
#   c0/c1 no se vieron cambiar: sin identificar.
#   Medidas: solo+vel=0x01 · equipo+vel=0x03 · relevo+vel=0x13 · relevo+item=0x12 (predicho ✓)
MODE_VELOCIDAD = 0x01
MODE_EQUIPO    = 0x02
MODE_RELEVO    = 0x10

# ★★★★★ MÍNIMO DE CORREDORES POR EQUIPO PARA ARRANCAR UN RELEVO (2026-09-05).
#   Por algo se llama relevo: hace falta a quién pasarle la batuta. Con 2 en total (1v1) no hay
#   relevo posible, y una partida así **rompe el cartel** — medida en vivo, ver `MODO_RELEVO.md` §2.5.
#
#   ⚠ Y EL CLIENTE NO LO IMPIDE. Su guard de arranque (`0x592B50`, el que corre antes de mandar el
#     `FF24`) exige tres cosas y **ninguna es ésta**:
#       1. al menos 2 ocupantes EN TOTAL          (`[cRoom+0xB8] - N >= 2`)
#       2. que estén todos listos                 (`[ocupante+0x167]`)
#       3. equipos PAREJOS — y sí corre en relevo (`0x58BFF0`: CoopMode 0, 2 o GameMode 5)
#     Un 1v1 cumple las tres. ⇒ el mínimo por equipo hay que ponerlo NOSOTROS, server-side, que
#     además es la ruta barata: cero parches al ejecutable.
RELEVO_MIN_POR_EQUIPO = 2               # 2v2 el mínimo · 3v3 la sala llena

# ★★★★★ MODO JEFE / "CAPTAIN MODE" — el mínimo por equipo y el sorteo del capitán (2026-09-07).
#   Mismo razonamiento que el relevo, y por la MISMA razón medida: el guard del cliente
#   (`0x592B50` + `0x58BFF0`) mete al jefe en el saco de "esta sala exige equipos", pero **no pide
#   ningún mínimo propio**. Recorridos los ocho sitios donde el cliente pregunta `GameMode == 5`:
#   ninguno es un guard de arranque.
#
#   ⛔⛔ Y ACÁ EL 1v1 NO ES SÓLO FEO: el init de la escena de carrera (`0x4F9D50`) entra sí o sí en
#      el bloque `test word [cGame+0x0c], 0x2000` —el bit que **sólo** tiene el jefe— y ahí:
#          004fabb2  call 0x4EBBF0        ; FindCaptain(equipo) -> **0xFF si no hay capitán**
#          004fabd7  jb  ...              ; 255 < 6 ? NO
#          004fabd9  call 0x74FF1F        ; _invalid_parameter_noinfo  (puede matar el proceso)
#          004fabe4  mov ecx,[edx+esi*4]  ; vector[255] = 1020 B pasado el final -> BASURA
#          004fabe9  call 0x502CF0        ; método sobre un `this` basura -> c0000005
#      ⇒ **si no hay capitán en los DOS equipos, el cliente se cae al arrancar.** Por eso el guard
#        de abajo exige capitanes designados, y no sólo gente.
#   ⚠ Esto está LEÍDO del disasm, no medido en vivo. Si alguna vez se mide y no muere ahí, el
#     sospechoso siguiente es `0x4F3FA0` (el apuntado de ítems, misma compuerta `0x2000`).
JEFE_MIN_POR_EQUIPO = 2                 # 2v2 el mínimo, igual que el relevo
JEFE_SORTEAR_CAPITAN = True             # False = no designar (queda el crash: sólo para medirlo)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★★ EL IMPULSOR DEL MODO JEFE — lo carga EL SERVER, y es una regla NUESTRA (2026-09-07)
#
# ⛔ EN JEFE EL CLIENTE NO CARGA LA BARRA. Lo hace a propósito:
#       00504f7f  test ecx, 0x2000        ; CalcGameFlags. 0x2000 = JEFE
#       00504f85  jne  0x50503f           ; ★ si es jefe, sale sin tocar ningún contador
#   ⇒ sin el `FF176` del server, la barra no sube NUNCA. Medido: en las 5 carreras de jefe del
#     2026-09-07 no salió ni un `FF176` y la barra quedó en cero para los 6.
#
# ★ PERO EL CLIENTE SÍ AVISA. Unas líneas más abajo, en el camino por el que el jefe SÍ pasa:
#       00505082  xor  eax, 0x28          ; 40, desofuscado
#       0050509f  call 0x409e30           ; resto = combo % 40
#       005050b4..d4                      ; 4 compuertas: sin el efecto 0x19 · EQUIPO · VELOCIDAD ·
#                                         ;   NO relevo   -> el jefe (0x2017) pasa las cuatro
#       005050e3  push 0x32 / call 0x5039c0   ; ★ FF4E sub=0x32, sin datos
#   ⇒ cada cliente nos avisa a los 40, 80, 120… de combo. El aviso **no dice cuánto combo**:
#     sólo "llegué a otro múltiplo de 40". La cuenta la lleva el server.
#
# ★ Y CÓMO SE APLICA: `FF176 [n]` (handler `0x5DFEA0`) deja el byte en `[cGame+0x1570]`; al frame
#   siguiente `0x4EAF10` —en su rama exclusiva de jefe, y sólo para el corredor propio— lo lee, lo
#   consume (`= 0`) y llama a `0x4FF9A0`, que **SUMA** (`add edx, ebx`) sobre `[player+0x340]`.
#   ⚠⚠ Y si el resultado PASA el tope, `0x4FF9A0` **pone la barra en CERO** (`0x4FF9E8`). Por eso
#      el server lleva su propio espejo y nunca manda de más.
#
# ★ EL TOPE ES 100 EN JEFE Y 40 EN VELOCIDAD (`0x4FF670`: `mov bl,0x28` / `mov bl,0x64`). Esa
#   diferencia es la que sostiene el diseño de abajo: en velocidad una persona sola llena la barra
#   con sus 40 combos; en jefe hace falta MÁS de un aporte. Los autores subieron el tope a
#   propósito, y eso sólo tiene sentido si la carga viene de varios.
#
# ⚠⚠⚠ LA REGLA DE ABAJO ES NUESTRA, NO DE LOS COREANOS. La original vivía en su server y no la
#   tenemos: se buscó en el exe 2013, en el 2019 con nombres, en los 161 pak y en los comentarios
#   de los devs, y no está. Lo que SÍ es del juego son los dos números (40 y 100) y el hecho de
#   que el aviso exista. Todo lo demás —cuánto, y a quién— lo elegimos nosotros.
#
# EL DISEÑO (propuesto por el usuario el 2026-09-07):
#   La barra es **del equipo**: cuando UNO llega a 40 de combo, suben los TRES de su equipo, y el
#   CAPITÁN un poco más. Explica lo que el usuario vio en un video del juego original —la barra
#   sigue cargando aunque el jugador falle combos—, que con una barra individual no cerraba.
# ══════════════════════════════════════════════════════════════════════════════════════════════
JEFE_IMPULSOR = True                    # ★ interruptor maestro. False = como antes (barra muerta)
JEFE_IMPULSOR_TOPE = 100                # el tope del cliente (`0x4FF695`). NO subirlo: si se pasa,
                                        #   el cliente vacía la barra.

# ⛔ FUENTE 1 — LOS COMBOS. **APAGADA por decisión del usuario (2026-09-07).**
#   Se probó y anda, pero se quedó con la fuente de los ítems sola: es la que él vio en el video
#   del juego original (*"secciones largas que NO recargan, y secciones que sí, y es cuando usan
#   ítem"*), y con las dos prendidas la barra se llenaba demasiado seguido.
#   ⚠ El código queda entero y probado: para volver a prenderla alcanza con este `True`. La señal
#     (`FF4E sub=0x32`) se sigue logueando igual, así que se ve pasar aunque no cargue.
JEFE_CARGA_POR_COMBO = False
JEFE_CARGA_CAPITAN   = 25               # lo que suma el CAPITÁN por cada aviso -> 4 avisos = 100
JEFE_CARGA_COMPANERO = 20               # lo que suman los demás del equipo    -> 5 avisos = 100
#   ★ Los dos dividen a 100 exacto, así que la barra cierra justa y nunca se pasa por redondeo.
#   El capitán llena 25% más rápido: se nota, y no es abusivo.
# ★★ AGRUPAR ANTES DE MANDAR — y esto NO es cosmético. El byte del `FF176` se consume **por
#   frame** (`0x4EB07D`), así que dos paquetes al MISMO jugador dentro del mismo cuadro (~16 ms)
#   pierden el primero. Y en un juego de ritmo los tres compañeros cruzan la nota 40 casi al mismo
#   tiempo ⇒ tres avisos juntos ⇒ cada jugador recibiría tres paquetes pegados y perdería dos.
#   Por eso se junta lo que haya que sumarle a cada uno durante esta ventana y se manda UNO SOLO.
JEFE_CARGA_MS_AGRUPAR = 250             # ms. 0 = mandar al toque (⚠ con 3 en equipo se pierden)

# ★★★★★ SEGUNDA FUENTE DE CARGA: USAR UN ÍTEM (idea del usuario, 2026-09-07)
#   Mirando un video del juego original: *"veo secciones largas de juego que NO recargan el
#   impulsor, y secciones que SÍ recargan — a sí mismo o a aliados — y es cuando usan ítem"*.
#
#   ✅ SE PUEDE, y el cliente da todo lo que hace falta:
#     `0x50C9B0` es el despachador de acciones de carrera; su acción `0xC8` (`0x50CAEE`) es
#     **usar ítem**. Las acciones de efecto llaman a `0x50A490(idEfecto, slot, …)`, que aplica
#     el efecto y **lo anuncia**: `0x50A5A4` -> `0x5039C0` con eventId **1** ⇒ `FF4E sub=0x01`,
#     y el **id del efecto va en el dato**.
#
#   ⚠⚠ Y ACÁ ESTABA LA TRAMPA, que el usuario vio antes que yo: **el disparo del impulsor del
#     jefe usa el MISMO evento**. Verificado:
#         0050c7d5  cmp eax, ecx / jl        ; ¿la barra llegó al tope?
#         0050c7e5  push 0xf3                ; ★ el efecto del impulsor del jefe
#         0050c7ed  call 0x50a490            ; -> se anuncia como sub=0x01
#     Cargar con cada `0x01` sería el impulsor recargándose a sí mismo.
#     ⇒ Por eso se EXCLUYE el `0xF3`. Es justo lo que propuso el usuario: *"si el server sabe que
#       el impulsor usado fue el morado, no lo cuenta; si es otro ítem, sí recarga"*.
#   ★★ ÉSTA ES LA FUENTE QUE QUEDÓ VIVA (la de los combos está apagada, ver arriba).
JEFE_CARGA_POR_ITEM         = 10        # a los COMPAÑEROS de equipo. 0 = apagar esta fuente
# ★★★★★ 2026-09-07 — DE 15 A 25 (de 7 ítems a 4). ES UN AJUSTE DE BALANCE, Y SALE DE MEDIR.
#
#   ⛔ EL SÍNTOMA, reportado por los jugadores: *"el jefe siempre llega último"*, y de los dos
#     equipos. El usuario explicó el mecanismo: en modo jefe **todos le tiran los ítems al jefe
#     enemigo**, así que se pasa la carrera frenado, y el impulsor es lo único que lo compensa.
#
#   ★ MEDIDO SOBRE EL LOG DE PRODUCCIÓN (`taller/_analisis/`, 28 partidas · 86 min de juego):
#         · el **65,6 %** de los ataques van al jefe, cuando por azar le tocaría ~33 %.
#           ⇒ **come el DOBLE de castigo** del que le corresponde. El reporte era correcto.
#         · recibe un ataque **cada 2,7 s** y con el 15 conseguía un impulso cada 9,1 s,
#           o sea **3,3 ataques por impulso**.
#
#   ★ Y LA SIMULACIÓN, sobre esas mismas partidas (`taller/_analisis/simular_impulsor.py`: los eventos
#     son reales, lo único que cambia es este número):
#         +15 (7 it) -> 1 impulso c/9,1 s -> 3,3 ataques por impulso   (lo que había)
#         +17 (6 it) -> 7,7 s -> 2,8
#         +20 (5 it) -> 6,4 s -> 2,4
#      ★  +25 (4 it) -> 5,1 s -> 1,9  ← ACÁ. Duplica los impulsos (568 -> 1008) y con eso
#                                       compensa el doble de castigo, que es exactamente el
#                                       desbalance medido. Ni más ni menos.
#         +34 (3 it) -> 3,8 s -> 1,4  (2,4× los impulsos: se pasa)
#         +50 (2 it) -> 2,5 s -> 0,9  (impulso casi permanente)
#
#   ⚠ POR QUÉ NO MÁS: con las dos fuentes prendidas el usuario ya vio que *"la barra se llenaba
#     demasiado seguido"* y apagó la de combos. Pasarse acá lleva al mismo lugar por otra puerta.
#   ⚠ LO QUE ESTO **NO** PROMETE: un puesto de llegada. Cuánto empuja el impulso y cuánto frena
#     cada ataque lo maneja el CLIENTE, no nosotros. Lo medido y simulado es cuántos impulsos gana
#     y cada cuánto. Si con esto sigue llegando último, el sospechoso pasa a ser la FUERZA del
#     impulso, no su frecuencia — y esa no se toca desde acá.
#   ⇒ Para volver a medir: `python taller/_analisis/simular_impulsor.py` con un log nuevo.
JEFE_CARGA_POR_ITEM_CAPITAN = 25        # ★ al CAPITÁN, que llena en 4 ítems contra 10
#   ⚠ El 25 SÍ divide a 100 (4×25 = 100 exacto), a diferencia del 15 que dejaba el último tramo
#     recortado. Igual el recorte a `JEFE_IMPULSOR_TOPE` sigue estando: pasarse VACÍA la barra.
JEFE_EFECTOS_QUE_NO_CARGAN = (0xF3,)    # ★ el impulsor del jefe. NO sacar el 0xF3 de acá.
# ★★★ DÓNDE VIAJA EL ID — CORREGIDO CONTRA EL LOG (2026-09-07, primera corrida real).
#   Yo había supuesto que el `A` de nuestro descifrador **era** el id. **Falso**, y la red de
#   seguridad lo cazó sola: el log se llenó de `efecto id=33685760 fuera de rango -> NO cargo`.
#   El `A` es un u32 con TRES bytes empaquetados. Lo arma `0x5039C0`:
#       00503a32  shl cx, 8          ; cl -> byte 3
#       00503a40  shl ax, 8          ; al -> byte 1
#       00503a44  or  edi, edx       ; dl -> byte 2
#       00503a49  shl edi, 0x10 / or edi, ecx
#     ⇒ `A = (cl << 24) | (dl << 16) | (al << 8) | 0`   ← el byte 0 NUNCA se usa
#   Y para el evento de efecto (`sub=0x01`), medido sobre las 7 muestras de la corrida:
#       al (byte 1) = ★ EL ID DEL EFECTO       (salieron 1, 10, 11 y 15)
#       dl (byte 2) = el slot del que lo usó   (coincidió con `st.room_slot` en las 7)
#       cl (byte 3) = el slot al que le pegó   (slot 1 usó uno sobre el slot 2)
#   ⇒ el id es **`(A >> 8) & 0xFF`**, y por eso es un BYTE: el rango va hasta 255.
JEFE_EFECTO_ID_MAX = 255



# ★★★★★ MANDAR EL EQUIPO TAMBIÉN AL **PADRÓN** DEL CLIENTE, con un `FF37` por asiento ocupado.
#   Hay DOS lugares donde el cliente guarda el equipo, y hasta el 2026-09-07 llenábamos uno solo:
#       · `[asiento+0x157]`  = el COLOR de la grilla de la sala  -> lo escribe el `FF99`
#       · `sRoomUser+0x4A`   = el PADRÓN `[0x931660]`            -> ★ lo leen las DECISIONES
#   `0x4EC970` (GetTeam) devuelve el segundo y tiene **78 llamadores**; entre ellos el guard del
#   START (`0x592B50`), que cuenta "equipo 1" contra "el resto" y **exige que empaten**.
#   ⇒ Con el padrón en cero, una sala 3v3 se lee 0 contra 6 y el cliente ni manda el `FF24`.
#      Síntoma exacto: *"El juego comenzará cuando hayan suficientes usuarios"* con la sala llena.
#   El único escritor de ese byte es `0x4EC8F0`, con **siete** llamadores, y el handler del `FF0C`
#   NO es uno de ellos: se llega por `FF37` (`0x592D90`) o por `FF175` (`0x5958A0`).
#   ⚠ Apagarlo si aparece un efecto visual repetido al entrar a la sala: ver la nota de
#     `enviar_equipos` sobre `0x5AFFD0`, que es el sospechoso.
EQUIPO_AL_PADRON = True

# ★★★★★ CARTELES DEL CLIENTE QUE EL SERVER PUEDE SACAR — `FF68 [n]` (2026-09-05).
#   El handler `0x5D0DC0` es de tres líneas y es una palanca enorme:
#       read(1) -> n  ·  eax = n + 0xFF  ·  0x433380 (tabla de textos)  ·  0x4946D0 (popup)
#   ⇒ **`FF68 [n]` abre un cartel con el texto número `255 + n`**, con las palabras del propio
#     cliente y ya traducidas. Alcance: 255..510. Ni inventamos texto ni parcheamos nada.
#
#   La tabla se lee con `taller/re2013/strings_cliente.py`, que la saca del PROPIO cliente 2013
#   (`rnr_script/string_lt/system.csv`, 947 entradas) desempacándolo con `taller/re2013/desempacar.py`.
#
#   ⚠⚠ NO SIRVE LA TABLA DEL CLIENTE CHINO DE 2018. Tiene 2931 entradas y **diverge**: los
#     números bajos coinciden, los altos no. Elegí el 390 leyendo la china —allá dice "se
#     necesitan al menos 4 jugadores"— y en el 2013 el 390 es un aviso sobre Rcoin irregular.
#     El cartel habría salido completamente equivocado. *La coincidencia de los primeros
#     doscientos no prueba nada de los otros setecientos.*
FF68_BASE = 255                         # `FF68 [n]` muestra el texto `FF68_BASE + n`
STR_MIN_2_JUGADORES = 389               # "Por lo menos deben haber dos participantes en el juego."

# ★★★★★ `FF36 [codigo]` — LA RESPUESTA "NO SE PUEDE ARRANCAR" (2026-09-05).
#   Handler `0x5CE7F0`. Hace las DOS cosas que hacían falta:
#     1. saca el cartel que le corresponde al código, con el texto del cliente, y
#     2. ★★ `mov byte [cRoom+0x93F0], 0` — **DESBLOQUEA EL BOTÓN START**.
#   Ese `+0x93F0` es el "ya apreté empezar" que pone `0x59AE9F`. Sin bajarlo, el host queda
#   trabado sin poder hacer nada: es exactamente lo que reportó el usuario al rechazar por chat.
#   ⚠ Y con esto el `FF68` deja de hacer falta para este caso: el `FF36` llega a textos que el
#     `FF68` no alcanza (el 254 y el 74 están por debajo de su base de 255).
FF36_TODOS_LISTOS    = 1                # texto  73 "El juego comenzará cuando todos estén listos."
FF36_FALTAN_USUARIOS = 2                # texto  74 "…cuando hayan suficientes usuarios."
FF36_NO_JUGAR_SOLO   = 3                # texto  75 "No puede iniciar el juego solo en Multi juego"
FF36_RELEVO_1V1      = 5                # texto 254 ★ "No puede competir 1:1 Batalla de Relevos."
FF36_COMPOSICION     = 4                # texto 207 ★ "No puede iniciar el juego con la composición
#                                       #             actual" — el del MODO JEFE (verificado en el
#                                       #             disasm: `0x5CE82B cmp al,4 / push 0xCF`).
#   (6 -> texto 57 · 7 -> el nº 7 de OTRA tabla, `0x9D50F8`: sin identificar)

# ★★ Encoding del byMode de la RESPUESTA del FF4B (el portador del modo, hallado 2026-07-30).
#   El `flags` que manda el cliente usa bit0=velocidad · bit1=equipo · bit4=relevo, pero el byMode
#   INTERNO puede tener otra distribucion: en el CBT-2011 era bit4=equipo · bit2=ITEM (velocidad =
#   bit2 en 0), o sea que alla request != byMode y hacia falta traducir.
#   Candidatos, para medir en vez de adivinar (una sala por corrida y listo):
#     "cbt"  = traduccion del CBT: bit4 equipo · bit2 item                 <- 1er intento
#     "eco"  = el flags CRUDO del cliente (hipotesis: misma distribucion)
#     "cbt+relevo" = como "cbt" pero conservando el bit4 del relevo aparte (bit5)
#   ★ MEDIDO 2026-07-30 con "cbt": el usuario pidio relevo+item (flags=0x12), mandamos byMode=0x14
#     y el cartel de la sala paso a **"item + equipo"**. ⇒ **bit2 = ITEM y bit4 = EQUIPO quedan
#     CONFIRMADOS tambien en el 2013** (el CBT acerto en esos dos). Lo unico que falta es el bit del
#     RELEVO, que en el CBT no existia (alla no habia relevo).
FF4B_BYMODE_ENC  = "cbt"
# ✅ CONFIRMADO en vivo (usuario, 2026-07-30): **str1 = el TITULO de la sala**. Se nota porque el
#    cliente rota frases hechas en cada FF4B ("Sala para usuarios educados.", "En busca de
#    jugadores...", "¡Bienvenido!~", "Disfrute el R2beat!", "¿Hay alguien listo para el juego?") y al
#    reflejarlo el titulo de la sala cambia con cada cambio de modo. (Los "indices numericos" que
#    parecian salir de 0x46C120/0x46C190 son otra cosa.)
FF4B_STR1_NOMBRE = True     # str1 = TITULO de la sala (echo). False = string vacio.

# ★ SONDA del bit de RELEVO: se prenden TODOS los candidatos a la vez (valido porque son bits
#   sueltos) y despues se bisecta -> 1 corrida en vez de 3. Se EVITA el 0x80 a proposito: en el CBT
#   ese bit era la variante COUPLE y podria mandar la sala a modo pareja.
#   ⛔ CORRIDA 1 (2026-07-30): byMode=0x3D (equipo|item|0x20|0x08|0x01) -> el cartel siguio en
#      "item + equipo" ⇒ **0x20, 0x08 y 0x01 DESCARTADOS**.
#   ⛔ CORRIDA 2 (2026-07-30): byMode=0x56 (equipo|item|0x02|0x40) -> igual "item + equipo"
#      ⇒ **0x02 y 0x40 DESCARTADOS**. Con eso el byMode queda AGOTADO salvo el 0x80 (que en el CBT
#      era la variante couple) ⇒ **el RELEVO no es un bit del byMode**.
#   ⏳ CORRIDA 3: los 5 u8 de la COLA del FF4B, que hoy van casi todos en cero. r7 es un ARGUMENTO
#      PROPIO del applier 0x5971F0 (igual que los flags que salen de r9/r11), asi que es el mejor
#      candidato. Se prenden r7, r8 y r10 juntos y despues se bisecta.
#   ★★ CORRIDA 3 (2026-07-30): con la cola en r7=r8=r10=1 la sala se fue a **modo COOPERATIVO**.
#      Positivo, pero de OTRO modo: ⇒ el **colab sale de alguno de r7/r8/r10** (y NO de r9, como
#      habia supuesto por los flags del handler). El RELEVO sigue sin aparecer.
#      Siguiente: bisecar r7 / r8 / r10 con FF4B_COLA_PROBE para fijar cual es el colab.
# ★ ESTADO DEL MAPEO (medido en vivo 2026-07-30, reporte del usuario):
#     ✅ solo/equipo  -> byMode bit4      FUNCIONA
#     ✅ velocidad/item -> byMode bit2    FUNCIONA
#     ❌ relevo        -> NO esta en el byMode (todos los bits menos 0x80 descartados) ni en r7/r8
#                        como bandera de 1. Hipotesis nueva: r7 es un ENUM de modo de equipo
#                        (0=solo? 1=equipo? 2=relevo?) -> se prueba r7 = 2.
#     ✅ cooperativo   -> **r9 = 1**  CONFIRMADO POR AISLAMIENTO 2026-07-30: se lo mande como sonda
#                        del "jefe" (cola=[0,0,1,0,0]) y la sala se fue a COOPERATIVO.
#                        (Encaja con la corrida grande: la tupla (0,1,2) eran r7/r8/**r9**, no r10.)
#     ⛔ r10 = 1 no hace nada (se lo mande en colab y la sala quedo en item+solo).
#     ✅ jefe          -> **r11 = 1**  CONFIRMADO 2026-07-30 (el otro byte del `bySuperRoomCoupons`:
#                        r9 -> bit2 = cooperativo, r11 -> bit3 = jefe. "SuperRoom" era la de jefe).
#     ✅ relevo        -> `byMode` **bit7 = 0x80**  CONFIRMADO 2026-07-30. (En el CBT ese bit era la
#                        "variante couple"; en el 2013 el couple es roomtype 6 aparte y el bit quedo
#                        reusado para el relevo.) Se llego por eliminacion: era el ultimo bit libre.
#   ⛔ Descartados por medicion para el relevo: bits 0x01/0x02/0x08/0x20/0x40 del byMode · r7=1 ·
#      r8=1 · r10=1 · r7=2 como enum de equipo.
#   Cada sonda se activo SOLO para su propio modo, asi cada corrida respondia varias sin mezclarlas.
FF4B_RELEVO_BITS = 0x80                 # ✅ bit7 = RELEVO (confirmado)
FF4B_COLA_COLAB  = (2,)                 # ✅ r9  = COOPERATIVO (confirmado)
FF4B_COLA_JEFE   = (4,)                 # ✅ r11 = JEFE        (confirmado)
FF4B_COLA_RELEVO = ()                   # (el relevo se prueba por VALOR en r7, no por bandera)
FF4B_RELEVO_R7   = 0                    # ⛔ r7=2 como enum de equipo: descartado. 0 = no tocar r7.
FF4B_COLA_PROBE  = ()                   # sonda manual apagada

# ★ ULTIMO TRAMO: mandar el FF4B TAMBIEN al crear la sala, para que el modo elegido en el dialogo de
#   CREACION se aplique sin que el usuario tenga que abrir la config. El modo sale del propio FF10
#   (mismo formato que el FF4B), asi que no hace falta nada nuevo.
#   ⚠ En el CBT un FF4B NO PEDIDO abria el popup "el modo cambio" (por eso alla lo dejaron de mandar y
#     usaban un FF13 silencioso). Si acá pasa lo mismo, hay que buscar la via silenciosa del 2013 en
#     vez de este atajo. Se enciende ahora que los 5 selectores estan mapeados.
FF4B_AL_CREAR = True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★ MODO COOPERATIVO = "GROUP RACING" / CHASE (perseguir al GORILA) — 2026-07-30
#
# Cómo funciona (segun el usuario + los assets del cliente):
#   - En este modo NO se elige musica: entran los jugadores, el master da START y se cargan
#     **3 canciones** con sus charts REALES, que se van consumiendo y rotando. Si se terminan las 3
#     sin atrapar al gorila = se pierde; si lo atrapas antes, se gana.
#   - La PISTA no la fija el server a ciegas: el cliente tiene una pantalla propia de seleccion de
#     mapa para este modo -> clase `cChaseStageSelect` (`.\GroupRacing\cChaseStageSelect.cpp`,
#     codigo en 0x56B280..0x56B882) que arma `rnr_room/groupracing_mapselect01.spr` y `…02.spr`.
#     ⇒ mandar `room_map` normal (11 = MARAVILLA ESPACIAL) es justamente lo que hacia cargar la
#       pista equivocada.
#   - Assets del modo en `rnr_group_racing.pak`: gorila con sus animaciones (run/throw/rope/win/
#     lose/status_lv1..4), cocos y bananas, cuerda y cohete del jugador, cajas de premio
#     (wood→jewel), rangos S..F, `script/groupracingcontrol.xml` (fail anivel=5.0, boost vel=1.06
#     time=180 frequency=40 rocketvel=1.1, item frequency=900), `script/bossnpc.xml`,
#     `itemtable.txt`/`itemappear.txt`/`npcitemtable.txt`, y sonidos `Chase_*`.
#
# Estado: se cablea (a) las 3 canciones, y (b) satisfacer el gate de "elija una musica" solo, para
# poder llegar al START y CAPTURAR el resto del protocolo del chase (map-select + rotacion).
# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ INTERRUPTOR MAESTRO DEL CHASE — dejarlo en False = "ESTADO BUENO CONOCIDO" (2026-07-30)
#
#   False (estado actual)  = como estaba ANTES de tocar el chase, y ese estado **SI FUNCIONABA a
#     medias**: eligiendo la musica en OTRO modo y volviendo a cooperativo, el START arrancaba,
#     **salia el mini intro y APARECIA EL GORILA**... pero con **1 sola cancion** y en la **pista
#     equivocada** (map 11 = MARAVILLA ESPACIAL / "space wonder").
#     ⇒ Es el punto de partida para retomar: hay mono, falta pista y falta la rotacion de 3 temas.
#
#   True = enciende los 3 experimentos de esta sesion, TODOS SIN EXITO todavia:
#     (a) `CHASE_MAP` (pista fija del modo, candidato 102 = m_back03/forest.bin)
#     (b) FF25 con songcount=3 + los 3 songids
#     (c) PlayData automatico para no tener que usar el picker
#     ⛔ Con esto encendido el usuario NO pudo arrancar: seguia saliendo "elija una musica", y al
#        forzarlo cambiando de modo la partida arrancaba **sin el mono, en velocidad y en space
#        wonder** (o sea PEOR que con el interruptor en False).
#     Hipotesis para la proxima: el gate de la cancion no lo satisface nuestro FF139 PlayData en
#     cooperativo (el applier 0x5BA510 exige que el songid coincida con el que el cliente guardo
#     local en `[[0x9314ec]+4]+0x594`, y en cooperativo el cliente quizas nunca guarda ninguno).
#     Medirlo con `re/trace_chase_gates.py` ANTES de volver a tocar el server.
CHASE_EXPERIMENTAL = False

CHASE_NUM_CANCIONES = 3               # el modo consume 3 canciones (dato del usuario)

# ★★★ "Manera de Lista de juego" = `[[0x9314ec]+0x48]` (el selector de abajo a la izquierda del panel
#   "Info Musica"). El gate del boton START exige que valga 2 o 3, O que haya canciones seleccionadas.
#       1 = En orden · 2 = Aleatorio · 3 = TOP 20 ALEATORIO · 4 = NUEVOS 20 ALEATORIO
#   En sala el default es 4 -> por eso pedia "seleccione musica". 2 = Aleatorio es lo que el
#   cooperativo hace por diseño. Poner None para NO mandar el FF1C (volver al comportamiento viejo).
#   ★★★ QUIEN LO ESCRIBE (disasm, 2026-08-04): UNA sola funcion,
#   `cRoomMusicSelect::SetPlaySequence(mode,...)` = **`0x5BF2C0`**. Y el que la invoca es el campo
#   **`type`** del FF1C — hay una TABLA DE SALTOS (`0x5CE778`, indice `0x5CE7D0`) en el handler
#   `0x5CE4C0`. O sea que el modo NO viaja en `byMusicLoopType`: viaja en el `type`.
#       type 5    -> SetPlaySequence(1)   (speed random)
#       type 6    -> SetPlaySequence(0)   (en orden)
#       type 0x1F -> SetPlaySequence(2)   ★ TOP 20      -> EXENTO del gate del START
#       type 0x20 -> SetPlaySequence(3)   ★ NUEVOS 20   -> EXENTO del gate del START
#   ⚠ ERROR PROPIO CORREGIDO: mandamos `type=5, byMusicLoopType=2` y `+0x48` quedo en **1**. Lo lei
#     como "interno = cable − 1" y era casualidad: el 1 lo puso `type=5 -> SetPlaySequence(1)`. El
#     `byMusicLoopType` no se usa para esto. Una sola medicion alcanzo para inventar una regla falsa.
#
#   Los 4 modos, por el NOMBRE DEL BOTON que busca la propia `0x5BF2C0`:
#       0 `Button_play_sequence` (En orden)   -> exige seleccion
#       1 `Button_speed_random`  (Aleatorio)  -> exige seleccion
#       2 `Button_paly_top20`    (TOP 20)     -> ★ la lista la arma el JUEGO, sin seleccion
#       3 `Button_paly_new20`    (NUEVOS 20)  -> ★ idem
#       4 = "sin sala" (lo escribe la misma funcion cuando `[cRoom+0x9574] != 0x1fef`)
#
#   ★★★ CAUSA RAIZ de por que en cooperativo esto queda sin setear:
#   `cRoomMusicSelect::Show()` (`0x5C0230`) arranca con
#       `cmp dword [[0x9314c0]+0x9564], 4 ; je salir`
#   ⇒ **con GameMode 4 se saltea ENTERA**, y es ella la que normalmente llena los vectores, aplica el
#   filtro (escribe `+0x4c`) y llama a `SetPlaySequence` (escribe `+0x48`). Es INTENCIONAL: el
#   cooperativo tiene su propia UI de sala en `[cRoom+0x10e9c]`. Por eso hay que darle el modo por red.
# ★★★★ EL FF1C QUE CONSTRUYE EL PICKER DE MÚSICA DE LA SALA (2026-09-03).
#   Se manda al ENTRAR a cualquier sala, no sólo en cooperativo. Es la causa del diluvio de
#   `FF3D` (~59/s, uno por frame): sin ese paquete el picker de sala nunca se construye, y la
#   Update por-frame del cliente lo desreferencia igual. Ver el comentario largo en
#   `lobby_salas`, donde se manda.
#   ⚠ Si al entrar a una sala aparece algún diálogo de selección de música que antes no salía,
#     es esto: se apaga acá.
FF1C_AL_ENTRAR = True

# ⛔ ACÁ VIVIÓ `MYRECORD_AL_ENTRAR_A_SALA` (2026-09-17), para matar el ítem fantasma que
#   reaparecía al entrar a una sala. También se cayó: el fantasma lo creaba el `FF69` nuestro,
#   no la entrada a la sala. Ver la nota larga junto a las campanas.
#   ⚠ Y no era gratis: cada `FF69`/`FF6A`/`FF3E` dispara una reconstrucción COMPLETA del panel
#     (`0x4CF340`, que vacía el vector del panel y lo rehace leyendo `[0x9314E0]+0x164`). Entre el
#     MyRecord, los 9 `FF69` de cargas y los `FF3E`, eran ~15 reconstrucciones por entrada a sala
#     — el repintado que anonimo03 escuchaba: *"escucho repintados, y eso es esconder el problema"*.

# ★★★★★ EL PICKER TAMBIÉN EN EL LOBBY (2026-09-05) — contra el diluvio de `FF3D`.
#   `FF1C_AL_ENTRAR` construye el picker al entrar a una SALA, y eso arregló el diluvio de la sala.
#   Pero **el diluvio también arranca en el LOBBY**, antes de pisar ninguna sala: medido con seis
#   clientes a la vez, los seis empiezan en el MISMO punto —justo después del `FF1C type=5` del
#   login— y mandan ~52 `FF3D` por segundo, uno por frame, hasta que se cierra el juego.
#   Comparación con el server que funciona (capturas del 02-09): **31 a 284 `FF3D` por sesión**.
#   La nuestra del 03-09 13:21: **113.470**. O sea que el problema es nuestro y ya existía antes.
#   ⚠ Y NO es el eco: el referente también contesta `05 00 00 02 20` byte por byte igual que
#     nosotros. Lo que él manda y nosotros no es el `1f 00 00 00 ff` TEMPRANO.
#   ⇒ Se manda el mismo paquete al terminar el saludo del lobby. Es una PRUEBA: si el diluvio no
#     baja, apagar esto y buscar por otro lado — no dejarlo puesto "por si acaso".
#   ★★ PRENDIDA el 2026-09-04, y ahora con la causa MEDIDA, no supuesta:
#     · El `FF3D` NO es "el cliente sin entender": es un **reporte de error de audio**. La
#       función que lo manda (`0x5C89B0`) la dispara `0x4EA450`, que tiene los dos textos
#       en el exe: *"[Error] Bgmfile is null"* y *"[Error] Can not find the sound device"*.
#       Justo antes de prender el aviso, el cliente loguea `"[BGM Error] file : %s"`.
#     · `0x4EA450` **apaga el bit apenas lo manda** ⇒ 13.789 envíos no son uno pegado: es el
#       mismo fallo repitiéndose **una vez por cuadro**.
#     · Y lo manda **SÓLO EL ANFITRIÓN** (`[cRoom+0x9574] ^ 0x1fef == 0`). Por eso de seis
#       clientes inunda uno solo — medido: 13.530 de 13.789 con contador consecutivo.
#     · ★ EL MOMENTO, del log del 04-sep 14:35:59 (conexión `:5565`, usn 3):
#           recv_ctr=9  -> FF1C     (el del login, que NO contestábamos)
#           recv_ctr=10 -> FF13B
#           recv_ctr=11 -> FF3D     ← ★ arranca acá, **en el LOBBY**, 1 s después de entrar
#                                      al canal y 13 s ANTES de que exista ninguna sala.
#   ⇒ Las dos puntas coinciden: el aviso es "no pude abrir un archivo de música", y arranca
#     justo donde el picker del lobby se queda sin construir. Se prende.
#
# ⛔⛔⛔ APAGADA EL 2026-09-07: **ESTE PAQUETE ES EL QUE MATA A LOS JUGADORES DE HARDWARE
#   MODESTO**. Es la causa del crash `0x006840E7` que veníamos persiguiendo desde el 05-sep.
#
#   MEDIDO, no deducido, en una laptop con Intel HD Graphics 5500 y Windows 10, contra el
#   servidor LOCAL, con la cuenta del jugador que reportó el problema (uid 6735) y variando
#   ESTA SOLA LINEA:
#
#       FF1C_EN_EL_LOBBY = True   ->  ⛔ crash a los ~30 s ·  c0000005 00000000 006840E7
#       FF1C_EN_EL_LOBBY = False  ->  ✔ vivo 192 s, entra al canal, `GuildInfo`, todo normal
#
#   Y la dirección del crash es EXACTAMENTE la que reportó `jugador19` (Intel HD 500). En su
#   `network_*.log` y en el de la laptop, la secuencia es la misma, byte por byte:
#       [MUSIC] SendEditMusicFromRoom (5 0, 2 128)     ← el cliente manda su type 5
#       [CASH][Get] error 0 0
#       [MUSIC] CmdEditMusic type:31, ...              ← ★ NUESTRO 0x1F
#       EXCEPTION_ACCESS_VIOLATION en 006840E7         ← muere acá mismo
#
#   ★ QUE PASA ADENTRO. `0x6840D0` es un getter genérico: compara el índice contra la CANTIDAD
#     (`[ecx+0xA0]`) y, si pasa, lee `[ecx+0x40] + índice*8`. Con el `0x1F` recibido **en el
#     lobby** el cliente cree tener 14 entradas y el arreglo **nunca se creó** ⇒ lee la dirección
#     0x68 = 13×8. Es el mismo defecto de forma que ya medimos en `0x005C5A6B`: el cliente de
#     2013 usa lo que le decimos sin comprobar que exista.
#
#   ⚠ POR QUE SOLO A ALGUNOS: en una máquina moderna la estructura ya está construida cuando
#     llega el paquete y no pasa nada. En una lenta —HDD, gráficos integrados— el paquete gana la
#     carrera y llega antes. Encaja con el cartel *"no hay salas disponibles"* que el jugador ve
#     **durante los logos**: el cliente está armando la lista antes de tiempo.
#
#   ⇒ Y esto lo pusimos NOSOTROS el 04-sep. El servidor de referencia manda el `0x1F` sólo al
#     ENTRAR A UNA SALA (`FF1C_AL_ENTRAR`), nunca en el lobby. La idea era cortar el diluvio de
#     `FF3D`; el precio era matar a los jugadores con hardware lento.
#
#   ✅ Y EL `0x1F` AL ENTRAR A UNA SALA (`FF1C_AL_ENTRAR`) ES SANO — comprobado en la misma
#     laptop, en una sala de verdad con dos jugadores: lo recibió DOS veces
#     (`CmdEditMusic type:31` a los 0:27:37 y 0:28:03) y no se cayó. Tiene sentido: ahí el
#     cliente ya tiene la sala construida y el paquete no le gana ninguna carrera.
#     ⇒ Lo que hay que sacar es SÓLO el del lobby. `FF1C_AL_ENTRAR` se queda.
#
#   ⏳ El diluvio de `FF3D` queda otra vez abierto — pero es ancho de banda, no un crash. En la
#     corrida de prueba con esto apagado se contaron 36 `FF3D` en 192 s, o sea que en el lobby
#     no reaparece; el caso del anfitrión dentro de una sala está sin volver a medir.
FF1C_EN_EL_LOBBY = False

CHASE_FF1C_TYPE = 0x1F

# ★ PREMIOS de la caja del chase (una entrada por caja; se barajan en cada victoria, asi que elegir
#   caja importa). Van como **RCoin** (`type=1`) porque es el unico premio 100% seguro: un itemId que
#   no exista en la tabla del cliente lo CRASHEA (`0x57C038` usa el resultado de FindItem sin chequear
#   NULL). Para repartir ropa habria que validarla antes contra el shop_lt.
#   ★ SON 6: el cliente dibuja una grilla FIJA de 6 cofres (visto en pantalla). Mandando menos, los
#     cofres sobrantes quedan dibujados pero vacios.
#   ★★ REPARTO como el original (descripcion del usuario, y el wire lo soporta nativo):
#      una caja puede estar VACIA (`M=0`), traer RCOIN (`type=1`), o traer **UNA MONEDA GORILA**, que
#      es un byte propio por caja (`coin=1`) y por eso solo le toca a uno o dos jugadores.
#      Cada fila = (rcoin, monedas_gorila). Se BARAJA en cada victoria, asi elegir caja importa.
# ★ Fracción de la exp que se lleva el jugador si el gorila se le ESCAPA. Es una decisión de DISEÑO
#   nuestra (el juego no la dicta): 0.5 = la mitad, por haber jugado igual las canciones.
#   1.0 = sin penalización · 0.0 = nada.
CHASE_EXP_DERROTA = 0.5

# ★★★ EL COOPERATIVO PAGA EL DOBLE — y esta vez NO es una perilla inventada: está MEDIDO.
#   El usuario lo recordaba del juego original ("pagaba como 2x o 2.5x, por eso es largo y
#   son 3 canciones"), y la captura del 2026-09-02 lo confirma sobre el mismo server y la
#   misma sesión, con jugadores de precisión equivalente:
#
#       cooperativo (3 canciones)   6 carteles · 33 filas · exp promedio 2037 · pd 84.6
#       una sola canción            5 carteles · 21 filas · exp promedio 1008 · pd 86.2
#       ⇒ 2.02x
#
#   ⚠ Ojo con la lectura fácil: son 3 canciones, así que si la exp fuera aditiva por canción
#     daría 3x. Da 2x. O sea que **no es "tres canciones, tres veces la exp"**: es un
#     multiplicador propio del modo. Por eso va como factor y no como suma por canción.
#   El Rcoin NO se multiplica: en la captura da 33.2 contra 31.9, o sea igual.
CHASE_EXP_MULT = 2.0

# ★★★ EL BONO INVISIBLE POR SALA LLENA — vale para TODOS los modos, no sólo el cooperativo.
#   Es un incentivo para jugar acompañado que el juego nunca anunció en pantalla.
#
#   ⚠ NO está en la captura: ese server NO lo implementa. Medido, exp por punto de
#     precisión, misma sesión:
#         una canción   3 jugadores 12.5 · 4 jugadores 11.9 · 5 jugadores 11.2
#         cooperativo   5 jugadores 24.2 · 6 jugadores 24.0
#     Plano, o incluso bajando un poco. Así que esto NO es "restaurar lo que hace el otro
#     server": es diseño, y hay que leerlo como tal.
#
#   Lo que sí lo respalda son DOS fuentes independientes que caen en el mismo tope:
#     · el recuerdo del usuario: "con la sala llena el primero llegaba como a 1500 cuando
#       normalmente sacabas 1000" ⇒ 1.5x
#     · `groupbonus.xml` del cliente chino desempacado: 2 personas +15% · 3 +30% · 4 +40%
#       · 5 +50% ⇒ tope 1.5x
#     ⚠ Ese xml es del cliente CHINO de 2018 y el nuestro no lo trae; además sus ítems son
#       de la tienda de amigos, así que su `person` podría contar miembros del grupo y no
#       ocupantes de la sala. Se usa como forma de la curva, no como prueba.
#
#   Se aplica SÓLO a la exp. El Rcoin no: en la captura no se mueve ni con el modo
#   (33.2 en coop contra 31.9 en una canción) ni con la cantidad de gente.
#   "Reduciendo por posición" ya lo hace `RANK_BONUS_POR_PUESTO`; esto es un factor parejo
#   para toda la sala, encima de eso.
#   ✅ APROBADO por el usuario el 2026-09-02 mirando la tabla resultante, ACUMULACIÓN
#     INCLUIDA: los dos factores se multiplican, así que un cooperativo con la sala llena
#     paga `2.0 x 1.5 = 3x`. Con un jugador de pd 85 eso es:
#         1 canción   1050 solo  ->  1575 con la sala llena
#         cooperativo 2100 solo  ->  3150 con la sala llena
#     No es un descuido: se le mostró la cuenta y dijo que estaba bien. Si algún día
#     parece demasiado, se baja acá o en `CHASE_EXP_MULT` — pero no es un bug.
BONO_POR_JUGADORES = {1: 0.00, 2: 0.15, 3: 0.30, 4: 0.40, 5: 0.50, 6: 0.50}

# ★★★★★ 2026-09-02 — EL TABLERO ES SIEMPRE DE 6 Y NINGUNA CAJA VA VACIA (regla del usuario).
#   Como funciona el minijuego: elige primero el que mas aporto al gorila, despues el siguiente,
#   y asi; cada uno se lleva UNA caja de las que quedan. Al final se revela el contenido de
#   TODAS. O sea que es una loteria: las 6 tienen premio y lo que cambia es cuanto.
#   ⛔ Lo de antes estaba mal por dos lados y se vio en vivo: el tablero se armaba con
#      `len(jugadores)` cajas (2 en una partida de 2) mientras la pantalla dibuja SEIS, y ademas
#      dos de las seis filas eran `(0, 0)` = vacias. Medido: el 2º jugador eligio el cofre 5, no
#      existia en el tablero, se le reasigno la caja 0 ... y le toco una VACIA.
#   ⇒ 6 filas, todas con premio, cada una distinta para que elegir tenga sabor.
# ★★★★★ LA SEGUNDA COLUMNA ES **EXPERIENCIA**, NO UN "RPoint" (corregido el 2026-09-10).
#   anonimo03 preguntó *"los rpoint ¿es exp?"* y la respuesta salió del exe, no de un nombre:
#     · el `type 2` de la caja hace, en `0x57D140`:  get(`0x485590`) + value -> set(`0x485570`)
#     · esas dos leen y escriben **`[jugador+0x2D0]`** (ofuscado con `^0x1FEF`)
#     · y ese MISMO campo lo escribe el handler del `FFB9`, que en el cliente 2019 —el que trae
#       los nombres de los devs— se llama **`CmdSyncExp`**. El `FF92` es `CmdEditExp`, ídem.
#     · el consumidor es la barra de nivel (`0x58D670`): divide ese valor por `tabla_exp[nivel]`.
#   ⇒ Era exp desde siempre. La estábamos guardando en la columna `rpoint` de la base, que **no
#     viaja en ningún paquete**: la exp de la caja se perdía entera. Ahora se paga con `db_add_exp`.
#
# ★ CUÁNTO. El referente reparte **50 RCoin + 1000 exp** por caja, iguales todas (medido en
#   `mitm_20260909_181537.txt`, línea 22767). Nuestro RCoin es mucho más generoso que el suyo
#   (100..1200 contra 50), así que copiarle el 1000 pelado sería desproporcionado en el otro eje.
#   ⇒ REGLA SIMPLE Y VISIBLE: **la caja paga tanta exp como RCoin.** Una carrera de cooperativo
#     paga ~2000-3000 de exp, así que la caja suma entre un 5 % y un 40 % de una partida — un
#     premio que se siente sin reemplazar al de jugar.
#   ⚠ Es una PERILLA DE DISEÑO, no un dato del juego. Si es mucho (o poco), se toca acá.
CHASE_CAJA_PREMIOS = [           # (rcoin, EXP) — se BARAJA en cada victoria
    (100,   100),
    (200,   200),
    (300,   300),
    (500,   500),
    (800,   800),
    (1200, 1200),
]
# ★ Cuantas de las 6 llevan ADEMAS una Moneda Gorila (se sortea el numero y cuales). Es el premio
#   gordo del minijuego: `coin=1` es un byte propio de la caja, no un `type` de la lista.
# ★★★★ EL TOPE PARA ABRIR LA CAJA DEL PREMIO (segundos) — 2026-09-09.
#   ⛔ EL CUELGUE QUE ARREGLA: el revelado sólo avanzaba **cuando llegaba un `sub=4`**. Si el
#     último que faltaba se desconectaba, la sala se quedaba en el cartel PARA SIEMPRE y la gente
#     se iba de a una. Reportado por un jugador: *"el primero llega a elegir pero se pasa al
#     último y ya no deja escoger a nadie más"*.
#   ★ El REFERENTE da el turno igual que nosotros pero **no depende de la respuesta**: entre turno
#     y revelado le pasan 0-3 s, y en las capturas viejas hay 39 pares en el MISMO segundo.
#   ★ Y que el cliente lo acepta lo confirmó el disasm de los DOS clientes: para revelar sólo pide
#     que la caja exista y que ese slot no tenga otra. No mira si el jugador eligió.
#   ⚠ 8 s y no 6: el cliente **se auto-elige solo a los 6 s** (`0x57CEE0`). Primero que conteste
#     él; esto es la red para cuando ese paquete NO llega. En 0 o None vuelve a esperar para
#     siempre (el comportamiento viejo). Ver `lobby_carrera._tope_apertura`.
# ★★★★★ EL TOPE PARA UN CLIENTE QUE DEJÓ DE LEER (milisegundos) — 2026-09-09.
#   ⛔ Reportado en vivo: *"hay carreras que no están empezando ni terminando, y son varias salas"*.
#     En el log, **cuatro salas destrabándose en el MISMO segundo**, una de ellas **6 minutos tarde**
#     para un reloj de 30 s: estaban bloqueadas y se soltaron juntas.
#   ★ CAUSA: `sendall` corre dentro del candado y no tenía tope. Un cliente que deja de leer llena
#     su buffer y **bloquea al hilo que le escribe** — que suele ser el de OTRO jugador haciendo una
#     difusión. Una PC colgada congela salas ajenas.
#   ⚠ El keepalive NO cubre esto: sólo vigila conexiones calladas. Con datos sin confirmar manda
#     `tcp_retries2`, que en el VPS vale 15 = **~15 minutos**.
#   ⇒ `TCP_USER_TIMEOUT` acota eso. Es del kernel: no cambia el bloqueo de Python (a diferencia de
#     `settimeout`, que tocaría también el `recv`, y eso ya rompió el lobby una vez).
#   ⚠ EL TRATO: un jugador con muy mala conexión puede quedar rajado a los 20 s. La alternativa de
#     hoy es peor — ese jugador cuelga SALAS ENTERAS por minutos. Se prefiere perder uno a colgar seis.
#   ★ En 0 se apaga. Ver `lobby.activar_keepalive`, que es donde se aplica a CADA conexion.
TOPE_ENVIO_MS = 20000

# ★★★★★ EL BARRIDO DE SALAS FANTASMA — 2026-09-15, reportado por anonimo03 y MEDIDO en prod.
#
#   ⛔ EL RETRATO, del log del 12-sep: el `usn 6671` sentado en el slot 2 de las salas **19, 22 y
#     27 al mismo tiempo**; su conexión dada de baja el 12-sep a las 20:13:13; y las tres salas
#     **todavía publicadas el 15-sep a las 17:20** — tres días después.
#     En esa lista de 11 salas, **6 eran fantasma**, y entre todas se comieron **4 692 entradas**
#     de jugadores reales que iban a esperar a alguien que no estaba.
#
#   ★ La causa está tapada en `lobby_salas.sacar_de_la_sala_anterior` (la puerta). Esto es la RED:
#     recorre las mesas y saca a los que ya no están. Hace falta aparte de la puerta por dos
#     motivos, y ninguno es redundancia:
#       1. **limpia lo que YA está roto** — las 6 salas de prod se van solas, sin reiniciar; y
#       2. cubre cualquier camino nuevo que deje un asiento colgado. El molde de este bug
#          (estado de la sala guardado por conexión) ya apareció seis veces en este repo.
#
#   ⚠ Las dos reglas del barrido NO son iguales de agresivas, y está explicado en su docstring:
#     sin conexión viva se saca en el acto; conectado-pero-en-otra-sala necesita **dos pasadas**,
#     porque `h_18_ff11` se sienta antes de escribir `room_id` y hay una ventana legítima ahí.
#   ★ En 0 se apaga el barrido (la puerta sigue funcionando igual).
BARRIDO_MESAS_SEG = 60

# ⏸ Estuvo PAUSADO en 0 desde el 2026-09-09 para que aquel deploy subiera sólo el arreglo del
#   bloqueo. ▶ REACTIVADO el 2026-09-10, y ahora con la medición que lo justifica:
#
#     En prod, entre las 11:40 y las 13:05 del 10-sep:
#         tableros repartidos : 37
#         revelados completos : 20     ⇒ **17 salas (46 %) se quedaron colgadas en el cartel**
#     Con el tope en 0 no hay NADA que las destrabe: el revelado sólo avanza cuando llega un
#     `sub=4`, así que basta con que uno no conteste para que la sala entera se quede ahí.
#
#   ⚠ 8 s y no 6: el cliente **se auto-elige solo a los 6 s** (`0x57CEE0`, timer de 0x168 = 360
#     cuadros). Primero que conteste él; esto es la red para cuando ese paquete NO llega.
#   ★ Y que el cliente lo acepta está leído del exe: `0x57B530` sólo pide que la caja exista y
#     que ese slot no tenga otra (`0x57AAA0`). **No mira de quién es el turno.**
#   En 0 vuelve al comportamiento viejo (esperar para siempre). Ver `lobby_carrera._tope_apertura`.
GORILA_TOPE_APERTURA = 8.0

CHASE_GORILA_CAJAS = (1, 3)      # entre 1 y 3, variable en cada partida
# ⏳ HIPOTESIS (del usuario, sin verificar): el `coin=2` = **Moneda Zombie** seria la moneda del
#   **MODO JEFE**, que todavia no logramos arrancar (necesita equipos asignados, `0x4FB43B`). Encaja
#   con que el cliente traiga `rnr_group_racing/ui/zombiecoin_img.bmp` y con el `horrorcontrol.txt`
#   que aparecio entre los documentos de los devs (un modo zombie planificado y nunca publicado).
#   ⇒ NO usarla en el chase: si la hipotesis es correcta, seria mezclar la economia de dos modos.
# `byMusicLevelFilter` = la fila de iconos de banda de arriba del picker. Con el filtro en 0 la lista
#   sale VACIA (medido: el cliente ni llama al chequeo de permiso por cancion, no enumera nada).
#   0xFF = todas las bandas. ⚠ Esto es una SONDA: si rompe algo, el sospechoso es este byte.
CHASE_FILTRO_BANDAS = 0xFF

# ★ LA PISTA DEL CHASE es FIJA (el usuario confirmo que nunca fue elegible por el jugador).
#   Candidatos = los 4 escenarios ESPECIALES del `stage_lt.txt`, que son los unicos SIN `Title` y
#   tienen su pak propio en `R2Beat/rnr_bg/`:
#       100 = m_back01/track_night.bin   ·   101 = m_back02/track.bin
#       102 = m_back03/forest.bin  ← el mas probable (bosque = gorila)
#       103 = m_back04/track.bin
#   ⚠ Mandabamos DEFAULT_ROOM_MAP=11 = "MARAVILLA ESPACIAL" (space wonder) = la pista equivocada que
#     veia el usuario. Con la pista mal NO puede aparecer el gorila.
#   ★ Como verificarlo GRATIS: el cliente reporta los assets que no puede cargar por **FF59**
#     (ver el handler del 0x59 mas abajo). Si el indice esta mal, el FF59 dice el path exacto.
CHASE_MAP = 102
# ★★★ 2026-07-30 — LOS INDICES 100-103 ESTAN DESCARTADOS POR DISASM. El chase usa un ESPACIO DE
#   NUMERACION PROPIO: con GameMode==4 (cooperativo) el cliente conmuta al `cChaseStageSelect`
#   (`0x58F110`) y lo FUERZA a `0x3A98` = **15000** (`0x58F170`, descarta el argumento). El validador
#   `0x56B730` hace `lea ecx,[arg-0x3A98]; cmp cx,0x567` ⇒ **rango legal 15000..16383**.
#   Y en `0x46BD21` la etiqueta de la sala sale de ahi: 0x3A98="Chase", 0x3A99="jugador27".
#   ⇒ el 11 (maravilla espacial) y los 100-103 estan TODOS fuera de rango.
#   ⛔ MEDIDO 2026-07-30: mandar **15000 en el `map` del FF25 NO sirve** — el cliente lo tomo LITERAL
#      como indice de carpeta y pidio `rnr_bg/back15000/logo_lt.tga` (dicho por el propio FF59).
#      ⇒ el `map` del FF25 es el INDICE DE ASSET; el 15000..16383 es la numeracion INTERNA del
#      cChaseStageSelect y las dos NO son la misma cosa. La traduccion entre ambas sigue sin hallarse.
#   ★★ 2ª sonda = **102 SI FUNCIONA** (reportado por el usuario en pantalla): el escenario CAMBIO
#      —no al esperado, pero cambio— y la jugabilidad quedo MAS CERCA de la esperada.
#      ⚠⚠ LECCION DE METODO: el FF59 se quejo de `rnr_bg/back102/logo_lt.tga` y con eso solo se dio
#      por fallada la sonda. **Un .tga faltante NO es un escenario que no carga.** El FF59 lista
#      assets sueltos, no el veredicto del escenario: el veredicto lo da la PANTALLA. Preguntar
#      SIEMPRE antes de descartar por un error de asset.
#   ⛔ 100/101/102/103 DESCARTADOS EN PANTALLA (el usuario los vio): son escenarios de MISION, y
#      ademas son los unicos del stage_lt SIN `Title` y SIN imagen de preview.
#   ★★★ CANDIDATO REAL = **9 = "PARQUE WEIMAR - Oeste" = `back09/zoo_town.bin`** — un parque con
#      ZOOLOGICO, que es de donde se escapa el gorila. Salio de la hoja de contactos de los 24
#      escenarios (`stage_lt.txt` + `rnr_image/img_stage/stage_img_*.bmp` del `rnr_image_lt.pak`).
# ★★★★★ LA DIFICULTAD DE LAS 3 CANCIONES DEL COOPERATIVO — 2026-09-05.
#
#   Lo pidió el usuario: *"a veces salen músicas MUY fáciles, y en el original las muy fáciles
#   casi no salían"*. Tenía razón, y la prueba está en el catálogo del propio juego.
#
#   `music_lt.txt` trae `Level="N"` por canción. Pero el nivel **no es una escala suelta**: el
#   cliente lo convierte en una **BANDA**, que es el casillero del picker. Leído de `0x40C5C0`
#   del propio cliente 2013 (ver `notas.banda_de_nivel`), son **OCHO bandas**:
#
#       banda 8 = niveles 1-2   (93 canciones nuestras)   ← lo "muy fácil"
#       banda 1 = niveles 3-4   (24)                      ← lo "muy fácil"
#       banda 2 = nivel   5     (74)
#       banda 3 = niveles 6-7   (161)
#       banda 4 = niveles 8-10  (155)
#       banda 5 = niveles 11-14 (222)
#       banda 6 = niveles 15-17 (85)
#       banda 7 = niveles 18-20 (7)
#
#   ⇒ **Las "muy fáciles" son las bandas 8 y 1 = niveles 1 a 4: 117 canciones, el 14 %.** Con 3
#     por partida eso da ~38 % de partidas con al menos una — justo lo que describió el usuario.
#
#   ⛔ CORRECCIÓN de lo que escribí primero: dije que *"el juego parte su biblioteca en dos
#      bolsas y el corte es el nivel 7"*, deduciéndolo de que la entrada `random_gosu` tiene
#      `Level="7"`. **Está mal.** La estructura real son ocho bandas, y el 7 es apenas el techo
#      de la banda 3. Lo destapó anonimo03 mandándome a leer el importador del CBT 2011.
#
#   ⚠ Lo que **todavía no está medido**: qué bandas usaba el COOPERATIVO. El sorteo lo hace el
#     servidor y no hay captura del original haciéndolo. Por eso es perilla y no constante.
#
#   Default **5** = "de la banda 2 para arriba": saca las dos bandas más fáciles enteras y no
#   toca nada más. Quedan 697 canciones, de sobra.
#   ★ Poné un nivel que sea PRINCIPIO de banda, si no el corte parte una banda al medio:
#     3 (banda 1+) · 5 (banda 2+) · 6 (banda 3+) · 8 (banda 4+) · 11 (banda 5+) · 15 (banda 6+)
#   ★ Para volver al sorteo plano de antes, poner None.
#
# ★★★★★ LA REGLA DE VERDAD, DICHA POR EL USUARIO CON LA CAPTURA EN LA MANO (2026-09-05):
#   *"si estamos en Luna = músicas Luna · si estamos en Sol = músicas Sol · si la licencia del
#     master es Novato Luna = músicas Novato Luna"*.
#   ⇒ El sorteo NO es "de tal nivel para arriba": es **de la banda del canal en el que estamos**,
#     que es la de la licencia del anfitrión — la misma que ya le mandamos en el `FFC9` para que
#     el picker le muestre su casillero. Con eso, "muy fácil" deja de ser un problema por sí solo:
#     en el canal Principiante las fáciles CORRESPONDEN, y en Luna no aparecen nunca.
CHASE_BANDA_DEL_CANAL = True           # ★ el sorteo sigue la banda de la licencia del anfitrión
# ⚠ Si una banda no tiene suficientes canciones se AMPLÍA hacia abajo, banda por banda, y se dice
#   en el log. Medido en nuestras 808: la banda 7 (Sol, niveles 18-20) tiene **3 canciones**, o sea
#   justo las 3 de una partida — sin esto, en el canal Sol saldrían siempre las mismas tres.
CHASE_BANDA_MINIMO = 12                # cuántas quiere tener antes de ampliar (4 partidas distintas)

# Las dos de abajo sólo se usan con `CHASE_BANDA_DEL_CANAL = False`, para forzar un rango a mano.
CHASE_NIVEL_MIN = 5
CHASE_NIVEL_MAX = None                 # tope opcional; None = sin tope
# ★★ (97) EL TOPE DE SONIDOS DEL COOPERATIVO — 22-oct (la caja negra 0x5738E7: la sala entera se caía al cargar).
#   El cooperativo carga de una el BGM y TODOS los `<EFFECT>` de sus 3 canciones como samples de Miles. Pasado el tope,
#   el BGM de la canción SIGUIENTE no entra (handle 0, «[BGM Error] Soud device error») y el cliente se cae en
#   0x5738D0. MEDIDO: en local con los 6 de la sala de prod (685 «Luz de Luna» = 756 efectos, después 5838): los 6
#   caídos, la sonda vio `AIL_allocate_sample_handle` = 0 desde el mel_719 · ⟲ las MISMAS 3 con la 685 al final: nadie.
#   En prod (1830 rondas, 17→22-oct): con < 700 efectos antes del último BGM, 1823 anduvieron y 0 se cayeron; con 700+,
#   6 de 7 se cayeron. ⇒ el sorteo pide que las 3 juntas sumen ≤ este tope y pone la de MÁS efectos al final (sus
#   efectos se cargan después de todos los BGM). La cuenta: `tablas-cliente/efectos_por_cancion.json`
#   (`herramientas/efectos_por_cancion.py`).
#   ⏸ APAGADO por defecto (22-oct, anonimo03: «no tomaremos en cuenta a los que no actualicen, sólo el escenario en que les
#   diré yo que actualicen»): el arreglo de fondo es la dll (98, Miles con 6000 canales, probado con la sala que se
#   caía); este tope era la red para las dlls viejas. Se prende con `R2_CHASE_TOPE_EFECTOS=600` (None = sin tope ni orden).
CHASE_EFECTOS_TOPE = int(os.environ["R2_CHASE_TOPE_EFECTOS"]) if os.environ.get("R2_CHASE_TOPE_EFECTOS") else None
# ★ (100) 22-oct, la caja negra 0x684107: el FF1C (cambio de canción) NO se reenvía al que todavía carga la sala
#   (`sala_poblada != sala`): su panel de música no tiene el dibujo cargado y el cliente se cae. Al terminar de cargar
#   la canción le llega igual (`FF1C_AL_ENTRAR`). `R2_FF1C_AL_QUE_CARGA=1` = como antes. (Y la dll lo cubre, (100).)
FF1C_NO_AL_QUE_CARGA = os.environ.get("R2_FF1C_AL_QUE_CARGA") != "1"

# ★ 2026-10-01 — anonimo03: el cooperativo en la pista **OCTUBRE** (Index 10 = `back10/track.bin`, la del
#   otoño con la calabaza y la bandera HALLOWEEN), para la temática Halloween. Antes: 9 = «PARQUE WEIMAR -
#   Oeste» (`back09/zoo_town.bin`, el zoológico de donde se escapa el gorila). Para volver: 9.
#   ⚠ Tiene que estar en `OWNED_STAGES_2013` (el 10 está).
# ★ 2026-11-06 — terminó Halloween: vuelve a 9, «PARQUE WEIMAR - Oeste» (anonimo03: «devolverle su número de pista correcta»).
CHASE_MAP_FIJO = 9
CHASE_USAR_MAP_FIJO = True


# ★ SONDA para hallar DONDE va el modo en el FF13 (el prefijo tiene 16 u8 sin mapear y hoy los
#   mandamos en CERO -> por eso TODA sala cae en "velocidad-solo", misma trampa que el my-slot).
#   None      = apagada (comportamiento normal)
#   "todos"   = escribe el `flags` del FF10 en TODOS los u8 desconocidos del prefijo a la vez
#               -> si la sala pasa a mostrar el modo correcto, el campo ESTA en el FF13; despues se
#                  bisecta (log2(16) ~ 4 corridas) en vez de probar los 16 uno por uno.
#   "cola"    = idem pero en la COLA (tras el nombre): @24+L u8, los 7 u32 y los u8 finales.
#               ⚠ NO toca @53+L (mascara de ocupacion, ya confirmada).
#   "ancho"   = ★ TODOS los campos sin mapear (prefijo Y cola) escritos RESPETANDO SU ANCHO.
#   <int>     = solo en ESE offset absoluto del prefijo (para bisecar / fijar el definitivo)
#
# ★ MEDIDO 2026-07-29, y ojo con la LECCION DE METODO:
#   Las corridas "todos" y "cola" escribian el modo BYTE POR BYTE -> los campos u16 quedaban en
#   0x0303 y los u32 en 0x03030303 (basura, no 3), asi que un campo de modo de 2 o 4 bytes NUNCA
#   podia matchear. Ambas dieron "velocidad + solo", pero eso SOLO descarta los u8:
#     DESCARTADOS de verdad: los 10 u8 del prefijo (@7..@13, @16, @21, @22) y los 5 u8 de la cola.
#     NO descartados: los 3 u16 del prefijo (@14, @17, @19) y los 8 u32 de la cola.
#   => una sonda "todos los bytes iguales" solo es valida para campos de 1 byte. Para campos anchos
#      hay que escribir el valor con su ancho (modo "ancho").
#   ★ 3ª corrida con modo "ancho" (u16 y u32 con el valor REAL 3): TAMBIEN dio "solo + velocidad".
#     ⛔⛔ Y ACA SE ESCRIBIO **"EL FF13 QUEDA DESCARTADO PARA EL MODO"**, QUE ERA FALSO.
#        RESUELTO 2026-09-04: el modo SI viaja en el FF13, en **@8**, como byMode. Ver la nota
#        larga de `build_ff13_2013`. Por que el negativo era falso:
#          esta sonda escribia en @8 el valor de los **flags** (`3`), y `3` en la codificacion del
#          byMode no prende ni item (0x04) ni equipo (0x10) => se ve "velocidad + solo", que es
#          IDENTICO al sintoma de estar roto. El resultado no distinguia una cosa de la otra.
#        La sonda se deja cableada y APAGADA: sirve para OTROS campos (los buffos, abajo).
#   ★★ PERO NO SON CAMPOS MUERTOS: en las corridas de sonda el usuario vio que **se activaban los
#     BUFFOS DE SALA** (visualmente). ⇒ los campos sin mapear del FF13 son las **OPCIONES/BUFFOS de
#     la sala**, no el modo. Identificacion positiva y punto de partida si algun dia queremos
#     controlar los buffos: encenderlos de a uno con FF13_MODE_PROBE=<offset> y mirar cual prende cual.
#   ⛔ PISTA DESCARTADA (era mia, y estaba mal): "el modo efectivo es el ROOMTYPE
#     [[0x9314ac]+0x1951], copiado del byte +0x34 de la entrada de sala, o sea que el modo llega
#     en el FF6E". El struct del +0x34/+0x36 es una entrada de la lista de **CANALES/SERVIDORES**,
#     no de salas: `0x4A7940` copia +0x34 (tier2 del canal) a +0x1951 y +0x36 a [roommgr+0x1328]
#     (= canal seleccionado), y el gate `0x49F980` compara +0x1951 contra 5, que es una CATEGORIA
#     DE CANAL. Lei una lista por la otra y la conclusion salio al revés: el modo NO viene del FF6E
#     y SI viene del FF13 (@8).
FF13_MODE_PROBE = None                # ⛔ APAGADA. Sirve para los BUFFOS de sala, no para el modo.

# ⛔ SONDA byMode (2026-07-30) — RETIRADA 2026-09-04, ya no hace falta: el byMode es @8 y va fijo
#   en `build_ff13_2013`. Se deja el epitafio porque la equivocacion es instructiva:
#   la sonda escribio el byMode CON LA CODIFICACION BUENA, pero en @2..@5, razonando que el
#   "byte #4" del CBT caia dentro del u32 de @2. El negativo (equipo+velocidad y solo+item
#   siguieron mostrando "velocidad + solo") era correcto Y no significaba nada sobre el campo:
#   el byte era el @8. Sumado a la sonda de arriba, que si toco @8 pero con el valor de los flags,
#   entre las dos cubrieron "el offset bueno con el valor malo" y "el valor bueno en el offset
#   malo" — y de ahi salio la conclusion falsa de que el FF13 no llevaba el modo.
FF13_MODE_OFFS  = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]   # @6 = mi-slot, NO tocar
# Campos del PREFIJO sin mapear, con su ancho real (del layout: @14/@17/@19 son u16). @6 = mi-slot.
FF13_PREFIJO_CAMPOS = [(7, 1), (8, 1), (9, 1), (10, 1), (11, 1), (12, 1), (13, 1),
                       (14, 2), (16, 1), (17, 2), (19, 2), (21, 1), (22, 1)]
# Campos de la COLA (indice dentro de `cola`, que arranca en @24+L), con su ancho. Se OMITE el 29
# (mascara de ocupacion @53+L, ya confirmada).
FF13_COLA_CAMPOS = ([(0, 1)] + [(1 + 4 * i, 4) for i in range(7)]      # @24+L u8 + 7x u32
                    + [(33, 4)] + [(37, 1), (38, 1), (39, 1), (40, 1)])  # @57+L u32 + 4x u8 finales

# ★★★★★ 2026-09-01 — LAYOUT REAL DEL FF0C, MEDIDO DEL WIRE DE UN SERVER QUE ANDA.
#   Capturados 42 `FF0C` de `<IP del referente>` con `re/mitm_divert.py`. Contra lo que armábamos
#   nosotros hay TRES diferencias, y las dos primeras son las que rompen la ropa:
#     1. El **CUERPO va DENTRO del array de ítems, como `item[0]`**, y el `itemcount` LO CUENTA.
#        Nosotros mandábamos el `char_id` DESPUÉS de los ítems y sin contarlo.
#     2. Donde nosotros poníamos `[char_id2:u32][u32 0]` van **DOS FLOATS: la POSICIÓN del asiento**
#        (X y Z). Medidos: X = -500 + 200*slot para los slots 0..5, Z = -140 fija.
#        ⇒ el cliente estaba leyendo un `char_id` como float (130900 -> ~1.8e-40) y plantaba
#          el avatar en el origen. Explica que la ropa/alas no aparecieran donde debían.
#     3. Va **UN ocupante POR PAQUETE**, con cabecera `[FF][k][00 00]`, y `k` NO es el contador
#        (vale 1 en el primero de una tanda y 2 en los demás). La cola tras el nick mide 48 B
#        EXACTOS en las 42 muestras.
#   El resto (exp@0, misión@4, flags@6, slot@11, char_id@14, itemcount@22) ya lo teníamos bien.
FF0C_LAYOUT_REAL = True                # False = volver al builder viejo (multi-ocupante)
FF0C_BANDERA_AURA = True               # mandar el Wing Id en la cola cuando lleva alas/aura

# ★★ 2026-09-01 — MEDIDO EN EL WIRE REAL (4 partidas cooperativas, 3 cartelones, 7 rondas):
#   · La corrida cooperativa son **3 canciones** = 3 rondas de gorila, y recién al terminar la
#     última el server manda el `FF27` vacío ("mandame tu resultado"). El cliente contesta con su
#     `FF28` (62 B, con un MD5 de 32 chars) y ENTONCES el server manda el cartel.
#   · `rank_bonus` no es una constante: es una **escalera por puesto**. Valores vistos:
#     puesto 1 -> 250/283 · 2 -> 200/215/220 · 3 -> 175/177/199 · 4 -> 100/121/132 · 5 -> 50.
#     Se toma la base de cada escalón (el resto parece un extra que todavía no sabemos de dónde sale).
#   · `basecoin` real anda entre 25 y 40 por jugador — no los 1000 fijos que mandábamos.
#   ⏳ SIN RESOLVER: qué decide la medalla **S vs A** por fila. NO es del equipo (hay carteles con
#     las dos) y no sale de `pd` ni de `star`: se vio `pd=80 star=0 -> S` y `pd=84 star=100 -> A`.
#     Hasta saberlo se deja `grado_de()` como estaba. Evidencia en `re/HALLAZGOS_COOP.md`.
FF27_PEDIR_RESULTADO = True            # mandar el FF27 al cerrar la corrida COOPERATIVA
# ★★★★★ EL FF27 EN LAS CARRERAS NORMALES (2026-09-04). Hasta hoy el `FF27` salía SÓLO al cerrar el
#   cooperativo, así que en velocidad/ítem/equipo/relevo **no salía nunca**. Dos consecuencias, y la
#   segunda es la grave:
#     1. El que no llegó no veía el contador. Es literal: el handler del FF27 (`0x5E3010`) hace
#        `SetTimer(hwnd, 0x99, 4000, NULL)` — **4 segundos**, no 5.
#     2. ⚠ El `FF27` NO es sólo el contador: es lo que hace que el cliente **cierre su participación
#        y mande su `FF28`**. Está medido en el server del CBT (2026-08-14): al filtrar ese envío por
#        modo, de 6 jugadores sólo los 2 que lo recibieron vieron el cartel y los otros 4 fueron
#        DESCONECTADOS por rezagados. ⛔ NO filtrar este envío por modo ni por "quién ya llegó".
#
#   DISPARADOR: el **primer `FF28` de LLEGADA** de la sala. Medido en la captura del server de
#   referencia sobre las 5 carreras no-cooperativas: el `FF27` cae encima del frame del primero
#   en llegar (`FF27` a +133 s vs primer frame 8024 = 134 s · +130 vs 132 · +132 vs 140 · +125 vs 130).
#   ★ Y el usuario explicó POR QUÉ coinciden: se llega a la meta **terminando de consumir la
#     canción**, así que "fin de canción" y "primer finalista" son el mismo instante. Las dos
#     lecturas que parecían competir eran la misma cosa.
FF27_AL_PRIMER_FINALISTA = True        # False = volver a no mandarlo (comportamiento viejo)

# ★★★★★ EL RELOJ DEL CARTEL — 2026-09-06. Segundos que se espera a los que faltan reportar.
#   ⛔ EL BUG QUE VIENE A TAPAR, visto en producción: el cartel esperaba a que reportaran TODOS
#     **sin ningún límite de tiempo**. Si un cliente no mandaba su `FF28` —se colgó, crasheó, o es
#     una máquina lenta que no llega— la sala ENTERA se quedaba clavada en la meta hasta que ese
#     jugador se desconectaba. Medido en la sala 8 (14:26:48): el cartel salió **2 min 33 s**
#     después, y NO porque el que faltaba reportara sino porque se cayó la conexión.
#   ★ Por qué 12 s: el propio `FF27` ya le da al cliente un contador de **4 s** para cerrar y
#     reportar. Los que reportan normal lo hacen dentro de los 5 s del primero (medido en 20
#     carteles de producción: el peor fue 4 s). 12 deja margen de sobra para una PC lenta y aun así
#     destraba la sala antes de que nadie se aburra.
#   ⚠ No es un dato del juego: es una PERILLA nuestra. En 0 se apaga el reloj y vuelve el
#     comportamiento viejo (esperar para siempre).
FF28_ESPERA_MAX = 12.0

# ★★★★★ EL RELOJ DEL **ARRANQUE** — 2026-09-08. El hermano del de arriba, y faltaba.
#   ⛔ EL BUG, reportado desde adentro de la partida y confirmado en el log de producción:
#
#       14:33:38  ⏳ FF25 cargó usn=9117; faltan [10026]
#       (y nada más: el `GO` nunca salió)
#       14:35:19  ★ conexión usn=10026 dada de baja      ← se fue con alt+F4 mientras cargaba
#
#     `h_31_ff25` **espera a que carguen TODOS** para mandar el `FF24 GO`, sin límite de tiempo.
#     Uno que nunca reporta —porque cerró el juego cargando, o crasheó, o su máquina no llega—
#     deja a la sala entera **mirando la pista sin que empiece nunca**. El usuario lo describió
#     igual: *"cargó pero no empezó; los demás cerraron alt+F4 para crear otra sala"*.
#
#   ★ Es EXACTAMENTE el mismo modo de falla que ya se había arreglado para el FINAL de la carrera
#     (`FF28_ESPERA_MAX`, arriba), en la otra punta: allá se esperaba el reporte, acá la carga. El
#     CBT ya tenía este guard; el 2013 se quedó sin él.
#
#   ★ Por qué 30 s: cargar una pista en una máquina modesta tarda entre 5 y 15 s (medido en el log:
#     los que cargan bien lo hacen dentro de los 3 s del primero, y el peor caso visto fue 11 s).
#     30 deja margen de sobra para una PC lenta y aun así destraba la sala antes de que nadie
#     cierre el juego.
#   ⚠ En 0 se apaga el reloj y vuelve el comportamiento viejo (esperar para siempre).
FF25_ESPERA_MAX = 30.0
# ★ 12-oct (anonimo03: «al espectador le empieza la carrera 1-2 s más tarde que a los corredores»): el GO salía apenas
#   cargaban los CORREDORES, y el que mira terminaba de cargar después (log 20:21:35: su FF25 llegó detrás del GO).
#   Ahora el GO espera también a los espectadores, pero como mucho estos segundos de más: un espectador lento no
#   puede trabar a los que corren. 0 = como antes (no se los espera).
GO_ESPERA_ESPECTADOR_S = 5.0

CHASE_RONDAS = 3                       # canciones (= rondas de gorila) por corrida cooperativa
# ★★★ EL `op3` DEL CARTEL DE PREMIOS AL PERDER — 2026-09-05.
#   El usuario vio la sección de premios **corrida un slot a la derecha**, y el log de esa misma
#   partida lo explica: `FF10E sub=3 slot ajeno 3` con el jugador en el slot 2. El slot ajeno está
#   a propósito (hace que el cliente entre en modo "mirando" en vez de habilitarle elegir caja
#   donde no hay premio), pero **ese mismo slot es el que el cliente resalta**.
#     "ajeno"  el primer NPC que no seas vos  (lo de hoy)
#     "yo"     tu propio slot -> ¿se endereza la fila? ⚠ te habilita 6 s de selección vacía
#     <int>    un slot a dedo
#   ⚠⚠ NO pongas 6 ni 0xFF sin comprobar antes que el cliente no use ese número como índice de su
#     vector de 6 jugadores: es el mismo cuadro que crasheaba el modo jefe.
FF10E_DERROTA_OP3 = "ajeno"

# ★★★★★ LOS EFECTOS DEL COOPERATIVO — cruzados contra TRES partidas, 2026-09-05.
#
#   El método: el usuario dice qué usó y en qué cantidad, y se cruza contra el recuento del log.
#   Funciona porque los ítems salen al azar (no se pueden pedir cantidades exactas) pero sí se
#   puede pedir que sean **distintas entre sí**. Tres partidas, y las tres cierran:
#
#     partida | lo que dijo                                     | lo que dijo el log
#     --------|-------------------------------------------------|---------------------------
#        A    | 1 rojo · 1 celeste · 1 verde · (2 combo-x40)     | 15×1 · 17×1 · 16×1 · (5×2)
#        B    | 5 rojo · 2 celeste · 2 verde (ítem + 40 combos)  | 15×5 · 17×2 · 16×2
#        C    | 0 rojo · 3 celeste · 1 verde                     |         17×3 · 16×1
#
#   ✅ `15` = **booster ROJO**    (de equipo)   — 2 partidas, cantidades 1 y 5
#   ✅ `17` = **booster CELESTE** (de equipo)   — 3 partidas, cantidades 1, 2 y 3
#   ✅ `16` = **booster VERDE**   (individual)  — 3 partidas, cantidades 1, 2 y 1
# ★★★ EL REPARTO, decidido por el usuario el 2026-09-05:
#       · TODOS los boosters van a la columna "Usar Booster"
#       · "Ayuda" son SÓLO la inyección y el jetpack
#       · y el jetpack cuenta en LAS DOS (no cuesta nada: un id puede estar en dos listas)
#
#   ⚠ CON QUÉ CONFIANZA ESTÁ CADA UNO — importa, porque no todos se midieron igual:
#     MEDIDO jugando, 2 o 3 partidas con cantidades distintas:
#         15 = booster ROJO (equipo) · 17 = booster CELESTE (equipo) · 16 = booster VERDE
#     LEÍDO de la tabla de nombres del cliente (`0x52E700` / `0x52F5xx`), NO medido en partida:
#         5 = booster · 19 = variante de booster · 28 = booster COHETE ("jetpack")
#         11 = curar  ⇒ la inyección
#     ⚠ El `11` como "Ayuda" se apoya además en una observación del usuario en videos de
#       YouTube ("la inyección aparece como el valor de Ayuda"), que él mismo puso en ~70 %.
#       Es una apuesta razonable, NO un hecho. Si el cartel muestra un número raro, empezá acá.
#     ⛔ El `243` es el booster del MODO JEFE: NO va en las listas del cooperativo.
COOP_EFECTOS_AYUDA = (11, 28)    # inyección + jetpack. Columna "Ayuda (n)".
#
#   ★ Y el `16` es además EL IMPULSOR: en la partida B el usuario usó "1 verde de ítem + 1 verde
#     de 40 combos" y salió `16×2`. O sea que **el booster verde es el mismo efecto se haya
#     conseguido con un ítem o cargándolo con 40 de combo**, que es lo que uno esperaría.
#   ⚠ Esa última parte se apoya en UNA sola partida (el ×2 de la B). Lo demás del `16` está
#     confirmado tres veces. Para dejarlo firme: una partida disparando SÓLO el de 40 combos,
#     3 veces, sin tocar ítems -> tiene que salir `16×3`.
#   ★ Es una LISTA, no un id suelto: el cliente tiene varios efectos que son "booster" (el 5, el
#     16 de invencibilidad, el 19, y el **28 = cohete**, que es el "jetpack"). Cuál cuenta en la
#     columna lo decidimos nosotros — ver la nota de abajo sobre qué se puede elegir y qué no.
COOP_EFECTOS_BOOSTER = (5, 15, 16, 17, 19, 28)   # todos los boosters, jetpack incluido
COOP_EFECTO_IMPULSOR = 16        # compat: el principal, para el log
#
# ★★ SÓLO PARA QUE EL LOG SE LEA. No decide nada: no se usa para contar, únicamente para poner
#    una etiqueta al lado del número en el recuento de fin de carrera. Cambiarla no cambia el
#    cartel. La confianza de cada fila está en `COOP_ITEMS_Y_CONTADORES.md` §3.
#    ⚠ El cliente tiene CUATRO listas distintas de "esto es un booster" (`0x571860`, `0x5717F0`,
#      `0x571980`, `0x50A490`) y NO coinciden entre sí. Por eso acá dice de dónde sale cada una.
#    ★★★ 2026-09-05: la partida de 12 ítems anotados en orden cerró SIETE de estos. El usuario
#      jugó anotando qué usaba; se cruzó renglón a renglón contra la secuencia del log y
#      encajó todo salvo un hueco (ver `COOP_ITEMS_Y_CONTADORES.md` §6).
COOP_NOMBRES_EFECTO = {
    2: "ocultar (leído)",
    3: "espejo (leído)",
    5: "impulsor de 40 COMBOS, modo normal (MEDIDO 6/6)",
    6: "TORTUGA al gorila (MEDIDO ×2)",
    8: "hielo (leído)",
    10: "JUEGO AUTOMÁTICO (MEDIDO)",
    11: "INYECCIÓN (MEDIDO ×2)",
    14: "GRANADA al gorila (MEDIDO ×2)",
    15: "impulsor ROJO de equipo (MEDIDO)",
    16: "impulsor VERDE (MEDIDO)",
    17: "impulsor CELESTE (MEDIDO)",
    18: "booster (leído: 0x571860)",
    19: "booster, ranura del 5 (leído)",
    28: "JETPACK / cohete (MEDIDO ×2)",
    29: "arena del gorila (leído)",
    32: "arena del gorila (leído)",
    243: "booster del modo JEFE (no va acá)",
}
#    ★★ Y el `destino` de cada evento, que antes se descartaba como ruido, resultó tener sentido:
#         252 (0xFC) = EL GORILA   ·   0..5 = un jugador   ·   igual al emisor = para uno mismo
#       Los dos ítems que se le tiran al gorila (6 y 14) fueron a 252 las cuatro veces, y el
#       jetpack fue al slot 1 (un compañero) las dos veces. NO se usa para contar nada todavía.
COOP_DESTINO_GORILA = 252
#
#   ✅✅ EL `5`, RESUELTO — 2026-09-05, 14:06, carrera por equipos completa.
#     **`5` es el impulsor que se carga con 40 de combo, en el modo NORMAL.** Medido **6 de 6**,
#     sin una sola excepción: cada `sub=0x32` (los hitos de combo 40·80·120·160·200·240) trae
#     pegado atrás un `sub=0x01 id=5`, y no hay ningún `id=5` suelto.
#     ★★ Y eso reconcilia las dos partidas que se contradecían: **el usuario tenía razón en la
#       partida A** cuando lo atribuyó a "2 de combo x40". Yo lo puse en duda porque en la B el
#       mismo disparo salió como `16`. No se contradicen: es **el mismo impulsor con otro id según
#       el modo** — `5` en carrera normal, `16` en cooperativo. Dos modos, dos ids.
#     ⚠ El `19` apareció ×2 en esa misma carrera y **NO** pegado a un hito de combo: es otra cosa,
#       sigue sin identificar.
#     ★ La lección se mantiene, sólo que al revés de como la escribí: con UNA partida no se
#       confirma nada **ni se descarta nada**. Archivar el 5 como "sin explicación" fue apurado.
#
#   ⛔ Hipótesis mía que se cayó: esperaba reconocer los ítems de equipo porque su `destino`
#     sería OTRO slot. Falso — el recuento dice `0 apuntados a OTRO jugador` en partidas con
#     boosters de equipo. "Ayuda" sale de esta lista de ids, no del campo destino.
#
#   ★ LA REGLA DE LAS TRES COLUMNAS, dicha por el usuario (que es quien las juega):
#       · "Usar Item"    = TODOS los ítems (individuales y de equipo)
#       · "Ayuda"        = SÓLO los de equipo (rojo + celeste)
#       · "Usar Booster" = el impulsor; el verde individual va a ítems, no a ayuda
#
# ═══ ¿QUÉ PODEMOS ELEGIR LIBREMENTE Y QUÉ NO? (pregunta del usuario, 2026-09-05) ═══
#
#   ✅ **"Ayuda (n)"** y **"Usar Item (x/y)"**: LIBRES DEL TODO. Son los bytes `@27`, `@25` y
#      `@26` de la fila del `FF28` y el cliente los **imprime crudos**. Cualquier número de 0 a
#      255 en cada uno, y los dos del par son independientes.
#
#   ⚠ **"Usar Booster (x/y)"**: libre PERO con una atadura. El cliente no dibuja los dos bytes:
#      dibuja **`(byte0 − byte1) / byte0`** (`0x577246`). O sea:
#        · el número de la DERECHA es `byte0` — ése lo ponemos directo
#        · el de la IZQUIERDA es una RESTA — se consigue con `byte1 = byte0 − loQueQueremos`
#      ⇒ Se puede mostrar cualquier par `a / b` **siempre que `a ≤ b`**. Si `a > b` la resta da
#        la vuelta y sale 255, 254… (fue exactamente el 255 del ensayo de centinelas).
#
#   ⚠ Y las tres son **de 1 byte**: el tope es **255**. De sobra para una partida.
#
#   ★ RECOMENDACIÓN: que los DOS pares se lean igual (los dos "usados / obtenidos", o los dos al
#     revés). Si uno dice usados/obtenidos y el otro obtenidos/usados, el cartel se lee mal y
#     nadie se va a acordar de cuál era cuál.
#
#   ⏳ LO ÚNICO QUE FALTA para poder elegir de verdad: **"obtenidos" no se puede contar todavía**
#     (agarrar un ítem no genera aviso). Hasta que aparezca ese evento, los pares salen "N/N".
FF10F_ESPERA = 6.0                     # segundos a esperar a los que no reportaron antes de resolver

# ★★★★★ EL RELLENO DEL MINIJUEGO — 2026-09-08.
#
#   EL PROBLEMA, en una línea: **el que no reporta no baja el promedio, BAJA EL LISTÓN.**
#
#   La regla que aplica el cliente (`0x5708C0` / `0x56FA30`, leídas del exe) es
#       aciertos * 2  >=  cuántos puntajes tengo en MI map
#   y el divisor NO es la cantidad de jugadores de la sala: es el tamaño del map de **ese**
#   cliente. Con los 6 adentro hacen falta 3 aciertos; con UNO SOLO adentro, `1*2 >= 1` y ese
#   jugador **gana él solo**. Es exactamente el síntoma reportado ("si 1 de los 6 cumple el
#   minijuego, se activa la función de gorila atrapado").
#
#   Y hay una trampa más, del lado nuestro: si un cliente no manda su `FF10F`, nadie recibe su
#   `[slot][score]`, así que **a todos** les queda el map corto. Un jugador que se cuelga le
#   regala la victoria al resto.
#
#   LA SOLUCIÓN: antes del `[06][00]`, completar a los que faltan. Con puntaje 0, que es
#   exactamente lo que manda el propio cliente cuando se le vence su temporizador sin que
#   aprietes nada — o sea que esto no inventa nada nuevo, sólo garantiza que llegue.
#
# ★★ Y ADEMÁS ES EL BANCO DE PRUEBAS. El usuario prueba con 6 Sandboxie y no puede jugar en
#    las seis a la vez: las otras cinco ventanas no hacen el minijuego. Subiendo
#    `CHASE_RELLENO_PUNTAJE` a 70..100 las cinco "aciertan"; bajándolo a 0..69 "fallan". Con
#    `CHASE_RELLENO_SLOTS` se le da un puntaje distinto a cada una y se arma la mesa que se
#    quiera (3 aciertos y 3 fallos, por ejemplo) para ver si el veredicto sale bien.
# ★★★★★ EL MÍNIMO DE JUGADORES DEL COOPERATIVO — 2026-09-08.
#
#   El cliente **no exige nada propio del modo**: su guard de arranque (`0x592B50`) pide 2
#   ocupantes, todos listos, y equipos parejos **sólo si la sala usa equipos** — y `0x58BFF0`
#   deja afuera al cooperativo (entran CooperationMode 0 y 2, y GameMode 5). Para el cliente,
#   con dos alcanza.
#
#   Pero el modo **supone de 3 a 6**. La lógica del gorila está indexada por cantidad de
#   jugadores y sólo existe para 6/5/4/3 (`0x568118`: `cmp eax,2 / jbe` y después 6,5,4,3);
#   con 2 o menos no carga ninguna fila. ★ Y los archivos del propio juego lo confirman 4 de 4:
#   `npcitemtable.txt` trae `//0(6명) //1(5명) //2(4명) //3(3명)` al lado de cada fila, e
#   `itemappear.txt` encabeza con `//플레이어수(6~3)` = "cantidad de jugadores (6~3)".
#
#   ⚠ Y un riesgo NO MEDIDO: unas líneas más abajo hay un `div` por el tamaño de una lista de
#     candidatos (`0x56836D`). Si la que queda vacía con ≤2 es ésa, es división por cero **en el
#     master**. No está comprobado cuál de las varias listas de la función es. Si alguien
#     reporta un cierre arrancando un cooperativo de dos, mirar ahí primero.
COOP_MIN_JUGADORES = 3           # de 3 a 6, que es para lo que hay datos
COOP_MIN_SOLO_AVISAR = False     # ★ True = NO corta, sólo lo escribe en el log.
                                 #   Está para poder probar con menos gente: el usuario prueba
                                 #   con 6 Sandboxie y un solo par de manos, y un mínimo duro le
                                 #   bloquearía sus propias pruebas.

CHASE_RELLENO = True             # completar el minijuego de los que no reportaron
CHASE_RELLENO_PUNTAJE = 0        # el puntaje del que FALLA (0 = como el timeout del cliente)
CHASE_RELLENO_PUNTAJE_OK = 95    # el puntaje del que ACIERTA (tiene que ser >= 70)
# ★★★ CUÁNTOS de los rellenados aciertan. `None` = ninguno; todos con `CHASE_RELLENO_PUNTAJE`.
#   Es la perilla que hay que usar para probar.
#
#   ⛔⛔ POR QUÉ CUENTA "CUÁNTOS" Y NO "CUÁLES" — 2026-09-08, el banco de pruebas se engañó a
#      sí mismo. El preset del caso 2 decía `CHASE_RELLENO_SLOTS = {1:95, 2:88, ...}`, o sea
#      "que acierten los asientos 1 y 2". Pero **el humano se sienta en el 2** (medido: `.npc
#      full` ocupó [3,1,4,0,5]), así que el 88 se tiraba a la basura, y el slot 0 —que no
#      estaba en el dict— caía al 0 por omisión. Quedó 1 acierto de NPC en vez de 2, total
#      2 de 6, y el gorila se escapó cuando la prueba esperaba lo contrario.
#      ⇒ El servidor y el cliente estuvieron BIEN los dos: **el que estaba mal era el
#        experimento**. Lo detectó el usuario mirando la pantalla y preguntando "¿es normal?".
CHASE_RELLENO_ACIERTOS = None

# ★★★★★ NPC "COMO EN PROD" — LA HERRAMIENTA PARA PROBAR SOLO (2026-09-10, pedida por anonimo03).
#
#   EL PROBLEMA: probar el gorila en local con `.npc full` no se parece en nada a una partida de
#   verdad. Los rellenos salen todos con el mismo número (`CHASE_RELLENO_PUNTAJE = 0`), así que el
#   gorila **siempre se escapa**, y los NPC **no aparecen en el cartel** — con lo cual la pantalla
#   de premios sale con una sola columna y no se puede mirar el orden ni el resaltado.
#
# ★ CON QUÉ SE CALIBRÓ: **56 rondas reales de producción** del 10-sep, sacadas del log
#   (volcadas a `taller/_analisis/scores_gorila_prod.txt`, fuera de git). De ésas, 35 traen puntajes continuos (las otras 21 son
#   todas 0/80/100 — ⏳ **hipótesis sin comprobar**: gente con el ítem de juego automático).
#
#       n=173 puntajes · media 57,4 · mediana 64 · p25=36 · p75=82
#         0- 9   9 %        50-69  18 %
#        10-29  10 %        70-89  29 %
#        30-49  19 %        90-100 14 %
#       aciertos (>=70): 44 %   ·   rondas GANADAS: 16 de 35 = 46 %
#
#   ⇒ Con esta tabla, en local el gorila se atrapa aproximadamente la mitad de las veces, igual
#     que en prod. Se pueden probar **las dos salidas** sin trucar nada.
#
# ⛔⛔ SOLO PARA LOCAL. Va atado al MISMO interruptor que la consola de GM (`R2_CONSOLA_GM`, que
#   pone `startserver.bat` y que **systemd no pone nunca**). En prod queda apagado solo, sin que
#   nadie tenga que acordarse. Ver `CONSOLA_GM_TODOS` más arriba.
#   ⚠ Los NPC del cartel van con `usn = None`, así que **no cobran nada**: el pago de exp y rcoin
#     saltea las filas sin `usn`. Son decorado, no cuentas.
CHASE_NPC_REALISTA = bool(CONSOLA_GM_TODOS or CONSOLA_GM_USNS)

# Los tramos medidos: (desde, hasta, cuántos de 173 cayeron ahí). Se sortea el tramo con ese peso
# y después un número uniforme adentro. No es una gaussiana inventada: es la forma real.
CHASE_NPC_PUNTAJES = [(0, 9, 16), (10, 29, 17), (30, 49, 33),
                      (50, 69, 31), (70, 89, 51), (90, 100, 25)]

# ★ Y las columnas del cartel, del mismo log (6 carteles de coop del 10-sep):
#     pd    entre 66 y 97   (mediana ~87)
#     combo entre 109 y 582
#   La exp del NPC NO se inventa: se copia la MEDIANA de la que cobraron los jugadores de verdad
#   en ese mismo cartel, así la columna se ve coherente con la partida que se acaba de jugar.
CHASE_NPC_CARTEL = True                # que los NPC salgan también en el cartel de resultado
CHASE_NPC_PD = (66, 97)
CHASE_NPC_COMBO = (109, 582)

# ★★★★★ PRIMERO EL QUE ACTIVÓ EL MINIJUEGO, DESPUÉS LOS DEMÁS POR ESFUERZO — 2026-09-10.
#
#   ★ LA REGLA, corregida por anonimo03: *"el que 'atrapó' es el que llega a estar lo más cerca del
#     gorila y activa el minijuego"*. No es el que mejor le pegó a la cuerda: es el que llegó.
#
#   ⛔ Y EL SERVER NO SE ENTERA POR NINGÚN PAQUETE. El minijuego **nace dentro del cliente**:
#     medido en la captura del referente (`mitm_20260909_181537`), el `FF10F` con el puntaje
#     aparece **sin que el server haya mandado una sola cosa** antes. No hay a quién preguntarle.
#
#   ⇒ Se DEDUCE de la pista: el gorila corre adelante, así que el que va más adelante es el que
#     lo tiene más cerca. Y ese dato **ya pasaba por el server** — lo relevábamos sin mirarlo:
#     el `FF4E sub=0x05` trae un float que crece parejo con la carrera (305 · 366 · 431 · 492 ·
#     553 · 614 · 675 · 740 …, +61 por tic) y es el sub más frecuente de todos.
#     Se anota en `carrera.AVANCE_COOP` y se congela al resolverse la ronda.
#
#   ⚠⚠ ES UNA INFERENCIA, NO UNA MEDICIÓN. Nadie comprobó en el exe que el disparador del
#     minijuego sea la proximidad; sale de lo que anonimo03 ve jugando, que es buena evidencia pero no
#     es el binario. Por eso está detrás de este interruptor: en `False` el orden vuelve a ser
#     100 % por esfuerzo, que es lo que había antes y también funciona.
#   ⚠ Si nadie mandó avance (una sala de puros NPC, o la ronda se resolvió antes de que llegara
#     un solo `sub=0x05`), no hay activador y manda el esfuerzo. No hay caso "a la fuerza".
# ── ★★★ EL MEDALLÓN DEL COOPERATIVO: sale de QUÉ TAN RÁPIDO atraparon al gorila ──────────────
#   La regla la dio anonimo03, que es el que lo juega (2026-09-15): *"si lo atrapan durante la primera
#   canción es un S, si durante la segunda un B, si durante la tercera un D"*, y *"si no lo
#   atrapan es F = perder, lo que ocurre cuando las canciones se acaban y el gorila escapa"*.
#
#   ⛔ ANTES SALÍA DE LA PRECISIÓN, y por eso estaba mal. Medido en prod (15:49:19, 6 jugadores):
#     **cinco de seis sacaron B habiendo atrapado al gorila**, y la única S fue por tener 97 de
#     precisión, no por la captura.
#
#   ⚠⚠ LOS CORTES SON POR RONDA DEL MINIJUEGO, y que una ronda sea una canción es lo más probable
#     pero **NO está medido**: en prod aparecen rondas 0..5 con 3 canciones. Por eso están acá y
#     no clavados en el código — se afinan JUGANDO, mirando el log.
#   Formato: `(ronda_máxima, letra_ascii)`, en orden. La primera que alcanza, gana.
CHASE_MEDALLON_POR_RONDA = ((1, 0x53),      # rondas 0 y 1  -> 'S'
                            (2, 0x42),      # ronda 2       -> 'B'
                            (3, 0x44))      # ronda 3       -> 'D'
#                            (y de ahí en adelante, 'F')

#   ⚠ En False el medallón del cooperativo vuelve a salir de la precisión, como hasta hoy.
CHASE_MEDALLON_POR_CAPTURA = True

CHASE_PRIMERO_EL_QUE_ACTIVA = True

# ★★★★★ EL RITMO DE LOS NPC AL ABRIR SU COFRE — segundos entre uno y el siguiente (2026-09-10).
#
#   ⛔ EL PROBLEMA QUE RESUELVE, dicho por anonimo03: *"como los NPC no son 'yo' player, sus cofres se
#     abren pero NO PUEDO VER EL ORDEN"*. Y tenía razón por partida doble:
#       · abrían **todos en el mismo instante**, apenas elegía el primer humano ⇒ en pantalla es
#         un solo parpadeo y no se distingue quién fue primero;
#       · y abrían **en el orden en que estaban sentados**, no por aporte al gorila ⇒ aunque se
#         hubiera visto, no habría sido el orden bueno.
#     Lo segundo era un bug de verdad y se arregló: los NPC entran ahora en la MISMA fila que los
#     jugadores (`_orden_de_la_sala`). Lo de acá es lo que lo hace VISIBLE.
#
#   ⇒ Con `1.2`, cada NPC recibe su `sub 3` (se resalta su columna), pasa un segundo largo, y
#     recién ahí abre. Se puede seguir con el ojo: 1º, 2º, 3º…
#   ⚠ En **0 abren de golpe**, que es como venía. Prod va en 0: allá no hay NPC en cooperativo y
#     un temporizador de más es una carrera de más.
CHASE_NPC_RITMO = 1.2 if CHASE_NPC_REALISTA else 0.0

# ★ PARA PROBAR EL ORDEN A DEDO (sólo local). Los dos vacíos = comportamiento normal.
#   `CHASE_NPC_APORTES` fija cuánto "aportó" cada asiento de NPC ⇒ fija **el orden de elección**.
#   `CHASE_NPC_CAJAS`   fija **qué cofre** agarra cada asiento de NPC.
#   Con los dos puestos, la ronda entera es predecible y se puede comparar contra la pantalla:
#       CHASE_NPC_APORTES = {1: 500, 3: 400, 4: 300, 5: 200, 0: 100}
#       CHASE_NPC_CAJAS   = {1: 5,   3: 4,   4: 3,   5: 2,   0: 1}
#   ⚠ Si el cofre pedido ya lo agarró otro, se le da el primero libre y **se dice en el log**.
#   ★ Y el server escribe el ORDEN ESPERADO en el log antes de empezar, para cruzarlo con la foto.
#   ⚠ Los dos van gateados por `CHASE_NPC_REALISTA` dentro del código: en prod son inertes aunque
#     queden con algo adentro. Vaciarlos devuelve el sorteo al azar.
# ▶ PRESET PUESTO PARA LA PRUEBA DEL 2026-09-10 (anonimo03 quería ver el orden en pantalla).
#   Con esto, en una sala de 6 con `.npc full` el orden queda FIJO y se puede comparar con la foto:
#       1º slot 1 (NPC, cofre 5) · 2º slot 3 (NPC, cofre 4) · 3º slot 4 (NPC, cofre 3)
#       4º slot 5 (NPC, cofre 2) · 5º slot 0 (NPC, cofre 1) · y el HUMANO donde caiga su aporte
#   ⚠ El humano NO está acá: su lugar lo decide lo que aportó de verdad en el minijuego. Si sacás
#     buen puntaje elegís antes; si sacás 0, último. Eso es lo que se quiere comprobar.
#   ⚠⚠ Y LOS NÚMEROS TIENEN QUE ESTAR EN LA MISMA ESCALA QUE LOS DEL HUMANO, que son la SUMA de
#     sus puntajes del minijuego (0..100 **por ronda**, y la corrida son 3). Con 500/400/300 el
#     jugador queda último siempre; con 90/70/50 le gana a todos a partir de la 2ª ronda. No hay
#     número bueno: la escala del humano CRECE con las rondas y la del preset no.
#
# ▶▶ POR ESO `CHASE_NPC_APORTES` QUEDA VACÍO (2026-09-10, después de la prueba de anonimo03).
#    Ya cumplió: con el preset puesto se comprobó que el orden sale exacto (foto de la pantalla
#    contra el log, las dos veces). Pero **el preset vuelve FALSO el orden de los NPC**: manda el
#    número fijo, no lo que ese NPC hizo en la cuerda. anonimo03 lo cazó en pantalla:
#      *"el NPC que capturó no ocupó el primer asiento"* — y era esto, no un bug.
#    ⇒ Vacío, el aporte de cada NPC es **el que sacó de verdad en el minijuego** (se acumula en
#      `CARRERAS[rid]["puntos_npc"]`), igual que el de un jugador. El orden pasa a ser real.
# ★★★★★ EL AVANCE INVENTADO DE LOS NPC, relativo al mejor humano — SÓLO LOCAL (2026-09-10).
#   ⛔ Un NPC **no manda `FF4E`**: se mueve sólo dentro de cada cliente. El server es CIEGO a su
#     posición ⇒ sin esto, el "activador" saldría siempre el jugador humano, que es justo al revés
#     de lo que se ve en pantalla. anonimo03 lo describió exacto: *"los NPC han estado activando el
#     minijuego; ellos no corren pero tampoco chocan, y uno se acerca tanto que lo activa"*.
#   ⇒ En local se les inventa un avance parejo con el del humano, y a veces por encima (porque no
#     chocan). `(0.85, 1.20)` = entre el 85 % y el 120 % del mejor humano.
#   ⚠ Esto NO decide quién activó: inventa el AVANCE. El activador lo sigue eligiendo el mismo
#     `max()` para todos, humanos y NPC.
#   ★ En prod no hay NPC en cooperativo y este bloque ni se evalúa.
CHASE_NPC_AVANCE = (0.85, 1.20)

CHASE_NPC_APORTES = {}
# ★ Este SÍ se deja: no cambia el orden, sólo QUÉ cofre agarra cada NPC. Sirve para leer la
#   pantalla de un vistazo (cada uno siempre en el mismo cofre) sin falsear nada.
#   ⚠ Si el cofre ya lo agarró otro, se le da el primero libre y se dice en el log.
CHASE_NPC_CAJAS = {1: 5, 3: 4, 4: 3, 5: 2, 0: 1}
CHASE_RELLENO_SLOTS = {}         # {slot: puntaje} a dedo, por asiento. Tiene PRIORIDAD sobre
                                 # `CHASE_RELLENO_ACIERTOS`. ⚠ Frágil: hay que saber dónde se
                                 # sienta el humano. Se deja porque a veces hace falta un
                                 # asiento puntual, pero para probar usá `_ACIERTOS`.
# ★★★★★ PUNTOS DE RANKING — DOS ESCALERAS, no una (2026-09-05, de dos capturas del juego ORIGINAL).
#   Es el campo `@2` de cada fila del cartel, la columna "Puntos de ranking". Lo decide el server.
#
#   ⛔ Antes había UNA sola tabla, `{1: 250, 2: 215, 3: 175, 4: 100, 5: 50}`, sacada de nuestro
#      corpus a ojo ("baja monótonamente con el puesto"). Las dos capturas la desmienten en las dos
#      puntas: ni los valores ni la forma. Rangos observados en el corpus (172-349 para el 1º) eran
#      la mezcla de los dos modos, y por eso las bandas se solapaban.
#
#   SOLO (velocidad/ítem sin equipo) — escalera limpia de 100 en 100, del 1º al 6º:
#   El 7 es 'no llego'. En el corpus del referente esas filas traian 12-31 sobre un maximo de
#   ~349, o sea entre el 4 % y el 9 % del primer puesto; 50 sobre 600 cae justo ahi.
RANK_BONUS_SOLO = {1: 600, 2: 500, 3: 400, 4: 300, 5: 200, 6: 100, 7: 50}
#
#   POR EQUIPOS (equipo, relevo, y presumiblemente jefe) — NO hay escalera: es plano y binario.
#   Medido en un 3v3 de Speed Relay: los TRES del equipo ganador 700, los TRES del perdedor 300.
#   ★ Y en esa misma captura los perdedores tocaron MEJOR (combo 236 contra 137, estrella 100 %
#     contra 90 %) y perdieron sólo por TIEMPO. O sea que esta columna premia el RESULTADO, no el
#     desempeño. Es una carrera de postas.
RANK_BONUS_GANADOR  = 700
RANK_BONUS_PERDEDOR = 300

# ★★★★★ Y LA EXP TAMBIÉN SE DECIDE POR EL RESULTADO, en los modos por equipos (2026-09-05).
#   Sin esto pasaba lo que el usuario vio y no le cerró: *"no es muy gracioso que los que ganaron
#   tengan casi la misma exp"*. Peor todavía — en la partida real el que MÁS cobró era del equipo
#   que PERDIÓ, porque la exp salía sólo de `pd*10 + combo + star` y ellos habían tocado mejor.
#
#   CALIBRADO contra la captura del 3v3 original y el objetivo que puso el usuario
#   (ganador ≈ 1900, perdedor 1300-1500, con la sala llena):
#       base del ganador  = 88*10 + 137 +  90 = 1107      -> 1107 * 1.15 * 1.50 = 1910  ✔
#       base del perdedor = 84*10 + 236 + 100 = 1176      -> 1176 * 0.80 * 1.50 = 1411  ✔
#   ★ Fijate que la base del PERDEDOR es más alta: tocó mejor y perdió por tiempo. Que igual cobre
#     menos es el punto — en una carrera de postas manda el resultado.
#   Con menos gente baja solo, por el bono de sala: 4 jugadores da 1782 / 1317.
EXP_MULT_GANADOR  = 1.15
EXP_MULT_PERDEDOR = 0.80

# ★ DESCUENTO DEL COOPERATIVO (2026-09-05, pedido del usuario mirando los carteles simulados).
#   El coop pagaba 3726 con la sala llena contra los 1852 de ganar un relevo, y PERDIENDO pagaba
#   1863 — o sea que perder un cooperativo rendía lo mismo que ganar una carrera de postas. Sale
#   del `CHASE_EXP_MULT = 2.0` del modo, aprobado cuando el relevo estaba en 750.
#   Se resta un valor FIJO **al final de toda la cuenta**, para que el número que baja sea el que
#   se ve: con 6 jugadores −500, con 3 −300, que son los dos que pidió el usuario.
#   ⏳ Los de 1, 2, 4 y 5 son INTERPOLADOS entre esos dos anclajes (~67 por jugador), no pedidos.
CHASE_EXP_DESCUENTO = {1: 170, 2: 230, 3: 300, 4: 370, 5: 430, 6: 500}

# ★ Y EN COOPERATIVO LA BRECHA SE ACHICA: cada uno se acerca un 20 % al MEJOR de la sala.
#   Pedido del usuario: con la sala llena el primero queda igual (~3226) y el último sube de 2431
#   a ~2600, bajando gradual. Tiene sentido de diseño: en el gorila se gana o se pierde JUNTOS,
#   así que el premio no debería abrirse tanto entre el que más aportó y el que menos.
#   ⚠ Se acerca al MEJOR y no al promedio: acercar al promedio también bajaría al primero, y el
#     pedido era dejarlo donde está.
#   Con `0.20`: 3226 · 3099 · 2972 · 2844 · 2717 · 2590.
CHASE_EXP_ACERCA_AL_MEJOR = 0.20
#
#   ⏳ Cooperativo y jefe: sin captura. Por ahora usan la escalera de solo, que es lo que había.
RANK_BONUS_POR_PUESTO = RANK_BONUS_SOLO
# ★ EL RCOIN FIJO DEL CARTEL. El cliente muestra `(u16)(coin + basecoin)` (`0x579E70`) y no
#   calcula nada: `coin` es lo que el jugador junta en la pista y viene en su reporte; esto lo
#   pone el server. ⇒ el que no junta ni una moneda igual cobra esto.
#   · en las 17 filas capturadas del server de referencia va de **25 a 40**, sin correlación con
#     nada (ver `CAPTURA_2026-09-02_GAMEPLAY.md`, sección del basecoin);
#   · **400 es una decisión de diseño del usuario (2026-09-05)**, no un dato del juego. Diez veces
#     lo que hacía ese server. Queda dicho para que nadie lo lea como "restaurado".
#   ⚠ Se trunca a u16: `coin + basecoin > 65535` muestra basura. Con 400 hay margen de sobra.
#   ⚠ Al PERDER se manda 0, por `FF28_DERROTA_CEROS`.
FF28_BASECOIN = 400

# ★★★ LAS COLUMNAS DEL CARTEL DE COOPERATIVO (2026-09-02, de una foto de la pantalla).
#   El cartel de "CHASE TOGETHER" tiene SEIS columnas, y tres no las mandamos:
#
#       EXP  |  Usar Booster (x/y)  |  Ayuda (n)  |  Usar Item (x/y)  |  Rcoin  |  Rank
#
#   Ya sabemos tres:  EXP = el `exp` de la fila · Rcoin = el `basecoin` · Rank = la medalla.
#   Faltan las otras tres, y los candidatos son los campos que sólo se llenan en cooperativo:
#   `b_d`/`b_e` (siempre casi iguales, pinta de par x/y), `b_f`, y los dos primeros bytes del
#   bloque de 12. Con las muestras que hay NO alcanza para decidir: en la captura `b_d`/`b_e`
#   llegan a 17/18 y en la foto el par más grande es 9/9, y son partidas distintas.
#
#   ⇒ CENTINELAS. Con esto en `True` cada campo sin mapear sale con un número distinto y
#     reconocible; se juega UNA partida de cooperativo, se mira el cartel, y cada número dice
#     dónde cayó. Es el mismo método con el que se mapeó el `FF13` y el `FF6E`.
#     ⚠ Dejarlo prendido manda basura en el cartel: es para UNA corrida, no para jugar.
#     ⛔⛔ APAGADO 2026-09-05, DESPUÉS DE TRES DÍAS PRENDIDO. Lo reportó el usuario:
#        *"el valor del cartel de booster - item - ayuda siempre son los mismos"*. Claro: son
#        los números de sonda, no datos. Quedó prendido desde el 02-sep y **nadie anotó el
#        resultado**, así que se pagó el costo de ensuciar el cartel tres días sin cobrar el
#        beneficio de mapear las columnas.
#        ⇒ REGLA: una corrida de centinelas se prende, se juega UNA partida, se ANOTA lo que
#          se vio, y se apaga en la misma sesión. Si no se anota, no se prende.
#        ⇒ Cuando se retome: prenderlo, jugar una de cooperativo, mirar el cartel y anotar
#          QUÉ NÚMERO cayó en QUÉ columna. El server ahora escribe la leyenda en el log al
#          armar el cartel, así que alcanza con cruzar la foto contra esa línea.
#     ★★ PRENDIDAS DE NUEVO EL 2026-09-05, a pedido del usuario: la vez pasada se apagaron sin
#        que nadie sacara la foto. **Esta corrida es para la foto.** Se juega UNA de cooperativo,
#        se mira el cartel, se anota qué número cayó en qué columna, y se apaga.
FF28_CENTINELAS = False                 # ⚠ para UNA corrida y se apaga. Ver arriba.
# ⏳ EL CARTEL DE DERROTA "CORRIDO" — sospechoso, no confirmado (2026-09-05).
#   Comparados byte a byte, el cartel de victoria y el de derrota **miden lo mismo** (41 B por
#   fila, mismo layout). Sólo cambian TRES valores: `rank_bonus` (600 -> 0), `basecoin` (35 -> 0)
#   y la letra del medallón ('S' -> 'F'). ⇒ El corrimiento **no es un desfase de bytes nuestro**.
#   Quedan dos explicaciones: (a) el cliente arma otra pantalla al perder, o (b) una de las dos
#   columnas en CERO se colapsa y arrastra la vista.
#   Con esto en `False` la derrota manda los MISMOS valores que la victoria. Si así deja de salir
#   corrido, la causa es (b) y está acá. Prueba de una línea.
FF28_DERROTA_CEROS = True
# ★★★ VALORES POR CAMPO, NO POR BYTE (2026-09-05, corregido con el cliente 2019).
#   El "bloque de 12 bytes" **no son 12 bytes sueltos: son SIETE campos**. El 2013 lo lee de un
#   saque y por eso parecía una bolsa; el 2019 lo lee uno por uno (`0xD03D99`…`0xD03E11`) y ahí
#   se ve la forma:  **u8, u8, u16, u16, u16, u16, u16**.
#   ⛔ Por eso la sonda de bytes sueltos no podía servir: poner 103 y 104 en los bytes 2 y 3 le
#      llega al cliente como el u16 **26727**, que en pantalla no se parece a nada.
#
#   Ahora cada campo lleva UN número, elegido para que se lea de una:
#       c0, c1  = 11, 22        los dos bytes sueltos
#       c2..c6  = 301..305      los cinco u16
#       b_d, b_e, b_f = 41, 42, 43   los tres sueltos del final de la fila
#
#   ★ Las columnas que faltan son *"Usar Booster (x/y)"*, *"Ayuda (n)"* y *"Usar Item (x/y)"*:
#     dos PARES y un suelto. Encajan justo con esta forma, así que la foto debería resolverlo.
#   ⚠ `b_a`, `b_c` y `b_g` se dejan en 0 a propósito: ya estaban en cero y no conviene meter tres
#     variables nuevas en la misma corrida. Si alguna columna sale vacía, ésos son los siguientes.
# ★★ 2ª CORRIDA (2026-09-05) — MODO BYTE, para deshacer un empate.
#   La 1ª corrida (modo campo: c0=11, c1=22, c2..c6=301..305) resolvió DOS de las tres columnas,
#   exacto, y las dos por la foto del usuario:
#       ✅ "Ayuda (n)"       = `b_f`            -> mostró 43
#       ✅ "Usar Item (x/y)" = `b_d` / `b_e`    -> mostró 41/42
#   Pero **"Usar Booster (x/y)" quedó ambigua**: mostró algo como `…45/11`. El `11` es `c0`, pero
#   el otro número no se puede atribuir — `45` es `0x2D`, que es el byte BAJO de `c2` (301). O sea
#   que no se sabe si el cliente 2013 lee ese bloque como u16 (como el 2019) o **byte a byte**.
#   ⇒ Ahora un número distinto POR BYTE, todos de dos cifras y ninguno confundible con 41/42/43:
#     lo que muestre la celda dice EXACTAMENTE qué byte es, sin truncamientos que interpretar.
FF28_CENTINELA_VALORES = {"b12_0": 51, "b12_1": 52, "b12_2": 53, "b12_3": 54,
                          "b12_4": 55, "b12_5": 56, "b12_6": 57, "b12_7": 58,
                          "b12_8": 59, "b12_9": 60, "b12_10": 61, "b12_11": 62,
                          # ★ éstos se dejan IGUAL que en la 1ª corrida a propósito: ya están
                          #   confirmados y sirven de ancla para comparar las dos fotos.
                          "b_d": 41, "b_e": 42, "b_f": 43}
RESPONDER_COMO_EL_REAL = True          # contestar los polls que antes dejábamos mudos (ver FF45/FF54)
REFRESCAR_ROPA_EN_SALA = True          # re-mandar el FF0C a la sala cuando alguien se cambia (FF1A)
REFRESCO_ROPA_FF15 = True              # ★ la vía del server 2011: FF15 fuerza el reload del mesh
REFRESCO_ROPA_RESPAWN = False          # respaldo DEDUCIDO (FF0E+FF0C) si el FF15 no anduviera
# ⛔ REVERTIDO 2026-09-01, a los 10 minutos de ponerlo: el jugador apareció DESNUDO.
#   El error fue de método: en el wire real la entrada propia venía con `itemcount=1`, pero el
#   jugador de esa captura (`TunTunSahur`, exp 1120 = cuenta recién hecha) **estaba desnudo de
#   verdad**. Generalicé una regla de una sola muestra. Tu ropa SÍ va en tu propio FF0C.
FF0C_YO_SIN_ROPA = False
FF0C_X0, FF0C_DX, FF0C_Z = -500.0, 200.0, -140.0     # posición del asiento por slot
# ★ La sala de 12 (6vs6, 10-oct): los asientos 6..11 se paran en una SEGUNDA FILA, atrás y al tresbolillo (corridos
#   medio lugar). La posición la decide el server en el FF0C (el exe no tiene tabla: informe del agente,
#   _trabajo/grupo/agente_avatares/INFORME.md §2); el piso de la sala multi va de X −1600..1600, Z −330..198.
#   En una sala normal los asientos 6..11 son espectadores y no se dibujan: esto no cambia nada ahí.
FF0C_FONDO_X0, FF0C_FONDO_Z = -400.0, 100.0


# ★★★★ 2026-09-01 — EL ID QUE VIAJA EN EL WIRE LLEVA EL CÓDIGO DE PERÍODO.
#   Síntoma: el jugador compró y equipó las alas, el FF0C SÍ las llevaba, y no aparecían.
#   Comparando con el REFERENTE: para las alas manda **1002513**, y el `Index` del catálogo es
#   `1000513` ("Alas de jugador36"). El dígito de MILES es el código de período (`period_code`):
#   1=P7 · 2=P30 · 9=PI(permanente). O sea, el real reporta el ítem TAL COMO SE COMPRÓ.
#   Nosotros normalizamos en la compra (`raw=1002690 -> item=1000690`) y mandamos el id "pelado",
#   que para estas alas **no es una variante que la tienda venda**: `1000690 "Alas Fenix Duo"` sólo
#   existe con `P30` (código 2).
#   ⚠ ALCANCE A PROPÓSITO ACOTADO: en el wire real conviven las dos formas — la ropa de guardarropa
#     viaja pelada (310566, 410491, 510429...) y sólo algunas llevan código. Como nuestra ropa de
#     guardarropa YA se ve bien, esto se aplica **sólo a las familias que están fallando**, no a todo.
# ⛔ APAGADO 2026-09-01: el modo PRÁCTICA renderiza las alas con el id PELADO (1000690), así que
#    el cliente resuelve ese id perfectamente y la teoría del código de período **no era la causa**.
#    Se deja el mecanismo por si algún día hace falta, pero no se usa: no acumular cambios sin probar.
WIRE_ID_CON_PERIODO = False
WIRE_ID_FAMILIAS = {"aura_summon", "pet"}      # alas / mascotas





# ★★★★★ 2026-09-01 — FF15: LO QUE FUERZA EL REDIBUJO DEL AVATAR EN LA SALA.
#   El síntoma (cambiarse los ojos o las alas dentro de la sala no actualiza el muñeco) ya estaba
#   resuelto y REVERSADO en el server del CBT 2011, que lo documenta así:
#       · "FF0C NO re-renderiza prendas de un ocupante ya dibujado; FF15 fuerza el reload con el
#          worn NUEVO"
#       · "PISA la apariencia COMPLETA del ocupante (identificado por SLOT) y al final dispara el
#          reload que reconstruye el mesh leyendo [occ+0x1a1]=faceByte"
#       · se manda a TODOS **incluido el dueño**: en sala tu propio avatar se renderiza desde el
#         registro de ocupante, no desde el avatar local.
#       · como PISA todo, hay que mandar el `worn` COMPLETO (`[char_id] + prendas`) o borra la ropa.
#   ★★ Y el campo #9 = **Wing.Id**, que la versión VIEJA del 2011 mandaba en cero. Su nota:
#       "#9 = Wing.Id para CAMBIOS en vivo ... Sin esto, equipar/quitar un ala estando ya en la
#        sala no se vería hasta re-entrar (el FF0C solo re-dibuja a ocupantes nuevos)."
#     Es exactamente el segundo síntoma reportado (las alas tampoco se actualizaban).
#   Acá se re-implementa el layout (17 campos, 5 con carga: slot, char_id, worn, Wing.Id, faceByte);
#   NO se copian bytes del 2011. El handler en el cliente 2013 es `0x5F4360` (tabla RX, cmd 0x15) —
#   ⚠ el del 2011 era `0x58dc60`: es el MISMO comando en otra build, así que el layout hay que
#     darlo por PROBABLE hasta verlo en pantalla, no por confirmado.
# ★★★★★ LA COTA DEL WORN — no es cosmética, sin esto el server escribe en la PILA del cliente.
#   Traída del server 2011 modularizado (`servidor/catalogo.py`, cota agregada el 2026-08-14):
#   el clasificador del cliente se queda con `(id % 10^7) // 100_000` = 0..99 y con ESE número
#   indexa un arreglo de pila SIN comprobar nada. En el handler del FF15 el arreglo es de **11
#   dwords y no tiene cookie /GS**: el índice 11 cae JUSTO en la dirección de retorno, y el valor
#   escrito es el propio item_id. O sea que una pieza de categoría >= 11 en el `worn` no es un
#   cuelgue: es una escritura de memoria elegida por el server.
#   Las categorías reales del avatar llegan hasta 10; del 11 para arriba son consumibles (cupones),
#   que no tienen malla ni ranura y nunca debieron viajar en un worn.
#   ✅✅ VERIFICADO EN EL CLIENTE 2013 — 2026-09-15. Este comentario decía *"NO verificamos que el
#     arreglo mida lo mismo"*. **Ya está verificado, y mide lo mismo: 11 dwords, en DOS handlers.**
#
#       FF15  0x5F3846  push 0x2c              ; memset del arreglo = 44 B = 11 dwords
#             0x5F387C  call 0x50E0B0          ; el clasificador -> al
#             0x5F3888  mov [esp+edx*4+0xa0], eax   ; ⛔ escribe SIN comprobar el índice
#       FF0C  0x5E8433  push 0x2c              ; el MISMO tamaño
#             0x5E845C  call 0x50E0B0
#             0x5E8468  mov [esp+ecx*4+0x138], edx  ; ⛔ ídem
#
#   ★ Y el clasificador del 2013 (`0x50E0B0`) hace **exactamente** nuestra cuenta, por un camino
#     raro pero equivalente: `id % 10^7` (multiplicador mágico `0x6B5FCA6B` + `imul 0x989680`),
#     lo pasa a texto, **le corta los últimos 5 caracteres** y lo vuelve a número.
#     ⇒ `categoria_worn()` coincide con el cliente. La fórmula no es una aproximación nuestra.
#
#   ⇒ La cota **se queda en 11**, ahora por medición propia y no por herencia del CBT.
#
#   ⚠⚠ CONSECUENCIA CONCRETA, y por eso vale la pena saberlo: **la Joya de la Amistad es
#     categoría 12** (`1200088` → `12`), así que **no puede viajar en el worn de ningún paquete**.
#     La ayuda del juego dice *"Equipar Joya de la Amistad… aparece cuando estés junto a tu amigo
#     del alma"*, o sea que el efecto existe — pero sale por otro camino, no por el worn.
#     ⏳ Los candidatos medidos son `desc+0x54`/`desc+0x58` del `FF0C`, que van a `nodo+0xD8` y
#       `nodo+0xD4` (`0x527DE0` y `0x527D70`). Sin cerrar. Ver `AMIGO_DEL_ALMA.md` §9.
CATEGORIAS_WORN = 11
OCUPACION  = {}                        # roomid -> {slot: usn}  = la MESA de cada sala

# ══════════════════ LUGARES PERSISTENTES (Sala de Conversación / Mi Casa) ══════════════════
# ★★★★ CAMBIO DE MODELO (2026-08-05, a pedido del usuario, que jugó el original):
#   > "son como salas de gameplay que NUNCA empiezan la partida y NUNCA cierran; la sala siempre
#   >  está viva aunque no esté nadie — por eso Libre 0 / Libre 1 / Libre 2 siempre existían"
#
#   Antes esto estaba MAL: no había ningún objeto de sala. Al entrar se sintetizaban el FF13/FF0C/FF61
#   sobre la marcha y al salir no quedaba nada ⇒ **cada entrada era una sala nueva improvisada**.
#   Eso hacía imposibles tres cosas a la vez: la lista de instancias (no hay instancias que listar),
#   la columna "Estado" (no hay a quién contar) y cualquier estado compartido de la sala.
#
#   Ahora las instancias se crean **al arrancar el server** y no se destruyen nunca. Entrar es UNIRSE
#   a una que ya existe.
#   ⚠ La CAPACIDAD (40) y los números de sala los hornea el CLIENTE; acá sólo llevamos la cuenta.
# ★ BISECCIÓN DEL MOVIMIENTO. El usuario reporta que **SÍ se podía mover** hace unos tests, y en
#   ese momento el FF0C del lugar llevaba un ocupante MÍNIMO (slot/nick/char_id/parts). Al pasar a
#   `armar_ocupantes()` (registro COMPLETO, con exp y demás) dejó de moverse. Encaja con lo medido
#   por el agente: la guarda `0x59CC17` mira `[user+0x14a]`, y esos bytes salen de la ENTRADA DEL
#   FF0C ⇒ algún campo del registro completo lo marca como 'sentado/bloqueado'.
#   True = registro mínimo (se mueve, pero el panel de usuarios muestra menos datos).
# ★★★★★ RESUELTO 2026-08-05: lo que trababa el movimiento en los lugares especiales era el **`exp`**
#   del ocupante del FF0C. MEDIDO: el cliente lo pasa por `ExpToLicencia` (`0x484A40`, tabla de
#   niveles en `0x8782A8`) y guarda la LICENCIA resultante en el descriptor del ocupante; con
#   licencia > 1 el input de movimiento queda bloqueado. Los otros 3 campos que sospechábamos
#   (`identity`, `gender`, `guild`) toman el MISMO valor se manden o no ⇒ nunca fueron el problema.
#   ⇒ Ya no hace falta el ocupante mínimo: va el COMPLETO (lista de usuarios poblada) pero con la
#     exp ACOTADA, así se mueve igual.
#   ⚠ Umbral medido: nivel 11 = 57.956 de exp, y ahí la licencia salta de 1 a 2.
FF0C_LUGAR_MINIMO = False
# ⚠ BISECCIÓN EN CURSO (2026-08-05). Con 57955 (= nivel 10, licencia 1) el jugador SIGUE SIN
#   MOVERSE, así que la explicación 'la licencia > 1 bloquea' NO alcanza. Se prueba con 0, que es
#   exactamente lo que llevaba el ocupante mínimo con el que SÍ se movía. Si con 0 se mueve, el
#   culpable es la exp y el umbral está entre 0 y 57955; si tampoco, la exp es INOCENTE y la
#   diferencia está en otro lado.
# ⛔ La exp resultó INOCENTE: con 57955 y con 0 el jugador seguía sin moverse. El bloqueo era el
#   slot mal listado (ver el bug del `or` en armar_ocupantes). Se manda la exp REAL otra vez;
#   0 = sin tope. Si algún día vuelve a aparecer algo raro con la licencia del ocupante, acá está
#   la perilla, pero no hay motivo para usarla.
LUGAR_EXP_TOPE    = 0
# ★ Cerrar el socket de login también cuando el cliente RE-LOGUEA sin pedir el FF02 (cambio de
#   canal). Sin esto el selector de canales sólo funciona UNA vez. Ver el comentario largo abajo.
CERRAR_LOGIN_EN_RELOGIN = True
RELOGIN_ESPERA          = 2.0      # segundos de gracia antes de dar por hecho que no viene el FF02
LUGAR_CAPACIDAD  = 40                  # medido: el slot del FF61 acepta 0..39 (0x28 = lleno)
# ★ ORDEN EN QUE SE SIENTAN LOS JUGADORES. El creador SIEMPRE cae en 2 (lo fija el cliente solo en
#   CREATEROOM), así que esto manda del 2º en adelante.
#   ✅ CONFIRMADO POR EL USUARIO (2026-09-05): *"el orden para los joiners, sea cual sea el modo de
#   juego, debe ser 2-3-1-4-0-5"*. Venía del CBT y estaba anotado como inferido; ya no lo es.
#   La lógica es que los dos equipos se llenan **desde el centro hacia afuera** y alternando lado,
#   para que nunca queden desparejos: 2 (rojo) · 3 (azul) · 1 (rojo) · 4 (azul) · 0 · 5.
#   ★ Es el mismo criterio que usa `h_47_ff18` al cambiar de equipo: el asiento más cercano al
#     centro (rojo `2,1,0` · azul `3,4,5`). El slot_mask 0x3F abre los 0..5.
ORDEN_ASIENTOS = [2, 3, 1, 4, 0, 5]
# ★ Y EN LA SALA DE 12 (6vs6, 10-oct). anonimo03 lo dibujó tarjeta por tarjeta: el creador en la 3 (asiento 2, como
#   siempre) y de ahí ALTERNANDO fila de arriba (rojo, 0..5) y fila de abajo (azul, 6..11), del centro hacia afuera
#   ⇒ los equipos quedan parejos en cada entrada. Tarjeta → orden de llegada: 1→9 2→5 3→1 4→3 5→7 6→11 · 7→10 8→6
#   9→2 10→4 11→8 12→12.
ORDEN_ASIENTOS_12 = [2, 8, 3, 9, 1, 7, 4, 10, 0, 6, 5, 11]
# ★ EL RELEVO DE 12 (14-oct, documentacion/RELEVO_12.md): 4 equipos de 3 en lugares FIJOS (anonimo03, la 2.ª captura):
#   fila de arriba 1-3 ROJO · 4-6 AZUL · fila de abajo 7-9 VERDE · 10-12 NARANJA (asiento = tarjeta − 1). Se reparte
#   de a uno por equipo (rojo, azul, verde, naranja, y vuelta), así los equipos se llenan parejos.
ORDEN_ASIENTOS_12_RELEVO = [0, 3, 6, 9, 1, 4, 7, 10, 2, 5, 8, 11]
RELEVO12_EQUIPOS = 4                     # rojo 1 · azul 2 · verde 3 · naranja 4
RELEVO12_POR_EQUIPO = 3                  # anonimo03: «cada equipo debe tener sus 3 jugadores completos para empezar»
RELEVO12_MIN_EQUIPOS = 3                 # anonimo03: «la partida empieza con al menos 3 o 4 equipos»

# ★★★ LA PUERTA DEL MODO ESPECTADOR (2026-09-07).
#   Con esto en True, cuando alguien intenta entrar a una sala LLENA se le contesta el `0x10` en
#   vez del `0x0F`. El `0x10` saca el popup 519 —*"No hay lugares vacíos en la sala. ¿Desea ser
#   espectador del juego en lugar de ello?"*— con dos botones; el `0x0F` sólo dice "no hay lugar".
#   ★ El modo espectador se decide AL ENTRAR, no estando sentado: por eso las sondas sobre el
#     `FF99` no movían a nadie a la lista. Ver `h_18_ff11` y `documentacion/`.
#   ⏳ Falta medir qué manda el cliente cuando el jugador acepta (candidatos `FFBA`
#     `CmdJoinRoomMassOb` y `FFBB` `CmdUpdateMassObservers`). Va a caer en `SIN handler`.
#   ⚠ En False vuelve al rechazo de siempre, sin tocar nada más.
OFRECER_ESPECTADOR = True

# ⛔⛔ EL `FFBB` **NO** VA A LOS QUE ESTÁN JUGANDO — 2026-09-08, medido en pantalla.
#   Con esto en True el contador de espectadores se difunde a toda la sala. Se probó y ROMPIÓ EL
#   ARRANQUE: el `FFBB` hace `[cRoom+0xC1C] = 1`, o sea *"esta sala está en modo espectadores"*, y
#   los que estaban sentados empezaron a recibir **"No puede iniciar el juego solo en Multi juego"**
#   con la sala en 2 jugadores y los dos listos. Peor: **la bandera no se apaga** (el handler
#   `0x5D7EC0` sólo tiene la rama de "> 0 -> prender"), así que el daño sobrevive al espectador.
#   ⇒ Queda en False. La bandera es de la VISTA del que mira, no del estado de la sala.
FFBB_A_TODA_LA_SALA = False

# ★★★ LOS CASILLEROS DE MIRAR, EN EL ORDEN EN QUE SE REPARTEN — y esto es una SONDA.
#   El `FF11` acepta slots `0..0x0B`: la sala tiene 6 asientos (0..5) y los **6..11** son los de
#   mirar. Se reparten en este orden, el primero libre.
#   ⛔ POR QUÉ ES UNA SONDA (2026-09-08): el 3er espectador —el del casillero **8**— crashea, y los
#     de los casilleros 6 y 7 no. El usuario preguntó justo lo que hay que preguntarse: *"¿por qué
#     sólo le pasa a él, o es por el slot de espectador que usa?"*.
#   ★ EL EXPERIMENTO QUE ESTÁ PUESTO AHORA: **el 8 se manda al final**, así que con hasta cinco
#     espectadores NO SE USA. El tercero que entre se lleva el 9.
#         · si el tercero **sigue crasheando** -> no es el casillero: es SER EL TERCERO (o es esa
#           cuenta) y hay que mirar qué tiene de distinto ese jugador;
#         · si **deja de crashear** -> el casillero 8 es el problema y se saca de la lista.
#     Es no destructivo a propósito: mide y, si la respuesta es la segunda, además lo arregla.
#   ⇒ La variante fuerte, para cuando haga falta: poner el 8 PRIMERO y que entre cualquier cuenta.
#     Si crashea el primero, es el casillero y no la persona. Misma bisección del ícono de licencia.
ESPECTADOR_SLOTS = (6, 7, 9, 10, 11, 8)
# ★ 14-oct · EL ESPECTADOR EN LA SALA DE 12 (documentacion/ESPECTADOR_12.md): los 12 lugares son corredores, así que
#   el que mira va al 12..17. Ese número NO cabe en el byte del FF11 (0x0C.. son errores): va el código propio
#   ESPECTADOR12_CODIGO + k y la dll (espectador12.c) lo convierte en el lugar 12 + k. Sin la dll: un error genérico.
ESPECTADOR_SLOTS_12 = (12, 13, 14, 15, 16, 17)
ESPECTADOR12_CODIGO = 0x30
# ★ 17-oct · (87) LOS QUE MIRAN, TAMBIÉN EN LA LISTA DE LOS CORREDORES (anonimo03: «la lista de espectadores no se puebla para
#   todos: desplegué la lista en otro corredor y se veía vacía»). Desde el 14-oct el FF0C del que mira (lugar 12..17) iba
#   SÓLO a los otros que miran — por precaución: la caída medida era del espectador SIN su propia ficha. En la de 6 los
#   corredores tienen a los que miran (6..11) y el juego lo maneja; en la de 12 la dll marca «mirón» a todo lugar ≥ 12
#   (0x528C54) y no dibuja su muñeco (0x58DEC0). En False: como antes (la lista sólo la ven los que miran).
ESPECTADOR12_A_CORREDORES = os.environ.get("R2_ESPECTADOR12_SOLO_MIRONES") != "1"
# ★ 17-oct · (87) Visualizar/Competir en la de 12 con el FF99 NATIVO (mueve de lugar sin rehacer la sala, como la de 6).
#   Va con la dll que recalcula la marca «soy mirón» tras el FF99 (sala12_vista.c). False: salir y volver a entrar (FF11).
FF99_12_NATIVO = os.environ.get("R2_FF99_12_REHACER") != "1"

# ── ★★ (92) 18-oct · LOS QUE MIRAN, REPUESTOS DETRÁS DEL QUE ENTRA (salas.difundir_ocupante) ──────────────────────────
#   anonimo03: «cuando un jugador nuevo entra, la lista de espectadores se vacía». Medido (la sala de jugador52 recreada 1 a 1,
#   sonda en el padrón): el FF0C k=1 del que entra («principio de lista») le borra a cada cliente los casilleros 6..11 de
#   la sala y del padrón — también al que mira su PROPIA ficha ⇒ al largar se cree corredor en el lugar 6/7 y se cierra
#   (prod 17-oct: jugador52, jugador10, jugador51; caja negra 0x4851C5 desde 0x563162). ⇒ detrás del k=1, el FF0C ESPECTADOR
#   de cada uno que mira con k=2. El FF99 nativo (sin rearmar la sala) queda como está. ESPECTADOR_EN_VIVO.md §6.
#   `R2_SIN_REPONER_ESPECTADORES=1` = como antes (el control al revés).
ESPECTADORES_TRAS_EL_QUE_ENTRA = os.environ.get("R2_SIN_REPONER_ESPECTADORES") != "1"

# ★★★★★ EL CAMBIO DE PUESTO SIN RECARGAR LA SALA — `FF99` de 5 bytes (2026-09-08, DESENSAMBLADO).
#   En False se contesta el `FF99` con un `FF11 [slot][tipo]`: anda, pero el cliente **reconstruye
#   la escena**, o sea que cambiar de puesto se ve como salir y volver a entrar. Lo reportó el
#   usuario y por eso se midió el camino bueno.
#
#   ★ EL HANDLER REAL ES `0x5E4A40` (sacado con `python taller/re2013/tabla_rx.py 0x99`).
#     ⛔ La nota vieja decía `0x5E5050` y **eso es una rutina de ordenamiento**: ahí no hay
#       ningún handler. Es el tercer disasm de esta zona que sale de una dirección mal anotada.
#       La tabla se EXTRAE, no se copia.
#
#   Lee CINCO bytes y el primero es el TIPO:
#       [tipo][origen][destino][equipo_origen][equipo_destino]
#
#       tipo 0 -> mueve, **sin cartel**            ← el que usamos
#       tipo 1 -> mueve y además `0x5E4140`
#       tipo 2 -> mueve y saca el popup 517 ("El juego que mirabas terminó, ¡competí ahora!"),
#                 pero SÓLO si uno de los dos puestos es el mío
#       tipo 3 -> popup 515 ("No hay lugares vacíos… ¿desea ser espectador?")   = RECHAZO
#       tipo 4 -> popup 516 ("El espectador no puede seleccionar un equipo")    = RECHAZO
#       otro   -> sólo lo loguea
#     ⇒ Los ids 515/516/517 son los del modo espectador (ver `MODO_ESPECTADOR.md` §4): este
#       paquete **es** el del botón, y los rechazos ya vienen con su texto hecho.
#
#   El tipo 0 llama a `0x5A0900(origen, eq_origen, destino, eq_destino)`, que busca los ocupantes
#   de los dos puestos y:
#       · si los DOS existen -> los intercambia (se pisan el campo `+0x155`, que es el puesto)
#       · si el DESTINO está vacío -> `0x5A0590(origen, destino)` = **lo MUEVE**
#   Y `0x5A0590` termina con lo que hace que esto valga la pena:
#       005a0880  cmp byte [me+0x40], bl      ; ¿el que se movió soy YO?
#       005a088c  mov byte [me+0x40], dl      ; ★ entonces mi asiento pasa a ser el destino
#   ⇒ **el cliente se re-ubica solo, sin reconstruir la sala**. Eso es exactamente lo que se pidió.
#
#   ★ Y CONFIRMA LOS CASILLEROS 6..11 DE UNA FORMA QUE NO DEJA DUDAS: en `0x5A0590`,
#       005a0618  cmp al, 6
#       005a061a  jae  <sigue>                ; destino >= 6 -> SE SALTEA el chequeo de abajo
#       005a061f  cmp byte [destino + cRoom + 0x9280], 0
#       005a0627  je   <sale sin hacer nada>  ; asiento CERRADO -> no se mueve
#     O sea: el cliente **acepta destinos 6..11 a propósito** (no valida esos), y **rechaza solo
#     un asiento cerrado 0..5**. La intuición del usuario —*"debe depender de si el slot está
#     abierto o cerrado"*— está escrita en el binario.
#   ⚠ Si `equipo_origen` viene 0xFF, el handler fuerza `equipo_destino = 0`. Por eso mandamos 0.
ESPECTADOR_CAMBIO_5B = True

NICK_MAX_FF0E = 15                     # ⚠ ver difundir_salida()
# ★★ EL FF0E DE UNO QUE SE VA EN PLENA CARRERA DE EQUIPOS ESPERA A QUE VUELVAN A LA SALA — 16-oct.
#   Las olas de prod (jugador16, 12 por equipos): uno se corta, el server le manda el `FF0E` a los
#   que quedan y **los 11 se caen en el mismo segundo** (AV leyendo 0 en `0x635362`, el medidor de
#   texto `0x635350`, llamado desde el dibujo por corredor de la carrera `0x4F97D0`→`0x500C66`).
#   El cliente lo saca de la sala pero la carrera lo sigue dibujando: su nombre ya es NULL.
#   Reproducido en local 2 de 2 (`herramientas/qa/director.py --caer jugador13:36`), también con el
#   globo apagado. ⇒ En la sala de 12, al que está corriendo se le GUARDA el `FF0E` y se le
#   manda cuando vuelve (su `FF13`). Ver `salas.difundir_salida` / `salas.soltar_ff0e_pendientes`.
#   ★ 17-oct · LA CAUSA: 0x4FC6E0 saca de la pista al que se fue SÓLO si su asiento es < 6 (`cmp bl,6`, 0x4FC979):
#   en la de 12 los de los asientos 6..11 quedaban sin nombre y corriendo. Por eso es «sala de 12» y no «por
#   equipos» (en prod cayeron también las de todos contra todos y 6 contra 6). La dll nueva lo arregla
#   (grande.c, gr_abandono) y lo avisa por FF59 («R2DLL abandono12=1»): a ése el FF0E le va en el momento.
FF0E_EN_CARRERA_ESPERA = True
# ★★ EL FFBB DE LA SALA DE 12 VA ANTES DEL GO — 16-oct (ESPECTADOR_12_SIN_TRANSMISION.md). `0x4F0A80` arma el reloj
#   del FF98 una sola vez al procesar el GO; si el FFBB llega después, ese corredor no transmite en toda la carrera.
#   False (con `R2_FFBB_DESPUES_DEL_GO=1`) = el orden viejo, para el control al revés.
FFBB_12_ANTES_DEL_GO = os.environ.get("R2_FFBB_DESPUES_DEL_GO") != "1"   # el env sólo para el QA
# ★ EL AVISO POR CHAT AL CAMBIAR LA DIFICULTAD (`FFC9`) — APAGADO A PEDIDO DEL USUARIO (2026-09-07).
#   El server de referencia SÍ lo manda: medido en `mitm_20260907_183811`, una línea por cambio con
#   el nick literal `Servidor`:  "Servidor.<nick> pone la dificultad de la sala en N".
#   Se probó en local y el usuario lo vio en pantalla: *"no queremos el comentario del servidor"*.
#   ⇒ Queda acá, apagado, y no borrado: el dato está medido y el día que se quiera imitar al
#     referente al pie de la letra se prende con un `True`. Lo que NO depende de esto es el `FF13`,
#     que es el que de verdad cambia la sala y sale siempre.
AVISO_DIFICULTAD_POR_CHAT = False

EQUIPOS = {}                           # roomid -> {slot: equipo}  (lo que decidió el SERVER)
# ★ APAGADAS EL 2026-09-05, a pedido del usuario. Los dos maniquíes ("Sala de prueba" y "Prueba
#   EQUIPO") existían para poder medir el ENTRAR A UNA SALA cuando no había un segundo cliente.
#   Ya hay salas reales, la lista funciona por canal y con paginación ⇒ sobran, y encima ensucian
#   la cuenta de páginas. Se dejan en `SALAS_DEMO` por si hace falta volver a medir: es este flag.
#   ⚠ El camino de "entrar a un maniquí" (`_era_demo` en `h_18_ff11`) queda vivo pero inalcanzable:
#     sin listarlas, el cliente nunca pide esos roomid. No se borra para no tocar el FF11.
MOSTRAR_SALAS_DEMO = False             # True = vuelven los dos maniquíes de medición

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★ LA LISTA DE SALAS: POR CANAL Y POR PÁGINA (2026-09-05)
#
# Dos cosas que faltaban, las dos en el `FF6E`, y las dos reportadas por el usuario:
#   · creaba la sala en el canal **Libre** y la sala aparecía **en la lista de TODOS los canales**;
#   · nunca se probó si las pestañas de página funcionan.
#
# ★★★ EL PRIMER BYTE DE LA RESPUESTA ES **EL NÚMERO DE PÁGINAS**. MEDIDO en el handler del
#   cliente (`0x5E0800`), no supuesto:
#
#       005e084c  mov   cl, byte [esp+0x19]     ; el 1er byte de la respuesta
#       005e0850  cmp   cl, 1
#       005e0853  jbe   0x5e0887                ; <=1 -> NO dibuja pestañas
#       005e0877  dec   cx                      ; >1  -> arma la barra de páginas con cl-1
#       005e0880  call  0x5D1B20
#       005e08f8  mov   byte [ecx+0x16fe], dl   ; y lo guarda como el total de páginas
#
#   ⛔ Acá estaba escrito que ese byte era **"1 = hay salas · 0 = lista vacía"**, deducido de las
#      221 respuestas del server de referencia. La OBSERVACIÓN era correcta y la LECTURA no: en
#      ese corpus nunca hubo más de una página, así que "nº de páginas" y "hay salas" dan el
#      mismo valor en las 221 muestras. Un corpus sólo puede desmentir lo que llegó a pasar.
#
# ⚠ Cuántas salas entran en una página lo decide LA PANTALLA, y en este cliente **no está medido**:
#   el 12 viene del CBT (allá sí se contó: con 8 quedaban 4 huecos). Si acá sobran o faltan filas,
#   se cambia este número y listo — el cliente dibuja las que le mandemos.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
FF6E_SALAS_POR_PAGINA = 12             # ⏳ del CBT; falta contarlo en la pantalla del 2013
SALAS_POR_CANAL       = True           # False = volver al comportamiento viejo (todas en todos lados)
SALAS_FALSAS_PAGINACION = 0            # ★ salas de mentira para probar las pestañas. En vivo: `.salas N`

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ LA PRECISIÓN CON MILÉSIMAS (94.532 en vez de 94) — PASO 1: EL CABLE
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Ver `documentacion/RBIT_DECIMALES_DE_PRECISION.md` para el análisis completo del plugin de
# SpaceWander, que es de donde salió el diseño.
#
# ⛔ ESTO NO SE PUEDE HACER SÓLO DESDE EL SERVER, y está comprobado en los dos sentidos:
#       lo que ENTRA (fin de canción):  `pd, star = data[6], data[7]`   -> UN BYTE
#       lo que SALE  (fila del FF28):   `bytes([pd & 0xFF, ...])`       -> UN BYTE
#   El cliente nos manda 94, no 94.532. Hace falta parchearlo para que (a) MANDE las milésimas y
#   (b) DIBUJE el punto (el número del cartel es de sprites, no hay `printf` que tocar).
#
# ★ Este paso es sólo el CABLE: el server ya sabe recibirlas, guardarlas y repartirlas. Mientras
#   no exista el parche del cliente, todo esto vale 0 y nada cambia en pantalla.
#
# ─── POR DÓNDE VIAJAN, HACIA EL CLIENTE ───────────────────────────────────────────────────────
# ⛔ NO van en el bloque de 12 bytes de la fila: ése **no está libre** (son 7 campos, y los dos
#   primeros ya los usa la columna «Usar Booster»).
# ★★ Van como un RENGLÓN DE BONUS con un tipo reservado. Es el punto de extensión que el
#   protocolo YA tiene, y es inerte por diseño:
#       · MEDIDO HOY en `0x5E8E10..0x5E8E42`: el bucle lee `[tipo:u16][valor:u16]` y hace
#         `push_back` **sin validar nada**. El transporte no mira el tipo.
#       · El filtro está en el DIBUJADO: un tipo que no esté en `bonus.xml` no se pinta.
#   ⚠ Lo segundo viene de una medición anterior del repo, no la re-verifiqué hoy. Si algún tipo
#     desconocido llegara a dibujar un renglón de basura en el cartel, **es esta línea**: se
#     apaga con `PRECISION_MILESIMAS = False` y se ve al instante.
# ★ 0xFF01 está libre: `bonus.xml` declara 119 tipos, el mayor es 183 (más el centinela 65535).
FF28_BONUSTYPE_MILESIMAS = 0xFF01

# ─── POR DÓNDE VAN A VENIR, DESDE EL CLIENTE ──────────────────────────────────────────────────
# ★★ MEDIDO sobre **16.624 paquetes reales de prod** (el `FF28` C→S mide siempre 62 bytes): los
#   bytes **46..56 son `00` en todos, sin una sola excepción**. Once bytes seguidos, libres.
#   ⇒ Ahí va a escribir el parche del cliente. Elegido 46 por ser el primero de la racha.
# ⚠ No es "está en cero, será libre": es que en 16.624 muestras el cliente nunca escribió ahí.
#   Un campo que siempre vale 0 podría igual ser un campo — pero entonces su valor es 0 y
#   pisarlo sólo afecta a nuestro propio parche, que es quien lo va a escribir.
FF28_C2S_OFF_MILESIMAS = 46

# El interruptor maestro. En False el server se comporta exactamente como antes.
PRECISION_MILESIMAS = True

# ★ Perilla de PRUEBA. Rompe el huevo y gallina: el parche del cliente no se puede comprobar sin
#   milésimas, y las milésimas no llegan sin el parche. Con un valor != 0 el server se las inventa.
#   En vivo: `.pd 532` en el chat (sólo para el que lo escribe). Prod queda en 0.
PRECISION_MILESIMAS_FORZADAS = 0

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ EL EMPUJÓN DE LISTA RESPETA LA PÁGINA DE CADA UNO — 2026-09-12
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ⛔ EL BUG: *"si estoy en página 2, pasan un par de segundos y me muestra la lista de la 1"*.
#   `difundir_roomlist` empuja la lista a TODOS cada vez que una sala arranca o termina una
#   canción (en prod, cada ~3 s con 25 salas) y mandaba **siempre la página 0**.
#
# ★ El cliente no se puede defender solo: su handler (`0x5E0800`) llama a `0x4A05A0`, que le pone
#   la página en el centinela `0x28` ("ninguna"), porque **la respuesta no dice de qué página es**.
#   Está hecho para que el server le mande la página que pidió. El dato ya viaja en cada `FF6E`;
#   sólo hacía falta acordarse de él (`st.salas_pag`).
#
# ★★ Y APARECIÓ RECIÉN AHORA por TAMAÑO, no por un cambio de código: hacen falta >12 salas para
#   que el cliente dibuje las pestañas. En prod, a la misma hora del día:
#       antes del 12-sep:   55-78 jugadores -> 7-12 salas -> pestañas el 19% del tiempo
#       después:           92-142 jugadores -> 14-27 salas -> pestañas el 97% del tiempo
#   La proporción salas/jugador no se movió (0,15 antes y después).
#
# False = vuelve al comportamiento viejo (todos reciben la página 1), sin tocar código.
FF6E_EMPUJE_RESPETA_PAGINA = True

# ★★★★★ EL MAPA DE LA FILA DEL `FF6E`, RECALIBRADO CON DATOS REALES (2026-09-17).
#   anonimo03: *"en la lista de salas, en el original marcaba si alguna campana de oro o plata estaba
#   activa; actualmente no lo está haciendo"*. Y después: *"quizá deberíamos medir completo los
#   offsets de cómo se listan las salas"*. Se hizo, y así quedó la fila (`25+n` bytes, n = nombre):
#
#     ofs      clave  qué es
#      0  u16  A      roomid & 0x7FF | tipo << 11
#      2  u8   B      máscara de estado (bit 0x02 = en juego)
#      3  u16  C      siempre 0 en el referente — sin nombre todavía
#      5  u16  D      siempre 0 — sin nombre todavía
#      7  u8   E      ocupantes totales
#      8  u8   F      espectadores; en pantalla sale `E - F`
#      9  u8   G      ⚠ capacidad + 6 (el cliente resta 6 en `0x5E0991`) — ver abajo
#     10       —      u8 largo + el nombre
#   11+n  u8   H      siempre 0 — sin nombre todavía
#   12+n  u8   I      siempre 0 — sin nombre todavía
#   13+n  u32  J      ★★★ CAMPANA DE ORO activa: el itemcode (181/183/774), 0 = ninguna
#   17+n  u32  K      ★★★ CAMPANA DE PLATA activa: el itemcode (297/304/775), 0 = ninguna
#   21+n  u8   L      ★★ el canal de LICENCIA que exige la sala (0 = libre, 8 = especial)
#   22+n  u8   M      bit de modo -> se lista como «Modo Cooperativo»
#   23+n  u8   N      -> se lista como «Grand prix de círculo»   (para el doc de círculos)
#   24+n  u8   O      bit de modo -> se lista como «Batalla de Jefes»
#
#   ★ CÓMO SE MIDIÓ, y por qué se puede confiar:
#     · `M`, `N`, `O` -> **bisección en vivo con anonimo03**, un byte por corrida, marcando SÓLO la
#       sala con campana para tener otra al lado. Los tres dieron algo distinto de lo previsto por
#       lectura estática: el apareo derivado a mano estaba corrido (un `add esp,0x1C` en la rama
#       de club corre el `esp` de todos los `mov [esp+X]` de abajo). **La bisección manda.**
#     · `J`, `K` -> el corpus del referente (27 capturas MITM, 1124 `FF6E`, 10.656 filas, 0 fallos
#       de parseo) + un cruce causa-efecto: suena el oro 181 en la sala 4 y el `J` de esa fila pasa
#       de 0 a 181 en el paquete siguiente.
#     · `L` -> el exe (`0x484A00`), no el referente: si `L != 0` y tu licencia es menor, el cliente
#       **esconde la sala de la lista**.
#
#   ⚠⚠ DEL CENSO NO SE CONCLUYE «NO SIRVE». `A_alto`, `C`, `D`, `H`, `I` y `N` salen 0 en las 10.656
#     filas del referente — y `N` es la prueba viviente de que eso sólo significa *«el referente no
#     lo usa»*: sale siempre 0 allá y la bisección midió que hace algo real. Es el mismo error del
#     «hay salas / está vacía» que ya costó una lectura falsa en `build_ff6e_roomlist`.
#   ⏳ `G`: el builder pone `s.get("G", 6)` y **nadie lo sobreescribe** ⇒ mandamos 6, el cliente
#     resta 6, y la lista muestra capacidad **0**. El referente manda **12** en 10.419 de 10.656
#     filas. **[H]** `G = capacidad + 6` arreglaría el número; se prueba en una sala y se ve.
#   ⏳ `L` sin llenar es por qué el canal de licencia no se muestra nunca (pedido aparte de anonimo03).

SLOTS_LIBRES = [3, 4, 5, 1, 0]        # ★ slots ocupables por NPC, en el orden en que se van llenando.

# FF3D/FF00 = alta frecuencia (UI/keepalive): contar, loguear 1º y cada 500 (sin ahogar, sin ocultar)
_HIFREQ = {0x3D, 0x00}
# ★ Alta frecuencia que SÍ se procesa (a diferencia de los de arriba): el movimiento (FF23). Se cuenta
#   y sale en el resumen de un minuto (`registro.resumir`), en vez de 2 líneas por paso (25-sep).
_RESUMIR_RX = {0x23, 0x98}         # ★ 12-oct: + el FF98 (la transmisión al espectador, `espectador_datos.py`)
CHAT_CACHE_SEG = 30.0      # el apodo y el estilo del chat, guardados en la conexión (ver lobby_menu.h_07_ff08)

# ── ★★★★★ EL FF3D ERA EL CLIENTE PIDIENDO UNA LISTA QUE NUNCA LE MANDAMOS (2026-09-24) ──────────
#   anonimo03: *"el ff3d volvió de nuevo, según yo son demasiados… es como el cliente quejándose de
#   algo"*. Tenía razón. MEDIDO con Frida en 6 clientes (`_trabajo/ff3d/sonda.py`, sólo mira):
#     · FF00 = un LATIDO: el reloj 0x3E8 del cliente, cada 10,0 s exactos (0x4081BE -> 0x5C5FD0).
#     · FF3D(0) = el reloj 0x1004 (0x408297 -> 0x5C89B0), con un período DISTINTO por cliente
#       (9 / 12 / 15 / 27 s, parejísimo). Lo programa el handler del `FF8C` (`0x5E9E00`):
#           SetTimer(0x1004, (rand() % 10) * 3000)       ← 0x5E9ED1..0x5E9EEB
#       ⇒ ★★ 1 de cada 10 veces el azar da 0 ms, Windows lo sube a su mínimo (~10-16 ms) y el
#         cliente manda un FF3D POR CUADRO: el «diluvio» de ~3.600/min que iba y venía sin razón
#         desde julio. El referente tenía el mismo (su peor sesión 3.564/min): contesta igual.
#   ★★★ QUÉ ES: un ANTI-TRAMPA. El `FF8C` trae `[u8 n] n × [f32]`; `0x5C0710` exige n = 112 y que
#     cada float sea IGUAL al +0x18 de la animación i de la tabla `0x904FD8` — las 112 animaciones
#     de TROPEZAR (`cha_left_fail.ani`… `fail_boy2_back_fly.ani`). Acortarlas es la trampa clásica
#     para levantarse antes. Si no coincide, el reloj queda armado y el cliente avisa con FF3D(0)
#     para siempre. Nosotros (y el referente) mandábamos n = 0 ⇒ fallaba en TODOS los clientes.
#   ⇒ Se mandan las 112 duraciones de `servidor/tablas-cliente/duraciones_tropiezo.json`, medidas
#     en dos clientes vivos (idénticas). Con eso la comprobación pasa y el reloj no se arma.
#   ✅ MEDIDO (24-sep, 6 clientes recién abiertos, 120 s, la misma sonda): FF3D 50 -> 0, y el
#     latido FF00 72 -> 72 (el control: la sonda escucha, lo que falta es el FF3D).
#   ★ Y el FF3D(0) pasa a SIGNIFICAR algo: si un cliente lo sigue mandando, sus animaciones de
#     tropezar no son las nuestras (archivos viejos del CBT, o tocados). Hoy sólo se loguea.
#   Nadie más usa la lista ni la comprobación (xrefs de 0x9D5098 / 0x5C0710): pasarla sólo apaga
#   ese reloj. En `False` vuelve a mandar n = 0, como antes.
FF8C_DURACIONES = True

# ── ★★★ CAMBIAR EL GAME ID — el ítem «Cambiando el GameID» y el `FF86` (2026-09-24) ─────────────
#   anonimo03: *"pongo el nuevo nombre y le doy ok, pero quedó stuck"*. El cliente mandaba `FF86` y no
#   había handler. Leído en el exe:
#     C->S `0x5D90C0`:  [u8 paso][u8 len][nombre]          paso 0 = ¿está libre?  · 1 = confirmo
#                        (el 0 lo manda al escribir; el 1 al aceptar el cartel del resultado 0)
#     S->C `0x5D9260`:  [u32][u8][u8 resultado][u8 len][nombre] -> `0x42BEB0`:
#          0 -> system.csv 724 «Puede utilizar el Game id %s. ¿Desea cambiar su Game id?» (pasa a paso 1)
#          1 -> cambiado (el cuadro final, con el nombre nuevo)
#          3 -> 726 «'%s' ya está en uso.»      4 -> 148 «Ha ocurrido un error DB»
#          5 -> 44 «El sobrenombre debe tener entre 6 y 12 letras incluyendo números.»
#          otro -> 727 «System Error : code %d»
#   (el u32 y el primer u8 el handler los lee y no los usa: van el usn y el paso, para el log).
#   El apodo vive en `chars.nickname` y amigos/parejas/GM van por uid o login: cambiarlo no los rompe.
#   Al confirmar se gasta el ítem (y el `FF6A` le baja el ícono).
CAMBIO_DE_NOMBRE = True
ITEM_CAMBIO_NOMBRE = 30084             # «Cambiando el GameID» (shop_lt, pestaña 0509, PN)
NOMBRE_LARGO = (6, 12)                 # el propio cartel 44 del cliente

# ── LA PESTAÑA «PERSONAJE» DEL ARMARIO (los premios del gacha) — 2026-09-08 ──────────────────
# ⛔ EL BUG: se gana un personaje en el gacha, el server lo guarda bien, y la pestaña sigue VACÍA.
#   La captura de anonimo03 mostró más de lo que él creía: estaba vacía **también de lo que ya tenía**.
#   No faltaba el premio — esa lista del MyRecord no se mandaba NUNCA (iba con el contador en 0).
#
# ★ Los premios del gacha NO son ropa: son PERSONAJES (`hero.txt` + `spec.txt` del cliente). Por eso
#   no aparecían en las pestañas de prendas.
#
# ★★ DÓNDE VA — leído del parser del MyRecord (`0x5EC8A0`), casi al final:
#       005edcf0  read(1)         ← el CONTADOR, un BYTE. Con 0 no lee nada.
#       005edd0c  read(4)         ← el personaje
#       005edd1d  read(8)         ← ocho bytes por personaje
#       005edd38  call 0x46f4e0   ← lo registra en el padrón `[0x934354]`
#   Y `0x46F4E0` **es del gacha**: adentro tiene el texto `[GACHA] Spec data error : %u`, que es lo
#   que escribe cuando el id no está en `spec.txt`. Esa es la atadura que lo prueba.
# ⛔⛔⛔ EN FALSE A PROPÓSITO — 2026-09-08, y esto es un EXPERIMENTO en curso.
#   MEDIDO en vivo: esta lista es la que da de alta al personaje en el sistema de ENERGÍA del
#   cliente (`0x46F4E0` -> el padrón `[0x934354]`). Y ese sistema **está roto en este build**:
#
#       ⏱ agotamiento: acumulador=0 … 240   items=1   [this+0x490]=0x0   ← NULO desde el 1er tick
#       EXCEPCION access-violation en 0x46f242 — lectura de la dirección 0
#
#   El temporizador `0x46F9D0` sube 1 por cuadro hasta 240 (~4 segundos), dispara el "탈진"
#   (agotamiento) y ahí lee `[this+0x490]` **sin comprobar si es nulo** — su función hermana
#   `0x46F920` sí lo comprueba sobre la misma tabla. Es un descuido del juego.
#   ⇒ Con `items=1` el bucle corre; con 0 ni arranca (`test ecx,ecx / jle`).
#
# ★ LA PREGUNTA QUE ESTO PRUEBA: la pestaña «Personaje» ¿se llena igual sin esta lista? El
#   personaje ahora también viaja en el `FF49` (`gacha.registros_ff49`), que es el DUEÑO de la
#   lista de personajes del cliente. Si alcanza con ése, apagando esto se van de una sola vez:
#       · el crash a los 4 segundos, y
#       · el pay-to-win (la energía que se gasta y se recarga con 300 RCoin)
#   ⚠ Si la pestaña queda VACÍA, hay que volver a prenderlo y buscar otra salida — y ahí lo que
#     falta es entender qué debería llenar `[this+0x490]`, que hoy nadie llena.
GACHA_LISTA_PERSONAJES = True

# ★ EL OFFSET, CONTADO — no adivinado. Con la cola en ceros todos los contadores intermedios valen
#   0, así que cada lista se saltea y el camino de lecturas es fijo. Del arranque de la cola hasta
#   ese byte hay 46: cuatro contadores de 1 byte, cuatro `u32` (16), y el resto escalares sueltos y
#   largos de texto en 0.
#   ⚠⚠ SI ALGÚN DÍA LA PESTAÑA SE ROMPE, **ÉSTE es el número a re-contar**, y se re-cuenta del exe,
#     no de este comentario. El método está en `documentacion/GACHA_CAPSULAS.md`.
# ⛔⛔ ACA DECIA 46, Y ESTABA MAL. Yo lo CONTE leyendo el disasm y lo escribi con la nota
#   "está CONTADO, no adivinado" — contado sí, correcto no. Es exactamente el error del que la casa
#   se cuida: una deducción razonable que se siente como una medición.
#   ★ El número de abajo está MEDIDO con frida, enganchando cada lectura del stream dentro del
#     handler del `FF03` (`0x5EC8A0`) y viendo en qué byte cae la que vuelve a `0x5EDCF5`:
#         ★★★ EL CONTADOR DE PERSONAJES se lee en el BYTE 5590 del paquete
#     Y despues, probando offsets contra ese numero medido: 44 -> 5589 · **45 -> 5590 JUSTO** ·
#     46 -> 5591 · 84 -> 5629. Mi cuenta original (46) estaba mal **por UN byte**.
#   ⇒ Y el síntoma que producía era el peor posible: el cliente leía un CERO ahí, no daba de alta a
#     ningún personaje en el padrón del gacha, y después el temporizador del agotamiento leía un
#     puntero nulo y **crasheaba a los 4 segundos**. Dos horas de cacería por 38 bytes míos.
GACHA_PERSONAJES_OFF = 45

# ★ La VIDA (HP) con la que viaja cada personaje del gacha en el MyRecord. El cliente la lee como
#   `valor/10` redondeado hacia arriba (`0x46F5BF`) y su default es 100. Iba en CERO — o sea, el
#   personaje llegaba con la vida vacía. Medido por el agente el 2026-09-08 y confirmado contra el
#   2019 (`CmdDecreasCharacterHP` / `RecoverCharacterHP` llaman a la función gemela).
#
# ★★★★★ 2026-09-09 — Y ESTE NÚMERO ES EL QUE APAGA EL PAY-TO-WIN. Medido con la pila de llamadas:
#     ✉ SendEditChar(110275)  pila: 0x4ce709 <- 0x46fb57 <- ... <- 0x4c87ba
#   `0x46FB57` está adentro de `0x46F9D0`, **el temporizador del agotamiento**. O sea: cuando al
#   personaje se le acaba la energía, el cliente lo da por AGOTADO (`탈진`) y **cambia solo a otro**,
#   avisándole al server con el mismo paquete que usa el clic. Por eso el jugador veía que "se
#   cambiaba de personaje con sólo abrir la pestaña": no era un fallo de la interfaz, era la
#   mecánica de energía haciendo su trabajo (y cobrando 300 RCoin por recargar).
#   ⇒ Con la energía alta el temporizador NUNCA llega al final: no hay agotamiento, no hay cambio
#     automático, y no hay nada que vender. Es el arreglo NATIVO — no se toca el exe, no se adivina
#     nada, y sale del propio campo que el juego ya define.
#   ⚠ Va en la cuenta del jugador, así que un número enorme se ve en pantalla ("Restante: N"). Se
#     elige uno grande pero legible.
GACHA_PERSONAJE_HP = 9999

# ★★★ EL FRENO DEL CAMBIO DE PERSONAJE (segundos) — 2026-09-08.
# ⛔ EL SÍNTOMA, medido por anonimo03 con dos cuentas en la misma sesión:
#     · clics MUY RÁPIDOS  -> el cliente se cae al segundo
#     · clics ESPACIADOS   -> aguanta bastante más
#   Esa diferencia no la explica un índice mal calculado: es una **carrera de tiempos**. Al cambiar
#   de personaje el cliente arranca a cargar un modelo 3D (`rnr_char/SP/SP0030A/SP0030A.md9`), y si
#   le entra otro cambio antes de terminar, se pisa a sí mismo.
#
# ★ Y por qué no pasaba en el juego original: **había un servidor lejos**. Entre el clic y la
#   respuesta pasaban 100-200 ms de red, que alcanzaban para que la carga terminara. Nosotros
#   contestamos en microsegundos, así que el jugador puede pedir tres cambios antes del primero.
#
# ⚠⚠ ESTO ES UN FRENO, NO EL ARREGLO. El bug vive en el cliente y arreglarlo de verdad sería
#   parchear el exe — que por la filosofía de la casa va ÚLTIMO y medido. Mientras tanto, esto lo
#   vuelve inalcanzable sin mentirle a nadie: al 2º clic apurado se le contesta "ahora no".
#   ★ Hay precedente en esta misma casa: el `FF1A` tiene un dedup con enfriamiento de 2 s por el
#     mismo tipo de problema (ver `h_37_ff1a`).
#   ★★ MEDIDO EN VIVO el 2026-09-08 con frida: el cambio entero tarda **15-18 ms**. 1,5 s era cien
#     veces de más, y encima **no evitó el crash**: en la captura hubo sólo dos cambios reales,
#     con dos segundos entre medio, y el cliente se cayó igual tres segundos después. O sea que
#     la teoría del ritmo se cae — queda como freno anti-spam, nada más.
GACHA_PERSONAJE_ESPERA = 0.35

# ⚠ EXPERIMENTO: mandar el personaje del gacha en el `FF49` CON las ranuras de ropa llenas en vez
#   de vacías. Ver la nota larga en `gacha.registros_ff49`. Idea de anonimo03 el 2026-09-08.
# ⛔ EN FALSE: el experimento SE CAYO. Se prendio para probar si el vacio causaba el crash, y el
#   crash era otra cosa (un byte en `GACHA_PERSONAJES_OFF`). Con la ropa encima, anonimo03 reporto:
#   *"el char volvio a quedarse al normal, solo cambia las caras y las manos"* — o sea la ropa
#   tapando el cuerpo del personaje, que es justo lo que este ajuste provoca.
GACHA_PJ_CON_ROPA = False

# ★★★★★ QUE UNA CÁPSULA NO ENTREGUE ALGO QUE EL JUGADOR YA TIENE — pedido de anonimo03, 2026-09-09:
#   *"¿podemos hacer que no toquen repetidos?, sigue tocando repetidos"*.
#
#   ⚠⚠ ESTO **NO** ES LO QUE HACÍA EL ORIGINAL, y conviene tenerlo claro antes de tocarlo. Allá el
#     repetido era el **premio de consuelo**: el padrón del cliente es un `std::map` por id
#     (`0x46F4E0` busca-o-inserta y reescribe la VIDA en `[+0x10]`) y, con `Stamina="100"` /
#     `StaminaRcoin="300"` en la tabla, los personajes **se gastan con el uso**. Sacar repetido te
#     **rellenaba** el que ya tenías.
#
#   ★ ACÁ ESO NO EXISTE: mandamos la vida FIJA (`GACHA_PERSONAJE_HP`) y no implementamos el
#     desgaste, así que un repetido no rellena nada — es una cápsula pagada a cambio de CERO.
#     Por eso se sacan del bombo. **El día que se implemente el desgaste, esto se revisa.**
#
#   ⚠ Sólo se descartan los ÍTEMS. Las monedas y la experiencia entran siempre: si no, una máquina
#     de puro RCoin se cerraría sola después de la primera tirada.
#   ⚠ Y cuando al jugador no le queda NADA por ganar en esa máquina, **no se le cobra la cápsula**:
#     se rechaza y se le avisa por chat. Ver `pool_para` y `h_ff69_abrir_capsula`.
GACHA_SIN_REPETIDOS = True

# ★★★★ NO CONTESTAR EL SONDEO DE FONDO DEL `FF6E` CUANDO NO HAY SALAS — 2026-09-09.
#   Reportado por anonimo03 con captura: **estando en la isla**, sin haber ido a multijugador, le
#   saltaba *"No hay salas disponibles. ¿Desea crear una?"*.
#   ★ Ese cartel es el popup **303** del cliente y lo dispara una lista VACÍA, no el pedido
#     (`0x5E0800`: `cmp dx,[esp+0x20]` / `jbe` sobre las páginas / `push 0x12F`). O sea que se lo
#     estábamos sacando nosotros al contestarle `count=0`.
#   ★ El cliente manda DOS `FF6E` distintos, y se separan por tres marcas que siempre coinciden:
#         de verdad -> tipo=1/2/13  pag=0       filtros=3f ?? 01 01
#         sondeo    -> tipo=0       pag=0xFFFF  filtros=3e ?? 00 00
#     `0xFFFF` es −1: el centinela de "ninguna página". En prod son el **15%** de los pedidos.
#   ⇒ Con salas se contesta igual que siempre. Vacío, se calla. Ver `lobby_salas.h_08_ff6e`.
#   ⚠ En False vuelve el comportamiento viejo, por si el cliente resultara reintentar en ráfaga.
FF6E_SONDEO_MUDO = True

# ★★★★ Y EL EMPUJE TAMPOCO MANDA LA LISTA VACÍA A QUIEN NO TIENE SALAS EN PANTALLA — 26-oct.
#   anonimo03, con captura de prod: *«cada que alguien entra o yo entro, sale ese popup, como si se hubiera intentado entrar
#   a una sala; en local no sale, porque sólo estamos nosotros; casi nadie juega en los X canales, sólo en Libre»*.
#   ★ El sondeo estaba cubierto (arriba), pero `salas.difundir_roomlist` le empuja la lista a TODOS cada vez que una
#     sala arranca o termina una canción (en prod, cada pocos segundos) y a los de un canal SIN salas les mandaba
#     `count=0` ⇒ el mismo popup 303. MEDIDO en el log de prod: anonimo03 entra 18:12:16 en «sunchobo» (0 salas), su
#     sondeo se calla bien (18:12:24), y el empuje de 18:12:22 («sunchobo=0 sala(s)») es el que le saca el cartel. En
#     local nadie arranca carreras ⇒ no hay empuje ⇒ no sale. Una sola vez: después el cliente queda en el estado que
#     lo silencia (`[roommgr+0x16FC] = 0x28`).
#   ⇒ El empuje vacío sólo va a quien TENÍA salas dibujadas (`st.lista_con_salas`): para que no se quede viendo una
#     sala que ya no existe. Al que nunca tuvo salas en pantalla no se le manda nada.
#   ⚠ En False vuelve el comportamiento viejo (lista vacía a todos).
FF6E_EMPUJE_SIN_VACIOS = True

# ★★ LA CAPACIDAD DE CADA CANAL — el denominador de la barra de población del selector.
#   ⚠ **NO puede ser 0**: la pantalla hace `usuarios * 80 / capacidad` con un `idiv` (`0x4a69e5`),
#     y una división por cero ahí **crashea el cliente**.
#   ★ El REFERENTE usaba 100 en los 7 canales normales y **500 en «Libre»** (visto en la captura
#     del 2026-09-02, con 52 jugadores adentro). Acá va uno solo para todos hasta que haga falta
#     distinguirlos: lo que estaba roto era el NUMERADOR, que iba clavado en 1.
#   ⚠ Se manda `min(gente, CAPACIDAD-1)` para que la barra nunca se dibuje al 100 % y el canal no
#     parezca cerrado por un pico.
#   ★ 2026-09-12 — **de 100 a 200**, a pedido de anonimo03. Es sólo el denominador de la barra: no
#     limita a nadie, no cierra canales y no toca ninguna regla. Con 106 jugadores en prod, con
#     100 la barra ya se dibujaba topada y el canal parecía lleno.
CANAL_CAPACIDAD = 200

# ★★★★ DOBLE LOGIN: si la misma cuenta abre otra sesión, la anterior SE MUERE.
#   Pedido de anonimo03 el 2026-09-09. Sin esto quedaban dos conexiones vivas con el mismo `usn`:
#   `CONEXIONES[usn]` se pisaba y la vieja seguía con su socket abierto, su hilo corriendo y su
#   silla ocupada, pero sin recibir nada. Un fantasma que además tapaba un asiento.
#   ⚠ El cambio de canal pasa por este mismo camino (el cliente re-loguea con el mismo `usn`) y
#     está bien: ahí la sesión vieja ya está muriendo y echarla es lo correcto.
#   ★ En False vuelve el comportamiento de antes. Ver `lobby.echar_sesion_anterior`.
DOBLE_LOGIN_ECHA_AL_ANTERIOR = True

# ★★★★ REPONER LA CANCIÓN DESPUÉS DEL `type 5` DEL PICKER — 2026-09-09.
#   Reportado por anonimo03: *"el picker funciona bien hasta empezar el juego, pero al regresar a la
#   sala se resetea"*. El `type 5` es lo que el cliente manda al SOLTAR el picker, y su handler
#   (`0x5CDE65`) hace `cRoom::SetMusic(0)`: **se borra la canción a sí mismo**.
#   Nosotros ya no lo relayamos —eso arregló que se la borrara a los DEMÁS— pero al que lo mandó
#   no se la reponía nadie. El server de referencia mandaba el `FF13` justo después, y el `FF13`
#   lleva la canción en el `@19`. Eso es lo que se hace ahora, y **sólo a ese jugador**.
#   ⚠ En False vuelve el comportamiento de antes. Ver `lobby_salas.h_29_ff1c`.
FF1C_REPONE_TRAS_TYPE5 = True

# ★★★★ EL `FFC9` DEL PICKER SE MANDA UNA VEZ POR SALA, NO EN CADA `FF13` — 2026-09-09.
#   Reportado por anonimo03: *"el máster activa ciertas bandas en el picker y al volver se reinicia a
#   Sol"*. Sol es SU LICENCIA, o sea justo lo que manda el `FFC9`.
#   ★ El picker guarda una MÁSCARA de bandas (el `byMusicLevelFilter` que el cliente nos manda:
#     `0x0c` = dos prendidas). El `FFC9` toma UNA banda y le aplica `LevelToMask` = un solo bit,
#     así que **por diseño no puede devolver lo que el anfitrión tenía**: re-mandarlo al volver
#     sólo lo empeora.
#   ⚠ El PRIMER envío no se toca: sin él el picker nace vacío (máscara 0 = lista vacía, medido).
#     Lo que se saca es el repetido.
#   ⚠ En False vuelve a mandarse siempre. Ver `lobby_salas.h_19_ff13`.
FFC9_PICKER_UNA_VEZ = True

# ★★★ EL REPUESTO DEL CARTEL DE MÚSICA, UNA VEZ POR SALA — EXPERIMENTO, 2026-09-09.
#   Pedido de anonimo03: *"también se podría guardar el lugar de la lista del picker"*.
#   ⛔ GUARDARLO NO SE PUEDE: el cliente NUNCA nos manda esa posición. Cruzado con el 2019:
#     `CmdSelectingMusicStage` (0x79) lleva [estado][tipo] y nada más, y `Scroll_Musiclist` es un
#     WIDGET de UI. No hay paquete con el índice de la lista.
#   ★ Lo único que SÍ controlamos es cuántas veces le hacemos reconstruir la lista: cada `FF1C`
#     cambia de pestaña (SetTab) y eso la repuebla desde arriba. El REFERENTE manda UN paquete al
#     entrar (`1f 00 00 00 ff`); nosotros mandamos ese y además el `type 0` del repuesto.
#   ⇒ En True el repuesto va sólo la PRIMERA entrada a la sala; al volver lo repone el `FF13`.
#   ⚠ SI SE ROMPE se ve enseguida: el cartel de Música en blanco al volver de la carrera.
#     Ahí se pone en False y vuelve el comportamiento de antes. Es un experimento, no una certeza.
# ⛔ EL EXPERIMENTO SE CAYÓ — probado por anonimo03 el 2026-09-09: *"no se sincronizó el lugar de la
#   lista"*. Ahorrar ese `FF1C` NO devuelve el scroll, así que era riesgo (el cartel de Música
#   podía quedar en blanco al volver) a cambio de nada. Vuelve a False.
#   ★ Lo que queda demostrado y sirve: **la posición de la lista no depende de cuántos `FF1C` le
#     mandemos**. Un candidato menos, y encima uno que parecía muy razonable.
#   ⚠ El bloque de arriba se deja escrito a propósito: explica qué se probó y por qué no fue.
FF1C_RESTAURA_UNA_VEZ = False

# ★★ LA VENTANA DE RAFAGA DEL FF19 (segundos). Al abrir el panel de personajes el cliente manda UN
#   `FF19` POR CADA personaje de la lista, en el orden de la pantalla — medido el 2026-09-09. Un
#   clic real llega solo; la enumeracion llega en rafaga. Dentro de esta ventana se rechaza y se
#   devuelve el personaje al que estaba antes.
#   ⚠ Es una HEURISTICA: el paquete son 4 bytes con el id y nada mas, no hay byte que diga
#     "enumerar" vs "elegir". Si aparece la forma buena, esto se saca.
#   ★ Ahora es la ESPERA antes de aplicar, no una ventana de rechazo: el pedido se guarda y se
#     decide pasados estos segundos. 0,4 s alcanza (la enumeracion llega mucho mas junta) y es
#     menos que la latencia de una red real, asi que no se nota.
GACHA_PERSONAJE_RAFAGA = 1.0

# ★ Al cambiar de personaje, SACAR al ocupante de la sala y volver a ponerlo (`FF0E` + `FF0C`).
#   Hace falta porque el `FF0C` **crea si el asiento esta libre y si ya esta ocupado no hace nada**
#   (medido en `FF0C_INFORME_AGENTE.md`): sin el `FF0E` delante, el distintivo de sexo del cartelito
#   se queda con el que tenias al ENTRAR a la sala. El `FF15` recarga el modelo -por eso el cuerpo
#   si cambiaba- pero no re-crea la entrada del ocupante.
#   ⚠ Si produce parpadeo o se pierde el "soy yo", poner en False: se vuelve al comportamiento
#     anterior (cuerpo bien, distintivo viejo hasta salir y volver a entrar).
REAPARECER_AL_CAMBIAR_PERSONAJE = True


# ★★★★★ ¿EL SALDO DE MONEDA GORILA VA EN **CADA** MyRecord? — 2026-09-10.
#
#   `True` = como venía desde siempre: los 8 MyRecord de una sesión llevan el saldo.
#   `False` = sólo el que contesta un `RX FF03` (el arranque de verdad del cliente).
#
# ⛔ POR QUÉ ESTÁ EN `True` (o sea, revertido): porque **mi diagnóstico no se sostuvo**.
#
#   Yo vi 500 en la base y 1000 en pantalla, y deduje "el cliente lo acumula, mandamos el
#   MyRecord de más". Cambié el código dos veces sobre esa deducción. Después:
#     · MEDÍ EL PAQUETE: lleva **una sola** entrada del ítem 540, con el count exacto. El server
#       manda bien. La duplicación, si existe, es entera del lado del cliente.
#     · Y anonimo03 aportó el dato que lo tumba: *"entre las pruebas cerraba y entraba y mi cantidad
#       subía según ganadas, NO se estaba duplicando — hasta antes de pedirte 500 monedas"*.
#
#   ⇒ Lo que había NO estaba roto. Y mientras tanto la interfaz se quedaba muerta al cambiar de
#     canal, que es un problema de verdad y sin explicación. **Primero se vuelve al estado
#     conocido-bueno y después se busca**, en vez de acumular arreglos sobre una hipótesis floja.
#
# ⏳ Lo que queda por medir, y en este orden:
#   1. con 6 monedas y esto en `True` (= exactamente como estaba cuando andaba), ¿vuelve la
#      interfaz? Si vuelve, el cuelgue es de los cambios de hoy o del número grande.
#   2. ¿el número grande (500) es lo que lo mata? Es lo único que cambió junto con el código.
#   3. y recién entonces, si de verdad se duplica, buscar POR QUÉ en el cliente — no a ciegas.
MYRECORD_SALDO_EN_CADA_REFRESCO = True   # ⚠ sin efecto con `MONEDA_GORILA_POR_FF69 = True`

# ★★★★★ EL SALDO DE MONEDA GORILA VA POR `FF69`, NO POR EL MyRecord — 2026-09-10.
#
#   ★ EL HALLAZGO, medido en los DOS clientes y capturado del referente:
#     El cliente tiene **dos funciones gemelas** para dar de alta un ítem, y el 2019 sin optimizar
#     les pone nombre (`cAccount::AddInventory` / `cAccount::SetInventory`):
#
#         AddInventory  -> SUMA     ← la que usa el **MyRecord (`FF03`)**
#         SetInventory  -> ASIGNA   ← la que usa el **`FF69` (`CmdGetItemCount`)**
#
#     No son un bug con dos versiones: son dos herramientas distintas, a propósito. En el 2013 la
#     suma es el `add eax, ecx` de `0x48F41C`; la gemela `0x48F350` no lo tiene. Y el reparto de
#     qué comando usa cuál es **idéntico en los dos builds**, seis años después.
#
#   ⇒ Mandar el SALDO en el `count` del ítem 540 del MyRecord lo hace **acumular**. Y encima el
#     barrido que dispara el `FF49` al cambiar de canal **CONSERVA** esa entrada (`0x48B39F`:
#     `test [entrada+8], 0xF000` / `je` = si el end_time no tiene esos bits, no la borra) ⇒ cada
#     cambio de canal le suma el saldo otra vez. anonimo03: *"me salen 1000"* con 500 en la base.
#
#   ★★ Y ASÍ LO HACE EL SERVER DE REFERENCIA. Capturado, con el ítem 540 adentro
#      (`mitm_20260902_144457.txt`), el contador subiendo a lo largo de la tarde:
#         14:36  FF69  01 | 1c 02 00 00 | 01 00 | …      ← "poné 1 moneda"
#         14:53  FF69  01 | 1c 02 00 00 | 03 00 | …
#         15:04  FF69  01 | 1c 02 00 00 | 06 00 | …
#      Él **nunca** le manda el saldo en el MyRecord. Y el `FF69` ya estaba en nuestra lista de
#      «los seis huecos que un server que funciona emite y nosotros no» (`FF_HANDLERS.md`).
#
#   Layout, leído de `0x5D0E00` (el handler del 2013) y calcado del 2019:
#       [modo:u8 = 1][item_id:u32][count:u16][rcoin_total:u32]      = 11 bytes
#     · `modo` tiene que ser **1** o el handler se va por la rama de error (`0x5D0E67`).
#     · el último u32 es el **RCoin**: si no coincide con el que el cliente ya tiene
#       (`[jugador+0x2D8] ^ 0x1FEF`, `0x5D0EBE`) saca un cartel de "+delta". Se manda el real.
#
#   ⛔⛔ Y LA ENTRADA DEL 540 SE SACA DEL MyRecord — **no se manda en 0**.
#     `0x5ED3D9`: `test ax,ax / jne / mov eax,1` ⇒ **un `count` de 0 se convierte en 1**, así que
#     dejarla en cero sumaría **+1 en cada MyRecord**. Sacarla es seguro: `SetInventory` **crea**
#     la entrada si no existe (`0x5A8695` en el 2019).
#
#   ★ La ventaja que decide: el `FF69` es **idempotente**. Se puede mandar las veces que haga
#     falta y el número queda igual — no hay que llevar la cuenta de cuántas veces se envió, que
#     es exactamente donde me equivoqué dos veces hoy.
#
#   En `False` vuelve al camino viejo (el saldo dentro del MyRecord, con su acumulación).
MONEDA_GORILA_POR_FF69 = True


# ★★★★★ QUÉ SE SIGUE VIENDO CON UN PERSONAJE DEL GACHA PUESTO — 2026-09-10.
#
#   ⛔ EL BUG DE ORIGEN, cazado por anonimo03 estrenando el premio del canje: *"al usar un personaje
#     gacha, la mascota se de-equipa"*. Y preguntando después: *"¿las alas se pierden también?"*.
#     Sí — las alas, la varita, el sombrero y lo de la mano: se perdía TODO.
#
#   CAUSA: un personaje del gacha **es un cuerpo entero** (`hero.txt` trae su modelo con cabeza,
#   torso y piernas), así que `gacha.apariencia` mandaba la lista de prendas **VACÍA** mientras
#   estuviera puesto — si no, la ropa le tapa el cuerpo especial (ése fue el bug del 08-sep,
#   *"salió con su ropa normal"*). Arreglaba la ropa y de paso borraba todo lo demás.
#   ★ Y ya estaba escrito que no son lo mismo: `paquetes.py` dice *«la mascota y los accesorios
#     **no son piezas de avatar**»*, con las 7 ranuras
#     `1 pelo · 2 top · 3 bottom · 4 zapatillas · 5 pet · 6 · 7 wand`.
#
#   ⇒ LISTA BLANCA, y el contenido lo eligió anonimo03 **mirando la pantalla**, en TRES pasos:
#     primero se probó dejando todos los accesorios, después lo acotó a *"manos, pet y alas"*, y
#     al verlo lo cerró en **alas y mascota**. Cada paso salió de mirar el resultado, no de
#     razonar sobre familias — por eso la lista es ésta y no la que yo había deducido.
#
#       ✓ se ve      pet (mascota) · aura_summon (alas/auras)
#       ⛔ se tapa    TODO lo demás: la ropa de cuerpo, la piel, los trajes enteros, el sombrero
#                    (`head_accessory`), la varita (`wand`) y lo de la mano (`wardrobe_hand`)
#
#   ⚠ Es lista BLANCA a propósito: lo que no esté acá **se tapa**. Así una familia nueva no puede
#     aparecer encima del cuerpo del gacha por descuido — que es el error caro de los dos (el bug
#     del 08-sep). Si algún accesorio tiene que verse, se agrega acá y se prueba EN PANTALLA.
#
#   ⚠⚠ Y un agujero APARTE que apareció mirando esto: hay 5 alas en la familia `seasonal`
#     («Alas Mecha Verde Fresco», «Alas Ángel Caído»…) y **`seasonal` no está en
#     `WEARABLE_FAMILIES`** ⇒ hoy esas alas **no se pueden equipar en absoluto**, con gacha o sin
#     gacha. No es este bug y no se toca acá, pero queda anotado.
#     ✅ CERRADO el 2026-09-24: la pestaña SEED (0600) toma la familia de sus iguales
#       (`shop_catalog.familias_seed`): esas alas son `aura_summon`, las varas `wardrobe_hand`…
GACHA_FAMILIAS_QUE_SOBREVIVEN = {"pet", "aura_summon"}


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# ★★★ AMIGOS — estrenado el 2026-09-10
# ═════════════════════════════════════════════════════════════════════════════════════════════════
# El disparador no fue una idea: fue el LOG DE PROD. **509 solicitudes de amistad** llegando y
# cayendo en "SIN handler", con el nick en claro adentro del paquete:
#
#     inner FF40 len=13 : 1d 00 00 00 00 07 4a 55 47 41 44 4f 52     "JUGADOR"     ×40
#     inner FF40 len=12 : 1d 00 00 00 00 06 4a 55 47 41 44 41        "JUGADA"    ×31
#
# ★ Las repeticiones son la misma persona insistiendo. Y el `uid` llega en **cero**: el cliente no
#   lo sabe, así que **el nick es lo que vale**.
#
# El mapa entero está en `documentacion/SOCIAL_MAPA_2013.md`. Los bytes son los del 2013, MEDIDOS:
# el `lobby_social.py` del CBT **no se porta tal cual** (trece subtipos cambiaron de forma).

# El tope de amigos. Sale de los propios carteles del cliente: el texto del error dice
# "no puede registrar más de 100 amigos". No es una elección nuestra.
AMIGOS_TOPE = 100

# ── ⚠ LA PERILLA DE SEGURIDAD ────────────────────────────────────────────────────────────────────
#   Cada amigo del `FF42` lleva 11 bytes de cola (`u8, u8, u32, u8, u32`) que están medidos en
#   TAMAÑO pero **no en significado** ([NM] en el mapa). Van en cero: el paquete queda bien
#   formado, pero **no sabemos qué dibuja el cliente con eso**.
#
#   ⇒ Si al ver la lista en pantalla algo sale raro (todos "desconectados", niveles absurdos, la
#     ventana en blanco), poner esto en **False**: el `FF42` sigue contestándose —que es lo que
#     enciende la interfaz— pero con la lista de amigos VACÍA. Es una línea, y separa
#     "el paquete está mal" de "los campos de cola están mal".
AMIGOS_LISTA_EN_FF42 = True

# ── ★★ EMPUJAR LA LISTA DE AMIGOS (FF40 0x03) ────────────────────────────────────────────────────
#   MEDIDO 2026-09-10: en toda una sesión de prueba, el cliente pidió el `FF42` **CERO veces**.
#   Ese cargador perezoso no se dispara en el 2013 por los caminos que la gente usa. ⇒ Si el
#   server no EMPUJA la lista, el cliente nunca se entera de quiénes son sus amigos, aunque la
#   base los tenga bien guardados. Era exactamente el síntoma: el alta andaba y la ventana vacía.
#
#   ⚠ El paquete lleva 11 bytes por amigo medidos **en tamaño pero no en significado**, que van en
#     cero. Si la lista sale rara en pantalla (todos desconectados, datos absurdos) o si el cliente
#     se porta mal, poner esto en False: se deja de empujar y se vuelve al estado anterior.
#   ⚠⚠ Hoy mismo un paquete mal armado mató al cliente (el techo de 4096 del FF57). Esta perilla
#     existe para no tener que buscar el archivo si pasa algo.
AMIGOS_EMPUJAR_LISTA = True

# ── ★ EL BYTE DE "ESTÁ CONECTADO" EN LA LISTA DE AMIGOS — EXPERIMENTO, 2026-09-10 ────────────────
#   anonimo03 probó y la lista YA SE VE. Lo que NO anda: pedir la ficha de un amigo saca el cartel
#   equivocado, y el susurro **no manda ni un paquete** (medido en el log: cero). Si el cliente no
#   emite nada, es que decide localmente que no se puede — y el sospechoso es el estado del amigo.
#
#   En el registro del `FF40 0x03` hay DOS bytes seguidos después del uid, medidos en tamaño pero
#   no en significado. En el CBT el de esa posición era "color/online" de la fila.
#     1 = mandarlo en el PRIMER byte      2 = en el SEGUNDO
#     3 = en los dos                      0 = ninguno (como antes del experimento)
#   ⇒ Si con 1 no cambia nada, probar 2. Es una línea y un reinicio.
#   ★ El valor no es inventado: va **1 si el amigo está conectado de verdad**, 0 si no.
AMIGOS_BYTE_ESTADO = 1

# ★★★★★ EL CAMPO QUE DICE "No conectado." — MEDIDO EN EL EXE EL 2026-09-10 ─────────────────────
#
#   anonimo03 lo reportó así: *"'conectado' aparece aunque todavía no haya abierto el otro cliente
#   — por descubrir qué valor anuncia en uno y prende en el otro"*. Es ESTE campo, y el cliente
#   lo dice con todas las letras en `0x459110`, el que arma el panel del amigo:
#
#       0x459146   ecx = 0xFFFF
#       0x45914b   cmp word [amigo+0x0a], cx
#       0x459154   jne  0x45917c
#          igual   -> push 0x4D ; call 0x433380   ->  texto #77  = "No conectado."
#          distinto-> push 0x1D ; call 0x433380   ->  texto #29  = "Servidor %d"
#                     y formatea ese MISMO u16 como el número.
#
#   ⇒ **`0xFFFF` = "No conectado."  ·  cualquier otro valor = "Servidor N".**
#   Y el constructor de la entrada (`0x45FD50`) lo inicializa justo en `0xFFFF`, que es la
#   confirmación independiente: el propio cliente arranca cada amigo como desconectado.
#
#   ⛔ Nosotros mandábamos **0** ⇒ "Servidor 0" ⇒ **todos conectados, siempre**. Exactamente el
#     síntoma. Y por eso perseguir el "punto verde" en los dos bytes de `AMIGOS_BYTE_ESTADO` no
#     iba a alcanzar nunca: la presencia no vive ahí.
#
#   ★★ EL NÚMERO DE CANAL ES EL ÍNDICE QUE NOSOTROS MISMOS PUBLICAMOS — corregido 2026-09-11.
#     ⛔ Primero puse **índice + 1** ("1..10, estable y ordenado"), que era una elección mía y
#       nada más. anonimo03 mandó dos capturas del mismo perfil —el suyo y el que ve su amigo— y en
#       la del amigo el campo **"Servidor" salía VACÍO** mientras "Ubicación: Sala No. 1" sí
#       cargaba. Estaba en el canal *Libre*, o sea el índice **9**; nosotros mandábamos **10**,
#       que no existe ⇒ el cliente no encontraba ese canal y dejaba el renglón en blanco.
#     ⇒ Va el índice TAL CUAL, que es el mismo `idx` con el que le publicamos la lista de
#       canales en el `CmdLobbyServerList` (`paquetes._entrada_canal(i, …)`, 0-based). No es una
#       elección nuestra: es el número que el cliente YA recibió de nosotros para ese canal.
#     ★ Y el 0 queda libre para usarse: el "no conectado" es 0xFFFF, no el cero.
AMIGOS_SERVIDOR_DESCONECTADO = 0xFFFF

# ★★ Y LOS CENTINELAS DE LA SALA, de la misma función que dibuja el renglón (`0x44C740`):
#       sala == 0xFFFF  ->  texto #30  "vestíbulo"        (está conectado, en el lobby)
#       sala == 0xFFFE  ->  texto #101 "Juego Personal"
#       otra            ->  texto #82  "Sala No. %d"
#   ⛔ Iba 0, que no es ninguno de los tres ⇒ a todo el que estaba en el lobby le salía
#     **"Sala No. 0"**. Reportado por anonimo03 el 2026-09-11.
SALA_VESTIBULO      = 0xFFFF
SALA_JUEGO_PERSONAL = 0xFFFE
AMIGOS_MANDAR_SERVIDOR = True      # False = volver a mandar 0 (el comportamiento de antes)

# ── ★★★ "JUGAR JUNTOS" — el `FF41` (2026-09-11) ──────────────────────────────────────────────────
#   ⛔ EL CAMPO DE LA SALA **NO ES UN NÚMERO PELADO**: es el mismo `A` empaquetado de la lista de
#     salas, `A = (TIPO << 11) | número`. Medido dos veces, por dos caminos independientes:
#       · `0x44C530`  hace `ax >> 11` para el tipo y `eax & 0x7FF` para el número, y compara cada
#         mitad contra la mía (`[0x9314c0]+0x957c` ^ 0xEF  y  `+0x9508`) para saber si YA estoy ahí.
#       · `0x44D5B6`  `and eax,0xF800 / cmp eax,0x5800` ⇒ el **tipo 11 (Mi Casa) queda excluido**
#         del "jugar juntos" A PROPÓSITO. No es un bug que arreglar.
#     Y es el MISMO formato que ya armábamos en `paquetes.build_ff6e_roomlist` desde el 2026-08-05
#     (`a = (roomid & 0x7FF) | (A_alto << 11)`). Mandábamos el número sin el tipo ⇒ el cliente leía
#     **tipo 0** para todo, y `0x44C596` (`cmp ax,5 / jb`) descarta el tipo 0.
#
#   ★★ CÓMO FUNCIONA EL AUTO-JOIN, medido de punta a punta:
#       1. el amigo está en OTRO canal -> el cliente muestra el botón «Jugar Juntos»
#          el amigo está en MI canal   -> NO hay botón: manda el `FF41` derecho (`0x44D5DA`)
#       2. al aceptar, guarda la sala en `[roommgr+0x132c]` y se muda de canal
#       3. ya en el canal nuevo, marca `[roommgr+0x12ea] = 1` y manda el `FF41` (`0x4A7EC4`)
#       4. al llegar la respuesta, `0x5CEC7A` mira esa marca:
#               con marca -> ★ ENTRA A LA SALA      ·      sin marca -> refresca la fila de la lista
#     ⇒ **El mismo paquete sirve para las dos cosas y quien decide es el cliente.** Nosotros
#       contestamos igual en los dos casos: no hay que adivinar para qué lo pidieron.
#
#   ⚠ DE LOS 10 CAMPOS DE LA RESPUESTA, 5 ESTÁN EN [NM] (tamaño medido, significado no). Van en
#     CERO, que es el valor que no dispara ninguna rama: el campo 7 distinto de 0 llama a
#     `0x58E760` y el 10 distinto de 0 prende un bit de una máscara. Ver `h_ff41_info_de_sala`.
#
#   ⇒ Si al usar «Jugar Juntos» algo sale raro, **esto en False**: el `FF41` vuelve a quedar sin
#     contestar, que es exactamente el estado de antes del 2026-09-11. No toca nada más.
FF41_INFO_DE_SALA = True

# ── ★★★ NO CONTESTAR EL FF41 HASTA QUE EL LOBBY ESTÉ ARMADO (2026-09-11) ─────────────────────────
#   anonimo03, probando: *"el que se une ve el error gráfico de la sala, y al salir a la lista de salas
#   no ve la sala del otro usuario"*. Y su diagnóstico, que resultó ser el correcto: *"el que le da
#   unirse no está cayendo bien entre la secuencia de unirse - mover canal - llegar - entrar sala"*.
#
#   ★★ MEDIDO CON SU CONTROL AL LADO, en el log del 2026-09-11 (tres entradas de cada tipo):
#
#       entrada NORMAL al canal        con «JUGAR JUNTOS»
#       ...                            ...
#       ctr=10  GuildInfo              ctr=10  ★ FF41        <- se mete acá
#       ctr=14  FF137                  ctr=15  FF137
#       ctr=15  FF1D   <- ★ TERMINA    ctr=16  ★ ENTERROOM   <- entra acá
#
#     El `FF1D` (payload `03`) es **la última parada del arranque del lobby**: llega 3 de 3 veces
#     en una entrada normal y **CERO veces** cuando hay auto-join. ⇒ El cliente **corta su propia
#     secuencia de arranque por la mitad** para meterse en la sala, y pinta la sala sobre un lobby
#     a medio armar. Ése es el error gráfico.
#
#   ⇒ EL ARREGLO: cuando el `FF41` llega ANTES del `FF1D`, se guarda y **no se contesta todavía**.
#     Sin respuesta el cliente no tiene motivo para irse, sigue su secuencia, manda el `FF1D` — y
#     ahí le contestamos. Entra a la sala con el lobby ya armado.
#
#   ★ No se fuerza nada del lado del cliente: sólo se le contesta **cuando corresponde**. Es la
#     regla que puso anonimo03: *"si usamos trucos podemos romper"*.
#
#   ⚠⚠ EL RIESGO, dicho con todas las letras: si un cliente **nunca** manda el `FF1D`, su pedido
#     queda sin respuesta y «Jugar Juntos» no hace nada para él. No queda colgado ni roto —queda
#     como estaba antes del 2026-09-11— pero tampoco funciona. Está medido que llega siempre en
#     este cliente; si aparece uno que no lo manda, **esto va a False** y se contesta al toque.
#
#   ⛔ A PROPÓSITO NO HAY TEMPORIZADOR. Despachar el pendiente desde otro hilo mandaría un FF55
#     fuera de orden, y el contador del cifrado del lobby es exactamente lo que costó el arreglo
#     grande del 2026-09-10 (ver §0 de `PENDIENTE_SUBIR_A_PROD.md`). Todo corre en el hilo de la
#     conexión, como el resto del server.
FF41_ESPERA_LOBBY = True

# ── ★★★ AVISARLE A LOS AMIGOS QUE ENTRÉ/SALÍ DE UNA SALA (2026-09-12) ────────────────────────────
#   anonimo03, después de que «Jugar Juntos» empezó a andar: *"agregué varios amigos, pero el botón
#   dejó de aparecerme para unirse luego de funcionar una o dos veces"*.
#
#   ⛔ LA CAUSA, medida en el log: las 14 actualizaciones de lista de esa sesión son **todas** por
#     entrar o salir de un CANAL. **Ninguna por entrar a una SALA.** ⇒ cuando un amigo entra a una
#     sala, sus amigos no se enteran: su ficha sigue diciendo *vestíbulo* (`sala = 0xFFFF`), y
#     `0x44D480` esconde el botón cuando la sala es el vestíbulo. Por eso "funcionaba una o dos
#     veces": sólo cuando la lista se había re-mandado por casualidad justo antes.
#
#   ★ No lo rompimos ahora: **siempre fue así**. Lo que cambió es que ese dato antes no decidía
#     nada y hoy decide si el botón aparece. Molde de [[el-bug-que-no-falla]].
#
#   ── POR QUÉ EL PAQUETE FINO Y NO RE-MANDAR LA LISTA ──────────────────────────────────────────
#   Decisión de anonimo03: *"la que sea más cercana a la forma nativa"*. Y la nativa es el aviso
#   puntual, no la lista entera:
#     · el cliente 2019 tiene un comando DEDICADO para esto: **`FF034 CmdUpdateFriendPlace`**
#       ("actualizar el lugar del amigo") — o sea el concepto existe y es de a uno. **[M]**
#     · ⛔ pero en el 2013 ese opcode está MUERTO (`0x5C54D0` drena y tira) ⇒ **no se puede usar**;
#       acá el camino vivo es el **FF40 sub `0x04`** (`0x5EFD59`), que lleva canal + sala. **[M]**
#   ⇒ Se manda el `0x04`, que es un paquete chico por amigo, en vez de la lista completa de todos.
#
#   ⚠⚠ EL RIESGO: el `0x04` **nunca se mandó todavía**. El layout está medido campo por campo
#     (`AMIGOS_2013.md` §5.1) pero 6 de sus 15 campos son [NM] y van en cero. Si algo sale raro
#     —el amigo aparece desconectado, se rompe el susurro, la ventana parpadea— esto va a
#     `"lista"` y se vuelve al camino viejo, que está probado.
#
#       "fino"   -> FF40 sub 0x04, un paquete por amigo        ← la forma nativa
#       "lista"  -> re-mandar la lista entera (lo de siempre)  ← la red de seguridad
#       None     -> no avisar nada (el comportamiento de antes del 2026-09-12)
AMIGOS_AVISO_DE_SALA = "fino"

# ── ★★★ EL AMIGO DEL ALMA / JOYA DE LA AMISTAD (FF40 sub 0x3B) — 2026-09-15 ──────────────────
#   Pedido de anonimo03: *"cablear la joya de amistad"*. Es el hermano de la pareja, **no existe en el
#   CBT**, y hasta hoy no tenía una sola línea de server: el cliente mandaba sus paquetes y nadie
#   contestaba. Todo el mapa está en `documentacion/AMIGO_DEL_ALMA.md`.
#
#   ⚠ En `False` se vuelve exactamente a ayer: se registra en el log y no se contesta nada. Como
#     el sistema no existía, apagarlo no puede romper nada que antes anduviera.
AMIGO_DEL_ALMA = True

#   ★★★ CUÁNTOS amigos del alma puede tener uno: **DOS**, y lo dice el cliente.
#
#   ⛔ ACÁ ESCRIBÍ QUE EL NÚMERO "ERA NUESTRO" Y QUE "no está en ninguna parte, ni en el texto ni
#     en el binario". **Estaba mal, y lo destapó anonimo03 probando**: intentó agregar un tercero y le
#     saltó el cartel del cliente, no el nuestro. En el log no hay ni un rechazo del server.
#
#   ★★ El número está en el binario, dos veces:
#         0x450E03  cmp dword [panel+0xBA8], 2   -> si NO es menor que 2: str#913 "ya no puedes
#                                                   tener más amigos del alma"
#         0x450DCD  cmp byte  [esi+0x2718], 2    -> str#897 "el usuario que ingresaste ya tiene
#                                                   la máxima cantidad"
#   ⇒ El tope es del CLIENTE. Poner acá un número mayor no agrega nada: el jugador ni siquiera
#     puede pedir el tercero. Poner uno menor sí sirve, si alguna vez se quiere ser más estricto.
#
#   ★ Y cierra con la ayuda del juego: *"cuando TRES amigos del alma estén juntos aparecerá un
#     diamante adicional"* = **yo + mis dos**. No eran tres amigos: eran tres personas.
ALMA_TOPE = 2

#   ⏳ El cartel a todo el server (str#904 *"%s y %s son ahora amigos del alma"*). Hoy **sólo deja
#     el renglón en el log**: el texto existe y está traducido, pero todavía no está medido por
#     qué paquete sale — el sub `0x3B` no lo usa en ninguna de sus ramas. Prefiero un anuncio que
#     falta a un paquete inventado.
ALMA_ANUNCIO = True

#   ⛔ CUÁNTO VIVE UNA SOLICITUD SIN CONTESTAR, en segundos. **Nació de un bug real** (15-sep): el
#     popup salía mal armado y no se dibujaba, pero la solicitud igual quedaba anotada ⇒ el
#     destinatario quedaba **inalcanzable para siempre**, y el server contestaba *"ya tiene un
#     cartel abierto"* a todo el mundo. La lección es más general que aquel bug: **anotar que
#     mandé un paquete no prueba que el otro lo haya visto.**
#   ⇒ Pasado este tiempo, otra persona puede volver a pedirle. (El mismo proponente puede
#     reintentar en cualquier momento: eso re-manda el diálogo.)
ALMA_VENCE = 120

#   ⛔⛔ REPOBLAR «Amigo de Alma» AL ENTRAR — y el precio, que está MEDIDO.
#     anonimo03: *"si es que están registrados, no me aparecen"*. La fila se insertaba **sólo en el
#     momento de registrarse, en vivo**; al volver a entrar nadie la mandaba de nuevo. Es la misma
#     lección que ya está escrita tres veces acá: *el dato en la base no se dibuja solo*.
#
#   ⚠⚠ **No existe ningún paquete que inserte esa fila sin sacar un cartel.** `0x45F430` es el
#     único insertador y tiene **exactamente dos llamadores** en todo el exe, los dos detrás de un
#     cartel que está en la rama, no en un campo:
#         0x5F25D2 <- subs 0x02/0x03 -> str#910   ·   0x5F2366 <- subs 0x24/0x25 -> str#906
#   ⇒ Con esto en `True`, al entrar sale **un cartel por cada amigo del alma**. Es el costo de que
#     la fila exista. En `False` la fila sólo aparece al registrarse (lo de antes).
#   ✅✅ YA NO HACE FALTA — 2026-09-15, y lo destrabó anonimo03: *"si la maquinaria ya funciona en
#     vivo, hay forma nativa de lograrlo"*. **La hay, y estaba en un paquete que ya mandábamos**:
#     la SEGUNDA lista del `FF40 0x03` (la que iba con el comentario *"vacía"*) es la de los
#     amigos del alma, la inserta `0x45F240` **sin cartel**, y encima lleva la joya y el estado.
#   ⇒ Esto queda en **False**. Se deja la perilla —y no el código borrado— porque es el único
#     camino medido para insertar una fila del alma *fuera* de la lista, y puede hacer falta el
#     día que haya que meter una sola sin re-mandar todo.
ALMA_REPOBLAR = False

# ── ★★ PAREJA (FF40 sub 0x0A) — 2026-09-12 ───────────────────────────────────────────────────────
#   Cuántas propuestas puede mandar uno por sesión. **No es una elección nuestra**: el propio
#   cliente tiene el cartel #141 *"Puede enviar su propuesta 10 veces al día"*.
#   ⛔ ACÁ DECÍA *"se cuenta por SESIÓN del server"*, y en prod eso fue: el server corrió del
#     18-sep al 23-sep sin reiniciar y el contador NUNCA volvió a 10 (jugador24 en 0). Desde el
#     23-sep se cuenta por DÍA de verdad (fecha del server), como dice el cartel.
PAREJA_TOPE_DIARIO = 10

# ── ★★★ CASARSE ESTANDO CASADO — COMO EL ORIGINAL (2026-09-23, decisión de anonimo03: "A") ─────────
#   Medido en el diálogo «Proponer» del propio cliente (`0x42438C`…`0x4243F1`, gemelo en
#   `0x426872`): antes de mandar nada, el cliente mismo hace dos chequeos:
#       ¿es YA mi pareja?      -> str#133 «Ya está unido a este usuario» y corta
#       ¿YO tengo pareja?      -> str#134 «Ya está unido a otro usuario. Al aceptar este anillo,
#                                 cancelará su relación actual. ¿Está seguro…?» y SI ACEPTA, PROPONE
#   ⇒ El juego original DEJABA proponer estando casado: la relación vieja se termina al casarse.
#   ⛔ Nuestro server lo cortaba con el código 4 (str#144 «Ya está unido a este usuario»), que
#     además es FALSO cuando el otro está casado con un tercero (lo vio anonimo03: jugador1 -> jugador50).
#   True  = se puede proponer aunque uno (o los dos) estén casados; al ACEPTAR, las parejas viejas
#           se rompen con la misma ruptura de siempre (avisos, adorno, recuerdo en la mochila).
#   False = como hasta el 23-sep: el código 4 si alguno de los dos está casado.
PAREJA_CAMBIAR_COMO_ORIGINAL = True

#   ★ Cuánto vive una propuesta sin contestar, en segundos. **0 = no vencen** (como el original).
#   ⛔ En prod, a jugador35 le quedó una colgada el 21-sep y todo el que le propuso después recibió
#     el error 2 durante días. Eso YA NO depende de vencer (2026-09-23):
#       · una persona puede tener VARIAS propuestas recibidas (el panel las lista), así que una
#         colgada no bloquea a nadie;
#       · el que propuso la cancela con la X de «Propuesta entregada» (sub2 5 / sub2 12);
#       · si se desconecta cualquiera de los dos, se cierra con su texto (#150 / #145).
#   ⚠ Y vencer tenía un costo: el server la olvidaba mientras el renglón seguía en el panel, y el
#     OK de después no hacía nada. Por eso 0. Queda la perilla por si alguna vez hace falta.
PAREJA_PROPUESTA_VENCE = 0

# ── ★★★ CASARSE ENTRE EL MISMO GÉNERO — 2026-09-15, pedido de anonimo03 ────────────────────────────
#   `True` = cualquiera con cualquiera · `False` = la regla del juego original (sólo varón+mujer).
#
#   ★★ POR QUÉ SE PUEDE, Y NO ES UNA CORAZONADA: **el cliente no tiene ese bloqueo.** El texto que
#     sale al rechazar es el #143 (*"No puede enviar una propuesta a usuarios del mismo género"*),
#     y se buscó `push 0x8f` —el índice 143— **en las 342.785 instrucciones del `.text`**: no
#     aparece **ni una vez**. El único camino que lo dibuja es el genérico `system.csv[140 + code]`
#     del paquete de error, o sea **el que mandamos nosotros**.
#   ⇒ La regla era del SERVER desde siempre. Sacarla no le pide nada al cliente ⇒ **no hay que
#     tocar el exe**, que es justo lo que este proyecto intenta evitar siempre que puede.
#
#   ★ Y lo que sigue funcionando igual, revisado pieza por pieza antes de abrirlo:
#       · la animación de propuesta (`FF46`) elige la voz con **el género de cada ocupante**
#         (`0x593EF2` → `0x436380`) ⇒ cada uno se arrodilla con su propia voz, sin caso especial
#       · el enlace de asientos (`0x527B00`) guarda **slot y anillo**, y no mira género
#       · el recuadro de la sala (`0x527720`) compara `[nodo+0xC4]` con `slot±1`, tampoco
#     ⇒ No hay ninguna pieza del dibujo que dependa de que sean de géneros distintos.
#
#   ⚠ En `False` vuelve a salir el cartel #143 y todo queda como el 2013 original. Es una línea.
PAREJA_MISMO_GENERO = True

# ── ★★★★★ EL MINI CHAR DE LA PAREJA EN «MI INFO» (FF77) — 2026-09-15 ──────────────────────────
#   Pedido de anonimo03: *"que «mi info» muestre el minichar de mi pareja y el mío — era una función
#   nativa si no me equivoco"*. **Era nativa.** El último byte de la cola del `FF77` es un flag
#   que abre un bloque entero con el nombre, el avatar y la fecha de la pareja; nosotros lo
#   mandábamos en cero desde siempre, así que el cliente se lo saltaba.
#
#   ⚠⚠ EN `False` SI PASA CUALQUIER COSA FEA, y esto es lo primero que hay que probar en pantalla:
#     las seis ranuras del avatar de la pareja pasan por el **resolver de avatar** del cliente, y
#     ahí una pieza que no sea prenda base **cierra el juego**. Se manda el mismo filtro de 4
#     prendas que ya usa el avatar propio (`paquetes.seis_ranuras`, una sola copia), pero el
#     avatar propio nunca se probó con la mochila de otra persona.
#   ★ Con esto apagado, «mi info» vuelve exactamente a lo de ayer: el flag en 0 y sin bloque.
FF77_PAREJA = True

#   ⏳ [H] EL ANILLO DETRÁS DEL MINI CHAR (2026-09-23). Con el muñeco de la pareja ya dibujado,
#   anonimo03: *"creo que también tenía que salir su joya de pareja detrás de ellos"*. El bloque de la
#   pareja arranca con un `u32` («A») que iba en 0, y en el `FF4A` de la pareja el anillo viaja
#   justo así, como `u32`. ⇒ La apuesta: «A» = el Index del anillo. NO está medido el consumidor.
#   Si no aparece nada (o aparece otra cosa), va a False y el bloque vuelve a mandar 0.
FF77_PAREJA_ANILLO = True

# ── ⚠⚠ LA PERILLA DEL CASAMIENTO ────────────────────────────────────────────────────────────────
#   `False` = se recibe la propuesta, se muestra el cartel y se puede RECHAZAR, pero al aceptar
#   **no se casa a nadie**. Sirve para probar la primera mitad —que está toda MEDIDA— sin mandar
#   el paquete del casamiento, que **tiene dos campos [NM]**:
#     · los **7 bytes de fecha** (en el CBT era un u64; acá cambió y no está confirmado)
#     · un **segundo nombre** que el CBT no tenía, y no sabemos de quién es
#   ★ El TAMAÑO sí está medido, así que el paquete no desincroniza la conexión: como mucho se
#     dibuja algo raro. Pero si al aceptar pasa cualquier cosa fea, **esto va a False** y la
#     propuesta/rechazo siguen andando.
PAREJA_ACEPTAR = True

# ── ★★ EL CARTEL GLOBAL DE LA BODA (FF40 sub 0x12) ──────────────────────────────────────────────
#   *"Ha nacido una pareja"*, el anuncio que ve TODO el server. ⚠ Es un broadcast: un paquete por
#   jugador conectado. Hoy con 44 es barato; si el server crece, es lo primero que hay que mirar.
#   ⛔ Y lleva la corrección que el CBT pagó cara: va `flag=0` (con 1 el cartel dice "cambiaron el
#     anillo") y el **ChargeId**, no el Index — en esa rama el cliente NO traduce, y con el número
#     equivocado el cartel sale sin el dibujo del anillo.
PAREJA_ANUNCIO_GLOBAL = True

# ── ★★★ LA PROPUESTA ANIMADA CON VOZ (FF46) ─────────────────────────────────────────────────────
#   El proponente se ARRODILLA y suena la voz ("¿aceptarías mi anillo?"). No es un adorno del
#   cliente: **lo dispara el server**, y no lo mandabamos nunca. Va a toda la sala.
#   ⚠ Solo se mandan los subs **0 (proponer)** y **2 (el no)**, que son LIMPIOS.
#     ⛔ El sub 1 (el SI) arrastra un cartel obligatorio cuyo texto (str#158) esta **VACIO** en
#       nuestro system.csv ⇒ saldria " & <nombre>", el mismo "cartel &" que el CBT sufrio.
#       Para usarlo hay que llenar ese renglon primero, y eso toca el cliente (reempacar el pak),
#       que es justo lo que ya rompio el cliente dos veces. Queda pendiente a proposito.
PAREJA_ANIMACION = True

# ── ★★ EL CARTEL «<A> & <B> ha llegado.» al entrar una pareja a la sala (FF48) ──────────────────
#   ⛔ El informe del agente dio este paquete por INUSABLE ("saldria ' & <nombre>'"). Es FALSO:
#     el cartel usa CINCO textos (#158 vacio de prefijo, #159 " &", #414, #160 "ha llegado.",
#     #161), no dos. Medido en 0x5965F5..0x5966E3. El vacio es un prefijo a proposito.
PAREJA_ANUNCIO_SALA = True

# ── ⚠ EL REFRESCO DEL ENLACE CON `FF15` — A PRUEBA (2026-09-12) ─────────────────────────────────
#   anonimo03, mirando el resultado: *"el pintado del slot SÍ se corrige, pero pasa por el color
#   equivocado y ocurre un repintado = no nativo, y esconde el problema"*. **Tiene razón.**
#
#   ⛔ EL PARPADEO ES CULPA DE ESTE REFRESCO: el `FF15` **re-escribe la entrada del ocupante**, así
#     que pisa el color del equipo, y `enviar_equipos` lo repone un instante después. El jugador ve
#     el slot cambiar al color de "solo" y volver. El server original no podía hacer eso.
#
#   ★★ LA PREGUNTA QUE HAY QUE MEDIR, y por eso esta perilla existe SEPARADA:
#     **¿hace falta el `FF15`, ahora que el `FF0C` lleva el enlace bien puesto?**
#     El `FF0C` aplica el enlace al CREAR al ocupante, y el recuadro se dibuja leyendo el campo de
#     UN nodo. Cuando M entra, a F le llega el `FF0C` de M ⇒ el nodo de M se crea con su enlace
#     apuntando a F ⇒ **podría alcanzar con eso solo**.
#   ⇒ `False` = sin `FF15`, sólo el `FF0C`. Si el recuadro se sigue viendo, **el refresco sobra**
#     y el parpadeo se va con él. Si desaparece, el `FF15` hace falta y hay que buscar la forma
#     nativa de no pisar el equipo.
#   ⚠ Es un A/B, no una preferencia: hay que probarlo en las dos posiciones antes de decidir.
# ── ★★★ AL ENTRAR ALGUIEN, AVISAR SOLO DE EL (2026-09-12) ───────────────────────────────────────
#   ⛔ Mandabamos la lista ENTERA a cada uno de los que ya estaban: con 5 adentro, 5 FF0C por
#     cliente, 4 de ellos de gente que YA tenia. Y el cliente saca "%s ha entrado a la sala de
#     juego." por cada uno que procesa ⇒ spam de carteles **con nombres de otros**.
#   ★ Lo vio anonimo03: "hay 5 jugadores, entra 1 nuevo, solo el nombre de el deberia aparecer".
#   ⇒ Y de paso el trafico de entrar a una sala baja de N² a N.
#   ⚠  vuelve a la lista entera (lo de antes) si algo se rompe.
FF0C_SOLO_EL_QUE_ENTRA = True

# ══ ✅ A/B RESUELTO el 2026-09-12: GANÓ EL LADO B (sin FF15) ═══════════════════════════════════
#   ★★★ Y la causa real era otra: el `FF48` llevaba el enlace y se mandaba ANTES del `FF0C` del
#     recién llegado ⇒ **le borraba el enlace a los que ya estaban** (ver `salas.difundir_ocupante`).
#     Mi refresco por `FF15` no arreglaba nada: tapaba un bug que yo mismo causaba, y encima
#     parpadeaba. anonimo03 lo marcó como *"no nativo, y esconde el problema"* — tenía razón en las dos.
#   ⇒ Con el `FF48` en su lugar, el `FF15` **sobra para prender**. Y para APAGAR no sirve:
#     `0x591FD0` nunca escribe `nodo+0x50`, y el apagado nativo es el propio `FF48` con anillo 0.
#   ⚠ Queda en False. Se deja la perilla —y no el código borrado— porque el `FF15` sigue siendo el
#     único camino medido hacia `nodo+0xC4` sin pasar por el `FF48`, y puede hacer falta el día que
#     haya que refrescar un enlace sin tener los dos nombres a mano.
PAREJA_REFRESCO_FF15 = False

# ── ✅ EL ENLACE DE PAREJA EN LA SALA (los corazones entre los dos asientos) ────────────────────
#   ★ CONFIRMADO EN PANTALLA el 2026-09-12: el recuadro con el anillo aparece. Era hipotesis.
#   El asiento de la pareja está MEDIDO (`cola[12]`, con `0xFF` = soltero). **La posición del
#   itemId del anillo NO**: sale de calcar el CBT, donde quedó resuelto al final, y de descartar
#   el otro `u32` del bloque (que son las alas, ya medidas).
#   ⇒ Si al sentarse con la pareja no aparece el recuadro, o aparece algo raro en otro lado,
#     **esto va a False** y se vuelve a "todos solteros", que es el estado correcto de antes.
FF0C_ENLACE_PAREJA = True

# ── ★★★★★ LA JOYA DE LA AMISTAD EN LA SALA (FF0C `cola[33..36]`) — 2026-09-15 ─────────────────
#   Pedido de anonimo03: *"las joyas, así como ves en la cabeza de pareja, o en el slot que vayan"*.
#   La ayuda del juego lo confirma: *"La joya que tienes equipado aparece cuando estés junto a tu
#   amigo del alma"*.
#
#   ⛔ NO viaja en el `worn`, aunque la ayuda diga "equipar": la joya es **categoría 12** y el
#     arreglo del cliente tiene **11** ranuras — mandarla ahí le escribe la pila. Ver
#     `CATEGORIAS_WORN`, verificado en los dos handlers.
#   ★★★ El camino real, medido de punta a punta:
#         0x5E868D  read(4) -> desc+0x58   ·   0x528C19 lo lee   ·   0x527D70 -> nodo+0xD4
#     ⇒ `nodo+0xD4` es al amigo del alma lo que `nodo+0x50` (el anillo) es a la pareja.
#   ★★ La posición sale de contar las lecturas del parser, y **se valida sola en CUATRO anclas
#     que este repo ya midió en pantalla**: alas `cola[5]` · cara `cola[11]` · pareja `cola[12]`
#     · género `cola[41]`. Los cuatro caen exactos con el mismo conteo.
#
#   ⚠ En False el campo vuelve a ir en cero, que es como viajaba hasta hoy. No puede
#     desincronizar nada: el byte ya estaba, sólo cambia su valor.
#   ⛔⛔ PROBADO EN PANTALLA EL 2026-09-15: **NO SE DIBUJA NADA, y el campo estaba MAL ELEGIDO.**
#     El paquete salía bien (`cola[33..36] = 1200088`, comprobado), así que el error era la
#     identificación: seguí la cadena un eslabón más y `nodo+0xD4` **no es un ítem**.
#         0x538C64 · 0x53DAEE · 0x5770DA  leen nodo+0xD8 y nodo+0xD4 juntos
#                                          y se los pasan a `0x6190A0`
#         0x6190A0  los ajusta con `add edi,0x15` / `add ebx,-4` ⇒ son **COORDENADAS**
#     ⇒ Mandarle un item id ahí es meterle una posición absurda. Por eso queda en **False**.
#   ★ La lección, otra vez la misma: *que los cuatro anclajes del conteo cierren prueba DÓNDE cae
#     el campo en el cable, no QUÉ significa*. Las anclas estaban bien; el significado, no.
#     Ver [[leer-al-consumidor]].
#   ⛔⛔⛔ PROBADO EN PANTALLA Y **NO ES LA JOYA**: `cola[28]` es del SISTEMA DE MEDALLAS.
#     Lo resolvió anonimo03 mirando videos del juego: el `(null)` que aparecía al encenderlo es **el
#     nombre de la medalla**, no el de un amigo del alma. (El panel «Ver Perfil» tiene su pestaña
#     «Mis Medallas», y ahí dice *"No tienes medallas"*.)
#   ★ Lo que SÍ quedó medido, y es nuevo para el proyecto: `cola[28]` = un id chico con `0xFF` =
#     ninguna, que el cliente comprueba en `0x527707` (`cmp byte [nodo+0xD1],0xff / setne`) y
#     cuyo nombre se dibuja arriba de la cabeza. **Es la MEDALLA equipada.**
#   ⚠ El `0xFF` de `<Friend Id="255">` era una coincidencia: los dos sistemas usan el mismo
#     centinela. Eso fue lo que me hizo confundirlos.
#   ⇒ Queda en False. Ver `AMIGO_DEL_ALMA.md` §11-ter y el pendiente de MEDALLAS.
FF0C_JOYA_DEL_ALMA = False

# ── ★★★★★ LAS JOYAS DEL ALMA EN LA SALA — `cola[40]` = CONTADOR + N bytes (2026-09-23) ─────────
#   La joya NO es un campo suelto: el personaje recibe una LISTA de joyas. Medido de punta a punta:
#       FF0C  0x5E86E3 read(1) = N  ·  0x5E86F9 N x read(1) = los `Id` de ring.txt <Friend>
#             -> desc+0x5C (un vector de bytes) -> 0x5B35D1 -> 0x5B0AA0
#       0x5B0AA0  por cada Id: 0x50FB10 = su `RoomFx`, y lo engancha al personaje en dummy01..04
#                 (con 3 usa otras posiciones: el "diamante adicional" de la ayuda del juego)
#   ★ Por qué `cola[40]` y no el 41 que decía el conteo viejo: `cola[18]` es una BANDERA
#     (0x5E85EE `cmp / je`): en 0 el cliente SE SALTEA el byte siguiente, y todo lo de detrás cae
#     un byte antes. Lo confirmó la sonda (`herramientas/pareja/sonda_pareja.py`): las 6 cuentas
#     —3 chicas incluidas— llegaron con la lista VACÍA; si el contador fuera el 41 (el género),
#     cada chica habría traído "1 joya". ⇒ el 41 es el byte que el cliente lee DESPUÉS de la
#     lista, y el género queda confirmado donde estaba.
#   ⇒ La lista: el `Id` de la joya de cada amigo del alma PRESENTE EN LA SALA (la ayuda: *"la joya
#     aparece cuando estés junto a tu amigo del alma"*; *"si tenés más, las joyas aumentan"*).
#   ⚠ En False se manda la lista vacía (`cola[40] = 0`), que es como viajó siempre.
FF0C_JOYAS_ALMA = True

# ── ★★★ LOS MARCOS DE ASIENTO — `FF0C cola[10]` y `FF15 #11`, UN BYTE (2026-09-23) ──────────────
#   Los ítems «Slot …» / «Caja ranura …» de la pestaña 0506. El byte es el `Index` de
#   `servidor/tablas-cliente/slotpack.txt` (la tabla del cliente, que lo llama *"el número que se
#   recibe del servidor"*). Medido de punta a punta:
#       FF0C  0x5E8557 read(1) -> desc+0x3D -> 0x5B322D -> sRoomUser+0x194 (nodo+0x1A4)
#       FF15  0x5F390E read(1) -> 0x59FB90(slot, n) -> el MISMO nodo+0x1A4, y re-arma el efecto
#       dibujo 0x5AD722: nodo+0x1A4 != 0 -> 0x50F8C0(n) = la fila -> su sprite y BeginFrame
#   ★★ LA FUSIÓN DE PAREJA LA HACE EL CLIENTE: `0x595430` exige que los DOS tengan número, que
#     sea EL MISMO y que su fila diga `Couple="1"`; `0x527720`, que la pareja esté al lado. Ahí
#     cambia al `CoupleBeginFrame` y pone el `EffectId` (`0x59F610`).
#   ⇒ En False el byte vuelve a 0, que es como viajó siempre (= sin marco).
MARCO_DE_ASIENTO = True
#   ★ Y POR ESO EL DE PAREJA SE COMPRA PARA LOS DOS: si sólo lo tiene uno, el cliente nunca
#     fusiona. Al comprarlo con pareja, la pareja recibe uno igual (mismo plazo), como el anillo
#     (`PAREJA_ANILLO_AL_QUE_ACEPTA`). Si ya lo tiene, no se le da otro. Cada uno lo equipa.
MARCO_PAREJA_PARA_LOS_DOS = True
#   ★ LA MASCOTA DE PAREJA, igual (pedido de anonimo03, 23-sep: *"un miembro la compra y ambos la
#     reciben"*). Y no es sólo regalo: el cliente dispara el «se encuentran» y los combos de corazón
#     y beso (`pet.xml`: `Couple_Find`, `CoupleCombo_0..4`) sólo si la PAREJA —el enlace que ya
#     mandamos, sRoomUser+0x1DC— tiene puesta la otra mitad del par (`0x592970` -> `0x524210`).
MASCOTA_PAREJA_PARA_LOS_DOS = True

# ── ★★★ LOS CUPONES DE LA PARTIDA — `FF80` = `CNetwork::CmdGameCoupon` (2026-09-23) ─────────────
#   Nunca lo mandábamos. Es cómo cada cliente se entera de qué cupones tiene ACTIVADOS cada jugador
#   de la carrera. Handler 2013 `0x5E76F0` (el 2019 lo nombra y lee la misma forma):
#       [u8 n]  n × { [u8 asiento] [u8 m]  m × [u32 ítem] }
#   -> `0x528970(asiento, ítems)` cuenta los `ItemEffect` y llena la tabla del administrador de
#   asientos (`[0x931660]+0x20`, clave `efecto << 16 | asiento`), que es la que consulta
#   `0x5285D0(asiento, efecto)` DURANTE la carrera — p. ej. `0x5074C6`: el «Grito del Héroe» de
#   cada modo (efectos 394/395/396/632).
#   ⛔ Sin esto, cada cliente sólo veía SUS cupones (para uno mismo el cliente mira su propia lista,
#     `0x489250`). anonimo03, 23-sep: *"funciona, pero visualmente sólo lo ve el que lo compró"*.
#   ⇒ Sale justo antes del `FF25`, a los que corren y a los que miran.
FF80_CUPONES_DE_PARTIDA = True
#   Las familias cuyos ítems activados viajan en el `FF80`. Los Modos Héroe y las Profecías;
#   ⏳ los cupones de premio se suman cuando se implementen (ver `MODIFICADORES_Y_RETOS.md`).
FAMILIAS_EN_FF80 = ("hero_mode", "prophecy")
#   ★ QUIÉNES SON LOS MODOS HÉROE: los lista el propio cliente, en `setitem.txt`, como contenido del
#   «Pack de 4 modos héroe» (`nonWear` = se activan, no se visten). Se leen de ahí.
PACK_MODOS_HEROE = 491
#   ★ (136) Y LOS QUE NO VIENEN EN ESE PACK: el «Modo Aleatorio» (29-oct), el quinto, traído del 2019 (1000210,
#   ItemEffect 2585; lo hace la dll, `heroe_aleatorio.c`). El pack 491 sigue siendo de 4 a propósito: es el que
#   ya compró la gente. Ver `documentacion/MODO_ALEATORIO.md`.
MODOS_HEROE_SUELTOS = (1000210,)
#   Familias que se ACTIVAN de a varias: equipar una no saca a otra de la misma familia. Los modos
#   héroe se pueden combinar (su texto: *"se puede usar paralelamente con otros cupones del Modo
#   Héroe"*). Las Profecías también: el cliente mira las tres por separado (bits 2/4/8 de
#   `0x4FF830`), así que tener dos a la vez es algo que el propio juego contempla.
FAMILIAS_QUE_SE_SUMAN = ("hero_mode", "prophecy")
#   ★ (96) LAS AYUDAS DE CARRERA SE SUMAN (22-oct, reporte de Arminda en Discord: «¿se desactivó usar Auto
#   Impulsor y Diastone juntos? sólo se puede poner uno de nuevo; al activar Diastone se desactiva el Auto
#   Impulsor o el Juego automático»). Viven en la pestaña 0509, la familia «skin» del catálogo, que es un
#   cajón de sastre (pieles, piedras de ritmo, cupones dash, llaves, tickets…) y el server dejaba UNO por
#   familia: prender una ayuda sacaba a la otra de la base, y desde el arreglo de las «2 alas» (12-oct, en prod
#   el 16-oct) además se la apagaba al cliente en el momento (log de prod 22-oct 04:44: «1000999 reemplaza a
#   [1000659] (cat. 10): se le apagan al cliente»). Por EFECTO (`ItemEffect` de shop_lt), así entran también
#   sus packs y las versiones «Café». Una ayuda no saca a nadie ni la saca nadie; el resto de «skin» sigue igual.
#     17 Auto Impulsor · 1630 Juego automático · 525 Diastone · 271 Impulsor con Protección ·
#     40 Auto Inicio · 2482 Allcombo
#   `R2_AYUDAS_UNA_SOLA=1` = como antes (una sola).
AYUDAS_DE_CARRERA_EFECTOS = (() if os.environ.get("R2_AYUDAS_UNA_SOLA") == "1"
                             else (17, 1630, 525, 271, 40, 2482))

# ── ★★★ EL BONO DE LOS MODOS HÉROE — un renglón de EXP por modo activo (2026-09-23) ──────────────
#   ítem -> (bonustype, EXP fija). Los `bonustype` salen de `bonus.xml` del 2013, sección `<group>`
#   «영웅모드» = 41 · 42 · 43 · 53 (todos `requite="E"` = EXP). Qué número va con qué modo:
#   41/42/43 en el orden de los ítems (Espejo/Niebla/Locura) y 53 para Sin Piedras.
#   ✅ CONFIRMADO en pantalla (anonimo03, 24-sep, con `.autoplay` al 99%): los 4 renglones salen con el
#     ícono de su modo, y se cobraron los 600 (log 11:47:39: `+3057 = 1638 + 819 pareja + 600`).
#   ★ El MONTO lo decidió anonimo03 (23-sep): *"150 de exp a cada uno de los 4, para un total de 600"*.
#     Ningún cliente lo trae escrito. Es FIJO (el renglón viaja como número; ver MODIFICADORES_Y_RETOS).
#   Condición: el modo activo y la carrera terminada. Sin Piedras además pide `BONO_HEROE_PD_MIN`
#   de precisión (su texto: *"el bonus aumenta … contando desde el puntaje de 90%"*).
#   ★ (136) 1000210 Modo Aleatorio -> 54: renglón nuevo («Bono Modo Aleatorio», `heroe_aleatorio_crear.py`), en el
#     mismo grupo «영웅모드» de bonus.xml, 150 como los otros.
BONO_HEROE = {1000206: (41, 150), 1000207: (42, 150), 1000208: (43, 150), 1000328: (53, 150), 1000210: (54, 150)}
BONO_HEROE_PD_MIN = {1000328: 90}

# ── ★★★ LAS PROFECÍAS — «Profecía Ganador / Allcombo / 97%» (2026-09-24) ────────────────────────
#   Se activan en «Mi Casa» (como los modos héroe) y, si se cumple lo que profetizan, pagan EXP y
#   Rcoin al final. Texto del juego (`string_lt/item.csv`, efectos 797/798/799): *"Rcoin & Exp
#   serán dados como bono … Tu habilidad puede ser mostrada al hacer la acción antes de jugar …
#   Efecto de sonido te felicitará … Los efectos no se aplican en el Modo Cooperativo"*.
#   ★★★ LO QUE HACE EL CLIENTE SOLO (leído en el exe, `0x4FF830`):
#     · pregunta por los efectos 797/798/799 de cada asiento en la tabla del `FF80`
#       (`0x5285D0`) ⇒ sin `FF80` los demás no ven la Profecía de nadie;
#     · AL TERMINAR, para saber si se CUMPLIÓ, busca en SU fila del cartel (`cResult`, vtable
#       `0x87ED60` +0x34 -> `0x53A440` -> `0x534EA0`) el renglón 59 / 61 / 63 (bits 2/4/8) ⇒ el
#       festejo lo dispara el renglón de EXP que mandamos. El server decide; el cliente festeja.
#     · y no mira nada si `[0x9314C8]+0xC & 0x160` ([H] el modo de juego: el texto dice que en
#       cooperativo no aplica, pero ese bit NO está medido). El server no paga en cooperativo.
#   ítem -> (qué profetiza, bonustype EXP, bonustype Rcoin). Los tipos salen de `bonus.xml` del
#   2013: 59/61/63 `type="3"` (EXP, columna x=146) y 60/62/64 `type="1"` (Rcoin, x=640), Image 5
#   frames 77/78/79 — los mismos que Steam y el chino comentan `예고1등/예고올콤/예고97`.
PROFECIAS = {1000377: ("primero", 59, 60), 1000378: ("allcombo", 61, 62), 1000379: ("97", 63, 64)}
#   ✅ LOS MONTOS LOS DECIDIÓ ANONIMO03 (24-sep: *"está correcto"*) — ningún cliente los trae. Con la
#   forma que promete el texto: *"más bono en función al número de jugadores"* (Ganador) y
#   *"más bonos dependiendo de la dificultad de la canción"* (Allcombo y 97%).
#     qué -> ((EXP base, EXP por unidad), (Rcoin base, Rcoin por unidad))
#     unidad = cada RIVAL en la carrera (Ganador) · el NIVEL de la canción (Allcombo, 97%)
#   Ej.: ganar contra 5 = 100+250 EXP y 50+125 Rcoin; allcombo en una de nivel 8 = 260 / 130.
#   ⚠ El *"más bonos en tu canal con licencia"* del Ganador NO está: no hay canales con licencia.
PROFECIA_MONTO = {
    "primero":  ((100, 50), (50, 25)),
    "allcombo": ((100, 20), (50, 10)),
    "97":       ((50, 15), (25, 5)),
}
PROFECIA_PD_MIN = 97                    # «Profecía 97%»
#   ★ 05-nov, anonimo03: «profecías en 10». Desde la reubicación de niveles hay canciones de más de 10★ (Level 21..26,
#     `taller/importador2013/reubicar_niveles.py`); para el PAGO de «97%» y «allcombo» el nivel se topa acá
#     (Level 20 = 10★): una de 13★ paga como una de 10★.
PROFECIA_NIVEL_TOPE = 20
#   ★ Ganar SOLO no es ganar: en una carrera de uno siempre salís 1º. Hace falta al menos un rival
#     de verdad (con cuenta; los NPC de `.npc` no cuentan).
PROFECIA_GANADOR_MIN_JUGADORES = 2

# ── ★★★ LOS CUPONES DE PREMIO — «Cupón EXP Up» y «Cupón Coin Up» (2026-09-24) ──────────────────
#   Texto del juego (efectos 46/47): *"Si tienes este cupón en Mi Casa, obtendrás más EXP.
#   Utilízalo con otros cupones para un mayor efecto"* · *"incrementará tu recompensa de Rcoins"*.
#   ★ El cliente NO hace nada con los efectos 46/47 (ninguna consulta a `0x5285D0`, a diferencia de
#     los modos héroe o las Profecías): el premio es 100% del server — el renglón «bono de ítem»
#     de `bonus.xml` (`<group>` «아이템보너스»: 9 = EXP `type 3`, 10 = Rcoin `type 1`, mismo ícono).
#   ★★ NO SE ACTIVAN: TENERLOS ES TENERLOS ACTIVOS. Medido (anonimo03, 24-sep): en Mi Casa el cliente
#     no ofrece activarlos y al clickearlos NO manda nada (ni un `FF1A`). Lo dice el texto: *"Si
#     tienes este cupón en Mi Casa…"*. (La 1ª versión pedía activarlos como el Auto Impulsor y
#     por eso no cobraba nadie.) Siguen en su familia `coupon_buff`.
#     · EXP Up (30011): se vende por DÍAS (P3/P30). Tenerlo sin vencer = paga.
#     · Coin Up (1200033): se vende por CARGAS (packs x10…x300, que se abren al comprar). Gasta
#       UNA por carrera TERMINADA (el que no llega no cobra ni gasta), con el `FF6A` de las campanas.
#   ítem -> (qué, bonustype)
CUPONES_PREMIO = {30011: ("exp", 9), 1200033: ("rcoin", 10)}
#   ✅ EL PORCENTAJE LO DECIDIÓ ANONIMO03 (24-sep): +30% — ningún cliente lo trae. De lo que da la
#   carrera (EXP de la fila; Rcoin = `coin` + `FF28_BASECOIN`, lo que muestra el cartel).
CUPON_PREMIO_PORCIENTO = {"exp": 30, "rcoin": 30}
#   ★ EL BONO DE DERROTA (188, efecto 722 — el exe no lo consulta: también es todo server). Texto:
#     *"Obtendrá 200 Rpuntos adicionales como bonus cuando pierdes teniendo este cupón. No se puede
#     usar con otros cupones de Rpuntos-Up al mismo tiempo. No se aplica si tienes GOAL. No se
#     aplica en partidos en equipo y partidos de relevos."*  (Rpunto = EXP en este proyecto.)
#     ⇒ Paga si NO llegaste a la meta (`fallo` = sin GOAL) o perdiste el cooperativo, habiendo
#       jugado (combo o precisión > 0: el que se quedó quieto no cobra), fuera de equipo/relevo.
#       Y es EXCLUSIVO con el EXP Up: si paga éste, el EXP Up no.
#     Renglón 58 (`<group>` «OTL», `type 3` = EXP, ícono propio). El monto lo dice el texto: 200.
#   ítem -> (bonustype, EXP fija)
BONO_DERROTA = {188: (58, 200)}

# ── ★★★ LOS PACKS DE ESCAPARATE SE ABREN (`setitem="1"`) — 2026-09-23 ─────────────────────────────
#   Comprar un set entregaba el ítem de escaparate en vez de su contenido (le pasó a mucha gente en
#   prod). El contenido está en `servidor/tablas-cliente/setitem.txt`. Ver `catalogo.entregar_compra`.
#   ⚠ Y un set NUNCA cuenta como «ya lo tenés»: el que ya quedó con el escaparate de antes puede
#     volver a comprarlo y ahora sí recibir el contenido.
TIENDA_ABRE_SETS = True

# ── ★★★ LA TARJETA DE NOMBRE — `FF0C cola[14]` y `FF15 T1`, UN BYTE (2026-09-23) ────────────────
#   Los «Slot para Game id …»: el fondo del recuadro del apodo. El byte es el `index` de
#   `servidor/tablas-cliente/namecard.xml`. Medido:
#       FF0C  0x5E85B8 read(1) -> desc+0x4C -> 0x5B3301 -> sRoomUser+0x1E5
#       FF15  T1 -> 0x597960 -> el mismo sRoomUser+0x1E5
#       sala  0x592416 / 0x5987F5: nodo+0x1F5 -> el dibujo del nombre de `[0x93433C]`
#   ⚠ OJO, hay DOS objetos de tarjetas en el cliente: el de `[0x9342A0]` (el que busca `0x4826E0`)
#     queda VACÍO por un bug del arranque; el que dibuja el nombre es `[0x93433C]`, que es el que
#     recibe `NameCard.xml`. Ver `MARCOS_DE_ASIENTO.md` §6 (primero lo di por bug del cliente: la
#     búsqueda vacía era la del objeto que no dibuja).
#   ⇒ En False el byte vuelve a 0 = sin tarjeta, como viajó siempre.
TARJETA_DE_NOMBRE = True

# ── ★★★ EL TEXTO SOBRE LA CABEZA (FF0C, la string de `cola[4]`) — 2026-09-15 ──────────────────
#   ⛔ Al encender la joya del alma apareció **`(null)` sobre las cabezas**, donde antes no había
#     nada: el flag activa el dibujo de ese renglón y el renglón se queda sin texto.
#   ★★ El destino está medido: `0x5E8510` pasa esa string a `0x463380(str, dst, 0x49, f)`, que le
#     mide el largo y la trunca a un ancho de 0x49 ⇒ **es un texto que se DIBUJA**.
#   ⚠⚠ Meter texto **corre todo lo que viene detrás** en la cola, así que se inserta (no se
#     escribe en posición fija) y el banco vuelve a comprobar las CINCO anclas después.
#   ⏳ QUÉ VA AHÍ es todavía [NM]: la apuesta es el nombre del amigo del alma. Si sale otra cosa
#     —o sale en el lugar del círculo— la prueba lo dice en una corrida.
#   ⇒ En False se vuelve a la string vacía, que es como viajó siempre.
#   ⛔⛔ PROBADO EN PANTALLA: esa string es **el nombre del CÍRCULO (gremio)**, no el del amigo
#     del alma. Se dibuja como `<círculo> nick` al lado del personaje y arriba, en el slot —
#     exactamente como salió en la prueba (`<jugador50> jugador1`).
#   ★ Sirve igual, y mucho: **queda identificado el campo del círculo en el `FF0C`**, que el
#     proyecto no tenía. El día que se implementen los círculos, va acá.
#   ⇒ Queda en False: poner el nombre de un amigo del alma ahí es mostrar un gremio que no existe.
# ★★ 24-sep: ENCENDIDO con los círculos — `occ["texto_cabeza"]` = el nombre del círculo (salas.py).
FF0C_TEXTO_DE_CABEZA = True
# ★ 23-oct · LOS CRAYONES DE CÍRCULO (CRAYONES_MAZINO.md): el nombre del círculo de un jugador con su crayón de
#   círculo tildado viaja con una MARCA al principio ('^' + 'A'+color) y la dll (`circulo_color.c`) lo dibuja de ese
#   color. ⛔ Un cliente SIN esa dll muestra «^B» delante del nombre del círculo ⇒ la dll y esto van JUNTOS.
#   False = el nombre del círculo sin marca (todos en blanco, como siempre).
CRAYON_CIRCULO = True

# ── ★★ LOS CÍRCULOS (24-sep) — `circulos.py`, `documentacion/CIRCULOS_HALLAZGOS.md` ────────────────
#   Crear / unirse / echar / pasar el mando se hacía en la WEB de Softnyx (`/Circle/*.aspx`); acá se
#   hace con `.circulo …` en el chat. Los números son los de las reglas oficiales de esa web
#   (`CircleRulePopup.aspx`, archivada): «crear cuando tu nivel es sobre 10», «unirte cuando tu
#   nivel es mayor a 5», «hasta 10 jefes incluyendo al líder», «hasta 50 miembros», «el nombre no
#   debe exceder los 12 caracteres».
CIRCULOS = True                 # False = todos «sin círculo», como antes del 24-sep
CIRCULO_NIVEL_CREAR = 11
CIRCULO_NIVEL_UNIRSE = 6
CIRCULO_MAX_MIEMBROS = 50
CIRCULO_MAX_JEFES = 10          # contando al líder
CIRCULO_NOMBRE_MAX = 12
CIRCULO_AVISO_MAX = 56          # el aviso de la Mensajería (tope del CBT, [NM] en el 2013)
CIRCULO_CHAT_COLOR = 2          # color del chat del círculo (tabla 0x886290: 2 = verde, como la pestaña)
CIRCULO_GRACIA_SALIDA = 8.0     # s antes de avisar «cerró sesión» (un cambio de canal vuelve en ~1 s)
# Los bytes de rango del cliente (`cCircleInfoView`, 0x601090): los usa el FFD7 y la base.
CIRCULO_RANGO_LIDER = 0x5A
CIRCULO_RANGO_JEFE = 0x50
CIRCULO_RANGO_MIEMBRO = 0x0A
# ★★ LA ECONOMÍA (24-sep) — las dos tablas vienen HORNEADAS EN EL CLIENTE, no se inventan:
#   · el TOPE de EXP de cada nivel (`0x8874D0`, lo usa `GetCircleLevel` = `0x5FDB80`): el cliente
#     DEDUCE el nivel del tope que le mandamos en el `FFD4` (tope <= TOPES[n] -> nivel n; el centinela
#     0x7FFFFFF8 = nivel 10). La EXP se frena en el tope hasta que se paga «subir de nivel».
#   · el COSTO de subir, en dinero de círculo (`0x88722C`, lo dibuja el diálogo `0x5FA5C0`).
#   `probar_circulos.py` las compara contra el exe.
CIRCULO_TOPES = (10900000, 23450000, 36660000, 50530000, 65060000,       # nivel 1..5
                 80250000, 96100000, 112940000, 131440000)               # nivel 6..9
CIRCULO_TOPE_MAX = 0x7FFFFFF8   # nivel 10: sin tope
CIRCULO_COSTO_NIVEL = (10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 100000)  # desde nivel 1..9
# ★★ EL BALANCE (25-sep, anonimo03: *"objetivos más alcanzables, reales, según la economía en rcoin"*).
#   Los topes y los costos de arriba están HORNEADOS en el cliente (el nivel lo deduce del tope y el
#   costo lo muestra de su tabla) ⇒ lo que se ajusta es cuánto rinde cada Rcoin donado.
#   El original era 1 Rcoin = 1 EXP y 100 Rcoin = 1 dinero: medido en prod (respaldos 18 → 24-sep,
#   1.159 activos, `_trabajo/circulos/economia_rcoin_prod.py`) un activo junta ~1.000 Rcoin netos
#   por día (mediana; p75 3.800, p90 8.400) ⇒ un círculo mediano tardaba ~2 AÑOS en el nivel 2.
#   Con 150 / 40, simulado (sin contar lo que se gaste en la tienda):
#       círculo chico (5 × 1.500/día)   nivel 2 en 10 días · nivel 5 en 47 · nivel 10 en ~150
#       mediano       (8 × 2.000/día)   nivel 2 en  5 días · nivel 5 en 23 · nivel 10 en  ~72
#       grande        (20 × 4.000/día)  nivel 2 en  1 día  · nivel 5 en  7 · nivel 10 en  ~17
#   ⚠ El recibo que dibuja el CLIENTE al donar lo calcula él a 1:1 y /100 (`0x5E3B70`): los números
#     de verdad le llegan aparte, en una línea de SERVER (`circulos.donar`).
# ★ SUBIR DE NIVEL (FFE1, 25-sep): los regalos de `cirlcelevelbonus.xml` — «círculo ítem (30 días) xN»
#   por el nivel al que se llega. Van al INVENTARIO del círculo (muebles al azar de la tienda).
CIRCULO_REGALOS_POR_NIVEL = {2: 1, 3: 1, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4, 9: 5, 10: 6}
CIRCULO_REGALO_DIAS = 30
# ★★ EL BONO DE CÍRCULO en el cartel del resultado (25-sep): el renglón `bonustype 70` de `bonus.xml`
#   («써클보너스 유저경험치» = bono de círculo, EXP del usuario, columna de EXP). `cirlcelevelbonus.xml`
#   da `expbonus` = el nivel (1..10), que el panel muestra «Bono exp Lv N» ⇒ N % de la EXP de la
#   carrera × `CIRCULO_BONO_EXP_FACTOR` (1 = el original). 0 = apagado.
CIRCULO_BONO_TIPO_EXP = 70
CIRCULO_BONO_EXP_FACTOR = 1
# ⛔⛔ 29-sep — VUELVE EL ORIGINAL DEL EXE (anonimo03). Con 150/40 los círculos llenaron todas las barras en 4
#   días (Mazino: 1,87 M Rcoin donados = 131 M de EXP, nivel 10) y ya no quedaba a qué apuntar. Se bajan
#   a nivel 2, se les DEVUELVE lo donado (`herramientas/circulos_devolucion.py`) y la tasa vuelve a 1:1,
#   que además es lo que el cliente dibuja en su propio recibo (`0x5E3B70`). La tabla de arriba del 25-sep
#   queda como registro de por qué se había subido.
CIRCULO_EXP_POR_RCOIN        = 1     # EXP de círculo por cada Rcoin donado (el original; fue 150 del 25 al 29-sep)
CIRCULO_DINERO_POR_100_RCOIN = 1     # dinero de círculo por cada 100 Rcoin donados (el original; fue 40)

# ── ✅ EL REGISTRO DEL ANILLO (`FF45`): el nombre de la pareja y la FECHA en la mochila ─────────
#   Pedido por anonimo03 el 2026-09-12: *"cuando se casa se genera un ítem del anillo usado, que sirve
#   para recordar el aniversario —activo— o como recuerdo cuando la pareja rompe —inactivo—"*.
#   ★ El formato y la fecha están MEDIDOS (`PAREJA_PENDIENTES_AGENTE.md` §3), y hasta hoy
#     contestábamos una lista VACÍA: el ack era válido, sólo que no traía nada.
#   ⚠ En False se vuelve al ack vacío de antes, que nunca rompió nada.
PAREJA_REGISTRO_ANILLOS = True

# ── ✅ EL ANILLO TAMBIÉN AL QUE ACEPTA ─────────────────────────────────────────────────────────
#   ⛔ MEDIDO el 2026-09-12: el que PROPUSO tenía los 3 anillos y la que ACEPTÓ **ninguno** ⇒ su
#   mochila no tenía de dónde colgar el recuerdo, y el aniversario sólo lo veía uno de los dos.
#   ★ No se le saca al que propuso: el anillo **se queda** como recuerdo (regla 5 de la tienda,
#     *"no se puede reutilizar"*, la cumple el `estado` de la tabla `anillos`, no borrar el ítem).
#     Si lo borráramos, borraríamos el recuerdo que este mismo trabajo viene a crear.
PAREJA_ANILLO_AL_QUE_ACEPTA = True

# ── ✅ EL CORAZÓN (Y EL SUSURRO) DE LA LÍNEA «MI PAREJA» ───────────────────────────────────────
#   ★★★★★ MEDIDO el 2026-09-12: la fila de la pareja se crea con **`0x45FD50`** (`0x45ef65`), que
#   es **el constructor de entrada de AMIGO** — el mismo que `lobby_social._servidor_de` ya tenía
#   documentado: *"inicializa ese campo justo en 0xFFFF"* = **desconectado**.
#   ⇒ La fila **nace apagada**, y el `FF4A` no trae ningún campo que la cambie. El paquete que
#     escribe la presencia de una entrada es el de amigos, y la pareja no está en esa lista ⇒
#     **nadie se la escribía nunca**.
#   ★ Con esto se le manda el `FF40/0x04` («fulano se movió») **de la pareja**, que lleva
#     `[u16 servidor][u16 sala]` y cuyo bit `0x10` deja el estado en 15, *"uno de los siete valores
#     que destraban el susurro"* — justo lo que anonimo03 describió.
#   ⚠ En False se vuelve a la fila siempre apagada, que es el estado anterior y no rompe nada.
PAREJA_PRESENCIA = True

# ── 💞 EL BONO DE PAREJA EN LA PARTIDA (el renglón de bonus del `FF28`) ────────────────────────
#   ★★★★★ MEDIDO EN EL 2013, no copiado. La fila del cartel termina en un `u16` que nosotros
#   mandábamos en 0 y llamábamos `inner_count`: **es la cantidad de RENGLONES DE BONUS** que
#   vienen atrás, de 4 bytes cada uno. El bucle existe en nuestro handler (`0x5E8C40`):
#
#       0x5e8dfa  lee 2  -> M          0x5e8e19  lee 2 -> bonustype
#       0x5e8e08  jae    -> corta      0x5e8e27  lee 2 -> valor
#                                      0x5e8e35  call 0x471F00 = al vector de ESE jugador
#
#   ⇒ Con M=0 la fila mide lo de siempre y el stream sigue alineado solo. Por eso nunca rompió
#     nada: mandábamos la lista vacía y el cliente la leía como vacía.
#
#   ★★ Y LOS DOS NÚMEROS DEL ANILLO SALEN DE **NUESTRO** `rnr_script/bonus.xml`:
#
#       <subgroup Image="6" frame="14" commetn="couple_반지">    ← 반지 = ANILLO
#         <bonus type="5"  requite="M"/>      ← M = dinero
#         <bonus type="32" requite="E"/>      ← E = exp
#
#   ⚠⚠ **HAY TRES GRUPOS QUE HABLAN DE PAREJA Y NO SON LO MISMO** (aviso de anonimo03: *"no confundir
#     tipos de bonos, buscá el que justamente ACTIVA tener pareja"*). Leyendo el archivo en cp949,
#     que es lo que lo vuelve legible:
#
#       couple_반지      = couple_**ANILLO**        frame 14   ->  5 (M) · 32 (E)   ← ★ ÉSTE
#       love_커플아이템   = love_**ítem** de pareja   frame 18   -> 11 (E) · 12 (M)
#       커플펫           = **mascota** de pareja     frame 11   -> 44 (E)
#
#     ⇒ El que se activa por **tener pareja** es el del ANILLO. Los otros dos son un ítem
#       consumible y una mascota: mandar sus números daría el ícono equivocado en el cartel.
#
#   ⛔ **ACÁ EL CBT SE EQUIVOCA PARA EL 2013.** Allá anotaron que el 32 era *"punto (Rpoint)"*,
#     porque su tabla traía un atributo `type` numérico. La nuestra usa `requite` con LETRAS, y
#     el cliente las mapea así (`0x54428D`): `'M'`→0 · `'T'`→2 · cualquier otra→1.
#     ⇒ En el 2013 el **32 es EXP**, no punto. Se lee de la tabla, no se deduce del CBT.
#
#   ⚠ **El ícono se dibuja aunque el valor sea 0** (el CBT lo midió) ⇒ un bono en 0 deja un "+0"
#     colgado en el cartel. Por eso cada uno se manda **sólo si su porcentaje es > 0**.
PAREJA_BONO_TIPO_RCOIN = 5       # `requite="M"` en bonus.xml
PAREJA_BONO_TIPO_EXP   = 32      # `requite="E"`
#   ★★ ¿PAGA CADA ANILLO UNA COSA DISTINTA? **NO** — preguntado por anonimo03 y contestado por el
#     archivo, no por mí: los atributos que existen en TODO `ring.txt` son
#     `Index · ChargeId · MsgId · RoomFx · SlotBackId · Sprite · Frame · EffectRand · Kick · Id`,
#     y **ninguno menciona bonus, exp ni coin**. Los dos bonustype cuelgan del GRUPO
#     `couple_반지` entero ⇒ **los 20 anillos de pareja pagan lo mismo, y pagan las dos cosas.**
# ── ★★★ EL BONO DEL AMIGO DEL ALMA — 2026-09-15 ────────────────────────────────────────────────
#   Lo pide la ayuda del juego: *"**Bonus de Amigo del Alma**: juega con tus amigos del alma para
#   que tú y ellos puedan recibir Rcoin y Rpoint adicionales"*.
#
#   ★★ Y LOS ÍCONOS ESTÁN EN LA TABLA DEL CLIENTE (`bonus.xml`), **[M]**:
#       bonustype 132..136 = `우정보너스 레벨1..5` = "bono de amistad, niveles 1 a 5"
#       los cinco con `type="1"` —el MISMO tipo que el bonustype 5, el Rcoin de la pareja— y en la
#       misma posición con frames consecutivos ⇒ es **un ícono con cinco caras**, no cinco bonos.
#
#   ⚠⚠ EL NIVEL ES NUESTRO. La tabla trae cinco caras y **no dice qué las elige**. Se usa *cuántos
#     amigos del alma llegaron al cartel*, que es lo que sugiere la ayuda (*"si tienes más amigos
#     del alma, las joyas también aumentan"*). Con el tope del cliente en 2, hoy sólo se alcanzan
#     los niveles 1 y 2; los otros tres quedan para cuando se sepa de dónde salen.
#   ⏳ Y falta el **Rpoint** que menciona la ayuda: no encontré su bonustype. Hoy sólo va el Rcoin,
#     que es el que está medido por el `type="1"`.
# ── ★★★ EL BONO DE LA MASCOTA GORILA — 2026-09-15 ────────────────────────────────────────────
#   ⛔ Lo preguntó anonimo03: *"si podemos canjear la mascota de la moneda gorila pero no comprobé si
#     su bono se está pagando"*. **No se pagaba.** En todo el server había una sola mención a
#     esos dos ids, y era la del canje en la tienda: el jugador gastaba sus monedas, se ponía la
#     mascota y no cobraba un peso de más.
#
#   ★★ Y LOS PORCENTAJES NO SON NUESTROS: los dice el propio juego, en la descripción del ítem
#     (`string_lt/item.csv` vía el `ItemEffect` de `shop_lt.txt`), palabra por palabra:
#         600164 «Gorila Verde»   -> *"Recibe **15%** adicional en Exp y Rcoins equipando este ítem"*
#         600178 «Gorila Rosado»  -> *"Recibe **30%** adicional…"*
#   ⇒ Cambiarlos acá es cambiar lo que la tienda le promete al jugador. Si se tocan, hay que
#     tocar también el texto del cliente — o el ítem pasa a mentir.
#
#   ⚠ **EQUIPADA, no en el inventario**: el texto dice *"equipando este ítem"*.
#   ⚠ `{}` apaga el bono por completo.
MASCOTA_GORILA_BONO = {600164: 0.15, 600178: 0.30}

ALMA_BONO_TIPO_BASE  = 131     # 131 + nivel = el bonustype (132..136)
ALMA_BONO_NIVEL_MAX  = 5
ALMA_BONO_RCOIN      = 0.25    # +25 % de (rcoin de la pista + base). 0 = apagado

PAREJA_BONO_RCOIN = 0.5          # +50 % de (rcoin de la pista + base). 0 = apagado
PAREJA_BONO_EXP   = 0.5          # +50 % de la exp. ★ Confirmado en pantalla que el de rcoin sale


# ── ★★★ `.autoplay` — EL AUTOPLAY ESCONDIDO, PRENDIDO DESDE EL SERVER (2026-09-24) ───────────────
#   Pedido de anonimo03: *"¿esto se puede controlar totalmente serverside con comando gm?"* — para
#   probar los bonos que piden precisión (modos héroe, Profecías, allcombo) sin saber jugar.
#   El cliente trae dos autoplays: el de la tienda (estado 0x19, FRENADO: cada nota vale 0%) y el
#   ESCONDIDO (estado 0x0A, el ítem de carrera «오토»), que corre solo y da 99 por nota. Medido con
#   `herramientas/autoplay.py`: cada uno dura 6,0 s y la precisión queda en 99,00%.
#   ★ CÓMO LO PRENDE EL SERVER: cada vez que el cliente prende un ítem de carrera lo avisa con un
#     `FF4E sub=0x01 A=(destino<<24)|(emisor<<16)|(tipo<<8)` (medido: `A=0x02020A00 B=0x64` desde
#     el asiento 2), y el handler que lo recibe NO filtra su propio asiento (ver el "sin eco al
#     emisor" de `lobby.py`). ⇒ el server le manda ESE aviso con su propio asiento y el cliente se
#     lo aplica a sí mismo. Sin exe, sin DLL, sin Frida.
#   ★ CUÁNDO: a ritmo FIJO, uno cada `AUTOPLAY_CADA` s, un poco antes de que se apague el anterior.
#     ⛔ La 1ª versión esperaba una "confirmación": el cliente, cuando ÉL prende un ítem, lo avisa
#       por red — y se suponía que también lo haría con el que le manda el server. **No lo hace**
#       (medido 24-sep 11:31, prueba de anonimo03: `0 autoplays confirmados` en 2 carreras). Sin
#       confirmación el server reintentaba cada 1 s, y el cliente **aplicaba cada uno** (aunque el
#       anterior siguiera activo) ⇒ anonimo03: *"se activa varias veces cada segundo, se escucha mucho
#       spam de su activación"*. ⇒ que el cliente acepte uno encima del otro es justo lo que deja
#       pedirlo ANTES de que se apague, sin huecos.
#     ⚠ [H] que el de encima RENUEVE los 6 s (`0x5092D0`, con el estado ya puesto, reescribe el
#       nodo en vez de rechazar). Si no los renovara habría huecos de ~5 s: se ve en la precisión
#       del cartel (con el de Frida quedó en 99,00%).
#   ⚠ Es una trampa a propósito: por eso es de GM (`COMANDOS_GM`) y tiene su interruptor.
AUTOPLAY_GM = True
AUTOPLAY_TIPO = 0x0A              # el escondido (사용_오토). El 0x19 es el de la tienda, el frenado
AUTOPLAY_B = 0x64                 # el `B` que manda el propio cliente (medido)
AUTOPLAY_DURA = 6.0               # s que dura cada uno (medido: 360 cuadros, 6,0 s en 47 de 47)
AUTOPLAY_CADA = 5.5               # s entre pedidos: medio segundo ANTES de que se apague el anterior


# ── ★★ EL RÉCORD DEL JUGADOR y LAS MEDALLAS (2026-09-24) ──────────────────────────────────────────
#   El mapa entero en `documentacion/MEDALLAS_Y_RECORD.md`. En corto:
#   · El cliente trae 24 medallas en 6 escaleras (`tablas-cliente/medal_lt.txt`) y decide SOLO cuáles
#     tenés: compara un contador por escalera con el `Value` de cada una. Los contadores le llegan en
#     el `FF77` (el perfil), en el bloque de 7 `u32` = [medalla puesta][escalera 1..6].
#   · Nosotros los CONTAMOS al cobrar cada carrera (`medallas.contar_carrera`) y los guardamos en la
#     tabla `record`. Escaleras: 1 = mejor EXP de UNA partida · 2 = mejores Rcoin de UNA partida
#     (anonimo03 24-sep: *"por las campanas o por evento se llegaría"*) · 3 ganadas · 4 perdidas ·
#     5 veces con 97%+ · 6 allcombos.
RECORD_Y_MEDALLAS = True
#   Qué contador va en cada escalera (el índice es `MedalID // 100`).
RECORD_ESCALERAS = {1: "exp_max", 2: "rcoin_max", 3: "ganadas", 4: "perdidas", 5: "pd97", 6: "allcombo"}
#   ⚠ En individual, la carrera cuenta como ganada/perdida sólo si corrieron al menos éstos (con
#     cuenta). Solo, «ganar» es terminar: sería regalar la escalera 3. Mismo criterio que la
#     Profecía del ganador (`PROFECIA_GANADOR_MIN_JUGADORES`). El cooperativo y los equipos cuentan
#     siempre: ahí se puede perder de verdad.
RECORD_MIN_JUGADORES = 2
RECORD_PD_MIN = 97                 # la escalera 5 («97 más de precisión»)
#   ★ QUÉ COLUMNA DEL PERFIL ES CUÁL — ✅ CONFIRMADO EN PANTALLA (anonimo03, 24-sep, `.record sonda`):
#     mandados 11/22/33 salió «Record: 11 G 22 E 33 P», «Ranking 7», «Tasa de Victorias 16 %»
#     (= 11/66). ⇒ @9 = G (ganadas) · @17 = E (empates) · @13 = P (perdidas). En carrera no hay
#     empate: la E queda en 0.
RECORD_COLUMNAS_FF77 = {9: "ganadas", 13: "perdidas", 17: "empates"}
#   El cartel «¡Medalla adquirida!» (`FFD1`) al cruzar un escalón, en el mismo cobro.
MEDALLA_AVISO = True
#   ★ LA MEDALLA ARRIBA DE LA CABEZA (FF0C). Medido 24-sep leyendo al consumidor:
#       0x5E866B read(1) -> cola[27] -> desc+0x45 -> nodo+0xD1   (la «bandera»: 0xFF = ninguna)
#       0x5E867C read(4) -> cola[28..31] -> desc+0x48 (`0x5E8A52`) -> escena+0x208 (`0x5B32DD`)
#       0x59ED53 mov ecx,[eax+0x208] -> 0x467820 = el NOMBRE de la medalla en medal_lt -> se dibuja
#     ⇒ el id va en `cola[28..31]` — ✅ MEDIDO con Frida en el cliente vivo (24-sep 18:17): con el id
#       en 29 el cliente buscaba la medalla 25601 (`01 64 00 00`). ⛔ O sea que el «cola[28]» del
#       15-sep NO era una bandera: era el byte bajo del ID. Con 1/3/4 ahí el cliente buscaba las
#       medallas 1, 3 y 4, que no existen ⇒ «(null)». La bandera de verdad es `cola[27]`.
#   ⚠ [NM] qué hace la bandera `cola[27]`: hoy viaja en 0. Se barre con
#     `.record cabeza N` (no toca la base; `off` vuelve a lo normal).
FF0C_MEDALLA = True
# ★ La MARCA y el NIVEL del círculo en la tarjeta de la sala: `FF0C cola[32..35]` / `cola[36..39]`
#   (25-sep, `paquetes.build_ff0c_2013_real`). False = como antes (en cero: «1 <círculo>», sin emblema).
FF0C_MARCA_CIRCULO = True
# ★ El COLOR DEL APODO (los lápices 1000349..1000354): `FF0C cola[13]` y `FF15 #14` (25-sep).
FF0C_COLOR_APODO = True
# ★★ (140) 30-oct · LA CEREMONIA DE ENTRAR A LA SALA de los demás: `FF0C cola[17]` = el `Index` de su fila
#   `Location="Room"` de `specialentrance.xml` (`0x5E85D7` -> desc+0x43 -> `sRoomUser+0x163` -> `0x5B2260`, que la
#   reproduce cuando el recién llegado termina de aparecer), con el bit 0x80 prendido (`0x5E87CC`: sin él el cliente lo
#   borra). Va SÓLO en el FF0C del que entra (`difundir_ocupante`):
#   en la lista de los que ya estaban, en cero, o el que llega vería la entrada de todos. False = como antes.
#   Ver `documentacion/CEREMONIAS_AURAS_Y_FLOTAR.md` §7.
FF0C_ENTRADA_A_SALA = True
#   ★ EL AVISO A TODO EL SERVER al ganar una medalla: `FF40` subtipo 0x36 (el cliente arma la línea
#     «<apodo> usuario <medalla> medallas adquirida»). anonimo03: *"creo que el servidor mandaba un mensaje
#     global… no recuerdo si era en todas"*. En la tabla del cliente sólo las 6 difíciles (x03) traen
#     `NoticeImage` ⇒ por defecto sólo ésas.   "dificiles" · "todas" · None (apagado)
MEDALLA_AVISO_GLOBAL = "dificiles"

# ═══ LA PRESENTACIÓN PERSONAL y el cartel de cada entrada (29-sep) — `presentacion.py` ════════════
#   El cartel «Hemos añadido Buscar amigos… ¿Desea escribirla ahora?» salía en CADA entrada porque la
#   letra de «Buscar amigos» del `FF03` iba en 0 y al `FF94` no le contestábamos nunca. Leído del exe:
#   `0x4C07FE` (el cartel), `0x5ED8B0` (la letra en el FF03), `0x5E0FA0` (la respuesta del FF94).
#   Ver `documentacion/PRESENTACION_PERSONAL.md`.
#   Contestar el `FF94` (tipos 3 = registrar · 4 = cambiar la letra · 6 = editar). False = como antes.
PRESENTACION_CONTESTA = True
#   La letra + edad + texto en la cola del `FF03` (tras la 2ª lista de inventario). False = el 0 de antes
#   (⇒ el cartel vuelve a salir en cada entrada).
PRESENTACION_EN_FF03 = True
#   Dónde, contado desde el final de la 2ª lista de inventario: 4 contadores en 0, 4 u32, 3 u8 y un u32
#   (`0x5ED4AF`..`0x5ED8A2`) = 27. ★ Cruzado con `GACHA_PERSONAJES_OFF` (45, MEDIDO): 27 + 3 + 15 = 45.
PRESENTACION_OFF_FF03 = 27
#   La presentación de OTRO en su ficha (`FF77` cola: string 2 = el texto, +2 = la edad). ⏳ [D] leído
#   del exe (`0x44DE25` los dibuja de `cAccount+0x436/+0x4D4`), se confirma en pantalla.
PRESENTACION_EN_FF77 = True
#   ★ 12-oct «MIS PREFERIDOS» EN EL PERFIL (anonimo03: «añadí ítems al carrito y deberían poblarse en Mis preferidos, por
#   si un amigo inspecciona esa parte del perfil, pueda regalarse ese ítem desde ese mismo recuadro»). La lista del
#   `FF77` (@54) es la grilla de la pestaña «Mis Preferidos» del perfil (medido en pantalla: salía la ropa puesta, y al
#   mirar a OTRO cada casilla trae su botón «Regalo»). El mini char NO la usa (se viste con las 6 ranuras de @30).
#   True = la lista del carrito (`preferidos_tienda`) del que se mira · False = la ropa puesta, como antes.
PERFIL_LISTA_PREFERIDOS = True
#   ★ 12-oct (anonimo03: «le regalé a jugador5 lo que tenía en sus preferidos y sigue apareciendo ahí»). El cliente NO lo saca
#   solo: lo único que borra de su lista es la respuesta al FF70 (`0x48B0A0`, un solo llamador). Lo hace el server: al
#   regalar con éxito, el ítem sale del carrito del que lo recibe (y si está conectado, le llega su lista nueva por FF71,
#   sin cartel). False = queda en el carrito, como el juego de fábrica.
REGALO_SACA_DE_PREFERIDOS = True
#   ★ 28-oct (132) EL CARRITO DE LA TIENDA (anonimo03: «comprar todo» desde la tira del carrito, `tienda.c` de la d3d9): lo
#   COMPRADO (FF2A/FF50 con éxito) sale del carrito del que lo compró, y le llega su lista nueva por FF71 (sin cartel):
#   la tira se vacía sola, en vivo. Vale también para la compra de a una. False = queda en el carrito, como de fábrica.
COMPRA_SACA_DE_PREFERIDOS = True
#   ★ 28-oct (132) anonimo03: «enviar regalo… lo enviado debe cumplir la lista de F o M». Un regalo de chica a un chico (o
#   al revés) se rechaza con el cartel de fábrica «%s no puede usar este ítem» (res 4). El sexo de la prenda:
#   `shop_catalog.sexo_de`. False = se regala cualquier cosa a cualquiera, como antes.
REGALO_MISMO_SEXO = True

# ★ 12-oct «INVITAR A LOS DEL VESTÍBULO» (`FF52`, `invitacion.py`): el anfitrión invita y a los del lobby de su canal
#   les sale «%d Número (%s) Sala le ha enviado una invitación» con OK para entrar. En prod caía en «SIN handler»
#   (5.625 en 12 días). False = sólo se le contesta «enviada» al que invita, sin difundir nada.
INVITAR_VESTIBULO = True
#   ★ y «Invitar a un amigo a mi sala» (`FF40 0x07`, `invitacion.atender_amigo`): al amigo le sale «%s le ha enviado una
#   invitación» con OK para unirse. 608 «SIN handler» en prod en 12 días. False = «no puede ser invitado».
INVITAR_AMIGO = True

# ★ 12-oct «INGRESO RÁPIDO» (`FF72`, `entrada_rapida.py`): una sala al azar de su canal, esperando, con lugar, sin clave
#   y del modo y la licencia que marcó en «Configuraciones de ingreso rápido»; entra por el FF11 de siempre. Si no hay,
#   «No hay salas disponibles. ¿Desea crear una?». 1.712 «SIN handler» en prod en 12 días. False = siempre ese cartel.
ENTRADA_RAPIDA = True

# ★ 12-oct LA TRANSMISIÓN AL ESPECTADOR (`FF98`, `espectador_datos.py`): lo que los corredores mandan «para el que mira»
#   (los eventos de su carrera, ofuscados con el magic) se descifra y se le pasa EN CLARO a los espectadores de la sala.
#   Caía en «SIN handler» (247.510 en 12 días). False = se cuenta y se tira, como antes.
ESPECTADOR_DATOS = True
# ★ 12-oct «TODO CON EL MISMO RETRASO» (anonimo03: «o todo en vivo o todo, absolutamente todo, con el mismo delay, para que
#   tenga coherencia»): el que mira ve la carrera REPRODUCIDA desde el FF98 (con las teclas reales de cada corredor:
#   combos, golpes, tropiezos), ~0,75 s atrás (la dll: `transmision.c`). Para que nada le llegue antes, al que mira ya
#   NO se le releva en vivo el FF4E de un corredor que le está mandando su FF98 en esta carrera (si no, el impulsor
#   llegaba antes y DOS veces: `0x4FCAD0` no tiene filtro de repetidos). Un corredor sin FF98 sigue yendo en vivo, de
#   respaldo (si no, se le quedaría congelado). False = como antes: el FF4E también en vivo a los que miran.
# ★ 17-oct · False: el que mira va «EN VIVO, como un corredor más» (anonimo03: «el espectador tiene que ver las posiciones e
#   impulsores como los ven los corredores») — la dll con `[transmision] en_vivo=1` ignora el FF98 y mueve a todos en
#   piloto con este FF4E en vivo, igual que el juego de un corredor. ⚠ Va JUNTO con esa dll: con una dll diferida
#   (en_vivo=0) el impulsor le llegaría dos veces. True = lo diferido del 12-oct.
ESPECTADOR_DIFERIDO = os.environ.get("R2_ESPECTADOR_DIFERIDO") == "1"
#   El tipo 6 (editar una presentación ya registrada) en el original pedía el «vale de cambio de
#   presentación» (자기소개 변경권, resultado 8 si no lo tenías). Acá es gratis: no existe el ítem.
PRESENTACION_CAMBIO_GRATIS = True

# ═══ EL PICKER (29-sep) — `picker.py`, `documentacion/PICKER_SISTEMA.md` ═══════════════════════════
#   Las PREFERIDAS se guardan (FF138/FF13A) y vuelven al entrar (FF137). False = el FF137 vacío de antes.
PICKER_PREFERIDAS = True
#   «Mi record» por canción en el FF139 (mejor combo, precisión entera, veces). False = todo en 0, como antes.
PICKER_RECORD = True
#   El byte B del FF139 (dibuja el cuadro 0x1E de music_select_host02.spr). ⏳ [NM] qué es: se prende con
#   el ALL COMBO de esa canción como primera hipótesis; confirmarlo en pantalla. None = siempre 0.
PICKER_FF139_FLAG = "allcombo"
#   ★ LAS MILÉSIMAS de «Mi record» (29-sep): 2 B más AL FINAL del FF139 (0..999). El exe con los parches de
#   `herramientas/record_decimales.py` dibuja «94.354»; un exe viejo las ignora (lee sus 19 B y listo).
#   Van sólo si hay récord y la precisión es < 100. False = el FF139 de 19 B de siempre.
PICKER_RECORD_DECIMALES = True
#   ★ TOP 5 RANK (09-oct, `documentacion/TOP5_RANK.md`): el ranking de la canción viaja PEGADO al FF139 (detrás
#   de las milésimas, que entonces van SIEMPRE: 0xFFFF = «sin decimales»). Lo lee la d3d9 (top5.c) y lo muestra
#   el botón «TOP 5 RANK» del picker. Un cliente sin la dll lee sus 21 B y el resto lo ignora.
#   False = el FF139 de siempre. `PICKER_TOP5_N` = cuántos van (la ventana muestra 5 y se corre con la ruedita).
PICKER_TOP5 = True
PICKER_TOP5_N = 10
#   La POPULARIDAD: jugadas TERMINADAS por canción en los últimos N días. El «cambio» (flechas) es contra
#   la misma cuenta corrida un día. Se recalcula en lote cada `PICKER_POPULAR_CADA` segundos (VPS chico).
PICKER_POPULAR_DIAS = 7
PICKER_POPULAR_CADA = 600
#   Cuántas canciones van en el FF13B (el orden «popular» del cliente y el TOP 20). Las que no, «-° lugar».
PICKER_POPULAR_TOPE = 500
#   Las MANERAS DE LISTA: guardar el modo de la sala (FF1C tipo 0 una · 6 en orden · 5 aleatorio ·
#   0x1F TOP 20 · 0x20 NUEVOS 20) y SORTEAR en el START los tres al azar. False = como antes (el START
#   usa la última canción elegida, y el tipo 1 —que también es TILDAR una casilla— la cambia).
PICKER_MODOS = True
#   ⚠ El cliente manda un tipo 5 SOLO, pegado a nuestro `FF1C 0x1F` de «construir el picker» (medido 29-sep,
#   log local 11:29:41/11:29:44). Ése no es el anfitrión eligiendo Aleatorio: dentro de esta ventana no
#   cambia el modo de una sala que ya tiene uno.
PICKER_FF1C_AUTO_S = 5.0
#   ★ EL CARTEL DE LA SALA en los modos al azar (29-sep, anonimo03: el invitado seguía viendo «Skyline» con el
#   anfitrión en ALEATORIA). El invitado dibuja SIEMPRE la canción de la sala (su pestaña está clavada en 4,
#   `0x5BEAD9`), y la canción 0 del `music_lt.txt` ES «Aleatoria» (random_chobo.bmp). ⇒ En Aleatorio/TOP 20/
#   NUEVOS 20 la canción de la sala pasa a 0 y se le avisa a la sala; al volver, a cada uno se le repone el
#   cartel del MODO (anfitrión: 5 / 0x1F / 0x20 = su pestaña 1/2/3, medido `0x5CDE65`/`0x5CDF98`/`0x5CDFB1`;
#   invitado: 5 = SetMusic(0)). False = como antes (queda la última canción elegida).
PICKER_CARTEL_SALA = True
#   ★★ (119) …PERO EN COOPERATIVO NO (26-oct, la sala 9 de prod del 24-oct: «Elija una música» y había que cambiar de
#   modo y volver). El cooperativo no tiene selector: el server sortea las 3. Su manera de lista es el `0x1F` (TOP 20,
#   [sel+0x48]=2, EXENTO del gate `0x5BE320`: «anfitrión · +0x48 ∉ {2,3} · 0 tildadas ⇒ texto 98»). Reponer el cartel
#   de la sala —«aleatorio» si se creó en un modo normal— le dejaba al anfitrión +0x48=1 en cada vuelta (medido), y el
#   que hereda la sala pierde las tildadas (941 → 0, medido 3 veces) ⇒ el cartel. Cambiar de modo y volver lo
#   destrababa porque el FF4B del cooperativo manda el `0x1F`. True = en cooperativo no se repone nada (queda el 0x1F
#   de «construir el picker»); `R2_COOP_CARTEL_SALA=1` = como antes. `COOP_ELIJA_UNA_MUSICA.md`.
COOP_SIN_CARTEL_SALA = os.environ.get("R2_COOP_CARTEL_SALA") != "1"

# ★ LAS CAMPANAS Y LAS POSICIONES AL QUE ENTRA, DETRÁS DEL `FF0C` (29-sep). Se mandaban en el `FF13`, 2 s antes
#   de que el cliente tuviera a los ocupantes: el `FFF5` los busca en `cRoom+0x9C` y si no están lo ignora
#   (`0x587AC0`) ⇒ las dos campanas de un mismo jugador caían juntas y se veía una sola. False = en el FF13.
CAMPANA_TRAS_FF0C = True
# ★★★ LAS CAMPANAS VIAJAN EN EL `FF13` (29-sep, el camino NATIVO). La cola del FF13 trae +5..+36 = [item][x][z][rot]
#   de la campana de oro y de la de plata, y el cliente las planta SOLO, sin la animación de tocarla y en el punto
#   exacto (`0x59DEC0` -> `0x444260` flag 0). anonimo03: *"al entrar se ve la animación de tocar campana"* — era nuestro
#   re-plantar con el paquete de TOCARLA. False = el truco de antes (FFF5 + FFA9/FFC3 tras el FF0C, con animación).
CAMPANA_EN_FF13 = True

# ═══ LA TIRA DE ANUNCIOS de arriba del lobby (29-sep) — `tira.py`, `documentacion/TIRA_DE_ANUNCIOS.md` ═══
#   El `FFBF` (cTicker): la tira que pasa arriba del lobby. Se manda al entrar y al cambiar de canal, y a TODOS
#   cuando un GM la cambia con `.tira` (el cliente la reemplaza entera: sirve EN VIVO). False = no se manda nada.
TIRA_ACTIVA = True
#   Largo de CADA texto, y el TOTAL de la tira (textos + 9 espacios entre uno y otro): el cliente los junta en UN
#   buffer de ~2.450 B (`0x931AF0` hasta el siguiente global). Se deja margen.
TIRA_TEXTO_MAX = 300
TIRA_TOTAL_MAX = 1800

# ═══ «ENVIAR REGALO» de la tienda (12-oct) — `regalo.py`, `documentacion/REGALO.md` ═══
#   El FF53 viaja cifrado en un FF4F: se abre, se le cobra al que regala y el ítem va al inventario del otro.
#   False = el sobre se ignora (como antes: el cliente se queda esperando la respuesta).
REGALO_ACTIVO = True
#   ★ El aviso «Ha recibido [ítem] de X» (el popup CELESTE del FF54, con la imagen del ítem): en vivo si está conectado,
#   si no al entrar al lobby. False = el popup amarillo del FFCE («Premios de Evento han llegado»), sin decir quién.
REGALO_AVISOS = True

# ★ 15-oct · LA MISIÓN DE HOY del lobby (`mision_hoy.py`, `documentacion/MISION_DE_HOY.md`): el FF117 empujado y el
#   FF118 del cobro. anonimo03: «día nuevo a la medianoche, hora de Perú» ⇒ UTC−5 (Perú no tiene horario de verano).
MISION_HOY_ACTIVA = True
MISION_HOY_UTC = -5

# ★ 15-oct · LAS MISIONES DE ROMPECABEZAS (la tragamonedas de «Modo Misión», `puzzle.py`, `MISIONES_PUZZLE.md`).
#   False = la lista vacía (`FFAF`) y «falla al obtener la ID» al armar. anonimo03: el entrenamiento no cuenta; se terminan
#   con el reset del día. El PREMIO: escalón del id × meta × esto (anonimo03, al verlo andar: «el de prueba me gusta»).
PUZZLE_ACTIVO = True
PUZZLE_RCOIN_POR = 10           # el escalón va 1…18 y la meta 1…9 ⇒ de 10 a 1.620 Rcoin
PUZZLE_EXP_POR = 100            #                                     ⇒ de 100 a 16.200 EXP
#   ★ 12-oct (anonimo03: «las campanas no pueden regalarse»): lo que NO se regala (también dentro de un pack). El que
#   regala ve «%s no puede usar este ítem» (res 4) y no se le cobra.
REGALO_NO_SE_REGALA = tuple(CAMPANAS)

# ═══ LOS SETS DEL ARMARIO (12-oct) — `conjuntos.py`, `documentacion/ARMARIO_CONJUNTOS.md` ═══
#   SET1..SET4 de «Mi Armario»: Guardar / Cargar (`FF73`). False = «No se puede guardar el CONJUNTO» y no se manda nada.
CONJUNTOS_ACTIVO = True
CONJUNTOS_MAX = 10             # ★ 12-oct: SET1..SET10 (la d3d9 `ropero.c` dibuja el desplegable en 2×5; el de
# ★ 25-oct — al personaje elegido en el selector (con el FFC9 guardado, en el 1.er FF6E): sus sets (FF73 sub 2, aunque
#   sean cero) y su ropa con «ponerse esta lista» (FF73 sub 3), que limpian lo del personaje anterior
#   (`conjuntos.sincronizar_al_elegir`). Uno por uno, para MEDIR: con la sala oscura en los de Novato.
SELECTOR_SYNC_SETS = True
SELECTOR_SYNC_ROPA = True
# ★ 25-oct — el FFC9 guardado del personaje elegido, mandado ya en el lobby. ⚠ El FFC9 es la DIFICULTAD de la sala
#   (`0x5D8490` -> `0x58E490`: game+0x9512, y si ya existe [game+0x10E8C] se la APLICA, vt+0xDC). En el lobby sí
#   existe: «dificultad 1» (Novato) dejaba la sala OSCURA. Para medir.
SELECTOR_FFC9_TARDE = True
#                                fábrica trae 4 — un cliente sin la dll nueva sólo ofrece SET1..SET4)

# ═══ «¿QUIÉN TE INVITÓ?» (11-oct) — `referido.py`, `documentacion/REFERIDO.md` ═══
#   El que crea su personaje escribe el apodo de quien lo trajo (`FFE2`) y ése cobra `REFERIDO_RCOIN` (anonimo03: 5k).
#   False = se contesta «No existe el Nickname» a todo (el jugador omite y sigue; ya no queda clavado).
REFERIDO_ACTIVO = True
REFERIDO_RCOIN = 5000
#   Cuánto después de crear el personaje se acepta la respuesta (la ventana sale ahí mismo; esto corta a un
#   cliente tocado que la mande días después).
REFERIDO_VENTANA_S = 3600

# ★ 13-oct · «MODO DE 12 JUGADORES» + ÍTEM (MODO_6VS6.md §18). anonimo03: «que el modo ítem funcione en solo + ítem /
#   equipo + ítem con el modo 12 prendido». Antes la sala de 12 nacía sólo con velocidad porque crasheaba
#   («empieza sin audio y crashea a los segundos»). En False vuelve a eso. La dll tiene su par: [sala12] item.
DOCE_CON_ITEM = True

# ★ 14-oct · EL RELEVO DE 12 (RELEVO_12.md): con el «Modo de 12 jugadores» prendido, el relevo arma su sala de 12 con 4
#   equipos de 3. La dll tiene su par ([sala12] relevo y relevo12.c, que muda el motor del relevo a 4 equipos).
DOCE_RELEVO = True

# ★ 15-oct · LOS 4 EQUIPOS EN BATALLA EN EQUIPO (anonimo03: «que el modo de 4 equipos, que hoy es sólo del relevo, también
#   funcione en ítem y velocidad "equipo"» — EQUIPOS_4.md). La ventana de crear sala manda el bit 0x40 («4 equipos»)
#   junto al 0x80: la sala es la del relevo de 12 (4 colores, lugares fijos, banderas, flechita) y gana el PRIMER equipo
#   que mete a sus 3 en la meta (anonimo03). En False, la casilla «4 equipos» con equipo arma el 6 contra 6.
DOCE_CUATRO = True

# ★ 14-oct · LA VICTORIA EN LA SALA DE 12 POR EQUIPOS (anonimo03, 13-oct): «gana el equipo que llene 3 lugares en la llegada:
#   si llega 1 rojo, 1 azul, 1 rojo, 1 azul, el siguiente que alcance 3 gana — sería injusto darle la victoria al que
#   llegue primero sin tomar en cuenta el esfuerzo de los demás». Antes ganaba el equipo del 1.º. Sólo en la sala de
#   12 y en equipo (no relevo, no jefe: el jefe tiene su regla). En 0 vuelve a «gana el equipo del 1.º».
DOCE_GANA_CON = 3
