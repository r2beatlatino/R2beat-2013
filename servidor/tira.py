# -*- coding: utf-8 -*-
r"""tira — la TIRA DE ANUNCIOS de arriba del lobby (`cTicker`), el `FFBF` (29-sep).

anonimo03, con una captura vieja del juego: *"en la parte superior hay como una tira de anuncio, necesitamos
encontrarla y cablearla, y ver si sirve para mensaje o anuncio del servidor en vivo o sólo en el arranque"*.

LO MEDIDO EN EL EXE (`documentacion/TIRA_DE_ANUNCIOS.md`)
    clase       `cTicker` (`.\cTicker.cpp`, dibujo `rnr_ui/notice/ticker.spr`), instancia en `[0x9314A4]`
    el paquete  `FFBF` -> `0x5D80B0`:  [u8 n] { registro de 0x828 B } × n
                ★ lo primero que hace es VACIAR la tira (`0x443060`) y después agrega los n (`0x4436B0`)
                ⇒ cada FFBF REEMPLAZA la lista entera: sirve EN VIVO, no sólo al entrar.
    registro    +0x000 u32   id          (mismo id = reemplaza; activo=0 lo saca)
                +0x004 char[16] desde    "AAAAMMDDhhmmss" (`0x4097C0` -> mktime: hora LOCAL del jugador)
                +0x014 char[16] hasta    idem · fuera de la ventana el cliente lo BORRA (`0x4430E0`)
                +0x024 char[0x800] texto
                +0x825 u8    activo      (0 = no se agrega / se saca)
    el dibujo   cada ~18 s (timer 0x1194 de 0x4650 ms) junta los textos activos en UN buffer
                (`0x931AF0`, ~2.450 B hasta el siguiente global) separados por 9 espacios, y los pasa.

⚠ LAS TRAMPAS
  · la ventana va en la hora LOCAL de cada jugador (y los jugadores están en husos distintos): un «desde
    ahora» puede ser el futuro para otro, y un «hasta dentro de 2 h» ya pasó para el que va 12 h adelante;
    el cliente BORRA los dos sin decir nada (lo cazó `probar_tira`). Por eso al cliente va una ventana
    HOLGADA (un día de más de cada lado; permanente = 2000..2037) y el vencimiento de VERDAD lo hace el
    server: cuando un anuncio vence, vuelve a difundir la tira sin él (`_programar_vencimiento`).
  · `time_t` de 32 bits (VC 7.1): 2038 no existe. 2037-12-31 es el «para siempre».
  · el buffer de la tira es uno solo: el TOTAL (textos + separadores) se acota a `TIRA_TOTAL_MAX`.
"""
import struct
import time

from .ajustes import TIRA_ACTIVA, TIRA_TEXTO_MAX, TIRA_TOTAL_MAX
from .registro import log

REGISTRO = 0x828
OFF_DESDE, OFF_HASTA, OFF_TEXTO, OFF_ACTIVO = 0x004, 0x014, 0x024, 0x825
SEPARADOR = 9                                  # espacios que pone el cliente entre dos textos
SIEMPRE_DESDE, SIEMPRE_HASTA = "20000101000000", "20371231000000"


def _fecha(t):
    return time.strftime("%Y%m%d%H%M%S", time.localtime(t))


def texto_para_la_tira(texto):
    """El texto como lo dibuja el cliente: en ASCII (como el chat: una tilde se come la letra de al lado)."""
    from .chat import a_ascii
    return " ".join(a_ascii(texto).split())[:TIRA_TEXTO_MAX]


def registro(id_, texto, hasta=None, ahora=None):
    """Un registro de 0x828 B. `hasta` = epoch o None (para siempre)."""
    ahora = time.time() if ahora is None else ahora
    b = bytearray(REGISTRO)
    struct.pack_into("<I", b, 0, int(id_) & 0xFFFFFFFF)
    if hasta:
        desde, fin = _fecha(ahora - 86400), _fecha(min(hasta + 86400, 2145830400))
    else:
        desde, fin = SIEMPRE_DESDE, SIEMPRE_HASTA
    b[OFF_DESDE:OFF_DESDE + 14] = desde.encode("ascii")
    b[OFF_HASTA:OFF_HASTA + 14] = fin.encode("ascii")
    t = texto_para_la_tira(texto).encode("ascii")
    b[OFF_TEXTO:OFF_TEXTO + len(t)] = t
    b[OFF_ACTIVO] = 1
    return bytes(b)


def armar_ffbf(anuncios, ahora=None):
    """El cuerpo del FFBF con los anuncios vigentes, cortando cuando el total no entra en el buffer."""
    ahora = time.time() if ahora is None else ahora
    regs, total = [], 0
    for a in anuncios:
        if not a.get("activo", 1) or (a.get("hasta") and a["hasta"] <= ahora):
            continue
        largo = len(texto_para_la_tira(a["texto"]))
        if not largo:
            continue
        if total + largo + SEPARADOR > TIRA_TOTAL_MAX or len(regs) >= 255:
            log("LOBBY", f"  ⚠ la tira no entera: quedan afuera los anuncios desde el {a.get('id')}")
            break
        total += largo + SEPARADOR
        regs.append(registro(a["id"], a["texto"], a.get("hasta"), ahora))
    return bytes([len(regs)]) + b"".join(regs)


def _anuncios():
    from .basedatos import db_tira_anuncios
    return db_tira_anuncios()


