# -*- coding: utf-8 -*-
r"""lobby_alma — **EL AMIGO DEL ALMA / LA JOYA DE LA AMISTAD** (`FF40` sub `0x3B` + `0x3F`).

★★★ QUÉ ES. El hermano de la pareja: una relación de a dos, con su propio ítem (la **Joya de la
Amistad**), su propio popup, su propia línea en el panel de mensajería y su propio aniversario.
**No existe en el CBT** — se descubrió leyendo el 2013 (`SOCIAL_MAPA_2013.md` §2.5) y hasta hoy
no tenía una sola línea de server.

⚠ A diferencia de la pareja, **se puede tener más de uno** (str#896 *"Estás en el máximo número
  de amigos del alma que puedes tener"*). El tope lo pone el server: ver `ALMA_TOPE`.

═══ EL CABLE, MEDIDO ═══════════════════════════════════════════════════════════════════════════

    C2S / S2C   FF40 [0x3B][u8 sub][u32 JOYA][u8 len][nick]
    S2C         FF40 [0x3F][u8 ?][u8 0x17][u8 len][nick]        ← el popup, str#909

★★★★★ **EL `u32` NO ES UN UID: ES LA JOYA.** Es el hallazgo que evita el bug mudo, y está medido
  en `0x45F430` (`cMessenger::CmdAddBestFriend`, el insertador de la fila del panel):

      0045f48e  mov ecx, [esi+0x38]      ; el u32 del paquete
      0045f492  mov ecx, [0x931618]      ; ★ el manager de ÍTEMS
      0045f498  call 0x50f4b0            ; buscarlo en la tabla de ítems
      0045f49f  test bl, bl
      0045f4a1  jne  0x45f4b9
      0045f4a7  push 0x876ae8            ; "cMessenger::CmdAddBestFriend : %d"
      0045f4ac  call 0x634a30            ; ⛔ AL LOG, Y SE VA SIN AGREGAR LA FILA

  ⇒ Con el `u32` en 0 —o con un ítem que el cliente no conozca— **el amigo del alma no aparece
    nunca**, y el único rastro queda en el log del cliente. Es **exactamente** la misma trampa que
    el 2º `u32` del `FF4A` de pareja, que costó una caza entera. Ver [[leer-al-consumidor]].
  ★ Las joyas válidas están en `rnr_script/ring.txt` como `<Friend>`, y **no tienen ChargeId**:
    ahí viaja el `Index` tal cual (1200088 · 1200090 · 1200091). No hay traducción que hacer,
    al revés que con los anillos de pareja.

═══ LOS SUBTIPOS, cada uno con el texto que dispara ════════════════════════════════════════════

Sacados de las ramas del handler `0x5F1E60`, cruzando cada `cmp al,N` con su `push <idx>` +
`call 0x433380`. **[M]** — no son nombres deducidos: es qué cartel sale con cada número.

    S2C  0x29  str#908  "%s ha solicitado ser tu amigo del alma"     ← al destino
    S2C  0x24  str#906  "%s ha aceptado la solicitud"     + AGREGA LA FILA  ← al que pidió
    S2C  0x02  str#910  "%s ha sido registrado como tu amigo del alma"  + AGREGA  ← al que aceptó
    S2C  0x0C  str#907  "%s ha rechazado la solicitud"                ← al que pidió
    S2C  0x16  str#911  "%s rompió la amistad del alma"               ← al que queda
    S2C  0x26  str#893  "Has roto la amistad del alma con %s"         ← al que rompe
    S2C  0x27  str#914  "%s canceló la solicitud"
    S2C  0x09  str#915  "%s cerró el juego y se canceló la solicitud"
    ── el CAMBIO DE JOYA, medido pero NO implementado todavía ──
    S2C  0x2A  str#912  ·  0x0D  str#891  ·  0x15  str#892  ·  0x11  str#916

★★ El par `0x24` / `0x02` es **calcado** del par `sub2 4` / `sub2 8` de la pareja: uno va al que
  pidió y el otro al que aceptó, y **los dos** insertan la fila en el panel. Que dos sistemas
  distintos usen la misma forma es la señal de que la lectura está bien.

⛔ El `0x26` tiene una guarda DEL CLIENTE que conviene conocer (`0x5F1F20`..`0x5F1F47`): compara el
  nick del paquete contra **el mío** (`[0x9314e0]+0x1a8`) y sólo saca el cartel si son distintos.
  ⇒ Mandarse a uno mismo el 0x26 con el propio nombre no dibuja nada, y no es un bug nuestro.
"""
import struct
import time

from .ajustes import (ALMA_ANUNCIO, ALMA_REPOBLAR, ALMA_TOPE, ALMA_VENCE,
                      AMIGO_DEL_ALMA)
from .basedatos import (
    db_agregar_alma,
    db_almas_de,
    db_borrar_alma,
    db_get_char,
    db_poner_joya_alma,
    db_son_almas,
    db_uids_por_nick,
)
from .registro import log
from .salas import CONEXIONES

# ── Los subtipos S2C, con el texto que saca cada uno. **[M]**, ver la cabecera ────────────────
S2C_PREGUNTA   = 0x0A     # ★★★★★ EL DIÁLOGO DE ACEPTACIÓN — el que va al DESTINO
S2C_SOLICITA   = 0x29     # str#908  "%s ha solicitado…" ⛔ INSERVIBLE: su %s es local, ver §_pedir
S2C_ACEPTO     = 0x24     # str#906  "%s ha aceptado la solicitud"     + agrega la fila
S2C_REGISTRADO = 0x02     # str#910  "%s ha sido registrado como…"     + agrega la fila
S2C_RECHAZO    = 0x0C     # str#907  "%s ha rechazado la solicitud"
S2C_ROMPIO     = 0x16     # str#911  "%s rompió la amistad del alma"
S2C_ROMPI      = 0x26     # str#893  "Has roto la amistad del alma con %s"
S2C_CANCELO    = 0x27     # str#914  "%s canceló la solicitud"

