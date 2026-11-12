# -*- coding: utf-8 -*-
"""referido — «¿Quién te invitó?» (`FFE2`): el nuevo escribe el apodo de quien lo trajo y ése cobra Rcoin.

★ 11-oct, anonimo03: *«el que invitó reciba 5k de rcoin, y por ahora dejarlo hasta ahí»*. Doc:
  `documentacion/REFERIDO.md` · prueba: `pruebas/probar_referido.py`.

CÓMO LO ARMÓ EL JUEGO (todo del exe 2013, sin parches)
  1. Al CREAR el personaje, el handler del `FF04` (`0x5E71D0`, rama de éxito) abre SIEMPRE el popup 0x32 =
     `cPopup_RecommandRegist` (la imagen `rnr_ui/popup/event_popup01.spr`, ya traducida: «¿Quién te invitó?»).
  2. OK con un nombre -> `FFE2 [u8 largo][apodo]` (`0x42E750` -> `0x5D87C0`) y la ventana se cierra a ESPERAR.
     «Omitir» -> `FFE2 "%%1skip"` (o `%%2skip`) y el juego sigue SOLO (no espera nada).
  3. La respuesta S→C `FFE2 [u8 resultado][u8 largo][apodo]` (`0x5D8970`):
        resultado 0 -> texto 656 «%s ha sido registrado como el que lo invitó» y, con su OK, el juego sigue;
        otro       -> texto 655 «No existe el Nickname…» y LE VUELVE A ABRIR la ventana (puede omitir).
     ⛔ Hasta hoy no se contestaba: el que escribía un nombre quedaba en la pantalla de crear personaje
       (en prod, ~28 de 162 entre el 29-sep y el 11-oct).
  4. Al que invitó, si está conectado: `FF40 [0x38][u8 largo][apodo del nuevo]` (caso `0x5EE87A`) -> texto 657
     «<nuevo> ha sido registrado <vos> como el que lo invitó». Y su saldo nuevo con `FFAB [u32]` (`0x5D6D20`: sólo
     fija `[player+0x2d8]`, sin cartel).

Lo que el juego trae y NO se usa todavía: el premio al llegar el invitado a NVL5 (`FF40 0x39`, el cartel
«Felicitaciones… 500 Rcoins» de `event_popup02`) y los Mong por 10/25/50 invitados. Ver el doc.

LAS REGLAS (las del server, no del cliente)
  · Sólo una vez por cuenta, y sólo una cuenta que CREÓ su personaje con esto andando (la fila de `referidos`
    nace en el `FF04`) y dentro de `REFERIDO_VENTANA_S`. Una cuenta vieja no puede cobrarle a nadie.
  · No a uno mismo. El apodo no es único (203 repetidos): entre varios, el conectado; si no, el de más EXP.
  · ⚠ Misma IP PÚBLICA que el que invitó (si está conectado) -> no. Las IP de la LAN/locales no cuentan: así se
    prueba con dos clientes en la misma PC. Antes de prod hay que decidir más reglas (ver el doc, §4).
"""
import ipaddress
import struct
import time

from .ajustes import REFERIDO_ACTIVO, REFERIDO_RCOIN, REFERIDO_VENTANA_S
from .basedatos import db_add_rcoin, db_get_char, db_uids_por_nick
from . import almacen
from .registro import log

OK, FALLA = 0, 1


def _str8(s):
    b = str(s or "").encode("cp1252", "replace")[:0x3F]
    return bytes([len(b)]) + b


def armar_ffe2(resultado, apodo=""):
    """S→C `FFE2 [u8 resultado][u8 largo][apodo]` (handler `0x5D8970`)."""
    return bytes([resultado & 0xFF]) + _str8(apodo if resultado == OK else "")


def armar_ff40_38(apodo_nuevo):
    """S→C `FF40 [0x38][u8 largo][apodo]`: al que invitó, el texto 657 (caso `0x5EE87A`)."""
    return bytes([0x38]) + _str8(apodo_nuevo)


def leer_ffe2(data):
    """C→S `FFE2 [u8 largo][apodo]` -> el apodo (cp1252), o None si no cierra."""
    if not data or len(data) < 1 + data[0]:
        return None
    return data[1:1 + data[0]].decode("cp1252", "replace").strip()


def _ip_publica(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local)


def al_crear(usn):
    """El `FF04` creó el personaje: el cliente va a abrir «¿Quién te invitó?». Se anota que puede contestar."""
    if REFERIDO_ACTIVO and usn:
        almacen.referido_pendiente(int(usn), time.time())


