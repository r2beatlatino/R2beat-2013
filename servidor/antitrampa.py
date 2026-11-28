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
import uuid
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
    ANTITRAMPA_LLEGADA_CUENTAS,
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
    ANTITRAMPA_SUELO_FACTOR,
    ANTITRAMPA_TANDA_DEMORA_H,
    ANTITRAMPA_AVISOS_GM_POR_MINUTO,
    ANTITRAMPA_CORRELACION_ALTERACION,
    ANTITRAMPA_CORRELACION_HERRAMIENTA,
    ANTITRAMPA_JSONL_MAX_MB,
    ANTITRAMPA_LATIDO_TOPE_S,
    ANTITRAMPA_MANIJAS_CONOCIDAS,
    ANTITRAMPA_FUERA_DEL_PANEL,
    ANTITRAMPA_SIN_DLL_GRACIA_S,
    ANTITRAMPA_SIN_DLL_AVISO,
    ANTITRAMPA_DLL_MD5,
    ANTITRAMPA_PERFECTA_NIVEL,
    ANTITRAMPA_PERFECTA_PD,
    ANTITRAMPA_PERFECTA_CARRERAS,
    ANTITRAMPA_PERFECTA_VECES,
    ANTITRAMPA_RETO_FALLOS,
    ANTITRAMPA_RITMO_PULSOS,
    ANTITRAMPA_RITMO_SD_MS,
    ANTITRAMPA_SALTO_NIVEL,
    ANTITRAMPA_SALTO_RECIENTES,
    ANTITRAMPA_SALTO_HISTORIA,
    ANTITRAMPA_SALTO_HISTORIA_MIN,
    ANTITRAMPA_SALTO_PD_MIN,
    ANTITRAMPA_SALTO_PUNTOS,
    ANTITRAMPA_R2AT_POR_MINUTO,
    ANTITRAMPA_RELOJ_CLIENTE_TOLERANCIA,
    ANTITRAMPA_RELOJ_CLIENTE_VECES,
    ANTITRAMPA_SENALES_DEBILES,
)
from . import antitrampa_eventos as eventos
from . import antitrampa_firmas as firmas
from .registro import log

FPS = 60
FRAME_SIN_META = 0xFFFFFFFF
_archivo_lock = threading.Lock()
# ★ Por usn y no por conexión: el cambio de canal abre otra conexión y la dll no repite su «hola» (el juego sigue
#   abierto). `{usn: {"hola": bool, "retener": bool, "sin_hola_avisado": bool}}`. Un «hola» nuevo = juego reabierto.
_CUENTAS = {}
_cuentas_lock = threading.Lock()
_R2AT = re.compile(r"R2AT((?: \w+=\S+)+)")
#   ★ 26-nov: un FF59 puede traer VARIOS renglones R2AT, y un valor puede tener espacios («proceso=Cheat Engine.exe»):
#   cada renglón se lee entero y el valor llega hasta la próxima « clave=».
_R2AT_LINEA = re.compile(r"R2AT((?: \w+=[^\r\n]*?)+)[ \t]*(?=[\r\n]|$)")
_R2AT_PAR = re.compile(r"(\w+)=(.*?)(?= \w+=|$)")


def _sesion(usn):
    """El estado de esta cuenta EN ESTA SESIÓN DEL JUEGO (de «hola» a «hola»). ⚠ Con `_cuentas_lock` tomado."""
    c = _CUENTAS.get(usn)
    if c is None:
        c = _CUENTAS[usn] = {"hola": False, "retener": False, "sin_hola_avisado": False}
    c.setdefault("sesion", uuid.uuid4().hex[:16])
    c.setdefault("reglas", set())                 # las reglas vistas en esta sesión (para la correlación)
    c.setdefault("gm_avisados", set())
    c.setdefault("r2at", deque(maxlen=max(ANTITRAMPA_R2AT_POR_MINUTO + 1, 2)))
    c.setdefault("visto", time.monotonic())
    c.setdefault("desde", time.monotonic())           # ★ 28-nov: desde cuándo la ve el server (gracia de «sin dll»)
    return c


def _contexto(st):
    """Lo que lleva cada evento de esta conexión: sesión, partida y versiones."""
    usn = getattr(st, "usn", None)
    with _cuentas_lock:
        c = _sesion(usn) if usn else {}
        sesion, exe, v, dll = c.get("sesion"), c.get("exe"), c.get("v"), c.get("dll")
    rid, magic = getattr(st, "room_id", None), getattr(st, "game_magic", None)
    partida = f"{rid}:{magic:08x}" if rid is not None and isinstance(magic, int) else (str(rid) if rid else None)
    ver_at = None
    if v:
        ver_at = f"r2at v{v}" + (f" · dll {dll}" if dll else "")
    return {"sesion": sesion, "partida": partida, "version_cliente": f"exe {exe}" if exe else None,
            "version_antitrampa": ver_at}


def marcar_salida(conn, ahora=None):
    """Anota en la conexión el instante del GO. Lo llama `dar_el_go`, una vez por jugador."""
    conn.at_go = time.monotonic() if ahora is None else ahora


def marcas_del_cartel(frame, combo, pd, star, combo_total, transcurrido, relevo=False, coop=False,
                      milesimas=0, llegadas=None, duracion_min=None):
    """Las reglas que rompe un reporte `FF28`. `[(regla, detalle), …]`; vacía si está limpio.

    `pd` y `star` son los bytes CRUDOS del paquete (antes del tope a 100). `transcurrido` = segundos
    desde el GO según el server, o `None` si no se sabe. `milesimas` = las de la precisión (0..999).
    `llegadas` = los frame de las últimas llegadas limpias de esa canción (o None). `duracion_min` = los segundos
    que como poco dura la canción según su chart (`notas.duracion_minima_de`, o None). Pura: no loguea ni avisa.
    """
    marcas = []
    if pd > 100 or star > 100:
        marcas.append(("porcentaje_imposible", f"pd={pd} star={star} (tope 100)"))
    # ★ 24-nov (el laboratorio: «Precisión personalizada» escribe entero y milésimas): 100.000 es el tope.
    elif milesimas > 999 or (pd == 100 and milesimas > 0):
        marcas.append(("precision_imposible", f"precisión {pd}.{milesimas:03d} (tope 100.000)"))
    # ★ 25-nov · el SUELO del chart: aun sin historia (canción nueva o que sólo jugó una cuenta), no se llega en
    #   menos de la mitad de lo que dura como poco la canción. Si salta, la anticipada no se suma (es la misma llegada).
    imposible = (duracion_min is not None and duracion_min > 0 and frame not in (0, FRAME_SIN_META)
                 and not relevo and not coop and frame / FPS < duracion_min * ANTITRAMPA_SUELO_FACTOR)
    if imposible:
        marcas.append(("llegada_imposible", f"llegó a la meta en {frame / FPS:.1f} s; su chart dura como poco "
                                              f"{duracion_min:.0f} s (tope {ANTITRAMPA_SUELO_FACTOR:.0%})"))
    # ★ 24-nov («Simular llegada»): la meta se dispara cuando el cliente quiere. El frame cuadra con el reloj del
    #   server, pero la carrera duró mucho menos que las llegadas limpias de esa canción.
    if (not imposible and llegadas and len(llegadas) >= ANTITRAMPA_LLEGADA_MUESTRAS
            and frame not in (0, FRAME_SIN_META) and not relevo and not coop):
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
        duracion_min = _duracion_de(cancion)   # el suelo del chart (llegada_imposible)
        marcas = marcas_del_cartel(frame, combo, pd, star, combo_total, transcurrido, relevo, coop,
                                   milesimas=milesimas, llegadas=llegadas, duracion_min=duracion_min)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude revisar el FF28 de usn={getattr(st, 'usn', None)}: {e!r}")
        return retener
    # una llegada limpia (sin ninguna marca, con meta real, carrera suelta) enseña cuánto tarda la canción
    if not marcas and cancion and frame not in (0, FRAME_SIN_META) and not relevo and not coop and combo > 0:
        _anotar_llegada(cancion, frame, cuenta)
        if not retener:
            _salto_precision(st, cancion, pd, milesimas)       # ★ 28-nov
    for regla, detalle in marcas:
        retener |= anotar(st, regla, detalle, {"cancion": cancion, "frame": frame, "combo": combo,
                                               "pd": pd, "star": star}) in _QUE_RETIENEN
    retener |= _farmeo_al_cartel(st, cancion, combo, pd, ahora) in _QUE_RETIENEN
    st.at_ultimo = (clave, retener)
    return retener