# ── Los subtipos C2S que manda el cliente. Sacados de sus 8 emisores (los `push` de
#    `0x5DEF30`): 0x0A 0x0B 0x0C 0x13 0x14 0x15 0x18, más el `0x44` del `0x3F`. **[M]**
C2S_PEDIR    = 0x0A
C2S_ACEPTAR  = 0x0B
C2S_RECHAZAR = 0x0C
C2S_ROMPER   = 0x18

# ── ★★ EL CAMBIO DE JOYA — el botón «Cambiar Joya» del panel (2026-09-15) ────────────────────
#   ⛔ anonimo03: *"cambiar la joya del alma, parecido a cambiar el anillo, en este momento hace
#     nada"*. El clic **sí llegaba**, y estaba en el log sin handler:
#         3b 13  da 4f 12 00  06 "Luis*A"   ← cambiar a la joya 1200090
#
#   ★★★ Es **el mismo flujo que el de la amistad, con otros números**, y eso no es una
#     suposición: el S2C `0x13` cae en la **misma rama** que el `0x0A` (`0x5F26D7`) y sólo cambia
#     el tipo de diálogo — `push 0x46` para la amistad, `push 0x48` para el cambio:
#         0x5F2752  cmp al, 0x0a  ->  0x5F278C  push 0x46
#         0x5F2790  cmp al, 0x13  ->  0x5F27B4  push 0x48
#   ⇒ Y por lo tanto vale la MISMA regla del `0x0A`: el OK del diálogo vuelve como un `0x13`, así
#     que hay que mirar si hay un cambio pendiente para saber si es *"pido"* o *"acepto"*.
C2S_CAMBIO    = 0x13
C2S_CAMBIO_OK = 0x14
C2S_CAMBIO_NO = 0x15

S2C_CAMBIO_PREGUNTA = 0x13   # el diálogo «¿aceptás cambiar la joya?» (tipo 0x48)
S2C_CAMBIO_PEDIDO   = 0x2A   # str#912  "Has solicitado cambiar la joya de la amistad a %s"
S2C_CAMBIO_HECHO    = 0x0D   # str#891  "Se ha cambiado la joya de la amistad con %s"  ★ + el ícono
S2C_CAMBIO_RECHAZO  = 0x15   # str#892  "%s ha rechazado el cambio de joya"

# Cambios de joya vivos: destino_uid -> {"de": uid, "joya": item_id, "cuando": ts}
#   ⚠ Aparte de `PENDIENTES` a propósito: una solicitud de amistad y una de cambio de joya pueden
#     estar abiertas a la vez entre las mismas dos personas, y mezclarlas haría que contestar una
#     cierre la otra.
PENDIENTES_JOYA = {}

# ★ El tipo del popup del `0x3F`. Medido en `0x5F2944`: `cmp al, 0x17` y con cualquier otro valor
#   el cliente **no dibuja nada**. No es un número nuestro.
POPUP_ALMA = 0x17

# Solicitudes vivas: destino_uid -> {"de": uid, "joya": item_id}
#   ⚠ En memoria a propósito, igual que las de pareja: una solicitud no sobrevive a un reinicio.
#     Si sobreviviera habría que vencerlas, o quedarían colgadas para siempre.
PENDIENTES = {}


def _nick_de(uid):
    return str((db_get_char(uid) or {}).get("nick", "") or "")


def _str8(s):
    b = str(s or "").encode("cp1252", "replace")[:0x1E]
    return bytes([len(b)]) + b


def _joyas_de(uid):
    """Las Joyas de la Amistad que tiene en el inventario, en orden de catálogo.

    ★ Se leen de `ring.txt` (`<Friend>`), que es **la misma tabla que lee el cliente**: si el ítem
      no está ahí, el cliente no lo reconoce y la fila del panel no se agrega (ver la cabecera).
    """
    # ⛔ La clave del ítem en el inventario es **`id`**, no `item_id`: la fila se arma en
    #   `almacen.leer_char` como `{"id": …, "exp": …}`. Escribir `item_id` acá devolvería `None`
    #   para todos y la lista saldría siempre vacía ⇒ *"nadie tiene joyas"*, sin ninguna pista.
    #   Es el molde exacto del `sexo`/`gender` de la pareja. Ver [[no-deducir-de-un-nombre]].
    from .catalogo import anillo_de
    _tengo = set()
    for _it in ((db_get_char(int(uid)) or {}).get("inventory") or []):
        try:
            _id = int(_it.get("id") if isinstance(_it, dict) else _it)
        except (TypeError, ValueError):
            continue
        if anillo_de(_id).get("tipo") == "friend":
            _tengo.add(_id)
    return sorted(_tengo)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  Los paquetes
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _s2c(sub, joya, nick):
    """`FF40 [0x3B][u8 sub][u32 JOYA][u8 len][nick]` — **el único builder** del sub `0x3B`.

    ★ Uno solo para los siete subtipos, porque **todas las ramas del handler leen exactamente lo
      mismo**: `read(4)` + `read(1)` + `read(len)`. Comprobado rama por rama con `campos13.py`
      (`0x5F23C0`, `0x5F22F1`, `0x5F262C`, `0x5F2727`). Tener un builder por subtipo sería tener
      siete oportunidades de escribir mal el mismo layout.
    """
    return bytes([0x3B, sub & 0xFF]) + struct.pack("<I", joya & 0xFFFFFFFF) + _str8(nick)


