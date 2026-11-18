# -*- coding: utf-8 -*-
"""antitrampa — lo que el server comprueba del cartel sin creerle al cliente.

El cliente manda en el `FF28` su frame de llegada, combo, pd y star. Acá se contrasta con lo que el
server sabe por su cuenta: el chart que él mismo sirvió (`notas.combo_total_de`) y el reloj propio
desde que mandó el GO. Las reglas y qué hacer con cada una están en `ANTITRAMPA_REGLAS` (`ajustes.py`).

Va abierto, como todo el server (AGPL): por eso sólo se comprueba lo que un cliente tocado NO puede
arreglar sabiendo la regla. El combo no puede pasar el total del chart y el reloj del server no lo
mueve el cliente.
"""
import datetime
import json
import os
import re
import threading
import time

from .ajustes import (
    ANTITRAMPA,
    ANTITRAMPA_ARCHIVO,
    ANTITRAMPA_EXE_MD5,
    ANTITRAMPA_FF3D0_MIN,
    ANTITRAMPA_LENTO_FACTOR,
    ANTITRAMPA_LENTO_MARGEN_S,
    ANTITRAMPA_REGLAS,
    ANTITRAMPA_RELOJ_MARGEN_S,
    ANTITRAMPA_RELOJ_TOLERANCIA,
)
from .registro import log

FPS = 60
FRAME_SIN_META = 0xFFFFFFFF
_archivo_lock = threading.Lock()
# ★ Por usn y no por conexión: el cambio de canal abre otra conexión y la dll no repite su «hola» (el juego sigue
#   abierto). `{usn: {"hola": bool, "retener": bool, "sin_hola_avisado": bool}}`. Un «hola» nuevo = juego reabierto.
_CUENTAS = {}
_cuentas_lock = threading.Lock()
_R2AT = re.compile(r"R2AT((?: \w+=\S+)+)")


def marcar_salida(conn, ahora=None):
    """Anota en la conexión el instante del GO. Lo llama `dar_el_go`, una vez por jugador."""
    conn.at_go = time.monotonic() if ahora is None else ahora


def marcas_del_cartel(frame, combo, pd, star, combo_total, transcurrido, relevo=False, coop=False):
    """Las reglas que rompe un reporte `FF28`. `[(regla, detalle), …]`; vacía si está limpio.

    `pd` y `star` son los bytes CRUDOS del paquete (antes del tope a 100). `transcurrido` = segundos
    desde el GO según el server, o `None` si no se sabe. Función pura: no loguea ni avisa.
    """
    marcas = []
    if pd > 100 or star > 100:
        marcas.append(("porcentaje_imposible", f"pd={pd} star={star} (tope 100)"))
    if not coop and combo_total is not None and combo > combo_total:
        marcas.append(("combo_imposible", f"combo {combo} > {combo_total} notas del chart"))
    if transcurrido is not None and frame not in (0, FRAME_SIN_META) and not coop:
        juego_s = frame / FPS
        tope = transcurrido * (1 + ANTITRAMPA_RELOJ_TOLERANCIA) + ANTITRAMPA_RELOJ_MARGEN_S
        if juego_s > tope:
            marcas.append(("reloj_rapido", f"el juego contó {juego_s:.1f} s y pasaron {transcurrido:.1f} s "
                                           f"({juego_s / max(transcurrido, 0.001):.0%})"))
        elif not relevo and juego_s < transcurrido * ANTITRAMPA_LENTO_FACTOR - ANTITRAMPA_LENTO_MARGEN_S:
            marcas.append(("reloj_lento", f"el juego contó {juego_s:.1f} s y pasaron {transcurrido:.1f} s "
                                          f"({juego_s / max(transcurrido, 0.001):.0%})"))
    return marcas


def juzgar_cartel(st, frame, combo, pd, star, cancion, relevo=False, coop=False, ahora=None):
    """Revisa el `FF28` de `st` y actúa según `ANTITRAMPA_REGLAS`. Devuelve True si hay que RETENER el premio."""
    if not ANTITRAMPA:
        return False
    clave = (frame, combo, pd, star)
    previo = getattr(st, "at_ultimo", None)
    if previo is not None and previo[0] == clave:     # el reintento del cliente o el reloj del cartel
        return previo[1]
    retener = _revisar_cuenta(st)
    try:
        from . import notas
        combo_total = notas.combo_total_de(cancion) if cancion else None
        go = getattr(st, "at_go", None)
        st.at_go = None                       # el próximo FF28 sin GO nuevo no se compara con éste
        transcurrido = None if go is None else (time.monotonic() if ahora is None else ahora) - go
        marcas = marcas_del_cartel(frame, combo, pd, star, combo_total, transcurrido, relevo, coop)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude revisar el FF28 de usn={getattr(st, 'usn', None)}: {e!r}")
        return retener
    for regla, detalle in marcas:
        retener |= anotar(st, regla, detalle, {"cancion": cancion, "frame": frame, "combo": combo,
                                               "pd": pd, "star": star}) == "retener"
    st.at_ultimo = (clave, retener)
    return retener


