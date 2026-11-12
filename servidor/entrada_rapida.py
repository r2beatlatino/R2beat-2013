# -*- coding: utf-8 -*-
"""entrada_rapida — «Ingreso Rápido» del lobby (`FF72`, `CmdQuickJoin2`), 12-oct.

El botón caía en «SIN handler»: 2.002 veces del 25 al 28-sep y 1.712 del 29-sep al 11-oct (`FF_PENDIENTES.md`).
anonimo03: *«debería llevar a una sala abierta y disponible, aleatoriamente»* — sí, respetando el cuadro «Configuraciones de
ingreso rápido» de al lado de la lista de salas. Doc: `documentacion/ENTRADA_RAPIDA.md` · prueba: `pruebas/probar_entrada_rapida.py`.

  C→S `FF72 [u8 canal][u8 modos][u8 ?][u8 licencias][u8 colab][u8 jefe]` (emisor `0x5D1D30`, botón `0x4A35F0`):
      canal     = `[roommgr+0x12E8]` (13 en Carrera Libre, como el tipo del `FF6E`)
      modos     = `[roommgr+0x12BD]`, leído de dónde dibuja la tilde de cada casilla (`0x4A1EE0`…):
                  0x10 PERSONAL · 0x08 EQUIPO · 0x20 RELEVOS (columna izq.) · 0x02 VELOCIDAD · 0x04 ÍTEM (der.)
      ?         = `[0x9040A0]` = `[QUICKJOIN] JOIN` del Config.ini del cliente (1)
      licencias = las estrellitas `[roommgr+0x466C]` (bit 0 = licencia 1…), 0xFF fuera del canal 13
      colab · jefe = los bits 2 y 3 de `[roommgr+0x12BF]` (MODO COLABORACIÓN · MODO JEFE)
  S→C `FF72 [u8]` (RX `0x5D1600`): < 6 = el asiento (entra) · 100..106 = carteles · el resto = popup 303 «No hay salas
      disponibles. ¿Desea crear una?» con OK → crear sala (`0x5C5ED0`).

  ⚠ El «entra» del `FF72` cambia de escena pero NO llama a `SetRoomType` (`0x58D3D0`), que el `FF11` sí: los ~7 sitios
    del cliente que preguntan «¿estoy en una sala de carrera?» quedarían con lo que hubiera. ⇒ Se entra por el `FF11`
    de siempre (`lobby_salas.h_18_ff11` con un pedido armado acá, tipo 13): mismo asiento, misma clave, mismos avisos.
    Si el `FF11` no lo sienta, el cartel es el del `FF11` («No hay lugares suficientes…»), sin un 2.º.
"""
import random
import struct

from .registro import log

PERSONAL, EQUIPO, RELEVOS, VELOCIDAD, ITEM = 0x10, 0x08, 0x20, 0x02, 0x04
NO_HAY_SALAS = 0xFF            # cae en el popup 303 «No hay salas disponibles. ¿Desea crear una?»
TIPO_CARRERA = 0x0D


def leer(data):
    """`FF72` C→S -> dict o None."""
    if len(data) < 6:
        return None
    canal, modos, join, lic, colab, jefe = data[:6]
    return {"canal": canal, "modos": modos, "join": join, "lic": lic, "colab": colab, "jefe": jefe}


def pasa_modo(sala, pedido):
    """¿La sala es de un modo que el jugador dejó marcado? (`B` = el byMode de la lista: 0x04 ítem · 0x10 equipo ·
    0x80 relevo; `M` cooperativo · `O` jefe)."""
    if sala.get("M"):
        return bool(pedido["colab"])
    if sala.get("O"):
        return bool(pedido["jefe"])
    b, m = int(sala.get("B", 0) or 0), pedido["modos"]
    vel = (m & ITEM) if b & 0x04 else (m & VELOCIDAD)
    if b & 0x80:
        tipo = m & RELEVOS
    elif b & 0x10:
        tipo = m & EQUIPO
    else:
        tipo = m & PERSONAL
    return bool(vel and tipo)


def candidatas(st, pedido):
    """Las salas de su canal a las que se puede entrar ya: esperando, con lugar, sin clave, del modo y la licencia
    que marcó. -> [fila de SALAS_VIVAS]."""
    from .lobby_salas import _pasa_el_filtro, _tope_de_casillas
    from .salas import CLAVE_SALA, SALAS_VIVAS
    canal = getattr(st, "canal", None)
    tope = _tope_de_casillas(getattr(st, "usn", 0))
    out = []
    for rid, s in list(SALAS_VIVAS.items()):
        if s.get("canal") not in (None, canal):
            continue
        if int(s.get("B", 0) or 0) & 0x02 or CLAVE_SALA.get(rid):
            continue
        if int(s.get("E", 0) or 0) >= int(s.get("G", 6) or 6) - 6:
            continue
        if not pasa_modo(s, pedido):
            continue
        if pedido["lic"] not in (0x00, 0xFF) and tope and not _pasa_el_filtro(s, pedido["lic"], tope):
            continue
        out.append(s)
    return out


def atender(st, data):
    from .ajustes import ENTRADA_RAPIDA
    from .lobby_salas import h_18_ff11
    usn = int(getattr(st, "usn", 0) or 0)
    pedido = leer(bytes(data))
    if pedido is None:
        return log("LOBBY", f"  ⚠ FF72 que no cierra de usn={usn}: {bytes(data).hex(' ')}")
    if getattr(st, "room_id", None):
        return log("LOBBY", f"  ⚡ FF72 usn={usn} ya está en la sala {st.room_id}: nada")
    lista = candidatas(st, pedido) if ENTRADA_RAPIDA else []
    if not lista:
        st.send_ff55(0x72, bytes([NO_HAY_SALAS]), name="FF72 no hay salas (popup 303)")
        return log("LOBBY", f"  ⚡ FF72 usn={usn} entrada rápida {bytes(data).hex(' ')} -> ninguna sala "
                            f"{'(apagado: ENTRADA_RAPIDA)' if not ENTRADA_RAPIDA else ''}-> «¿Desea crear una?»")
    sala = random.choice(lista)
    rid = int(sala["roomid"])
    a = ((TIPO_CARRERA & 0x1F) << 11) | (rid & 0x7FF)
    log("LOBBY", f"  ⚡★ FF72 usn={usn} entrada rápida {bytes(data).hex(' ')} -> {len(lista)} sala(s) posibles, "
                 f"le toca la {rid} ({sala.get('nombre', '')!r}): entra por el FF11")
    h_18_ff11(st, 0x11, struct.pack("<H", a) + b"\xff\xff\xff\xff" + b"\x01\x00" + bytes(5))
    if getattr(st, "room_id", None) != rid:
        # ⚠ sin un 2.º cartel: el FF11 ya le contestó el suyo («No hay lugares suficientes…», etc.)
        log("LOBBY", f"  ⚡ FF72 usn={usn}: el FF11 no lo sentó en la {rid} (ya le salió el cartel del FF11)")
