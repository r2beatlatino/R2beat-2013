# -*- coding: utf-8 -*-
"""multicuenta — tope de cuentas conectadas A LA VEZ desde la misma IP.

Hay programas externos que abren varias cuentas en el mismo PC para farmear Rcoin y exp. Al entrar al lobby
(`FF02`, `lobby.handle_lobby`) se cuentan las cuentas DISTINTAS que ya están conectadas desde esa IP; si con la
nueva se pasaría `MAX_CUENTAS_POR_IP`, no se la deja entrar (y queda en el log). La IP es la que ve el server
(`st.addr`), no la que dice el cliente: un cliente tocado no la puede cambiar.

El mismo jugador NO suma: re-loguear, cambiar de canal o de personaje es la misma cuenta. Las IP de
`IPS_SIN_TOPE` (cybers, casas con varios jugadores) y loopback no tienen tope. Ver `ajustes.MAX_CUENTAS_POR_IP`.
"""
import ipaddress

from .ajustes import IPS_SIN_TOPE, MAX_CUENTAS_POR_IP
from .registro import log


def es_loopback(ip):
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def cuentas_de_ip(ip, conexiones, cuenta_de, menos=None):
    """Las CUENTAS distintas conectadas ahora desde `ip`, sin contar `menos` (la que está entrando).

    `conexiones` = {usn: st} (`salas.CONEXIONES`); `cuenta_de(usn)` -> la cuenta de ese personaje. Las sesiones
    ya cerradas o reemplazadas por un doble login no cuentan."""
    cuentas = set()
    for st in list(conexiones.values()):
        if getattr(st, "cerrado", False) or getattr(st, "reemplazada", False) or getattr(st, "gm_npc", None):
            continue                          # ★ 27-nov: la GM NPC (del moderador) no le suma a su IP
        addr = getattr(st, "addr", None)
        if not addr or addr[0] != ip:
            continue
        cuenta = cuenta_de(getattr(st, "usn", None))
        if cuenta != menos:
            cuentas.add(cuenta)
    return cuentas


def supera_tope(ip, cuenta, conexiones, cuenta_de, tope=None, libres=None):
    """True si entrar con `cuenta` desde `ip` pasaría el tope de cuentas a la vez. Pura (salvo `cuenta_de`)."""
    tope = MAX_CUENTAS_POR_IP if tope is None else tope
    libres = IPS_SIN_TOPE if libres is None else libres
    if not tope or not ip or ip in libres or es_loopback(ip):
        return False
    return len(cuentas_de_ip(ip, conexiones, cuenta_de, menos=cuenta)) >= tope


def cuenta_de(usn):
    """La cuenta (username) del personaje; si no tiene, su usn: así cada uno cuenta como una cuenta."""
    try:
        from . import almacen
        return almacen.cuenta_de_uid(usn)[0] or f"usn:{usn}"
    except Exception:                         # noqa: BLE001
        return f"usn:{usn}"


def rechazar_por_tope(st, usn):
    """Al entrar al lobby: True (y queda en el log) si esta cuenta pasaría el tope de su IP. El llamador cierra."""
    from .salas import CONEXIONES
    addr = getattr(st, "addr", None)
    ip = addr[0] if addr else None
    cuenta = cuenta_de(usn)
    if not supera_tope(ip, cuenta, CONEXIONES, cuenta_de):
        return False
    ya = sorted(cuentas_de_ip(ip, CONEXIONES, cuenta_de, menos=cuenta))
    log("LOBBY", f"  ⛔ MULTICUENTA: ip={ip} ya tiene {len(ya)} cuenta(s) conectada(s) {ya} -> "
                 f"no entra {cuenta} (usn={usn}, tope {MAX_CUENTAS_POR_IP})")
    return True