def _s2c_popup(nick):
    """`FF40 [0x3F][u8 TIPO=0x17][u8 flag≠0][u8 len][nick]` — *"¿Quieres registrar a %s…?"*.

    ⛔⛔⛔ **NO USAR PARA AVISARLE AL DESTINO.** Se dibuja perfecto y con el nombre correcto, y
      aun así es el paquete equivocado: es **el diálogo del que VA A PROPONER**. Su OK llega a
      `0x4177E0` —único llamador `0x5F2A4C`, dentro de este mismo handler— que hace
      `push 0xa` + `call 0x5DEF30`, o sea **manda una solicitud nueva**. Mandárselo al destino es
      pedirle que proponga él, y eso fue un bucle infinito en vivo (2026-09-15).
      ⇒ El que pregunta *"¿aceptás?"* es el **S2C `0x0A`**. Ver `_pedir`.
    ★ Se deja armado —y no borrado— porque es la pieza que va a hacer falta el día que el server
      quiera abrirle a alguien el flujo de proponer (por ejemplo desde un comando o un evento).


    ⛔⛔ **ACÁ MANDÉ LOS DOS BYTES AL REVÉS** (2026-09-15, primera prueba en el cliente). El
      síntoma fue el peor de todos: el paquete salió, el cliente lo leyó **entero** —así que nada
      se desincronizó y no hubo ni un error en ningún lado— y **se fue sin dibujar el popup**.
      anonimo03 lo reintentó tres veces y el log sólo decía *"ya tiene un cartel abierto"*.

    ★★★ EL ORDEN, ahora normalizando el `esp` a mano en vez de leer la tabla de offsets de
      `campos13.py` como si fuera el orden del cable:

          0x5F28A2  lea eax,[esp+0x2f]  tras `push ebp`  ⇒ 1er campo -> **E+0x2B**
          0x5F28FA  lea ecx,[esp+0x19]  tras `push ebp`  ⇒ 2º  campo -> **E+0x15**
          0x5F2907  lea edx,[esp+0x1c]  tras `push ebp`  ⇒ largo     -> **E+0x18**

      y las dos puertas, con el `esp` ya devuelto a E por el lector:

          0x5F2928  cmp byte [esp+0x15], bl   ⇒ mira el **2º** campo: en 0 CIERRA el popup
          0x5F2940  mov  al,  byte [esp+0x2b] ⇒ mira el **1er** campo
          0x5F2944  cmp  al,  0x17            ⇒ y tiene que ser 0x17 o se va sin dibujar

    ⇒ El **0x17 va PRIMERO**. El segundo byte sólo tiene que ser distinto de cero.
    ★ La lección, y es la de siempre: la tabla de `campos13.py` dice **en qué orden se lee**, no
      **qué es cada campo**. Los offsets estaban bien (`@+43` = 0x2B); el que los asoció al revés
      fui yo. Ver [[medir-antes-que-deducir]] y [[la-herramienta-corta-en-silencio]].
    """
    return bytes([0x3F, POPUP_ALMA, 1]) + _str8(nick)


def _mandar(uid, payload, nota):
    _c = CONEXIONES.get(int(uid or 0))
    if _c is None or getattr(_c, "cerrado", False):
        return False
    _c.send_ff55(0x40, payload, name=nota)
    return True