def _duracion_de(cancion):
    """Lo menos que dura la canción según su chart (segundos), o None. Ver `notas.duracion_minima_de`."""
    if not cancion:
        return None
    try:
        from . import notas
        return notas.duracion_minima_de(cancion)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude calcular la duración de la canción {cancion}: {e!r}")
        return None


def _cuenta_de(st):
    """La CUENTA (username) del jugador, para no juzgarlo con sus propias llegadas. None si no se sabe."""
    try:
        from . import almacen
        return almacen.cuenta_de_uid(getattr(st, "usn", None))[0]
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude ubicar la cuenta de usn={getattr(st, 'usn', None)}: {e!r}")
        return None


def vara_de_fiar(filas):
    """De las llegadas `[(frame, cuenta), …]` (ya sin las del juzgado), los `frame` con los que se le puede juzgar, o
    `[]` si la vara no es de fiar: con llegadas con cuenta, tienen que salir de al menos LLEGADA_CUENTAS cuentas
    distintas (un alt solo no la fija). Sólo llegadas viejas sin cuenta: se aceptan como antes. Función pura."""
    cuentas = {cuenta for _frame, cuenta in filas if cuenta}
    if cuentas and len(cuentas) < ANTITRAMPA_LLEGADA_CUENTAS:
        return []
    return [frame for frame, _cuenta in filas]


def _llegadas_de(cancion, excluir=None):
    if not cancion:
        return None
    try:
        from . import almacen
        return vara_de_fiar(almacen.antitrampa_llegadas_filas(cancion, ANTITRAMPA_LLEGADA_HISTORIA, excluir=excluir))
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
    ahora = time.monotonic()
    with _cuentas_lock:
        c = _sesion(usn)
        c["visto"] = ahora
        desde = c["desde"]
        # ★ 28-nov: sin el «hola» ni un latido en la gracia (o con la dll apagada en su ini) = sin nuestra dll
        apagada = bool(c.get("apagado"))
        sin_dll = apagada or (not c["hola"] and not c.get("dll_vista")
                              and ahora - desde >= ANTITRAMPA_SIN_DLL_GRACIA_S)
        avisar_sin_hola = sin_dll and not c["sin_hola_avisado"]       # una vez por sesión
        c["sin_hola_avisado"] |= avisar_sin_hola
        retener = c["retener"] or _BLOQUEADOS.get(usn, 0) > ahora
        decirle = False
        if sin_dll and ANTITRAMPA_REGLAS.get("sin_antitrampa") in _QUE_RETIENEN:
            retener = True
            decirle = not c.get("sin_dll_dicho")
            c["sin_dll_dicho"] = True
    if avisar_sin_hola:
        anotar(st, "sin_antitrampa", "la dll del antitrampa está apagada en su ini" if apagada else
               f"terminó una carrera sin el «hola» ni un latido de nuestra dll en {ANTITRAMPA_SIN_DLL_GRACIA_S} s", {})
    if decirle:
        try:
            from .salas import avisar_a_uno
            avisar_a_uno(st, ANTITRAMPA_SIN_DLL_AVISO)
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude avisarle a usn={usn} que no tiene el antitrampa: {e!r}")
    if retener:
        log("TRAMP", f"  🚩 usn={usn}: premio retenido por lo que informó su cliente en esta sesión"
                     + (" (sin nuestra dll)" if sin_dll else ""))
    return retener


# Los ganchos que reconocemos (la dll los informa con «gancho=<nombre>»): nombre -> regla.
_GANCHOS = {"automatico": "juego_automatico", "sala": "sala_automatica", "relevo": "relevo_automatico",
            # ★ 24-nov: las rutas del laboratorio (INFORME_LABORATORIO.md §4-5)
            "tick_meta": "juego_automatico", "auto_normal": "juego_automatico", "pd0": "juego_automatico",
            "larga_a": "juego_automatico", "larga_b": "juego_automatico", "item_auto": "juego_automatico",
            "resultado": "resultado_alterado", "resultado_solo": "resultado_alterado",
            # ★ 28-nov: R2AutoRouteLab «Release-next» engancha el resultado 7 bytes antes (+0x101451)
            "resultado_b": "resultado_alterado"}
# ★ 28-nov · lo que dice el catálogo de firmas (antitrampa_firmas.py) según la clase de lo que se tocó
_REGLA_DE_CLASE = {"trampa": "trampa_conocida", "permitida": "n2hock_permitido"}


def _usa(va):
    """-> (firma o None, « · usa: programa · función» para el detalle, dict para la evidencia)."""
    f = firmas.identificar(va)
    if not f:
        return None, "", {}
    return f, f" · usa: {firmas.texto(f)}", {"programa": f.programa, "funcion": f.funcion, "clase": f.clase}


def _va(texto):
    try:
        return int(texto, 16)
    except ValueError:
        return -1


def leer_r2at(texto):
    """Los renglones R2AT de un FF59 -> [(dict de claves, renglón crudo), …]. Pura (para las pruebas)."""
    out = []
    for m in _R2AT_LINEA.finditer(texto or ""):
        cuerpo = m.group(1).strip()
        d = {k: v.strip() for k, v in _R2AT_PAR.findall(cuerpo)}
        if d:
            out.append((d, m.group(0)[:300]))
    return out


def al_ff59(st, texto):
    """Los renglones «R2AT …» de la dll (antitrampa.c). Devuelve True si había alguno (el FF59 ya está atendido).
    ★ 26-nov: TODOS los renglones del FF59 (antes sólo el primero), con tope por minuto, número de secuencia (`s=`,
    anti-repetición) y el LATIDO (`latido=`). Cada uno termina como evento en el registro central."""
    renglones = leer_r2at(texto)
    if not renglones:
        return False
    if not ANTITRAMPA or not getattr(st, "usn", None):
        return True
    for d, crudo in renglones:
        if _admitir_r2at(st, d):
            if "v" in d or "latido" in d:                 # ★ 28-nov: la dll está (para «sin_antitrampa»)
                with _cuentas_lock:
                    _sesion(st.usn)["dll_vista"] = True
            _un_r2at(st, d, crudo)
    return True


