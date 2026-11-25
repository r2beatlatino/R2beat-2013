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
    ANTITRAMPA_ANUNCIO_BANEO,
    ANTITRAMPA_ANUNCIO_PUBLICO,
    ANTITRAMPA_ARCHIVO,
    ANTITRAMPA_BANEO_EN,
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
    ANTITRAMPA_LLEGADA_FACTOR,
    ANTITRAMPA_LLEGADA_HISTORIA,
    ANTITRAMPA_LLEGADA_MUESTRAS,
    ANTITRAMPA_MODULOS_PERMITIDOS,
    ANTITRAMPA_MISMA_CANCION,
    ANTITRAMPA_PRECISION_CARRERAS,
    ANTITRAMPA_PRECISION_NIVELES,
    ANTITRAMPA_PRECISION_RANGO,
    ANTITRAMPA_REGLAS,
    ANTITRAMPA_RELOJ_MARGEN_S,
    ANTITRAMPA_RELOJ_TOLERANCIA,
    ANTITRAMPA_SIN_HABLAR,
    ANTITRAMPA_SILENCIOSO,
    ANTITRAMPA_TANDA_DEMORA_H,
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


def marcas_del_cartel(frame, combo, pd, star, combo_total, transcurrido, relevo=False, coop=False,
                      milesimas=0, llegadas=None):
    """Las reglas que rompe un reporte `FF28`. `[(regla, detalle), …]`; vacía si está limpio.

    `pd` y `star` son los bytes CRUDOS del paquete (antes del tope a 100). `transcurrido` = segundos
    desde el GO según el server, o `None` si no se sabe. `milesimas` = las de la precisión (0..999).
    `llegadas` = los frame de las últimas llegadas limpias de esa canción (o None). Función pura: no loguea ni avisa.
    """
    marcas = []
    if pd > 100 or star > 100:
        marcas.append(("porcentaje_imposible", f"pd={pd} star={star} (tope 100)"))
    # ★ 24-nov (el laboratorio: «Precisión personalizada» escribe entero y milésimas): 100.000 es el tope.
    elif milesimas > 999 or (pd == 100 and milesimas > 0):
        marcas.append(("precision_imposible", f"precisión {pd}.{milesimas:03d} (tope 100.000)"))
    # ★ 24-nov («Simular llegada»): la meta se dispara cuando el cliente quiere. El frame cuadra con el reloj del
    #   server, pero la carrera duró mucho menos que las llegadas limpias de esa canción.
    if (llegadas and len(llegadas) >= ANTITRAMPA_LLEGADA_MUESTRAS and frame not in (0, FRAME_SIN_META)
            and not relevo and not coop):
        normal = statistics.median(llegadas)
        if frame < normal * ANTITRAMPA_LLEGADA_FACTOR:
            marcas.append(("llegada_anticipada", f"llegó a la meta en {frame / FPS:.1f} s; esa canción suele tardar "
                                                 f"{normal / FPS:.1f} s ({frame / max(normal, 1):.0%})"))
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


def juzgar_cartel(st, frame, combo, pd, star, cancion, relevo=False, coop=False, ahora=None, milesimas=0):
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
        cuenta = _cuenta_de(st)               # para no juzgarlo con sus propias llegadas (mediana envenenable)
        llegadas = _llegadas_de(cancion, excluir=cuenta)
        marcas = marcas_del_cartel(frame, combo, pd, star, combo_total, transcurrido, relevo, coop,
                                   milesimas=milesimas, llegadas=llegadas)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude revisar el FF28 de usn={getattr(st, 'usn', None)}: {e!r}")
        return retener
    # una llegada limpia (sin ninguna marca, con meta real, carrera suelta) enseña cuánto tarda la canción
    if not marcas and cancion and frame not in (0, FRAME_SIN_META) and not relevo and not coop and combo > 0:
        _anotar_llegada(cancion, frame, cuenta)
    for regla, detalle in marcas:
        retener |= anotar(st, regla, detalle, {"cancion": cancion, "frame": frame, "combo": combo,
                                               "pd": pd, "star": star}) in _QUE_RETIENEN
    retener |= _farmeo_al_cartel(st, cancion, combo, pd, ahora) in _QUE_RETIENEN
    st.at_ultimo = (clave, retener)
    return retener