def _resolver(nick, yo):
    """El uid del destinatario. ⚠ **El apodo NO es único** (203 repetidos sobre 4807): se elige al
    que está CONECTADO, la misma regla que ya usan pareja y las solicitudes de amistad."""
    _uids = [int(u) for u in (db_uids_por_nick(nick) or []) if int(u) != int(yo)]
    if not _uids:
        return 0
    return next((u for u in _uids if CONEXIONES.get(u) is not None), _uids[0])


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  El flujo
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pedir(st, joya, nick):
    """C2S `0x0A` — *"quiero que %s sea mi amigo del alma"*.

    ⚠ El cliente **no tiene códigos de error numerados** para esto (la pareja sí, con su
      `140 + code`). Acá cada negativa es un subtipo distinto o nada: por eso las que no tienen
      paquete propio se registran en el log y se cortan en silencio, que es lo que hace el juego.
    """
    _yo = int(getattr(st, "usn", 0) or 0)
    _otro = _resolver(nick, _yo)
    if not _otro:
        log("LOBBY", f"  ⛔ ALMA: usn={_yo} pide a {nick!r}, que no existe (str#895)")
        return
    if _otro == _yo:
        log("LOBBY", f"  ⛔ ALMA: usn={_yo} se pidió a sí mismo -> lo tiro")
        return
    if db_son_almas(_yo, _otro):
        log("LOBBY", f"  ⛔ ALMA: usn={_yo} y uid={_otro} YA son amigos del alma")
        return
    # ★★ El tope se mira de LOS DOS LADOS, y el cliente tiene un texto para cada uno: str#896
    #   *"estás en el máximo"* y str#897 *"el usuario que ingresaste ya tiene la máxima cantidad"*.
    #   Mirar sólo el mío dejaría mandar solicitudes que el otro no puede aceptar nunca.
    if len(db_almas_de(_yo) or []) >= ALMA_TOPE:
        log("LOBBY", f"  ⛔ ALMA: usn={_yo} ya tiene {ALMA_TOPE} amigos del alma (str#896)")
        return
    if len(db_almas_de(_otro) or []) >= ALMA_TOPE:
        log("LOBBY", f"  ⛔ ALMA: uid={_otro} ya tiene {ALMA_TOPE} amigos del alma (str#897)")
        return
    if not _joyas_de(_yo):
        # str#894 *"No tienes ninguna Joya de la Amistad."* / str#889 ofrece comprarla.
        log("LOBBY", f"  ⛔ ALMA: usn={_yo} no tiene ninguna Joya de la Amistad (str#894)")
        return
    # ⛔ La joya que mande el cliente se COMPRUEBA contra el inventario: si no la tiene, se usa la
    #   que sí tiene. Creerle al cliente acá es dejar registrar con una joya que nadie compró.
    _joya = joya if joya in _joyas_de(_yo) else _joyas_de(_yo)[0]
    # ⛔⛔ ACÁ ANONIMO03 QUEDÓ TRABADO (2026-09-15). El popup salía mal armado y no se dibujaba, pero
    #   la solicitud **sí** quedaba anotada ⇒ al reintentar, el server contestaba *"ya tiene un
    #   cartel abierto"* y no mandaba nada más. Tres intentos, tres negativas, y en pantalla nada.
    #   ★★ La lección es más general que el bug del popup: **anotar que mandé algo no prueba que
    #     el otro lo haya visto.** Si el paquete se pierde, se dibuja mal o el jugador cierra el
    #     diálogo sin contestar, la anotación queda para siempre y el sistema se traba solo.
    #   ⇒ Dos salidas, las dos necesarias:
    _vieja = PENDIENTES.get(_otro)
    if _vieja is not None:
        if int(_vieja.get("de", 0)) == _yo:
            # (a) es EL MISMO que ya había pedido: reintentar tiene que RE-MANDAR el popup, no
            #     rebotar. Es exactamente lo que hace un jugador cuando no ve nada en pantalla.
            log("LOBBY", f"  ↻ ALMA: usn={_yo} reintenta con uid={_otro} -> re-mando el diálogo")
        elif time.time() - float(_vieja.get("cuando", 0)) > ALMA_VENCE:
            # (b) es OTRO, pero la solicitud vieja ya venció. Sin esto, una solicitud que nadie
            #     contestó deja al destinatario inalcanzable hasta que reinicie el server.
            log("LOBBY", f"  ↻ ALMA: la solicitud de uid={_vieja.get('de')} a uid={_otro} venció "
                         f"({ALMA_VENCE}s) -> la reemplazo")
        else:
            log("LOBBY", f"  ⚠ ALMA: uid={_otro} tiene un cartel abierto de uid={_vieja.get('de')} "
                         f"-> no encimo otro (vence en "
                         f"{int(ALMA_VENCE - (time.time() - float(_vieja.get('cuando', 0))))}s)")
            return
    if CONEXIONES.get(_otro) is None:
        log("LOBBY", f"  ⛔ ALMA: uid={_otro} ({nick!r}) está desconectado")
        return

    PENDIENTES[_otro] = {"de": _yo, "joya": _joya, "cuando": time.time()}
    # ★★★★★ SE MANDA **SÓLO EL `0x3F`**, y el porqué costó una prueba en vivo (2026-09-15).
    #
    #   ⛔ Primero mandaba también el `0x29` (str#908 *"%s ha solicitado ser tu amigo del alma"*)
    #     y en pantalla salió **«ha Solicitado ser tu amigo del alma»**, sin el nombre. No era un
    #     campo mal puesto: **ese `%s` NO SALE DEL PAQUETE.**
    #
    #       005f2239  call 0x414670     ; ★ el nombre sale de ACÁ
    #       005f223f  push 0x38c        ;   str#908
    #
    #     y `0x414670` devuelve el buffer **local** `0x931630`, que el propio cliente llena con
    #     *"el jugador que tengo seleccionado ahora"* (lo leen también `0x424550` y `0x4248A7`,
    #     que son la UI del perfil). ⇒ Para el que RECIBE, ese buffer tiene lo que él tenga
    #     abierto — o nada. **El `0x29` es incapaz de nombrar a un tercero.**
    #
    #   ⛔⛔ Y DESPUÉS MANDÉ EL `0x3F`, QUE TAMBIÉN ERA EL EQUIVOCADO. Ése sí lleva el nombre y
    #     se dibuja bien — anonimo03 lo vio con el nick correcto — **pero es el diálogo del que VA A
    #     PROPONER**, no el del que recibe. Lo probó la pantalla antes que el disasm: al apretar
    #     OK, a quien lo recibía le salía **«Escoje una joya»**, o sea el flujo de proponer.
    #
    #     Y el binario lo confirma exacto: el OK de ese diálogo llega a `0x4177E0`, que **tiene
    #     un solo llamador en todo el exe** (`0x5F2A4C`, adentro del handler del `0x3F`) y hace
    #
    #         00417836  push 0xa          ; el subtipo
    #         00417838  call 0x5def30     ; ★ manda un C2S 0x0A
    #
    #     ⇒ Mandarle el `0x3F` al destino es **pedirle que proponga él**. De ahí salía el bucle.
    #
    #   ★★★★★ EL BUENO ES EL **S2C `0x0A`** (rama `0x5F26D7`), y hace las tres cosas que hacen
    #     falta, en orden:
    #
    #         005f2764  call 0x45af80   ; ¿ya son amigos del alma? -> si sí, se va sin molestar
    #         005f277f  call 0x5edeb0   ; ★ guarda el NOMBRE que viene en el paquete
    #         005f278c  push 0x46       ; ★★ el tipo de diálogo
    #         005f27c1  call 0x4214c0   ; ★★★ y lo dibuja
    #
    #   ⇒ Es el único de los tres que **pregunta** en vez de avisar o de mandar a proponer.
    #   ★ La lección: tres paquetes distintos "parecían" el aviso al destino, y los tres se
    #     dibujaban. Lo que los separa no es que salgan en pantalla: es **qué hacen después**.
    #     Ver [[leer-al-consumidor]].
    _mandar(_otro, _s2c(S2C_PREGUNTA, _joya, _nick_de(_yo)),
            f"FF40/0x3B/0A ★ diálogo «¿aceptás a {_nick_de(_yo)} como amigo del alma?»")
    log("LOBBY", f"  ★★ ALMA: usn={_yo} ({_nick_de(_yo)!r}) le pide a uid={_otro} ({nick!r}) "
                 f"con la joya {_joya}")


