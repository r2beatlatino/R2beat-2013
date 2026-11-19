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
import socket
import statistics
import threading
import time
from collections import deque

from .ajustes import (
    ANTITRAMPA,
    ANTITRAMPA_ANUNCIO,
    ANTITRAMPA_ANUNCIO_PUBLICO,
    ANTITRAMPA_ARCHIVO,
    ANTITRAMPA_BLOQUEO_S,
    ANTITRAMPA_CAMPANAS_SEGUIDAS,
    ANTITRAMPA_COMBO_MINIMO,
    ANTITRAMPA_COMBO_VECES,
    ANTITRAMPA_EXE_MD5,
    ANTITRAMPA_GANCHOS,
    ANTITRAMPA_EXPULSIONES,
    ANTITRAMPA_EXPULSIONES_S,
    ANTITRAMPA_FARMEO_SENALES,
    ANTITRAMPA_FF3D0_MIN,
    ANTITRAMPA_LENTO_FACTOR,
    ANTITRAMPA_LENTO_MARGEN_S,
    ANTITRAMPA_LISTO_DESVIO_S,
    ANTITRAMPA_LISTO_MUESTRAS,
    ANTITRAMPA_MISMA_CANCION,
    ANTITRAMPA_PRECISION_CARRERAS,
    ANTITRAMPA_PRECISION_NIVELES,
    ANTITRAMPA_PRECISION_RANGO,
    ANTITRAMPA_REGLAS,
    ANTITRAMPA_RELOJ_MARGEN_S,
    ANTITRAMPA_RELOJ_TOLERANCIA,
    ANTITRAMPA_SIN_HABLAR,
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
                                               "pd": pd, "star": star}) in _QUE_RETIENEN
    retener |= _farmeo_al_cartel(st, cancion, combo, pd, ahora) in _QUE_RETIENEN
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
        retener = c["retener"] or _BLOQUEADOS.get(usn, 0) > time.monotonic()
    if avisar_sin_hola:
        anotar(st, "sin_antitrampa", "terminó una carrera sin que su dll mandara el «hola» del antitrampa", {})
    if retener:
        log("TRAMP", f"  🚩 usn={usn}: premio retenido por lo que informó su cliente en esta sesión")
    return retener


# Los ganchos que reconocemos (la dll los informa con «gancho=<nombre>»): nombre -> regla.
_GANCHOS = {"automatico": "juego_automatico"}


def _va(texto):
    try:
        return int(texto, 16)
    except ValueError:
        return -1


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
    elif "gancho" in d:                                    # un gancho conocido de un programa de trampas
        regla = _GANCHOS.get(d["gancho"], "codigo_modificado")
        anotar(st, regla, f"gancho «{d['gancho']}» en {d.get('va')}: {d.get('bytes', '').replace('_', ' ')}", {})
    elif "codigo" in d and _va(d["codigo"]) in ANTITRAMPA_GANCHOS:   # dll sin «gancho=»: por la dirección
        anotar(st, _GANCHOS[ANTITRAMPA_GANCHOS[_va(d["codigo"])]],
               f"gancho «{ANTITRAMPA_GANCHOS[_va(d['codigo'])]}» en {d['codigo']}: "
               f"{d.get('bytes', '').replace('_', ' ')}", {})
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
    elif "inyectadas" in d:
        _senal(st, "teclas_inyectadas", f"{d['inyectadas']} de {d.get('teclas', '?')} teclas las mandó un programa")
    elif "hilo" in d:
        anotar(st, "hilo_ajeno", f"un hilo del juego arranca en memoria inyectada ({d['hilo']})", {})
    elif "proceso" in d:
        anotar(st, "proceso_prohibido", f"tiene abierto {d['proceso']}", {})
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
    if accion == "expulsar":
        _expulsar(st, usn, nick, regla, detalle)
    return accion


# Las que informa el cliente fuera de una carrera: si son «retener», retienen todas las de la sesión.
_REGLAS_DE_CUENTA = {"modulo_prohibido", "juego_automatico", "codigo_modificado", "codigo_previo", "exe_desconocido", "memoria_ajena",
                     "depurador", "animaciones_tocadas"}
_QUE_RETIENEN = ("retener", "expulsar")
_BLOQUEADOS = {}                              # usn -> time.monotonic() hasta el que no puede jugar