def _admitir_r2at(st, d, ahora=None):
    """El tope de renglones por minuto y la secuencia (`s=`). False = el renglón se descarta; la primera vez de cada
    cosa en la sesión queda anotada (`telemetria_inundada`, `telemetria_repetida`)."""
    t = time.monotonic() if ahora is None else ahora
    marca = None
    with _cuentas_lock:
        c = _sesion(st.usn)
        c["visto"] = t
        ventana = c["r2at"]
        while ventana and t - ventana[0] > 60:
            ventana.popleft()
        if len(ventana) >= ANTITRAMPA_R2AT_POR_MINUTO and "v" not in d:
            c["descartados"] = c.get("descartados", 0) + 1
            if not c.get("inundado"):
                c["inundado"] = True
                marca = "inundada"
            admitido = False
        else:
            ventana.append(t)
            admitido = True
            s = d.get("s", "")
            if s.isdigit():
                s = int(s)
                ultimo = c.get("seq")
                if "v" in d:
                    c["seq"] = s                       # el «hola»: la secuencia de ESTA corrida del juego
                elif ultimo is not None and s <= ultimo:
                    c["repetidos"] = c.get("repetidos", 0) + 1
                    admitido = False
                    if not c.get("repetido"):
                        c["repetido"] = True
                        marca = "repetida"
                else:
                    if ultimo is not None and s > ultimo + 1:
                        c["perdidos"] = c.get("perdidos", 0) + (s - ultimo - 1)
                    c["seq"] = s
    if marca == "inundada":
        anotar(st, "telemetria_inundada", f"más de {ANTITRAMPA_R2AT_POR_MINUTO} renglones del antitrampa por minuto: "
                                          "los de más se descartan", {},
               evidencia={"tope_por_minuto": ANTITRAMPA_R2AT_POR_MINUTO})
    elif marca == "repetida":
        anotar(st, "telemetria_repetida", f"un renglón del antitrampa con la secuencia {d.get('s')} ya vista "
                                          "(repetido o fabricado)", {}, evidencia={"s": d.get("s")})
    return admitido


def _un_r2at(st, d, crudo):
    ev = {"r2at": crudo}
    if "v" in d:
        _al_hola(st, d, crudo)
    elif "latido" in d:
        _al_latido(st, d)
    elif "apagado" in d:
        anotar(st, "antitrampa_apagado", "la dll del antitrampa avisa que la apagaron en su ini", {}, evidencia=ev)
    elif "vigia" in d:
        anotar(st, "vigia_parado", "el hilo del antitrampa dejó de correr dentro del juego", {}, evidencia=ev)
    elif "gancho" in d:                                    # un gancho conocido de un programa de trampas
        regla = _GANCHOS.get(d["gancho"], "codigo_modificado")
        _f, usa, ev_usa = _usa(_va(d.get("va", "")))
        anotar(st, regla, f"gancho «{d['gancho']}» en {d.get('va')}: {d.get('bytes', '').replace('_', ' ')}{usa}", {},
               evidencia={**ev, **ev_usa}, firma=d["gancho"])
    elif "codigo" in d and _va(d["codigo"]) in ANTITRAMPA_GANCHOS:   # dll sin «gancho=»: por la dirección
        _f, usa, ev_usa = _usa(_va(d["codigo"]))
        anotar(st, _GANCHOS[ANTITRAMPA_GANCHOS[_va(d["codigo"])]],
               f"gancho «{ANTITRAMPA_GANCHOS[_va(d['codigo'])]}» en {d['codigo']}: "
               f"{d.get('bytes', '').replace('_', ' ')}{usa}", {}, evidencia={**ev, **ev_usa}, firma=d["codigo"])
    elif "codigo" in d:
        _codigo_tocado(st, d, ev)
    elif "modulo" in d and d["modulo"].lower().startswith(ANTITRAMPA_MODULOS_PERMITIDOS):
        # ★ 19-nov: el motor de práctica de Ñ2Hock (ToolBitPracticeEngine_<hash>.dll): la dll del launcher
        #   todavía lo informa como «toolbit», pero NO es el ToolBit de trampas. Sólo queda registrado.
        anotar(st, "modulo_permitido", f"tiene cargado {d['modulo']} (permitido)", {}, evidencia=ev,
               firma=d["modulo"].lower())
    elif "modulo" in d:
        anotar(st, "modulo_prohibido", f"tiene cargado {d['modulo']}", {}, evidencia=ev, firma=d["modulo"].lower())
    elif "memoria" in d:
        anotar(st, "memoria_ajena", f"{d.get('regiones')} región(es) de memoria ejecutable ajena, "
                                    f"la primera en {d['memoria']}", {}, evidencia=ev)
    elif "depurador" in d:
        anotar(st, "depurador", "un depurador enganchado al juego", {}, evidencia=ev)
    elif "inyectadas" in d:
        _senal(st, "teclas_inyectadas", f"{d['inyectadas']} de {d.get('teclas', '?')} teclas las mandó un programa",
               evidencia=ev)
    elif "hilo" in d:
        anotar(st, "hilo_ajeno", f"un hilo del juego arranca en memoria inyectada ({d['hilo']})", {}, evidencia=ev)
    elif "proceso" in d:
        firma = f" (firma {d['firma']})" if "firma" in d else ""
        anotar(st, "proceso_prohibido", f"tiene abierto {d['proceso']}{firma}", {}, evidencia=ev,
               firma=d["proceso"].lower())
    elif "manija" in d:                                    # ★ 24-nov: un programa con permiso de escribir el juego
        regla = "manija_conocida" if manija_conocida(d["manija"]) else "manija_escritura"   # ★ 28-nov
        anotar(st, regla, f"{d['manija']} tiene abierto el juego con permiso de escribir su memoria "
                          f"(acceso {d.get('acceso', '?')})", {}, evidencia=ev,
               firma=d["manija"].lower())
    else:
        log("TRAMP", f"  ? usn={st.usn}: renglón R2AT que no conozco: {crudo!r}")


def _codigo_tocado(st, d, ev):
    """★ 28-nov: `R2AT codigo=` — una página del exe cambió por fuera. El catálogo de firmas dice QUÉ programa y QUÉ
    función es por la dirección, y de eso sale la regla: trampa_conocida (retener en silencio), n2hock_permitido (una
    función de Ñ2Hock: registrar), arranque_restaurado (registrar) o, si no se conoce, codigo_modificado."""
    va, b = _va(d["codigo"]), d.get("bytes", "")
    f, usa, ev_usa = _usa(va)
    base = (f"{d.get('paginas')} página(s) del exe tocadas por fuera, la primera en {d['codigo']}: "
            f"{b.replace('_', ' ')}")
    if f and f.clase == "arranque":
        if firmas.arranque_restaurado(va, b):
            anotar(st, "arranque_restaurado", base + " · el punto de entrada del exe lo cambió un inyector o un launcher "
                                                     "al abrir el juego y ya está como de fábrica", {},
                   evidencia={**ev, **ev_usa}, firma=d["codigo"])
            return
        regla = "codigo_modificado"
    else:
        regla = _REGLA_DE_CLASE.get(f.clase, "codigo_modificado") if f else "codigo_modificado"
    anotar(st, regla, base + usa, {}, evidencia={**ev, **ev_usa}, firma=d["codigo"])


_DLLS = None


_ARCHIVOS_DLL = None


def _archivos_dll():
    """★ 28-nov: {md5 (12): bytes} de nuestras dll que este server tiene en disco (para el reto del latido)."""
    global _ARCHIVOS_DLL
    if _ARCHIVOS_DLL is None:
        import hashlib
        import os
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        a = {}
        for rel in (("exe", "d3d9.dll"), ("datos", "d3d9_prod.dll"), ("datos", "d3d9.dll")):
            try:
                with open(os.path.join(raiz, *rel), "rb") as f:
                    b = f.read()
                a[hashlib.md5(b).hexdigest()[:12]] = b
            except OSError:
                pass
        _ARCHIVOS_DLL = a
    return _ARCHIVOS_DLL