def _responder(st, acepta):
    """C2S `0x0B` aceptar · `0x0C` rechazar."""
    _yo = int(getattr(st, "usn", 0) or 0)
    _pend = PENDIENTES.pop(_yo, None)
    if not _pend:
        log("LOBBY", f"  ⚠ ALMA: usn={_yo} contesta una solicitud que no existe -> ignoro")
        return
    _de, _joya = int(_pend["de"]), int(_pend.get("joya", 0))

    if not acepta:
        _mandar(_de, _s2c(S2C_RECHAZO, _joya, _nick_de(_yo)),
                f"FF40/0x3B/0C «{_nick_de(_yo)} rechazó la solicitud» (str#907)")
        log("LOBBY", f"  ★ ALMA: usn={_yo} RECHAZÓ la solicitud de uid={_de}")
        return

    # ⚠ Se vuelve a mirar el tope: entre el pedido y el sí pudo entrar otra amistad. Es la misma
    #   carrera que la pareja tiene cubierta con su `db_pareja_de` antes de casar.
    if db_son_almas(_yo, _de):
        log("LOBBY", f"  ⚠ ALMA: usn={_yo} y uid={_de} ya eran amigos del alma")
        return
    if len(db_almas_de(_yo) or []) >= ALMA_TOPE or len(db_almas_de(_de) or []) >= ALMA_TOPE:
        log("LOBBY", f"  ⛔ ALMA: alguno llegó al tope mientras el cartel estaba abierto")
        return
    db_agregar_alma(_yo, _de, _joya)

    # ★★★ LOS DOS PAQUETES DEL ÉXITO, y son DISTINTOS a propósito: cada uno saca su texto y los
    #   dos insertan la fila en el panel (`0x45F430`). Es el mismo par que la pareja usa con sus
    #   sub2 4 y 8. Mandar el mismo a los dos dejaría a uno con el cartel del otro.
    _mandar(_de, _s2c(S2C_ACEPTO, _joya, _nick_de(_yo)),
            f"FF40/0x3B/24 «{_nick_de(_yo)} aceptó» (str#906) + fila en el panel")
    st.send_ff55(0x40, _s2c(S2C_REGISTRADO, _joya, _nick_de(_de)),
                 name=f"FF40/0x3B/02 «{_nick_de(_de)} registrado como tu amigo del alma» (str#910)")
    # ★★★ Y EL FOQUITO, detrás de los dos. ⛔ Reportado por anonimo03: *"el foquito sale apagado"*.
    #   La fila nace con el estado por defecto (`0x45F4BD mov byte [esp+0x14],0x10`) porque el
    #   paquete `0x3B` no trae el campo que lo decide. Se enciende con el `FF40/0x04`, igual que
    #   la pareja. ⚠ DETRÁS, nunca antes: la fila tiene que existir primero.
    _c_de = CONEXIONES.get(int(_de))
    if _c_de is not None and not getattr(_c_de, "cerrado", False):
        avisar_presencia_del_alma(_c_de, _yo, " (recién registrados)")
    avisar_presencia_del_alma(st, _de, " (recién registrados)")
    log("LOBBY", f"  ★★★ ALMA: usn={_yo} ({_nick_de(_yo)!r}) y uid={_de} ({_nick_de(_de)!r}) "
                 f"son amigos del alma con la joya {_joya}")
    if ALMA_ANUNCIO:
        _anunciar(_nick_de(_de), _nick_de(_yo))
    _redibujar_joyas(_yo, _de, " (recién registrados)")


def _redibujar_joyas(uno, otro, motivo):
    """★ Si los dos están en la MISMA sala, se les manda su `FF15` con la lista de joyas nueva.
    ⛔ anonimo03: *"al cambiar la joya de amistad en vivo por otra, no renderiza el cambio en la sala"*.
      La joya sólo viajaba al entrar (ver `salas.actualizar_ocupantes`)."""
    try:
        from .salas import actualizar_ocupantes
        _c1, _c2 = CONEXIONES.get(int(uno)), CONEXIONES.get(int(otro))
        _r1 = getattr(_c1, "room_id", None) if _c1 is not None else None
        _r2 = getattr(_c2, "room_id", None) if _c2 is not None else None
        if _r1 is not None and _r1 == _r2:
            actualizar_ocupantes(_r1, (int(uno), int(otro)), motivo=motivo)
    except Exception as _e:                                      # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude redibujar las joyas de {uno}/{otro}: {_e!r}")


def _romper(st, nick):
    """C2S `0x18` — romper la amistad del alma."""
    _yo = int(getattr(st, "usn", 0) or 0)
    _otro = _resolver(nick, _yo)
    if not _otro or not db_son_almas(_yo, _otro):
        log("LOBBY", f"  ⚠ ALMA: usn={_yo} quiere romper con {nick!r} y no son amigos del alma")
        return
    _joya = 0
    for _f in (db_almas_de(_yo) or []):
        if int(_f.get("otro_uid") or 0) == _otro:
            _joya = int(_f.get("joya") or 0)
    db_borrar_alma(_yo, _otro)
    # ★ Al OTRO le llega "rompió", a MÍ "has roto". Son dos textos distintos y dos subtipos
    #   distintos: el cliente no arma uno a partir del otro.
    _mandar(_otro, _s2c(S2C_ROMPIO, _joya, _nick_de(_yo)),
            f"FF40/0x3B/16 «{_nick_de(_yo)} rompió la amistad del alma» (str#911)")
    st.send_ff55(0x40, _s2c(S2C_ROMPI, _joya, _nick_de(_otro)),
                 name=f"FF40/0x3B/26 «has roto la amistad del alma con {_nick_de(_otro)}» (str#893)")
    log("LOBBY", f"  ★★ ALMA: usn={_yo} rompió la amistad del alma con uid={_otro}")
    _redibujar_joyas(_yo, _otro, " (rompieron la amistad)")


def _pedir_cambio_joya(st, joya, nick):
    """C2S `0x13` — *"quiero cambiar la joya que compartimos"*. El botón «Cambiar Joya»."""
    _yo = int(getattr(st, "usn", 0) or 0)
    _otro = _resolver(nick, _yo)
    if not _otro or not db_son_almas(_yo, _otro):
        log("LOBBY", f"  ⚠ ALMA/joya: usn={_yo} quiere cambiar con {nick!r}, que no es su amigo "
                     f"del alma")
        return
    # ⛔ La joya se comprueba contra el inventario, igual que al proponer: creerle al cliente es
    #   dejar cambiar a una joya que nadie compró.
    _mias = _joyas_de(_yo)
    if not _mias:
        log("LOBBY", f"  ⛔ ALMA/joya: usn={_yo} no tiene ninguna Joya de la Amistad (str#894)")
        return
    _joya = joya if joya in _mias else _mias[0]
    _actual = next((int(f.get("joya") or 0) for f in (db_almas_de(_yo) or [])
                    if int(f.get("otro_uid") or 0) == _otro), 0)
    if _joya == _actual:
        # ★ El mismo caso que el anillo de pareja: elegir la que ya tienen no es un error, pero no
        #   hay nada que cambiar ni a quién molestar.
        log("LOBBY", f"  ⚠ ALMA/joya: usn={_yo} eligió la que ya tienen ({_joya})")
        return
    if CONEXIONES.get(_otro) is None:
        log("LOBBY", f"  ⛔ ALMA/joya: uid={_otro} ({nick!r}) está desconectado")
        return
    PENDIENTES_JOYA[_otro] = {"de": _yo, "joya": _joya, "cuando": time.time()}
    _mandar(_otro, _s2c(S2C_CAMBIO_PREGUNTA, _joya, _nick_de(_yo)),
            f"FF40/0x3B/13 ★ diálogo «¿cambiamos la joya?» de {_nick_de(_yo)!r}")
    # ★ Y al que pidió, su acuse: str#912 *"Has solicitado cambiar la joya de la amistad a %s"*.
    st.send_ff55(0x40, _s2c(S2C_CAMBIO_PEDIDO, _joya, nick),
                 name=f"FF40/0x3B/2A «pediste cambiar la joya a {nick!r}» (str#912)")
    log("LOBBY", f"  ★★ ALMA/joya: usn={_yo} le pide a uid={_otro} cambiar {_actual} -> {_joya}")