def _revisar_cuenta(st):
    """Antes de juzgar un FF28: ¿la cuenta tiene el premio retenido por lo que informó su dll? Y si nunca dijo «hola»,
    se anota una vez (`sin_antitrampa`)."""
    usn = getattr(st, "usn", None)
    if not usn:
        return False
    with _cuentas_lock:
        c = _CUENTAS.setdefault(usn, {"hola": False, "retener": False, "sin_hola_avisado": False})
        avisar_sin_hola = not c["hola"] and not c["sin_hola_avisado"]
        c["sin_hola_avisado"] |= avisar_sin_hola
        retener = c["retener"]
    if avisar_sin_hola:
        anotar(st, "sin_antitrampa", "terminó una carrera sin que su dll mandara el «hola» del antitrampa", {})
    if retener:
        log("TRAMP", f"  🚩 usn={usn}: premio retenido por lo que informó su cliente en esta sesión")
    return retener


def al_ff59(st, texto):
    """Un renglón «R2AT …» de la dll (antitrampa.c). Devuelve True si era uno (el FF59 ya está atendido)."""
    m = _R2AT.search(texto)
    if not m:
        return False
    if not ANTITRAMPA or not getattr(st, "usn", None):
        return True
    d = dict(par.split("=", 1) for par in m.group(1).split())
    if "v" in d:
        with _cuentas_lock:
            _CUENTAS[st.usn] = {"hola": True, "retener": False, "sin_hola_avisado": False}
        log("TRAMP", f"  ★ usn={st.usn}: antitrampa del cliente v{d['v']} · exe {d.get('exe')} · previo={d.get('previo')}")
        if d.get("exe") not in ANTITRAMPA_EXE_MD5:
            anotar(st, "exe_desconocido", f"R2Beat.exe con md5 {d.get('exe')}", {"exe": d.get("exe")})
        if d.get("previo", "0") not in ("0", "-1"):
            anotar(st, "codigo_previo", f"{d['previo']} página(s) del exe ya tocadas al abrir el juego, la primera "
                                        f"en {d.get('previo_va')}", {})
    elif "codigo" in d:
        anotar(st, "codigo_modificado", f"{d.get('paginas')} página(s) del exe tocadas por fuera, la primera en "
                                        f"{d['codigo']}: {d.get('bytes', '').replace('_', ' ')}", {})
    elif "modulo" in d:
        anotar(st, "modulo_prohibido", f"tiene cargado {d['modulo']}", {})
    elif "memoria" in d:
        anotar(st, "memoria_ajena", f"{d.get('regiones')} región(es) de memoria ejecutable ajena, "
                                    f"la primera en {d['memoria']}", {})
    elif "depurador" in d:
        anotar(st, "depurador", "un depurador enganchado al juego", {})
    else:
        log("TRAMP", f"  ? usn={st.usn}: renglón R2AT que no conozco: {m.group(0)!r}")
    return True


def al_ff3d(st, data):
    """Cuenta los FF3D(0). Tras `ANTITRAMPA_FF3D0_MIN` en una sesión, una sola marca."""
    if not ANTITRAMPA or bytes(data[:1]) != b"\x00":
        return
    n = getattr(st, "at_ff3d0", 0) + 1
    st.at_ff3d0 = n
    if n == ANTITRAMPA_FF3D0_MIN:
        anotar(st, "animaciones_tocadas",
               f"{n} FF3D(0): las 112 animaciones de tropezar no coinciden con las del server", {})


def anotar(st, regla, detalle, extra):
    """Aplica la acción de la regla. Devuelve la acción (`"retener"`, `"avisar"`, …)."""
    accion = ANTITRAMPA_REGLAS.get(regla, "registrar")
    if accion == "apagado":
        return accion
    usn = getattr(st, "usn", None)
    nick = _nick(usn)
    log("TRAMP", f"  🚩 {regla} [{accion}] usn={usn} {nick!r}: {detalle}")
    _guardar({"cuando": datetime.datetime.now().isoformat(timespec="seconds"), "regla": regla,
              "accion": accion, "usn": usn, "nick": nick, "sala": getattr(st, "room_id", None),
              "detalle": detalle, **extra})
    if accion == "retener" and regla in _REGLAS_DE_CUENTA and usn:
        with _cuentas_lock:
            _CUENTAS.setdefault(usn, {"hola": True, "retener": False, "sin_hola_avisado": False})["retener"] = True
    if accion in ("retener", "avisar"):
        _avisar_gms(f"ANTITRAMPA {regla}: {nick or usn} — {detalle}"
                    + (" (premio retenido)" if accion == "retener" else ""))
    return accion


# Las que informa el cliente fuera de una carrera: si son «retener», retienen todas las de la sesión.
_REGLAS_DE_CUENTA = {"modulo_prohibido", "codigo_modificado", "codigo_previo", "exe_desconocido", "memoria_ajena",
                     "depurador", "animaciones_tocadas"}


def _nick(usn):
    if not usn:
        return ""
    try:
        from .basedatos import db_get_char
        return (db_get_char(int(usn)) or {}).get("nick", "")
    except Exception:                         # noqa: BLE001
        return ""


def _guardar(fila):
    try:
        with _archivo_lock:
            os.makedirs(os.path.dirname(ANTITRAMPA_ARCHIVO), exist_ok=True)
            with open(ANTITRAMPA_ARCHIVO, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except OSError as e:
        log("TRAMP", f"  ⚠ no pude escribir {ANTITRAMPA_ARCHIVO}: {e!r}")


def _avisar_gms(texto):
    try:
        from .gm import es_gm
        from .salas import CONEXIONES, avisar_a_uno
        for c in list(CONEXIONES.values()):
            if c is not None and es_gm(c):
                avisar_a_uno(c, texto)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude avisar a los GM: {e!r}")