def _cuenta_de(st):
    """La CUENTA (username) del jugador, para no juzgarlo con sus propias llegadas. None si no se sabe."""
    try:
        from . import almacen
        return almacen.cuenta_de_uid(getattr(st, "usn", None))[0]
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude ubicar la cuenta de usn={getattr(st, 'usn', None)}: {e!r}")
        return None


def _llegadas_de(cancion, excluir=None):
    if not cancion:
        return None
    try:
        from . import almacen
        return almacen.antitrampa_llegadas(cancion, ANTITRAMPA_LLEGADA_HISTORIA, excluir=excluir)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude leer las llegadas de la canción {cancion}: {e!r}")
        return None


def _anotar_llegada(cancion, frame, cuenta=None):
    try:
        from . import almacen
        almacen.antitrampa_anotar_llegada(cancion, frame, cuenta=cuenta)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude guardar la llegada de la canción {cancion}: {e!r}")


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
_GANCHOS = {"automatico": "juego_automatico", "sala": "sala_automatica", "relevo": "relevo_automatico",
            # ★ 24-nov: las rutas del laboratorio (INFORME_LABORATORIO.md §4-5)
            "tick_meta": "juego_automatico", "auto_normal": "juego_automatico", "pd0": "juego_automatico",
            "larga_a": "juego_automatico", "larga_b": "juego_automatico", "item_auto": "juego_automatico",
            "resultado": "resultado_alterado", "resultado_solo": "resultado_alterado"}


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
    elif "modulo" in d and d["modulo"].lower().startswith(ANTITRAMPA_MODULOS_PERMITIDOS):
        # ★ 19-nov: el motor de práctica de Ñ2Hock (ToolBitPracticeEngine_<hash>.dll): la dll del launcher
        #   todavía lo informa como «toolbit», pero NO es el ToolBit de trampas. Sólo queda registrado.
        anotar(st, "modulo_permitido", f"tiene cargado {d['modulo']} (permitido)", {})
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
        firma = f" (firma {d['firma']})" if "firma" in d else ""
        anotar(st, "proceso_prohibido", f"tiene abierto {d['proceso']}{firma}", {})
    elif "manija" in d:                                    # ★ 24-nov: un programa con permiso de escribir el juego
        anotar(st, "manija_escritura", f"{d['manija']} tiene abierto el juego con permiso de escribir su memoria "
                                       f"(acceso {d.get('acceso', '?')})", {})
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
_REGLAS_DE_CUENTA = {"modulo_prohibido", "juego_automatico", "sala_automatica", "relevo_automatico",
                     "codigo_modificado", "codigo_previo", "exe_desconocido", "memoria_ajena", "depurador",
                     "animaciones_tocadas"}
_QUE_RETIENEN = ("retener", "expulsar")
_BLOQUEADOS = {}                              # usn -> time.monotonic() hasta el que no puede jugar
_EXPULSADOS = {}                              # usn -> cuántas faltas tenía su cuenta al expulsarlo (esta sesión del server)


def fue_expulsado(st):
    """¿El antitrampa expulsó a este jugador (desde que arrancó el server)?"""
    return bool(_EXPULSADOS.get(getattr(st, "usn", None)))