def _responder_cambio_joya(st, acepta):
    """El sí o el no al cambio de joya."""
    _yo = int(getattr(st, "usn", 0) or 0)
    _pend = PENDIENTES_JOYA.pop(_yo, None)
    if not _pend:
        log("LOBBY", f"  ⚠ ALMA/joya: usn={_yo} contesta un cambio que no existe -> ignoro")
        return
    _de, _joya = int(_pend["de"]), int(_pend.get("joya", 0))
    if not acepta:
        _mandar(_de, _s2c(S2C_CAMBIO_RECHAZO, _joya, _nick_de(_yo)),
                f"FF40/0x3B/15 «{_nick_de(_yo)} rechazó el cambio de joya» (str#892)")
        log("LOBBY", f"  ★ ALMA/joya: usn={_yo} RECHAZÓ el cambio de uid={_de}")
        return
    if not db_son_almas(_yo, _de):
        log("LOBBY", f"  ⚠ ALMA/joya: rompieron mientras el diálogo estaba abierto")
        return
    db_poner_joya_alma(_yo, _de, _joya)
    # ★★ El `0x0D` hace DOS cosas medidas (`0x5F24C4`…`0x5F2534`): saca str#891 **y** actualiza el
    #   ícono de la fila con `0x458EA0(nick, joya)`. Por eso alcanza con este paquete: no hay que
    #   re-mandar la lista entera para que se vea la joya nueva.
    # ⚠ A cada uno con el nombre del OTRO: el cliente busca esa fila en su panel para actualizarla.
    #   Mandarle su propio nombre no encontraría nada — el mismo cuidado que el anillo de pareja.
    st.send_ff55(0x40, _s2c(S2C_CAMBIO_HECHO, _joya, _nick_de(_de)),
                 name=f"FF40/0x3B/0D «cambiaron la joya con {_nick_de(_de)!r}» -> {_joya}")
    _mandar(_de, _s2c(S2C_CAMBIO_HECHO, _joya, _nick_de(_yo)),
            f"FF40/0x3B/0D «cambiaron la joya con {_nick_de(_yo)!r}» -> {_joya}")
    log("LOBBY", f"  ★★★ ALMA/joya: usn={_yo} y uid={_de} pasan a la joya {_joya}")
    _redibujar_joyas(_yo, _de, " (cambiaron la joya)")


def _anunciar(n1, n2):
    """El cartel a todo el server: str#904 *"%s y %s son ahora amigos del alma"*.

    ⚠ Es un BROADCAST, igual que el de la boda. Hoy es barato; si el server crece, es de lo
      primero a mirar. Perilla: `ALMA_ANUNCIO`.
    ⏳ **[NM] por qué opcode sale este cartel.** El texto existe y está traducido, pero no encontré
      todavía qué paquete lo dibuja — el `0x3B` no lo usa en ninguna de sus ramas. Por eso hoy
      esto **sólo deja el renglón en el log**: prefiero un anuncio que falta a mandar un paquete
      inventado. Ver el pendiente en `AMIGO_DEL_ALMA.md`.
    """
    log("LOBBY", f"  ⏳ ALMA: «{n1} y {n2} son ahora amigos del alma» (str#904) — "
                 f"falta medir por qué paquete sale este cartel; no se manda nada")


