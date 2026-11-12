# -*- coding: utf-8 -*-
"""preferidos — «Mis preferidos» / «Mis Selecciones» de la tienda (el carrito): `FF6F` agregar · `FF70` sacar · `FF71`
la lista (12-oct). anonimo03: *«intenté usar el carrito o favorito»*: caía en «SIN handler» (en prod: 428 en 3 días).
Doc: `documentacion/REGALO.md` §4 · prueba: `pruebas/probar_regalo.py` §6.

  C→S `FF6F [u32 ítem]` → S→C `FF6F [u8 res][u32 ítem]` (`0x5E8FE0`): 0 «El ítem se ha guardado en Mis preferidos» (y lo
      anota en su lista) · 1 «No se puede guardar» · 2 «No puede coger el mismo ítem dos veces» · 3 «Puede guardar
      hasta %d» (el cliente pone 24)
  C→S `FF70 [u32 ítem]` → S→C `FF70 [u8 res][u32 ítem]` (`0x5D1540`): 0 «ha sido eliminado» (y lo saca) · 1/2 «no ha sido…»
  S→C `FF71 [u8 n][n × u32]` (`0x5E9140`): la lista entera (borra la suya y carga ésta) — se manda al entrar.
"""
import struct

from . import almacen
from .registro import hx, log

TOPE = 24                     # el «Puede guardar hasta %d» del cliente (0x5E90DA: push 0x18)
OK, NO_SE_PUEDE, REPETIDO, LLENO = 0, 1, 2, 3


def _item(data):
    return struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else None


def enviar_lista(st, motivo="al entrar"):
    if getattr(st, "_preferidos_enviados", False):
        return
    st._preferidos_enviados = True
    usn = int(getattr(st, "usn", 0) or 0)
    lista = almacen.preferidos_de(usn)
    if not lista:
        return
    st.send_ff55(0x71, bytes([len(lista)]) + b"".join(struct.pack("<I", x) for x in lista),
                 name=f"FF71 mis preferidos ({len(lista)}, {motivo})")


def sacar_regalado(dest, item):
    """★ 12-oct: le regalaron `item` a `dest` -> sale de su carrito. El cliente no lo hace solo (sólo borra con la
    respuesta al FF70, que además muestra «ha sido eliminado»): se le manda la lista ENTERA por FF71 (el handler
    `0x5E9140` borra la suya y carga ésta), sin cartel. En carrera o desconectado: sólo la base; la ve al entrar.
    -> qué pasó, para el log."""
    from .ajustes import REGALO_SACA_DE_PREFERIDOS
    from .salas import CONEXIONES
    if not REGALO_SACA_DE_PREFERIDOS or int(item) not in almacen.preferidos_de(dest):
        return ""
    almacen.sacar_preferido(dest, int(item))
    c = CONEXIONES.get(int(dest))
    if c is None or getattr(c, "cerrado", False) or getattr(c, "en_carrera", False):
        return f"· sale de sus preferidos (lo ve al entrar)"
    lista = almacen.preferidos_de(dest)
    c.send_ff55(0x71, bytes([len(lista)]) + b"".join(struct.pack("<I", x) for x in lista),
                name=f"FF71 mis preferidos ({len(lista)}, le regalaron el {item})")
    return f"· sale de sus preferidos (FF71 con {len(lista)})"


def sacar_comprado(st, item):
    """★ 28-oct (132): `st` compró `item` -> sale de SU carrito, y se le manda la lista entera por FF71 (sin cartel, como
    `sacar_regalado`). Es lo que vacía la tira del carrito de la tienda (`tienda.c`) después de «Comprar todo»."""
    from .ajustes import COMPRA_SACA_DE_PREFERIDOS
    usn = int(getattr(st, "usn", 0) or 0)
    if not COMPRA_SACA_DE_PREFERIDOS or not usn or int(item) not in almacen.preferidos_de(usn):
        return
    almacen.sacar_preferido(usn, int(item))
    lista = almacen.preferidos_de(usn)
    st.send_ff55(0x71, bytes([len(lista)]) + b"".join(struct.pack("<I", x) for x in lista),
                 name=f"FF71 mis preferidos ({len(lista)}, compró el {item})")
    log("LOBBY", f"  🛒 compró {item}: sale de su carrito (quedan {len(lista)})")


def atender(st, cmd, data):
    from . import shop_catalog
    usn = int(getattr(st, "usn", 0) or 0)
    raw = _item(data)
    if raw is None:
        log("LOBBY", f"  ⚠ FF{cmd:02X} preferidos que no cierra de usn={usn}: {hx(data)}")
        return
    lista = almacen.preferidos_de(usn)
    if cmd == 0x6F:
        item = shop_catalog.normalize_id(raw)
        if item is None:
            res = NO_SE_PUEDE
        elif item in lista:
            res = REPETIDO
        elif len(lista) >= TOPE:
            res = LLENO
        else:
            almacen.agregar_preferido(usn, item)
            res = OK
        st.send_ff55(0x6F, bytes([res]) + struct.pack("<I", (item or raw) & 0xFFFFFFFF), name=f"FF6F preferido {raw} res={res}")
        log("LOBBY", f"  🛒 FF6F usn={usn} agrega {raw} a Mis preferidos -> res={res} ({len(lista) + (res == OK)}/{TOPE})")
    else:
        item = shop_catalog.normalize_id(raw) or raw
        res = OK if almacen.sacar_preferido(usn, item) else NO_SE_PUEDE
        st.send_ff55(0x70, bytes([res]) + struct.pack("<I", item & 0xFFFFFFFF), name=f"FF70 saca {item} res={res}")
        log("LOBBY", f"  🛒 FF70 usn={usn} saca {item} de Mis preferidos -> res={res}")