def _usa_coordinador():
    """True cuando el server usa pases y tiene configurados `R2_CUENTAS_URL` y `R2_CUENTAS_FICHA_INTERNA`."""
    from . import pase
    return (pase.modo_pase()
            and bool((os.environ.get("R2_CUENTAS_URL") or "").strip())
            and bool((os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()))


def _enenos_id_de_cuenta(cuenta):
    """El Eñeños ID de esa cuenta (`users.enenos_id`, o extraído de `uid_<id>`), o None si es local vieja."""
    if not cuenta:
        return None
    try:
        from . import almacen
        eid = almacen.enenos_id_de_cuenta(cuenta)
        if isinstance(eid, int) and not isinstance(eid, bool) and eid > 0:
            return eid
    except Exception:                         # noqa: BLE001
        pass
    s = str(cuenta)
    if s.startswith("uid_") and s[4:].isdigit():
        n = int(s[4:])
        if n > 0:
            return n
    return None


def _escalon(usn, regla, detalle="", nick=""):
    """★ 19-nov — LA ESCALERA: suma la falta a la CUENTA y dice qué toca.
    Con pases y Coordinador configurado, sólo AVISA a Cuenta Eñeños (él cuenta las faltas y banea en `baneos`);
    sin pases o en cuentas viejas sin Eñeños ID, cuenta y banea en la base local como siempre.
    -> (faltas, cuenta, baneada). Sin base o sin cuenta cuenta como la primera."""
    if _usa_coordinador():
        try:
            from . import almacen
            cuenta, _ = almacen.cuenta_de_uid(usn)
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude buscar la cuenta de usn={usn}: {e!r}")
            return 1, None, False
        eid = _enenos_id_de_cuenta(cuenta)
        if eid is not None:
            from . import pase
            try:
                res = pase.avisar_antitrampa_interno(eid, regla, detalle=detalle, nick=nick, timeout=3.0)
            except Exception as e:            # noqa: BLE001
                log("TRAMP", f"  ⚠ no pude avisar al Coordinador (usn={usn}, eid={eid}): {e!r}")
                return 1, cuenta, False
            if res.get("estado") != "ok" or not isinstance(res.get("datos"), dict):
                log("TRAMP", f"  ⚠ no pude avisar al Coordinador (usn={usn}, eid={eid}): "
                             f"{res.get('error') or res.get('codigo')}")
                return 1, cuenta, False
            d = res["datos"]
            try:
                faltas = max(1, int(d.get("faltas") or 1))
            except (TypeError, ValueError):
                faltas = 1
            baneada = bool(d.get("baneada")) or d.get("escalon") == "baneo"
            return faltas, cuenta, baneada
    try:
        from . import almacen
        cuenta, n = almacen.antitrampa_sumar_falta(usn, regla)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude sumar la falta de usn={usn}: {e!r}")
        return 1, None, False
    if not cuenta:
        return 1, None, False
    baneada = False
    if ANTITRAMPA_BANEO_EN and n >= ANTITRAMPA_BANEO_EN:
        try:
            almacen.banear_cuenta(cuenta)
            baneada = True
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude banear la cuenta {cuenta!r}: {e!r}")
    return n, cuenta, baneada


def _expulsar(st, usn, nick, regla, detalle):
    """Lo que hace una regla «expulsar».
    ★ 24-nov — con `ANTITRAMPA_SILENCIOSO` (de fábrica) NO expulsa: retiene el premio en silencio y deja la detección
    pendiente para la tanda de un GM (`_detener_en_silencio`). Sin él, la expulsión al instante de siempre."""
    # ★ UNA falta por sesión del juego (de «hola» a «hola»): con dos funciones prendidas llegan dos ganchos en el mismo
    #   segundo (medido 19-nov: automático + sala ⇒ 1.ª y 2.ª juntas). Lo que llegue después sólo vuelve a cerrar.
    with _cuentas_lock:
        sesion = _CUENTAS.setdefault(usn, {"hola": True, "retener": False, "sin_hola_avisado": False}) if usn else {}
        ya = sesion.get("expulsado")
        sesion["expulsado"] = True
        reglas = sesion.setdefault("reglas_pendientes", set())
        nueva = regla not in reglas
        reglas.add(regla)
    if ANTITRAMPA_SILENCIOSO and usn:
        if ya and not nueva:
            log("TRAMP", f"  🤫 usn={usn}: {regla} otra vez en la misma sesión: ya está pendiente")
            return
        _detener_en_silencio(usn, nick, regla, detalle)
        return
    if ya:
        log("TRAMP", f"  ⛔ usn={usn}: {regla} en la misma sesión ya expulsada: no suma otra falta, sólo cierra")
        _cerrar_luego(st, usn, regla)
        return
    _sancionar(st, usn, nick, regla, detalle)


def _detener_en_silencio(usn, nick, regla, detalle):
    """★ 24-nov — EL MODO SILENCIOSO: el jugador no se entera de nada. Lo que quede de esta sesión no cobra (ni exp,
    ni Rcoin, ni récord, ni medallas, ni misiones: `retenido`), los GM conectados lo ven y la detección queda en
    `antitrampa_pendientes` hasta la tanda (`sancionar_tanda`, `.sanciones aplicar`)."""
    with _cuentas_lock:
        _CUENTAS.setdefault(usn, {"hola": True, "retener": False, "sin_hola_avisado": False})["retener"] = True
    pid = None
    try:
        from . import almacen
        pid, _ = almacen.antitrampa_dejar_pendiente(usn, regla, detalle=detalle, nick=nick)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude dejar pendiente la detección de usn={usn}: {e!r}")
    log("TRAMP", f"  🤫 usn={usn} {nick!r}: {regla} DETECTADO en silencio (pendiente #{pid}, premio retenido)")
    _avisar_gms(f"ANTITRAMPA {regla}: {nick or usn} detectado en silencio (premio retenido, "
                f"sancion pendiente #{pid}) — {detalle}")


def _sancionar(st, usn, nick, regla, detalle, otros_usns=()):
    """Aviso al jugador, anuncio y fuera. El cierre va un segundo después: que le lleguen los avisos.
    ★ 19-nov — la escalera, por cuenta: 1.ª falta = fuera · 2.ª = fuera con ADVERTENCIA · 3.ª = baneo permanente
    (en el Coordinador cuando el server usa pases; `BANNED:` local en servidores sin pases). El bloqueo por tiempo
    (`ANTITRAMPA_BLOQUEO_S`) queda en 0: la carrera de esta sesión no cobra igual.
    ★ 24-nov — la usa también la tanda (`sancionar_tanda`), con `st=None`: si no está conectado, la falta se suma
    igual y el baneo le cierra el login. -> (faltas, cuenta, baneada, qué)."""
    faltas, cuenta, baneada = _escalon(usn, regla, detalle=detalle, nick=nick) if usn else (1, None, False)
    if usn:
        _EXPULSADOS[usn] = faltas
        if ANTITRAMPA_BLOQUEO_S:
            _BLOQUEADOS[usn] = time.monotonic() + ANTITRAMPA_BLOQUEO_S
        with _cuentas_lock:                   # lo que quede de esta sesión no cobra (al reabrir limpio, sí)
            _CUENTAS.setdefault(usn, {"hola": True, "retener": False, "sin_hola_avisado": False})["retener"] = True
        _FARMEO.pop(usn, None)                # al volver, el farmeo se cuenta de cero (y puede volver a saltar)
    if baneada:
        al_jugador = (f"Fuiste expulsado por el antitrampa ({regla}). Es la {faltas}.ª vez: "
                      f"tu cuenta quedó BANEADA PERMANENTEMENTE.")
        que = f"BANEADA la cuenta {cuenta!r} ({faltas}.ª falta)"
    elif ANTITRAMPA_BANEO_EN and faltas == ANTITRAMPA_BANEO_EN - 1:
        al_jugador = (f"ADVERTENCIA: fuiste expulsado por el antitrampa ({regla}) por {faltas}.ª vez. "
                      f"La próxima, tu cuenta queda baneada para siempre.")
        que = f"EXPULSADO con advertencia ({faltas}.ª falta)"
    else:
        al_jugador = f"Fuiste expulsado por el antitrampa ({regla})."
        que = f"EXPULSADO ({faltas}.ª falta)"
    _avisar_gms(f"ANTITRAMPA {regla}: {nick or usn} {que} — {detalle}")
    log("TRAMP", f"  ⛔ usn={usn} cuenta={cuenta!r}: {que}")
    anuncio = (ANTITRAMPA_ANUNCIO_BANEO if baneada else ANTITRAMPA_ANUNCIO).format(nick=nick or f"usn {usn}")
    conns = []
    try:
        from .salas import CONEXIONES, avisar_a_uno
        conns = [c for c in [CONEXIONES.get(usn) or st] + [CONEXIONES.get(u) for u in otros_usns] if c is not None]
        for conn in conns:
            avisar_a_uno(conn, al_jugador)
        if ANTITRAMPA_ANUNCIO_PUBLICO:
            for c in list(CONEXIONES.values()):
                if c is not None and c not in conns:
                    avisar_a_uno(c, anuncio)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude avisar la expulsión de usn={usn}: {e!r}")
        conns = [st] if st is not None else []
    for conn in conns:
        t = threading.Timer(1.0, cerrar_conexion, args=(conn, f"expulsado por {regla}"))
        t.daemon = True
        t.start()
    return faltas, cuenta, baneada, que


# ═══ ★ 24-nov · LA TANDA (antitrampa SILENCIOSO) ═══════════════════════════════════════════════════════════════════
#   Las detecciones pendientes se sancionan juntas, cuando un GM lo decide (`.sanciones aplicar`), y sólo las que ya
#   tienen `ANTITRAMPA_TANDA_DEMORA_H` horas: el tramposo no puede relacionar la sanción con lo que hizo. UNA falta de
#   la escalera por cuenta y por tanda, junte las detecciones que junte (el detalle dice cuáles).
def _agrupar(filas):
    grupos = {}
    for f in filas:
        grupos.setdefault(f.get("cuenta") or f"usn {f['usn']}", []).append(f)
    return grupos


def resumen_pendientes():
    """Las líneas de `.sanciones`: quién tiene detecciones pendientes y cuáles ya entran en la próxima tanda."""
    from . import almacen
    todas = almacen.antitrampa_pendientes(0)
    if not todas:
        return ["antitrampa: no hay detecciones pendientes"]
    listas = {f["id"] for f in almacen.antitrampa_pendientes(ANTITRAMPA_TANDA_DEMORA_H)}
    lineas = [f"antitrampa: {len(todas)} deteccion(es) pendiente(s) de {len(_agrupar(todas))} cuenta(s)"]
    for clave, fs in _agrupar(todas).items():
        reglas = sorted({f["regla"] for f in fs})
        nick = next((f["nick"] for f in reversed(fs) if f.get("nick")), "") or clave
        listo = "entra en la tanda" if any(f["id"] in listas for f in fs) else \
            f"espera {ANTITRAMPA_TANDA_DEMORA_H}h"
        lineas.append(f"- {nick} ({clave}): {len(fs)}x {', '.join(reglas)} desde {fs[0]['cuando']} - {listo}")
    lineas.append(".sanciones aplicar [ya] | .sanciones perdonar <apodo>")
    return lineas


def sancionar_tanda(quien="", ya=False):
    """Aplica la escalera a cada cuenta con detecciones pendientes (de más de `ANTITRAMPA_TANDA_DEMORA_H` horas, o
    todas con `ya`). -> las líneas para el GM."""
    from . import almacen
    filas = almacen.antitrampa_pendientes(0 if ya else ANTITRAMPA_TANDA_DEMORA_H)
    if not filas:
        return ["antitrampa: no hay detecciones para sancionar" + ("" if ya else
                f" (con mas de {ANTITRAMPA_TANDA_DEMORA_H}h; '.sanciones aplicar ya' no espera)")]
    lineas = []
    for clave, fs in _agrupar(filas).items():
        reglas = sorted({f["regla"] for f in fs})
        usns = list(dict.fromkeys(f["usn"] for f in reversed(fs)))      # el más reciente primero
        nick = next((f["nick"] for f in reversed(fs) if f.get("nick")), "") or _nick(usns[0])
        detalle = f"{len(fs)} deteccion(es): {', '.join(reglas)}"
        try:
            faltas, cuenta, baneada, que = _sancionar(None, usns[0], nick, reglas[0], detalle, otros_usns=usns[1:])
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude sancionar {clave!r}: {e!r}")
            lineas.append(f"- {nick}: ERROR ({e!r}), queda pendiente")
            continue
        almacen.antitrampa_resolver([f["id"] for f in fs], "sancionada", quien)
        _guardar({"cuando": datetime.datetime.now().isoformat(timespec="seconds"), "regla": reglas[0],
                  "accion": "sancion_en_tanda", "usn": usns[0], "nick": nick, "cuenta": cuenta, "faltas": faltas,
                  "baneada": baneada, "quien": quien, "detalle": detalle})
        lineas.append(f"- {nick or clave}: {que}")
    log("TRAMP", f"  ⚖ tanda de sanciones de {quien!r}: {len(lineas)} cuenta(s)")
    return [f"antitrampa: tanda aplicada a {len(lineas)} cuenta(s)"] + lineas


def perdonar_pendientes(quien_es, quien=""):
    """Descarta (falso positivo) las detecciones pendientes de ese apodo, usn o cuenta. -> las líneas para el GM."""
    from . import almacen
    q = str(quien_es).strip().lower()
    fs = [f for f in almacen.antitrampa_pendientes(0)
          if q in (str(f["usn"]), (f.get("nick") or "").lower(), (f.get("cuenta") or "").lower())]
    if not fs:
        return [f"antitrampa: {quien_es!r} no tiene detecciones pendientes"]
    n = almacen.antitrampa_resolver([f["id"] for f in fs], "perdonada", quien)
    log("TRAMP", f"  🕊 {quien!r} perdonó {n} detección(es) de {quien_es!r}")
    return [f"antitrampa: {n} deteccion(es) de {quien_es} descartada(s)"]


def _cerrar_luego(st, usn, regla):
    try:
        from .salas import CONEXIONES
        conn = CONEXIONES.get(usn) or st
    except Exception:                         # noqa: BLE001
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