# ══════════════════════════════════════════════════════════════════════════════════════════════
def h_ff40_alma(st, cmd, data):
    """El despacho del `FF40` sub `0x3B` por su subtipo (el 2º byte).

    Layout **[M]** (emisor `0x5DEF30`): `[0x3B][u8 sub][u32 JOYA][u8 len][nick]`.
    """
    if not AMIGO_DEL_ALMA:
        log("LOBBY", f"  ⏸ FF40/0x3B con AMIGO_DEL_ALMA=False -> no contesto: {data.hex(' ')}")
        return
    _sub = data[1] if len(data) > 1 else 0xFF
    try:
        if len(data) < 7:
            log("LOBBY", f"  ⚠ FF40/0x3B de {len(data)} B, esperaba 7+: {data.hex(' ')}")
            return
        _joya = struct.unpack_from("<I", data, 2)[0]
        _ln = data[6]
        _nick = data[7:7 + _ln].decode("cp1252", "replace")
        if _sub == C2S_PEDIR:
            # ★★★★★ EL `0x0A` SIGNIFICA **DOS COSAS**, y confundirlas hizo un BUCLE INFINITO.
            #
            #   ⛔ EL SÍNTOMA (2026-09-15, con anonimo03 mirando): el popup salía, el jugador apretaba
            #     OK… y le salía otra vez. Y otra. En el log:
            #
            #       12:15:11  jugador1 le pide a jugador50   -> popup a jugador50
            #       12:15:14  jugador50 le pide a jugador1   <- ¡el OK del popup!
            #       12:15:17  jugador1 le pide a jugador50   <- y vuelta a empezar
            #
            #   ★★★ LA CAUSA, medida: **el botón OK del popup manda un `0x0A`**, no un subtipo de
            #     aceptación. El emisor es `0x4177E0` (su `call` al armador está en `0x417838`), y
            #     es el mismo `0x0A` que manda la UI del perfil desde `0x42452A`.
            #
            #   ⇒ **El subtipo no alcanza para saber qué quiere el jugador: hay que mirar si hay
            #     una solicitud pendiente PARA ÉL de la persona que nombra.** Si la hay, ese
            #     `0x0A` es un *"acepto"*; si no, es un *"pido"*.
            #   ★ Es la misma forma que ya tiene la pareja, sólo que allá el cliente usa dos
            #     subtipos distintos y acá reusa uno. Ver [[leer-al-consumidor]].
            _yo_ = int(getattr(st, "usn", 0) or 0)
            _pend_ = PENDIENTES.get(_yo_)
            if _pend_ and int(_pend_.get("de", 0)) == _resolver(_nick, _yo_):
                log("LOBBY", f"  ★★ ALMA: el 0x0A de usn={_yo_} nombrando a {_nick!r} es el OK "
                             f"del diálogo ⇒ lo trato como ACEPTAR, no como pedir")
                _responder(st, acepta=True)
            else:
                _pedir(st, _joya, _nick)
        elif _sub == C2S_ACEPTAR:
            _responder(st, acepta=True)
        elif _sub == C2S_RECHAZAR:
            _responder(st, acepta=False)
        elif _sub == C2S_ROMPER:
            _romper(st, _nick)
        elif _sub == C2S_CAMBIO:
            # ★★ MISMA TRAMPA QUE EL `0x0A`, y por el mismo motivo: el `0x13` es a la vez *"pido
            #   cambiar"* (el botón «Cambiar Joya») y *"acepto el cambio"* (el OK del diálogo).
            #   Las dos ramas viven juntas en `0x5F26D7` y sólo cambia el tipo de diálogo
            #   (`push 0x46` amistad · `push 0x48` cambio). ⇒ decide el pendiente, no el número.
            _yo_ = int(getattr(st, "usn", 0) or 0)
            _pj_ = PENDIENTES_JOYA.get(_yo_)
            if _pj_ and int(_pj_.get("de", 0)) == _resolver(_nick, _yo_):
                log("LOBBY", f"  ★★ ALMA/joya: el 0x13 de usn={_yo_} es el OK del diálogo ⇒ "
                             f"lo trato como ACEPTAR")
                _responder_cambio_joya(st, acepta=True)
            else:
                _pedir_cambio_joya(st, _joya, _nick)
        elif _sub == C2S_CAMBIO_OK:
            _responder_cambio_joya(st, acepta=True)
        elif _sub == C2S_CAMBIO_NO:
            _responder_cambio_joya(st, acepta=False)
        else:
            log("LOBBY", f"  · FF40/0x3B sub={_sub:#04x} sin handler todavía "
                         f"(joya={_joya}, nick={_nick!r}): {data.hex(' ')}")
    except Exception as e:                                       # noqa: BLE001
        # ⚠ Un error acá NO puede tumbar la conexión: es una solicitud de amistad, no el login.
        log("LOBBY", f"  ⛔ ALMA: el handler del sub={_sub:#04x} reventó: {e!r}")


def h_ff40_alma_popup(st, cmd, data):
    """El `FF40` sub `0x3F` **que manda el cliente** (`[0x3F][0x44][u8 len][nick]`).

    ⏳ **[NM] qué significa el `0x44`.** El cliente lo manda desde un solo sitio (`0x4244CB`), y
      hasta ver el log en vivo no sé si es *"abrí el popup"*, *"lo cerré"* o la respuesta misma.
      ⇒ Se registra y no se contesta. ★ Así salió el `FF47` de pareja: mirando qué llegaba cuando
        anonimo03 apretaba el botón. Ver [[medir-antes-que-deducir]].
    """
    log("LOBBY", f"  ⏳ FF40/0x3F del cliente ({len(data)} B): {data.hex(' ')} "
                 f"— anotado para medir con el botón en la mano")


def avisar_presencia_del_alma(dest, uid_otro, motivo=""):
    """Le manda a `dest` el **`FF40/0x04`** («fulano se movió») **de su amigo del alma**.

    ⛔⛔ EL SÍNTOMA, reportado por anonimo03 (2026-09-15): *"el foquito sale apagado"*. La fila
      aparecía en «Amigo de Alma» —o sea el registro andaba— pero con el indicador en gris,
      **aunque el otro estuviera en la misma sala**.

    ★★★ Y LA CAUSA ESTÁ MEDIDA, en `0x45F430` (el insertador de la fila):

          0045f4b9  cmp  byte [esi+0x3c], 0
          0045f4bd  mov  byte [esp+0x14], 0x10      ; ← el estado por defecto
          0045f4c2  je   0x45f4c9
          0045f4c4  mov  byte [esp+0x14], 0x0f      ; ← el otro estado
          0045f4d3  call 0x45fd50                   ; ★ el constructor de entrada de AMIGO

      `[esi+0x3c]` es un campo del struct que arma **el handler**, y el paquete `0x3B` **no lo
      llena** ⇒ queda en 0 ⇒ la fila nace con el estado `0x10`.

    ★★★★★ Y ES **EXACTAMENTE** EL MISMO AGUJERO QUE TENÍA LA PAREJA, hasta el constructor: allá
      también la fila nacía apagada porque `0x45FD50` *"inicializa ese campo justo en 0xFFFF"*, y
      lo arregló mandar el `FF40/0x04` detrás. Acá vale la misma solución, y **la misma pieza**:
      `lobby_social._s2c_ubicacion`, que ya está medida campo por campo.
    ⇒ Tres sistemas (amigos, pareja, alma) que comparten la fila del panel comparten también su
      forma de encenderla. Ver [[un-dato-derivado-se-esparce]].

    ⚠ Va SIEMPRE DETRÁS del paquete que crea la fila, nunca antes: la fila tiene que existir para
      que haya algo que encender. Es el mismo orden que el `FF4A` de pareja.
    """
    try:
        from .lobby_social import _s2c_ubicacion, _sala_de, _servidor_de
        _serv, _sala = _servidor_de(uid_otro), _sala_de(uid_otro)
        dest.send_ff55(0x40, _s2c_ubicacion(uid_otro, _nick_de(uid_otro), _serv, _sala),
                       name=f"FF40/0x04 presencia del amigo del alma {_nick_de(uid_otro)!r} "
                            f"(servidor={_serv} sala=0x{_sala:04X}){motivo}")
        return True
    except Exception as e:                                         # noqa: BLE001
        log("LOBBY", f"  ⛔ avisar_presencia_del_alma reventó: {e!r}")
        return False