def reto_esperado(archivo, nonce, latido):
    """El md5 (8, minúsculas) de los 256 bytes que la dll tiene que resumir en ese latido (antitrampa.c, at_hilo)."""
    import hashlib
    n = len(archivo)
    if n <= 512:
        return None
    off = ((nonce * 2654435761 + latido * 40503) & 0xFFFFFFFF) % (n - 256)
    return hashlib.md5(archivo[off:off + 256]).hexdigest()[:8]


def _reto_y_ritmo(st, d):
    """★ 28-nov · el RETO (¿es nuestra dll de verdad?) y el RITMO de las teclas, que vienen en el latido."""
    h = str(d.get("h") or "").lower()
    with _cuentas_lock:
        c = _sesion(st.usn)
        nonce, dll = c.get("nonce"), str(c.get("dll") or "").lower()[:12]
    archivo = _archivos_dll().get(dll) if dll else None
    if h and h != "-" and nonce is not None and archivo is not None and str(d.get("latido", "")).isdigit():
        bien = reto_esperado(archivo, nonce, int(d["latido"])) == h
        with _cuentas_lock:
            c = _sesion(st.usn)
            c["reto_bien" if bien else "reto_mal"] = c.get("reto_bien" if bien else "reto_mal", 0) + 1
            marcar = not bien and c["reto_mal"] == ANTITRAMPA_RETO_FALLOS
        if marcar:
            anotar(st, "dll_falsa", f"la dll dice ser la nuestra ({dll}…) pero no acierta el reto de sus propios bytes "
                                    f"({ANTITRAMPA_RETO_FALLOS} latidos): recompilada o cambiada", {},
                   evidencia={"dll": dll, "latido": d.get("latido"), "h": h})
    if str(d.get("pulsos", "")).isdigit() and str(d.get("sd", "")).isdigit():
        pulsos, sd = int(d["pulsos"]), int(d["sd"])
        if pulsos >= ANTITRAMPA_RITMO_PULSOS and sd <= ANTITRAMPA_RITMO_SD_MS:
            _senal(st, "teclas_robot", f"{pulsos} teclas en un minuto, cada una apretada {d.get('med', '?')} ms con "
                                       f"apenas {sd} ms de diferencia (una persona varía mucho más)",
                   evidencia={"pulsos": pulsos, "media_ms": d.get("med"), "desvio_ms": sd})


def _salto_precision(st, cancion, pd, milesimas):
    """★ 28-nov · el SALTO: anota la precisión de esta carrera limpia y mira si de golpe está muy por encima de la suya."""
    try:
        from . import almacen, notas
        cuenta = _cuenta_de(st)
        nivel = notas.nivel_de(cancion) if cancion else None
        if not cuenta or nivel is None:
            return
        almacen.antitrampa_anotar_precision(cuenta, cancion, nivel, pd + milesimas / 1000.0)
        if nivel < ANTITRAMPA_SALTO_NIVEL:
            return
        ps = almacen.antitrampa_precisiones(cuenta, ANTITRAMPA_SALTO_NIVEL,
                                            ANTITRAMPA_SALTO_RECIENTES + ANTITRAMPA_SALTO_HISTORIA)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude anotar la precisión de usn={getattr(st, 'usn', None)}: {e!r}")
        return
    recientes, antes = ps[:ANTITRAMPA_SALTO_RECIENTES], ps[ANTITRAMPA_SALTO_RECIENTES:]
    if len(recientes) < ANTITRAMPA_SALTO_RECIENTES or len(antes) < ANTITRAMPA_SALTO_HISTORIA_MIN:
        return
    import statistics
    prom, med = sum(recientes) / len(recientes), statistics.median(antes)
    if prom >= ANTITRAMPA_SALTO_PD_MIN and prom - med >= ANTITRAMPA_SALTO_PUNTOS:
        _senal(st, "salto_precision", f"sus últimas {len(recientes)} carreras difíciles promedian {prom:.1f} %; "
                                      f"antes, la mitad de las suyas no pasaba de {med:.1f} %",
               evidencia={"recientes": round(prom, 2), "historia": round(med, 2), "carreras_antes": len(antes)})


def _dlls_nuestras():
    """★ 28-nov: los md5 (12) de nuestras dll: ANTITRAMPA_DLL_MD5 + exe/d3d9.dll y datos/d3d9_prod.dll de este server."""
    global _DLLS
    if _DLLS is None:
        import hashlib
        import os
        s = {x.lower()[:12] for x in ANTITRAMPA_DLL_MD5}
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in (("exe", "d3d9.dll"), ("datos", "d3d9_prod.dll"), ("datos", "d3d9.dll")):
            try:
                with open(os.path.join(raiz, *rel), "rb") as f:
                    s.add(hashlib.md5(f.read()).hexdigest()[:12])
            except OSError:
                pass
        _DLLS = s
    return _DLLS


def manija_conocida(nombre):
    """★ 28-nov: ¿es el launcher, una superposición o un programa de sistema (no una herramienta de trampa)?"""
    n = str(nombre or "").strip().lower()
    # ★ 28-nov: «Ñ2Hock.exe» llega según la página de códigos del jugador («ñ2hock», «?2hock», «�2hock»…): basta «2hock.exe»
    return bool(n) and n != "?" and (any(n.startswith(k) for k in ANTITRAMPA_MANIJAS_CONOCIDAS) or n.endswith("2hock.exe"))


def _al_hola(st, d, crudo):
    """El «hola» de la dll: una corrida NUEVA del juego (sesión nueva). ★ 26-nov: ya NO limpia la retención si la
    cuenta tiene detecciones pendientes (un «hola» fabricado la borraba: el tramposo volvía a cobrar)."""
    pendientes = _tiene_pendientes(st.usn)
    with _cuentas_lock:
        viejo = _CUENTAS.get(st.usn) or {}
        nuevo = {"hola": True, "retener": bool(viejo.get("retener")) and pendientes, "sin_hola_avisado": False}
        if nuevo["retener"]:
            nuevo["expulsado"] = viejo.get("expulsado")
            nuevo["reglas_pendientes"] = set(viejo.get("reglas_pendientes") or ())
        _CUENTAS[st.usn] = nuevo
        c = _sesion(st.usn)
        n = str(d.get("n") or "")
        c["nonce"] = int(n, 16) if n and all(ch in "0123456789abcdefABCDEF" for ch in n) and len(n) <= 8 else None
        c.update({"v": d.get("v"), "exe": d.get("exe"), "dll": d.get("dll") or d.get("dllmd5"),
                  "lat": int(d["lat"]) if d.get("lat", "").isdigit() else 0, "ult_latido": time.monotonic(),
                  "seq": int(d["s"]) if d.get("s", "").isdigit() else None})
    log("TRAMP", f"  ★ usn={st.usn}: antitrampa del cliente v{d['v']} · exe {d.get('exe')} · previo={d.get('previo')}"
                 f"{' · dll ' + str(d.get('dll')) if d.get('dll') else ''}{' · retención conservada' if nuevo['retener'] else ''}")
    ev = {"r2at": crudo}
    dll = str(d.get("dll") or d.get("dllmd5") or "").lower()[:12]
    if dll and dll not in _dlls_nuestras():                # ★ 28-nov: una dll que no es ninguna de las nuestras
        anotar(st, "dll_desconocida", f"la d3d9.dll del jugador (md5 {dll}…) no es ninguna de las nuestras", {"dll": dll},
               evidencia=ev, firma=dll)
    if d.get("exe") not in ANTITRAMPA_EXE_MD5:
        anotar(st, "exe_desconocido", f"R2Beat.exe con md5 {d.get('exe')}", {"exe": d.get("exe")}, evidencia=ev,
               firma=d.get("exe"))
    if d.get("previo", "0") not in ("0", "-1"):
        f, usa, ev_usa = _usa(_va(d.get("previo_va") or ""))
        anotar(st, "codigo_previo", f"{d['previo']} página(s) del exe ya tocadas al abrir el juego, la primera "
                                    f"en {d.get('previo_va')}{usa}", {}, evidencia={**ev, **ev_usa})