def enviar_tira(st, motivo="al entrar"):
    """La tira al que entra al lobby (o cambia de canal). Con la tabla vacía no se manda nada.

    ★ Una vez por CONEXIÓN: en el login llegan el FF03 y el FF06 y los dos la piden; al cambiar de canal la
      conexión es nueva y sólo llega el FF06."""
    if not TIRA_ACTIVA or getattr(st, "tira_enviada", False):
        return
    try:
        anuncios = _anuncios()
        if not anuncios:
            return
        body = armar_ffbf(anuncios)
        _programar_vencimiento(anuncios)          # tras un reinicio, el primero que entra lo re-arma
        st.send_ff55(0xBF, body, name=f"FFBF tira de anuncios ({body[0]}) {motivo}")
        st.tira_enviada = True
    except Exception as e:                                             # noqa: BLE001
        log("LOBBY", f"  ⚠ no pude mandar la tira: {e!r}")


def difundir_tira():
    """La tira a TODOS los conectados (tras un cambio). Devuelve a cuántos llegó.

    ⚠ Con la tabla vacía se manda `n = 0`: el cliente VACÍA la suya (así se borra un anuncio en vivo)."""
    if not TIRA_ACTIVA:
        return 0
    from .salas import CONEXIONES
    body = armar_ffbf(_anuncios())
    n = 0
    for c in list(CONEXIONES.values()):
        if getattr(c, "cerrado", False):
            continue
        try:
            c.send_ff55(0xBF, body, name=f"FFBF tira de anuncios ({body[0]}) difusión")
            n += 1
        except Exception:                                              # noqa: BLE001
            pass
    log("LOBBY", f"  📰 tira de anuncios difundida: {body[0]} anuncio(s) a {n} conectado(s)")
    _programar_vencimiento()
    return n


_TIMER = {"t": None, "cuando": 0}


def _programar_vencimiento(anuncios=None):
    """Un temporizador para el PRÓXIMO vencimiento: ahí se vuelve a difundir la tira (sin el vencido)."""
    import threading
    try:
        anuncios = _anuncios() if anuncios is None else anuncios
    except Exception:                                                  # noqa: BLE001
        return
    ahora = time.time()
    prox = min((a["hasta"] for a in anuncios if a.get("activo", 1) and a.get("hasta") and a["hasta"] > ahora),
               default=0)
    if not prox or (_TIMER["t"] and _TIMER["cuando"] == prox):
        return
    if _TIMER["t"]:
        _TIMER["t"].cancel()
    t = threading.Timer(prox - ahora + 1, difundir_tira)
    t.daemon = True
    _TIMER["t"], _TIMER["cuando"] = t, prox
    t.start()


# ── para el PANEL (`/admin/tira`, `panel_admin.tira_*`, 29-sep) ──────────────────────────────────────────────
#   anonimo03: *"la opción de poner mensajes de tiras como por forms de filas en mi panel admin, una que siempre
#   estará y otras que pueden ser editadas"*. Cada fila: el texto, «siempre» o una fecha de vencimiento, y si
#   está activa. Guardar = dejar la tabla IGUAL a las filas del panel y difundir.
def lista_panel():
    ahora = time.time()
    filas = []
    for a in _anuncios():
        vence = int(a["hasta"] or 0)
        filas.append({"id": a["id"], "texto": a["texto"], "se_ve": texto_para_la_tira(a["texto"]),
                      "siempre": not vence, "vence": vence or None, "vencido": bool(vence and vence <= ahora),
                      "activo": bool(a["activo"]), "quien": a["quien"], "creado": a["creado"]})
    return filas


def guardar_panel(filas, quien="", ahora=None):
    """Deja la tabla igual a `filas` ([{id|None, texto, siempre, vence, activo}]) y difunde.

    -> (None, resumen) o (error, None). Valida TODO antes de escribir: una fila mala no deja la tabla a medias."""
    from .basedatos import db_agregar_tira, db_editar_tira, db_quitar_tira
    ahora = time.time() if ahora is None else ahora
    if not isinstance(filas, list) or len(filas) > 50:
        return "filas: una lista (hasta 50)", None
    limpias = []
    for i, f in enumerate(filas, 1):
        if not isinstance(f, dict):
            return f"fila {i}: mal armada", None
        texto = " ".join(str(f.get("texto") or "").split())
        if not texto_para_la_tira(texto):
            return f"fila {i}: falta el texto", None
        if len(texto) > TIRA_TEXTO_MAX:
            return f"fila {i}: el texto pasa de {TIRA_TEXTO_MAX} letras", None
        hasta = 0
        if not f.get("siempre"):
            try:
                hasta = int(f.get("vence") or 0)
            except (TypeError, ValueError):
                hasta = 0
            if hasta <= ahora:
                return f"fila {i}: poné «siempre» o un vencimiento en el futuro", None
        id_ = f.get("id")
        limpias.append((int(id_) if isinstance(id_, int) or (isinstance(id_, str) and id_.isdigit()) else None,
                        texto, hasta, bool(f.get("activo", True))))
    antes = {a["id"]: a for a in _anuncios()}
    quedan = {id_ for id_, *_r in limpias if id_ in antes}
    for id_ in set(antes) - quedan:
        db_quitar_tira(id_)
    nuevos = editados = 0
    for id_, texto, hasta, activo in limpias:
        if id_ in antes:
            a = antes[id_]
            if (a["texto"], int(a["hasta"] or 0), bool(a["activo"])) != (texto, hasta, activo):
                db_editar_tira(id_, texto, hasta, activo)
                editados += 1
        else:
            nuevo = db_agregar_tira(texto, hasta, quien, int(ahora))
            if not activo:
                db_editar_tira(nuevo, texto, hasta, False)
            nuevos += 1
    llego = difundir_tira()
    total = sum(len(texto_para_la_tira(t)) + SEPARADOR for _i, t, h, act in limpias if act)
    return None, {"nuevos": nuevos, "editados": editados, "quitados": len(set(antes) - quedan),
                  "llego_a": llego, "largo_total": total, "entra": total <= TIRA_TOTAL_MAX}