def repoblar_almas(st, motivo=""):
    """Le vuelve a dibujar la sección «Amigo de Alma» del panel. Se llama **al entrar**.

    ⛔⛔ EL SÍNTOMA, reportado por anonimo03 (2026-09-15): *"si es que están registrados, no me
      aparecen"*. La base los tenía en las dos direcciones, el registro había funcionado — y el
      panel decía **«No tienes amigos del alma»**.

    ★★★ LA CAUSA: **la fila se insertaba sólo en el momento de registrarse, en vivo.** Al volver a
      entrar nadie la mandaba de nuevo, y el cliente no la guarda. Es **la misma lección que ya
      está escrita tres veces en este proyecto** —el enlace de la sala, el cartel, el `FF45`—:
      *el dato en la base no se dibuja solo*. Ver [[dibujar-no-es-acreditar]].

    ⚠⚠ Y ACÁ VIENE EL PRECIO, QUE ESTÁ MEDIDO Y NO SE PUEDE EVITAR DESDE EL SERVER:
      **no existe ningún paquete que inserte la fila sin sacar un cartel.** `0x45F430` es el único
      insertador (lo dice el propio binario: su log es `cMessenger::CmdAddBestFriend : %d`) y
      **tiene exactamente DOS llamadores en todo el exe**:

          0x5F25D2  <- subs 0x02 / 0x03   ->  str#910 "%s ha sido registrado como tu amigo…"
          0x5F2366  <- subs 0x24 / 0x25   ->  str#906 "%s ha aceptado la solicitud"

      Los dos sacan el cartel **antes** de insertar, y el cartel no depende de ningún campo del
      paquete: está en la rama. ⇒ Repoblar cuesta un cartel por amigo del alma, al entrar.

    ★ Se usa el `0x02` porque su texto es el menos raro de los dos como bienvenida.
    ⚠ Si molesta, `ALMA_REPOBLAR = False`: la fila vuelve a aparecer sólo al registrarse, que es
      el estado de antes de este arreglo. Es una elección de anonimo03, no una limitación nuestra.
    """
    if not (AMIGO_DEL_ALMA and ALMA_REPOBLAR):
        return 0
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        if not _yo:
            return 0
        _n = 0
        for _f in (db_almas_de(_yo) or []):
            _otro = int(_f.get("otro_uid") or 0)
            _nk = _nick_de(_otro)
            if not _nk:
                continue
            # ⚠ La JOYA tiene que ir de verdad: con 0, `0x45F430` no encuentra el ítem y **se va
            #   sin insertar la fila** (§2 del expediente). Repoblar con joya 0 daría exactamente
            #   el mismo síntoma que no repoblar, y encima con el cartel saliendo.
            st.send_ff55(0x40, _s2c(S2C_REGISTRADO, int(_f.get("joya") or 0), _nk),
                         name=f"FF40/0x3B/02 repoblar «Amigo de Alma»: {_nk!r}{motivo}")
            _n += 1
        if _n:
            log("LOBBY", f"  ★★ ALMA: usn={_yo} -> repobladas {_n} fila(s) de «Amigo de Alma»"
                         f"{motivo}")
        return _n
    except Exception as e:                                         # noqa: BLE001
        log("LOBBY", f"  ⛔ repoblar_almas reventó: {e!r}")
        return 0


def avisar_a_mis_almas(st, motivo=""):
    """Al entrar y al salir, le refresca la presencia a **cada amigo del alma conectado**.

    ★★ Mismo razonamiento que `lobby_pareja.avisar_a_mi_pareja` y que
      `lobby_social.avisar_a_mis_amigos`: sin esto, cada cliente muestra **el estado congelado del
      instante en que él entró**, y el foquito se queda como estaba para siempre.
    ⚠ A diferencia de la pareja, acá pueden ser varios — por eso el bucle. Siguen siendo pocos
      (`ALMA_TOPE`), así que es barato.
    """
    if not AMIGO_DEL_ALMA:
        return
    try:
        _yo = int(getattr(st, "usn", 0) or 0)
        if not _yo:
            return
        _n = 0
        for _f in (db_almas_de(_yo) or []):
            _otro = int(_f.get("otro_uid") or 0)
            _c = CONEXIONES.get(_otro)
            if _c is None or getattr(_c, "cerrado", False) or _c is st:
                continue
            # ★ El paquete se arma desde la vista del OTRO: el que lo recibe es `_otro`, así que
            #   el que se movió soy YO. Invertirlo es el copiar-pegar que más caro sale, y la
            #   pareja ya lo tiene anotado con esas mismas palabras.
            if avisar_presencia_del_alma(_c, _yo, f" ({motivo})"):
                _n += 1
            # ★★★ Y LA MITAD QUE FALTABA, vista en el log del 2026-09-15:
            #
            #     13:29:36  jugador50 entra   -> jugador1 todavía NO estaba conectada
            #     13:29:39  jugador1 entra   -> le avisa a jugador50  ✔
            #                                   …y jugador50 nunca le avisó a ella  ⛔
            #
            #   El que entra PRIMERO le cuenta a nadie, y el que entra SEGUNDO sólo avisa. ⇒ El
            #   primero se queda sin saber del segundo **para siempre**.
            #   ⚠ Amigos y pareja no tienen este agujero porque el cliente les pide la lista y el
            #     `FF4A`; el alma no pide nada, así que las dos mitades las tenemos que mandar
            #     nosotros. ⇒ Al entrar, también **recibo** la presencia de los que ya están.
            if motivo != "se fue":
                avisar_presencia_del_alma(st, _otro, " (ya estaba conectado)")
        if _n:
            log("LOBBY", f"  ★ ALMA: usn={_yo} {motivo} -> presencia avisada a {_n} "
                         f"amigo(s) del alma")
    except Exception as e:                                         # noqa: BLE001
        log("LOBBY", f"  ⛔ avisar_a_mis_almas reventó: {e!r}")


def cuantos_del_alma(uid):
    """Cuántos amigos del alma tiene. Lo usa el panel y el banco."""
    return len(db_almas_de(int(uid or 0)) or [])