def _tiene_pendientes(usn):
    """¿La cuenta de este personaje tiene detecciones esperando la tanda?"""
    try:
        from . import almacen
        cuenta = almacen.cuenta_de_uid(usn)[0]
        return any(f.get("cuenta") == cuenta or f.get("usn") == usn for f in almacen.antitrampa_pendientes(0))
    except Exception:                         # noqa: BLE001
        return False


def _al_latido(st, d, ahora=None):
    """★ 26-nov · el LATIDO de la dll (cada 60 s): que sigue viva, cuántos renglones perdió, y su reloj. El reloj de la
    PC entre dos latidos (`t=`, GetTickCount al MANDAR) se compara con el del server: un speed hack que acelera el
    juego acelera también ese reloj."""
    t = time.monotonic() if ahora is None else ahora
    marca = None
    _reto_y_ritmo(st, d)
    with _cuentas_lock:
        c = _sesion(st.usn)
        c["ult_latido"] = t
        c["latidos"] = c.get("latidos", 0) + 1
        c["interrumpida"] = False
        for k in ("perdidas", "abiertas", "teclado"):
            if d.get(k, "").isdigit():
                c[f"lat_{k}"] = int(d[k])
        tc = int(d["t"]) if d.get("t", "").isdigit() else None
        prev = c.get("reloj_ref")
        if tc is not None:
            if prev is None:
                c["reloj_ref"] = (t, tc)
            else:
                srv = t - prev[0]
                cli = ((tc - prev[1]) & 0xFFFFFFFF) / 1000.0
                if srv >= 50:                                   # con menos, el retraso de la red pesa demasiado
                    razon = cli / srv
                    if abs(razon - 1) > ANTITRAMPA_RELOJ_CLIENTE_TOLERANCIA:
                        c["reloj_malos"] = c.get("reloj_malos", 0) + 1
                    else:
                        c["reloj_malos"] = 0
                    c["reloj_razon"] = round(razon, 3)
                    c["reloj_ref"] = (t, tc)
                    if c["reloj_malos"] >= ANTITRAMPA_RELOJ_CLIENTE_VECES:
                        marca = (razon, srv, cli)
                        c["reloj_malos"] = 0
    if marca:
        razon, srv, cli = marca
        anotar(st, "reloj_cliente", f"el reloj del juego corrió al {razon:.0%} del del server "
                                    f"({cli:.0f} s contra {srv:.0f} s entre latidos)", {},
               evidencia={"razon": round(razon, 3), "cliente_s": round(cli, 1), "server_s": round(srv, 1)})


def al_conectar(st):
    """El lobby registró esta conexión (FF02): la sesión del antitrampa existe desde ya (para el tablero)."""
    usn = getattr(st, "usn", None)
    if ANTITRAMPA and usn:
        with _cuentas_lock:
            _sesion(usn)["visto"] = time.monotonic()


def estado_de(usn):
    """El estado del antitrampa de un jugador, para el tablero: activo | sin_antitrampa | callado | apagado."""
    with _cuentas_lock:
        c = dict(_CUENTAS.get(usn) or {})
    if not c:
        return {"estado": "sin_datos"}
    t = time.monotonic()
    if c.get("apagado"):
        est = "apagado"
    elif not c.get("hola"):
        est = "sin_antitrampa"
    elif c.get("lat") and t - c.get("ult_latido", t) > ANTITRAMPA_LATIDO_TOPE_S:
        est = "callado"
    else:
        est = "activo"
    return {"estado": est, "sesion": c.get("sesion"), "version": c.get("v"), "dll": c.get("dll"), "exe": c.get("exe"),
            "latido_hace_s": round(t - c["ult_latido"]) if c.get("ult_latido") and c.get("lat") else None,
            "latidos": c.get("latidos", 0), "perdidos": c.get("perdidos", 0), "descartados": c.get("descartados", 0),
            "reloj": c.get("reloj_razon"), "retenido": bool(c.get("retener")), "reglas": sorted(c.get("reglas") or ()),
            "pendiente": bool(c.get("expulsado")),
            "usa": [{"texto": k, "tipo": v} for k, v in sorted((c.get("usa") or {}).items(),
                                                                 key=lambda kv: (firmas._ORDEN_TIPO.get(kv[1], 9), kv[0]))]}


def revisar_latidos(conectados, ahora=None):
    """El vigilante (cada 30 s): la dll que dijo que late (`lat=`) y lleva ANTITRAMPA_LATIDO_TOPE_S sin latir con el
    juego conectado -> `telemetria_interrumpida` (una vez; se rearma cuando vuelve a latir). `conectados` = {usn: st}.
    También olvida el estado de los que hace 6 h que no se ven (la memoria no crece sin fin)."""
    t = time.monotonic() if ahora is None else ahora
    marcar = []
    with _cuentas_lock:
        for usn, c in list(_CUENTAS.items()):
            st = conectados.get(usn)
            if st is None:
                if t - c.get("visto", t) > 6 * 3600:
                    _CUENTAS.pop(usn, None)
                    with _farmeo_lock:
                        _FARMEO.pop(usn, None)
                continue
            if c.get("hola") and c.get("lat") and not c.get("interrumpida") \
                    and t - c.get("ult_latido", t) > ANTITRAMPA_LATIDO_TOPE_S:
                c["interrumpida"] = True
                marcar.append((st, t - c.get("ult_latido", t)))
    for st, hace in marcar:
        anotar(st, "telemetria_interrumpida", f"la dll del antitrampa no late hace {hace:.0f} s con el juego "
                                              "conectado (suspendida, colgada o quitada)", {},
               evidencia={"sin_latido_s": round(hace)})
    return len(marcar)


def arrancar_vigilancia(conexiones, cada=30.0):
    """El hilo del vigilante de latidos. `conexiones` = salas.CONEXIONES (usn -> conexión)."""
    try:
        limpiar_correlaciones_falsas()            # ★ 28-nov: los retenidos por la correlación vieja
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ limpiando correlaciones falsas: {e!r}")

    def _ciclo():
        while True:
            time.sleep(cada)
            try:
                revisar_latidos({u: c for u, c in list(conexiones.items()) if c is not None
                                 and not getattr(c, "cerrado", False)})
            except Exception as e:            # noqa: BLE001 — el hilo no se puede morir
                log("TRAMP", f"  ⚠ vigilante de latidos: {e!r}")
    t = threading.Thread(target=_ciclo, daemon=True, name="antitrampa-latidos")
    t.start()
    return t


def al_ff3d(st, data):
    """Cuenta los FF3D(0). Tras `ANTITRAMPA_FF3D0_MIN` en una sesión, una sola marca."""
    if not ANTITRAMPA or bytes(data[:1]) != b"\x00":
        return
    n = getattr(st, "at_ff3d0", 0) + 1
    st.at_ff3d0 = n
    if n == ANTITRAMPA_FF3D0_MIN:
        anotar(st, "animaciones_tocadas",
               f"{n} FF3D(0): las 112 animaciones de tropezar no coinciden con las del server", {})