def _expulsar(st, usn, nick, regla, detalle):
    """Aviso al jugador, anuncio, bloqueo y fuera. El cierre va un segundo después: que le lleguen los avisos."""
    if usn:
        _BLOQUEADOS[usn] = time.monotonic() + ANTITRAMPA_BLOQUEO_S
        _FARMEO.pop(usn, None)                # al volver, el farmeo se cuenta de cero (y puede volver a saltar)
    _avisar_gms(f"ANTITRAMPA {regla}: {nick or usn} EXPULSADO ({ANTITRAMPA_BLOQUEO_S // 60} min) — {detalle}")
    anuncio = ANTITRAMPA_ANUNCIO.format(nick=nick or f"usn {usn}")
    try:
        from .salas import CONEXIONES, avisar_a_uno
        conn = CONEXIONES.get(usn) or st
        avisar_a_uno(conn, f"Fuiste expulsado por el antitrampa ({regla}). Podés volver en "
                           f"{ANTITRAMPA_BLOQUEO_S // 60} minutos.")
        if ANTITRAMPA_ANUNCIO_PUBLICO:
            for c in list(CONEXIONES.values()):
                if c is not None and c is not conn:
                    avisar_a_uno(c, anuncio)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude avisar la expulsión de usn={usn}: {e!r}")
        conn = st
    t = threading.Timer(1.0, cerrar_conexion, args=(conn, f"expulsado por {regla}"))
    t.daemon = True
    t.start()


def cerrar_conexion(conn, motivo):
    """`shutdown` y no `close`, como el cambio de canal: el hilo de la conexión sale por su camino normal."""
    log("TRAMP", f"  ⛔ cierro la conexión de usn={getattr(conn, 'usn', None)}: {motivo}")
    conn.cerrado = True
    try:
        conn.conn.shutdown(socket.SHUT_RDWR)
    except Exception:                         # noqa: BLE001
        try:
            conn.conn.close()
        except Exception:                     # noqa: BLE001
            pass


def esta_bloqueado(st):
    """La cuenta fue expulsada y todavía no pasó el bloqueo."""
    usn = getattr(st, "usn", None)
    return bool(usn) and _BLOQUEADOS.get(usn, 0) > time.monotonic()


# ═══ SEÑALES DE FARMEO ═════════════════════════════════════════════════════════════════════════════════════════════
#   Por usn (sobrevive al cambio de canal). Cada señal se anota una vez por sesión; con ANTITRAMPA_FARMEO_SENALES
#   distintas salta «farmeo». Los `al_*` los llaman los handlers; `ahora` es para las pruebas.
_FARMEO = {}
_farmeo_lock = threading.Lock()


def _estado(usn):
    return _FARMEO.setdefault(usn, {
        "fin": None, "reacciones": deque(maxlen=ANTITRAMPA_LISTO_MUESTRAS), "sin_hablar": 0,
        "cancion": None, "misma": 0, "campana_ronda": False, "campanas": 0,
        "combos": deque(maxlen=10), "precisiones": deque(maxlen=ANTITRAMPA_PRECISION_CARRERAS),
        "expulsiones": deque(maxlen=ANTITRAMPA_EXPULSIONES), "senales": set()})


def _ahora(ahora):
    return time.monotonic() if ahora is None else ahora


def _senal(st, regla, detalle):
    """Anota una señal (una vez por sesión) y, si ya van las suficientes, el «farmeo». Devuelve la acción más dura."""
    usn = getattr(st, "usn", None)
    with _farmeo_lock:
        e = _estado(usn)
        if regla in e["senales"]:
            return None
        e["senales"].add(regla)
        reales = sorted(s for s in e["senales"] if s != "farmeo"
                        and ANTITRAMPA_REGLAS.get(s, "registrar") not in ("apagado", "registrar"))
        farmeo = len(reales) >= ANTITRAMPA_FARMEO_SENALES and "farmeo" not in e["senales"]
        if farmeo:
            e["senales"].add("farmeo")
    accion = anotar(st, regla, detalle, {})
    if farmeo:
        accion = anotar(st, "farmeo", "señales: " + ", ".join(reales), {})
    return accion