def _elegir(nick, yo):
    """-> (uid, cuántos coincidían). Entre apodos repetidos: el conectado, si no el de más EXP."""
    from .salas import CONEXIONES
    todos = [u for u in db_uids_por_nick(nick) if u != yo]
    if not todos:
        return None, 0
    vivos = [u for u in todos if u in CONEXIONES and not getattr(CONEXIONES[u], "cerrado", False)]
    if vivos:
        return vivos[0], len(todos)
    return max(todos, key=lambda u: int((db_get_char(u) or {}).get("exp", 0) or 0)), len(todos)


def atender(st, data):
    """C→S `FFE2`. Contesta al nuevo y, si vale, le paga al que invitó."""
    from .salas import CONEXIONES
    yo = int(getattr(st, "usn", 0) or 0)
    nick = leer_ffe2(data)
    if nick is None:
        log("LOBBY", f"  ⚠ FFE2 que no cierra de usn={yo}: {bytes(data).hex(' ')}")
        return
    if nick.startswith("%%") and nick.endswith("skip"):
        omitio = almacen.referido_omitir(yo)                  # el cliente sigue solo: no se contesta
        log("LOBBY", f"  🤝 FFE2 usn={yo} OMITIÓ ({nick!r}){'' if omitio else ' — no tenía la ventana pendiente'}")
        return

    def fallar(por):
        st.send_ff55(0xE2, armar_ffe2(FALLA), name=f"FFE2 referido NO ({por})")
        log("LOBBY", f"  🤝 FFE2 usn={yo} escribió {nick!r} -> NO: {por} (el cliente reabre la ventana)")

    if not REFERIDO_ACTIVO:
        return fallar("REFERIDO_ACTIVO = False")
    fila = almacen.referido_de(yo)
    if fila is None:
        return fallar("esta cuenta no creó su personaje con el referido andando")
    if fila["invitador"] is not None:
        return fallar("ya contestó antes" + (f" (invitador uid={fila['invitador']})" if fila["invitador"] else " (omitió)"))
    if time.time() - float(fila["creado"]) > REFERIDO_VENTANA_S:
        return fallar(f"pasaron más de {REFERIDO_VENTANA_S} s desde que creó el personaje")
    yo_nick = str((db_get_char(yo) or {}).get("nick", "") or "")
    if nick.lower() == yo_nick.lower():
        return fallar("se escribió a sí mismo")
    inv, n = _elegir(nick, yo)
    if inv is None:
        return fallar("no existe ese apodo")
    mi_ip = (getattr(st, "addr", None) or ("",))[0]
    st_inv = CONEXIONES.get(inv)
    su_ip = (getattr(st_inv, "addr", None) or ("",))[0] if st_inv is not None else ""
    if mi_ip and mi_ip == su_ip and _ip_publica(mi_ip):
        return fallar(f"misma IP pública que el que invitó ({mi_ip})")
    if not almacen.referido_registrar(yo, inv, nick, REFERIDO_RCOIN, mi_ip):
        return fallar("otra respuesta le ganó (ya registrado)")

    saldo = db_add_rcoin(inv, REFERIDO_RCOIN)
    inv_nick = str((db_get_char(inv) or {}).get("nick", "") or nick)
    st.send_ff55(0xE2, armar_ffe2(OK, inv_nick), name=f"FFE2 referido OK: {inv_nick!r}")
    vivo = st_inv is not None and not getattr(st_inv, "cerrado", False)
    if vivo:
        try:
            st_inv.send_ff55(0x40, armar_ff40_38(yo_nick), name=f"FF40/0x38 te registró {yo_nick!r}")
            st_inv.send_ff55(0xAB, struct.pack("<I", saldo & 0xFFFFFFFF), name=f"FFAB saldo {saldo} (+{REFERIDO_RCOIN} referido)")
        except Exception as e:                                # noqa: BLE001
            log("LOBBY", f"  ⚠ no pude avisarle al que invitó (uid={inv}): {e!r}")
    log("LOBBY", f"  🤝★ FFE2 usn={yo} ({yo_nick!r}) registró a {inv_nick!r} (uid={inv}"
                 f"{f', 1 de {n} con ese apodo' if n > 1 else ''}) como el que lo invitó -> "
                 f"+{REFERIDO_RCOIN} Rcoin, saldo {saldo} ({'avisado en vivo' if vivo else 'desconectado: lo ve al entrar'})")