def anotar(st, regla, detalle, extra, evidencia=None, firma=""):
    """Aplica la acción de la regla y la deja en el REGISTRO CENTRAL. Devuelve la acción (`"retener"`, `"avisar"`, …).
    `extra` va al jsonl de siempre; `evidencia` (más `extra`) va al evento; `firma` separa detecciones distintas de la
    misma regla (dos programas distintos) de la MISMA detección repetida (que sólo suma repeticiones)."""
    accion = ANTITRAMPA_REGLAS.get(regla, "registrar")
    if accion == "apagado":
        return accion
    usn = getattr(st, "usn", None)
    if regla in ANTITRAMPA_FUERA_DEL_PANEL and accion == "registrar":
        return _solo_log(st, usn, regla, detalle, extra, evidencia, firma)
    nick = _nick(usn)
    ctx = _contexto(st)
    cuenta = _cuenta_de(st) if usn else None
    modulo = _MODULO_DE.get(regla, "dll" if evidencia and "r2at" in evidencia else "servidor")
    evento, nuevo = eventos.registrar(regla, detalle, usn=usn, cuenta=cuenta, nick=nick, sesion=ctx["sesion"],
                                      partida=ctx["partida"], modulo=modulo, accion=accion,
                                      evidencia={**(evidencia or {}), **extra}, firma=firma,
                                      version_cliente=ctx["version_cliente"],
                                      version_antitrampa=ctx["version_antitrampa"])
    if not nuevo:                                          # la misma detección persistente: sólo suma repeticiones
        return accion
    log("TRAMP", f"  🚩 {regla} [{accion}] usn={usn} {nick!r}: {detalle}")
    _guardar({"cuando": datetime.datetime.now().isoformat(timespec="seconds"), "evento": evento, "regla": regla,
              "accion": accion, "usn": usn, "nick": nick, "cuenta": cuenta, "sala": getattr(st, "room_id", None),
              "sesion": ctx["sesion"], "detalle": detalle, **extra})
    correlacion = None
    if usn:
        with _cuentas_lock:
            c = _sesion(usn)
            c["reglas"].add(regla)
            if accion == "retener" and regla in _REGLAS_DE_CUENTA:
                c["retener"] = True
            if regla == "antitrampa_apagado":
                c["apagado"] = True
            herr = sorted(c["reglas"] & set(ANTITRAMPA_CORRELACION_HERRAMIENTA))
            alt = sorted(c["reglas"] & set(ANTITRAMPA_CORRELACION_ALTERACION))
            if herr and alt and not c.get("correlacionado"):
                c["correlacionado"] = True
                correlacion = (herr, alt)
            u = firmas.usa_de(regla, {**(evidencia or {}), **extra})     # ★ 28-nov: «está usando»
            if u:
                c.setdefault("usa", {})[u[0]] = u[1]
            gm_nuevo = regla not in c["gm_avisados"]
            c["gm_avisados"].add(regla)
    else:
        gm_nuevo = True
    if accion in ("retener", "avisar") and gm_nuevo:
        _avisar_gms(f"ANTITRAMPA {regla}: {nick or usn} — {detalle}"
                    + (" (premio retenido)" if accion == "retener" else ""))
    if accion == "expulsar":
        _expulsar(st, usn, nick, regla, detalle, evento=evento)
    if correlacion:
        herr, alt = correlacion
        anotar(st, "manipulacion_correlacionada", f"herramienta ({', '.join(herr)}) y alteración del juego "
                                                  f"({', '.join(alt)}) en la misma sesión", {},
               evidencia={"herramientas": herr, "alteraciones": alt})
    return accion


def _solo_log(st, usn, regla, detalle, extra, evidencia, firma):
    """★ 28-nov: el ruido de todos (memoria ajena, launcher, arranque restaurado): log y jsonl una vez por sesión y
    firma, cuenta en la sesión, pero NO va al registro central (el panel no lo muestra)."""
    nuevo = True
    if usn:
        with _cuentas_lock:
            c = _sesion(usn)
            vistos = c.setdefault("solo_log", set())
            nuevo = (regla, str(firma)) not in vistos
            vistos.add((regla, str(firma)))
            c["reglas"].add(regla)
            u = firmas.usa_de(regla, {**(evidencia or {}), **extra})
            if u:
                c.setdefault("usa", {})[u[0]] = u[1]
    if nuevo:
        nick = _nick(usn)
        log("TRAMP", f"  · {regla} [registrar, fuera del panel] usn={usn} {nick!r}: {detalle}")
        _guardar({"cuando": datetime.datetime.now().isoformat(timespec="seconds"), "regla": regla,
                  "accion": "registrar", "usn": usn, "nick": nick, "sala": getattr(st, "room_id", None),
                  "detalle": detalle, **extra})
    return "registrar"


# Qué módulo del antitrampa vio cada regla (el resto: «dll» si vino de un R2AT, si no «servidor»).
_MODULO_DE = {"combo_imposible": "cartel", "porcentaje_imposible": "cartel", "precision_imposible": "cartel",
              "llegada_imposible": "cartel", "llegada_anticipada": "cartel", "reloj_rapido": "cartel",
              "reloj_lento": "cartel", "sin_antitrampa": "cartel", "animaciones_tocadas": "ff3d",
              "listo_automatico": "farmeo", "carreras_sin_hablar": "farmeo", "misma_cancion": "farmeo",
              "campanas_automaticas": "farmeo", "combo_repetido": "farmeo", "precision_constante": "farmeo",
              "expulsa_espectadores": "farmeo", "farmeo": "farmeo", "manipulacion_correlacionada": "correlacion",
              "auto_perfecto": "farmeo",
              "telemetria_interrumpida": "telemetria", "telemetria_inundada": "telemetria",
              "telemetria_repetida": "telemetria", "reloj_cliente": "telemetria"}


# Las que informa el cliente fuera de una carrera: si son «retener», retienen todas las de la sesión.
_REGLAS_DE_CUENTA = {"modulo_prohibido", "juego_automatico", "sala_automatica", "relevo_automatico",
                     "codigo_modificado", "codigo_previo", "exe_desconocido", "memoria_ajena", "depurador",
                     "animaciones_tocadas"}