def _farmeo_al_cartel(st, cancion, combo, pd, ahora=None):
    usn = getattr(st, "usn", None)
    if not usn:
        return None
    try:
        from . import notas
        nivel = notas.nivel_de(cancion) if cancion else None
    except Exception:                         # noqa: BLE001
        nivel = None
    senales = []
    with _farmeo_lock:
        e = _estado(usn)
        e["fin"] = _ahora(ahora)
        e["sin_hablar"] += 1
        e["misma"] = e["misma"] + 1 if cancion and cancion == e["cancion"] else 1
        e["cancion"] = cancion
        e["campanas"] = e["campanas"] + 1 if e["campana_ronda"] else 0
        e["campana_ronda"] = False
        if combo >= ANTITRAMPA_COMBO_MINIMO:
            e["combos"].append((combo, cancion))
        if nivel is not None and pd:
            e["precisiones"].append((pd, nivel))
        if e["sin_hablar"] >= ANTITRAMPA_SIN_HABLAR:
            senales.append(("carreras_sin_hablar", f"{e['sin_hablar']} carreras seguidas sin escribir en el chat"))
        if e["misma"] >= ANTITRAMPA_MISMA_CANCION:
            senales.append(("misma_cancion", f"la canción {cancion} {e['misma']} veces seguidas"))
        if e["campanas"] >= ANTITRAMPA_CAMPANAS_SEGUIDAS:
            senales.append(("campanas_automaticas", f"campana en {e['campanas']} rondas seguidas"))
        iguales = [c for c in e["combos"] if c[0] == combo]
        if (combo >= ANTITRAMPA_COMBO_MINIMO and len(iguales) >= ANTITRAMPA_COMBO_VECES
                and len({c[1] for c in iguales}) >= 3):
            senales.append(("combo_repetido", f"combo {combo} exacto en {len(iguales)} carreras de "
                                              f"{len({c[1] for c in iguales})} canciones distintas"))
        p = list(e["precisiones"])
        if len(p) >= ANTITRAMPA_PRECISION_CARRERAS:
            pds, niveles = [x[0] for x in p], [x[1] for x in p]
            if (max(niveles) - min(niveles) >= ANTITRAMPA_PRECISION_NIVELES
                    and max(pds) - min(pds) <= ANTITRAMPA_PRECISION_RANGO):
                senales.append(("precision_constante", f"precisión {min(pds)}–{max(pds)} en canciones de nivel "
                                                       f"{min(niveles)} a {max(niveles)}"))
    peor = None
    for regla, detalle in senales:
        accion = _senal(st, regla, detalle)
        if accion in _QUE_RETIENEN:
            peor = "expulsar"
    return peor


def al_listo(st, ahora=None):
    """«Listo» o «iniciar»: cuánto tardó desde su última llegada. Siempre lo mismo = lo aprieta un programa."""
    usn = getattr(st, "usn", None)
    if not ANTITRAMPA or not usn:
        return
    with _farmeo_lock:
        e = _estado(usn)
        if e["fin"] is None:
            return
        reaccion = _ahora(ahora) - e["fin"]
        e["fin"] = None                       # una reacción por carrera
        if not 0 < reaccion < 120:
            return
        e["reacciones"].append(reaccion)
        r = list(e["reacciones"])
    if len(r) >= ANTITRAMPA_LISTO_MUESTRAS and statistics.pstdev(r) < ANTITRAMPA_LISTO_DESVIO_S:
        _senal(st, "listo_automatico", f"{len(r)} carreras: listo/iniciar a los {statistics.mean(r):.2f} s "
                                       f"± {statistics.pstdev(r):.2f}")


def al_hablar(st):
    """Una línea de chat: hay alguien del otro lado."""
    usn = getattr(st, "usn", None)
    if usn:
        with _farmeo_lock:
            _estado(usn)["sin_hablar"] = 0


def al_campana(st):
    usn = getattr(st, "usn", None)
    if ANTITRAMPA and usn:
        with _farmeo_lock:
            _estado(usn)["campana_ronda"] = True


def al_expulsar_espectador(st, ahora=None):
    usn = getattr(st, "usn", None)
    if not ANTITRAMPA or not usn:
        return
    t = _ahora(ahora)
    with _farmeo_lock:
        ex = _estado(usn)["expulsiones"]
        ex.append(t)
        serie = len(ex) >= ANTITRAMPA_EXPULSIONES and t - ex[0] <= ANTITRAMPA_EXPULSIONES_S
    if serie:
        _senal(st, "expulsa_espectadores", f"{len(ex)} espectadores echados en {t - ex[0]:.0f} s")


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