_QUE_RETIENEN = ("retener", "expulsar")
_BLOQUEADOS = {}                              # usn -> time.monotonic() hasta el que no puede jugar
_ESCALON_FALLO = {}                           # usn -> True si su última falta NO se pudo sumar (ver `_escalon`)
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
    -> (faltas, cuenta, baneada). Sin base o sin cuenta cuenta como la primera.
    ★ 26-nov: si NO pudo sumar la falta (sin base, sin cuenta, el Coordinador no contestó) deja `_ESCALON_FALLO[usn]`:
    la tanda no marca esas detecciones como sancionadas (antes se perdían)."""
    _ESCALON_FALLO.pop(usn, None)
    if _usa_coordinador():
        try:
            from . import almacen
            cuenta, _ = almacen.cuenta_de_uid(usn)
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude buscar la cuenta de usn={usn}: {e!r}")
            _ESCALON_FALLO[usn] = True
            return 1, None, False
        eid = _enenos_id_de_cuenta(cuenta)
        if eid is not None:
            from . import pase
            try:
                res = pase.avisar_antitrampa_interno(eid, regla, detalle=detalle, nick=nick, timeout=3.0)
            except Exception as e:            # noqa: BLE001
                log("TRAMP", f"  ⚠ no pude avisar al Coordinador (usn={usn}, eid={eid}): {e!r}")
                _ESCALON_FALLO[usn] = True
                return 1, cuenta, False
            if res.get("estado") != "ok" or not isinstance(res.get("datos"), dict):
                log("TRAMP", f"  ⚠ no pude avisar al Coordinador (usn={usn}, eid={eid}): "
                             f"{res.get('error') or res.get('codigo')}")
                _ESCALON_FALLO[usn] = True
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
        _ESCALON_FALLO[usn] = True
        return 1, None, False
    if not cuenta:
        _ESCALON_FALLO[usn] = True
        return 1, None, False
    baneada = False
    if ANTITRAMPA_BANEO_EN and n >= ANTITRAMPA_BANEO_EN:
        try:
            almacen.banear_cuenta(cuenta)
            baneada = True
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude banear la cuenta {cuenta!r}: {e!r}")
    return n, cuenta, baneada


def _expulsar(st, usn, nick, regla, detalle, evento=None):
    """Lo que hace una regla «expulsar».
    ★ 24-nov — con `ANTITRAMPA_SILENCIOSO` (de fábrica) NO expulsa: retiene el premio en silencio y deja la detección
    pendiente para la tanda de un GM (`_detener_en_silencio`). Sin él, la expulsión al instante de siempre."""
    # ★ UNA falta por sesión del juego (de «hola» a «hola»): con dos funciones prendidas llegan dos ganchos en el mismo
    #   segundo (medido 19-nov: automático + sala ⇒ 1.ª y 2.ª juntas). Lo que llegue después sólo vuelve a cerrar.
    with _cuentas_lock:
        sesion = _sesion(usn) if usn else {}
        ya = sesion.get("expulsado")
        sesion["expulsado"] = True
        reglas = sesion.setdefault("reglas_pendientes", set())
        nueva = regla not in reglas
        reglas.add(regla)
    if ANTITRAMPA_SILENCIOSO and usn:
        if ya and not nueva:
            log("TRAMP", f"  🤫 usn={usn}: {regla} otra vez en la misma sesión: ya está pendiente")
            return
        _detener_en_silencio(usn, nick, regla, detalle, evento=evento)
        return
    if ya:
        log("TRAMP", f"  ⛔ usn={usn}: {regla} en la misma sesión ya expulsada: no suma otra falta, sólo cierra")
        _cerrar_luego(st, usn, regla)
        return
    _sancionar(st, usn, nick, regla, detalle)


def _detener_en_silencio(usn, nick, regla, detalle, evento=None):
    """★ 24-nov — EL MODO SILENCIOSO: el jugador no se entera de nada. Lo que quede de esta sesión no cobra (ni exp,
    ni Rcoin, ni récord, ni medallas, ni misiones: `retenido`), los GM conectados lo ven y la detección queda en
    `antitrampa_pendientes` hasta la tanda (`sancionar_tanda`, `.sanciones aplicar`)."""
    with _cuentas_lock:
        _sesion(usn)["retener"] = True
    pid = None
    try:
        from . import almacen
        # ★ 26-nov: UN pendiente por cuenta y regla mientras espere la tanda (antes: uno por cada «hola»)
        cuenta = almacen.cuenta_de_uid(usn)[0]
        ya = next((f["id"] for f in almacen.antitrampa_pendientes(0)
                   if f["regla"] == regla and (f.get("cuenta") == cuenta if cuenta else f.get("usn") == usn)), None)
        if ya is not None:
            pid = ya
        else:
            pid, _ = almacen.antitrampa_dejar_pendiente(usn, regla, detalle=detalle, nick=nick)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude dejar pendiente la detección de usn={usn}: {e!r}")
    eventos.poner_pendiente(evento, pid)
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
            _sesion(usn)["retener"] = True
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


def sancionar_tanda(quien="", ya=False, solo_cuenta=None):
    """Aplica la escalera a cada cuenta con detecciones pendientes (de más de `ANTITRAMPA_TANDA_DEMORA_H` horas, o
    todas con `ya`). ★ 28-nov: `solo_cuenta` = sólo esa cuenta (el botón «Sancionar ya» del tablero). -> las líneas."""
    from . import almacen
    filas = almacen.antitrampa_pendientes(0 if ya else ANTITRAMPA_TANDA_DEMORA_H)
    if solo_cuenta:
        filas = [f for f in filas if (f.get("cuenta") or "").lower() == str(solo_cuenta).lower()]
    if not filas:
        return ["antitrampa: no hay detecciones para sancionar" + ("" if ya else
                f" (con mas de {ANTITRAMPA_TANDA_DEMORA_H}h; '.sanciones aplicar ya' no espera)")]
    lineas = []
    for clave, fs in _agrupar(filas).items():
        reglas = sorted({f["regla"] for f in fs})
        usns = list(dict.fromkeys(f["usn"] for f in reversed(fs)))      # el más reciente primero
        nick = next((f["nick"] for f in reversed(fs) if f.get("nick")), "") or _nick(usns[0])
        detalle = f"{len(fs)} deteccion(es): {', '.join(reglas)}"
        grave = max(reglas, key=_gravedad)
        try:
            faltas, cuenta, baneada, que = _sancionar(None, usns[0], nick, grave, detalle, otros_usns=usns[1:])
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude sancionar {clave!r}: {e!r}")
            lineas.append(f"- {nick}: ERROR ({e!r}), queda pendiente")
            continue
        if _ESCALON_FALLO.pop(usns[0], None):
            lineas.append(f"- {nick or clave}: la falta NO se pudo sumar (sin base, sin cuenta o el Coordinador no "
                          f"contestó): queda pendiente")
            continue
        almacen.antitrampa_resolver([f["id"] for f in fs], "sancionada", quien)
        try:
            almacen.ev_marcar(pendientes=[f["id"] for f in fs], estado="sancionado", por=quien or "tanda",
                              nota=que)
            almacen.at_accion(quien or "tanda", "tanda", cuenta, usns[0], None, f"{que}: {detalle}")
        except Exception as e:                # noqa: BLE001
            log("TRAMP", f"  ⚠ no pude marcar los eventos de la tanda: {e!r}")
        _guardar({"cuando": datetime.datetime.now().isoformat(timespec="seconds"), "regla": grave,
                  "accion": "sancion_en_tanda", "usn": usns[0], "nick": nick, "cuenta": cuenta, "faltas": faltas,
                  "baneada": baneada, "quien": quien, "detalle": detalle})
        lineas.append(f"- {nick or clave}: {que}")
    log("TRAMP", f"  ⚖ tanda de sanciones de {quien!r}: {len(lineas)} cuenta(s)")
    return [f"antitrampa: tanda aplicada a {len(lineas)} cuenta(s)"] + lineas


def _gravedad(regla):
    from .antitrampa_eventos import RIESGOS, clasificar
    _cat, riesgo, confianza, _origen = clasificar(regla)
    return (RIESGOS.index(riesgo) if riesgo in RIESGOS else 0, confianza)


def perdonar_pendientes(quien_es, quien=""):
    """Descarta (falso positivo) las detecciones pendientes de ese apodo, usn o cuenta. -> las líneas para el GM."""
    from . import almacen
    q = str(quien_es).strip().lower()
    fs = [f for f in almacen.antitrampa_pendientes(0)
          if q in (str(f["usn"]), (f.get("nick") or "").lower(), (f.get("cuenta") or "").lower())]
    if not fs:
        return [f"antitrampa: {quien_es!r} no tiene detecciones pendientes"]
    n = almacen.antitrampa_resolver([f["id"] for f in fs], "perdonada", quien)
    try:
        almacen.ev_marcar(pendientes=[f["id"] for f in fs], estado="descartado", por=quien or "gm", nota="perdonado")
        almacen.at_accion(quien or "gm", "perdonar", fs[0].get("cuenta"), fs[0].get("usn"), None, f"{n} pendiente(s)")
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude marcar los eventos perdonados: {e!r}")
    _soltar_retencion({f["usn"] for f in fs if f.get("usn") is not None}, {f.get("cuenta") for f in fs} - {None, ""})
    log("TRAMP", f"  🕊 {quien!r} perdonó {n} detección(es) de {quien_es!r}")
    return [f"antitrampa: {n} deteccion(es) de {quien_es} descartada(s)"]


def _soltar_retencion(usns, cuentas=()):
    """★ 28-nov: al perdonar, la retención de ESTA sesión se levanta ya (antes seguía sin cobrar hasta reabrir el juego),
    salvo que le quede otra detección pendiente."""
    try:
        from . import almacen
        quedan = almacen.antitrampa_pendientes(0)
    except Exception:                         # noqa: BLE001
        quedan = []
    vivos_usn = {f.get("usn") for f in quedan}
    vivas_cta = {f.get("cuenta") for f in quedan} - {None, ""}
    with _cuentas_lock:
        for usn, c in _CUENTAS.items():
            mia = usn in usns
            if not mia and cuentas:
                try:
                    from . import almacen
                    mia = almacen.cuenta_de_uid(usn)[0] in cuentas
                except Exception:             # noqa: BLE001
                    mia = False
            if not mia or usn in vivos_usn:
                continue
            try:
                from . import almacen
                if almacen.cuenta_de_uid(usn)[0] in vivas_cta:
                    continue
            except Exception:                 # noqa: BLE001
                pass
            if c.get("retener"):
                c["retener"] = False
                c.pop("correlacionado", None)
                log("TRAMP", f"  🕊 usn={usn}: retención levantada (perdonado)")


_ALT_DEBILES = ("memoria_ajena",)


def limpiar_correlaciones_falsas(quien="servidor"):
    """★ 28-nov: perdona las `manipulacion_correlacionada` pendientes cuya única alteración era `memoria_ajena` (la que
    da cualquier juego limpio). Se corre al arrancar: los que la regla vieja retuvo sin motivo vuelven a cobrar.
    -> cuántas perdonó."""
    from . import almacen
    try:
        fs = almacen.antitrampa_pendientes(0)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude leer los pendientes para limpiar correlaciones: {e!r}")
        return 0
    falsas = []
    for f in fs:
        if f.get("regla") != "manipulacion_correlacionada":
            continue
        m = re.search(r"alteración del juego \(([^)]*)\)", f.get("detalle") or "")
        alt = {a.strip() for a in m.group(1).split(",")} if m else set()
        if alt and alt <= set(_ALT_DEBILES):
            falsas.append(f)
    if not falsas:
        return 0
    n = almacen.antitrampa_resolver([f["id"] for f in falsas], "perdonada", quien)
    try:
        almacen.ev_marcar(pendientes=[f["id"] for f in falsas], estado="descartado", por=quien,
                          nota="falso positivo: memoria_ajena sola ya no correlaciona")
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude marcar los eventos de las correlaciones falsas: {e!r}")
    _soltar_retencion({f["usn"] for f in falsas if f.get("usn") is not None},
                      {f.get("cuenta") for f in falsas} - {None, ""})
    log("TRAMP", f"  🕊 {n} manipulacion_correlacionada falsa(s) perdonada(s) (sólo memoria_ajena): "
                 + ", ".join(sorted({str(f.get('nick') or f.get('usn')) for f in falsas})))
    return n


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
        "expulsiones": deque(maxlen=ANTITRAMPA_EXPULSIONES), "senales": set(),
        "perfectas": deque(maxlen=ANTITRAMPA_PERFECTA_CARRERAS)})


def _ahora(ahora):
    return time.monotonic() if ahora is None else ahora


def _senal(st, regla, detalle, evidencia=None):
    """Anota una señal (una vez por sesión) y, si ya van las suficientes, el «farmeo». Devuelve la acción más dura."""
    usn = getattr(st, "usn", None)
    with _farmeo_lock:
        e = _estado(usn)
        if regla in e["senales"]:
            return None
        e["senales"].add(regla)
        reales = sorted(s for s in e["senales"] if s != "farmeo"
                        and ANTITRAMPA_REGLAS.get(s, "registrar") not in ("apagado", "registrar"))
        # ★ 26-nov: callado + teclado en pantalla (o la misma canción) no es un bot: hace falta una señal fuerte
        fuertes = [s for s in reales if s not in ANTITRAMPA_SENALES_DEBILES]
        farmeo = len(reales) >= ANTITRAMPA_FARMEO_SENALES and fuertes and "farmeo" not in e["senales"]
        if farmeo:
            e["senales"].add("farmeo")
    accion = anotar(st, regla, detalle, {}, evidencia=evidencia)
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
        total = notas.combo_total_de(cancion) if cancion else None
    except Exception:                         # noqa: BLE001
        nivel = total = None
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
        # ★ 28-nov · AUTO PERFECT: combo completo y precisión casi perfecta, una y otra vez, en canciones difíciles
        if nivel is not None and nivel >= ANTITRAMPA_PERFECTA_NIVEL and total:
            e["perfectas"].append(combo >= total and pd >= ANTITRAMPA_PERFECTA_PD)
            n = sum(e["perfectas"])
            if len(e["perfectas"]) >= ANTITRAMPA_PERFECTA_CARRERAS and n >= ANTITRAMPA_PERFECTA_VECES:
                senales.append(("auto_perfecto", f"combo completo y precisión ≥ {ANTITRAMPA_PERFECTA_PD} en {n} de sus "
                                                 f"últimas {len(e['perfectas'])} carreras de nivel "
                                                 f"{ANTITRAMPA_PERFECTA_NIVEL} o más"))
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
            try:                                  # ★ 26-nov: rota a .1 al pasar ANTITRAMPA_JSONL_MAX_MB
                if os.path.getsize(ANTITRAMPA_ARCHIVO) > ANTITRAMPA_JSONL_MAX_MB * 1024 * 1024:
                    os.replace(ANTITRAMPA_ARCHIVO, ANTITRAMPA_ARCHIVO + ".1")
            except OSError:
                pass
            with open(ANTITRAMPA_ARCHIVO, "a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except OSError as e:
        log("TRAMP", f"  ⚠ no pude escribir {ANTITRAMPA_ARCHIVO}: {e!r}")


_avisos_gm = deque()
_avisos_gm_lock = threading.Lock()


def _avisar_gms(texto):
    """★ 26-nov: con tope (ANTITRAMPA_AVISOS_GM_POR_MINUTO): una inundación de detecciones no inunda el chat de los
    GM; todo queda igual en el tablero."""
    t = time.monotonic()
    with _avisos_gm_lock:
        while _avisos_gm and t - _avisos_gm[0] > 60:
            _avisos_gm.popleft()
        if len(_avisos_gm) >= ANTITRAMPA_AVISOS_GM_POR_MINUTO:
            return
        _avisos_gm.append(t)
    try:
        from .gm import es_gm
        from .salas import CONEXIONES, avisar_a_uno
        for c in list(CONEXIONES.values()):
            if c is not None and es_gm(c):
                avisar_a_uno(c, texto)
    except Exception as e:                    # noqa: BLE001
        log("TRAMP", f"  ⚠ no pude avisar a los GM: {e!r}")
