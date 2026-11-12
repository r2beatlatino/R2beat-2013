# -*- coding: utf-8 -*-
"""registro — el log y el modo paso a paso

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
import datetime
import os
import sys
import threading
import time

from .ajustes import (
    LOG,
    PASO_HANDSHAKE,
)

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original

_loglock = threading.Lock()

# ★ 29-sep (optimización para el VPS, `documentacion/BANCO_VPS.md` §5): el archivo queda ABIERTO.
#   Antes se abría, se escribía y se cerraba en CADA línea (~300 por segundo con 300 conectados).
#   ⛔ PERO prod ROTA el log EN CALIENTE: `disk_trim.sh` lo RENOMBRA a `.1` y cuenta con que la línea
#     siguiente cree uno nuevo (`DEPLOY_VPS_2026-09-05.md` §12, probado en vivo). Con el archivo abierto
#     eso dejaría de pasar: seguiríamos escribiendo en el `.1` para siempre y el disco se llenaría.
#   ⇒ Una vez por segundo se mira si `LOG` sigue siendo EL MISMO archivo (dispositivo + inodo); si lo
#     renombraron o lo borraron, se abre uno nuevo. Lo que caiga en ese segundo queda en el `.1`, que
#     se guarda: no se pierde nada. Prueba: `probar_optimizaciones.py` §4 (renombra en caliente, en Linux).
#   ⚠ Sólo en Linux: Windows no deja renombrar un archivo abierto (y en esta máquina el log se renombra
#     al arrancar). Acá queda como era.
LOG_ABIERTO = os.name != "nt"
# ★ 29-sep: `R2_LOG_CONSOLA=0` = el log SÓLO al archivo, sin copia por la consola. En prod la consola va a
#   journald —otro proceso, en el MISMO núcleo— que guarda apenas 1 hora (el archivo lo tiene todo).
#   Medido en el WSL: 300 líneas/s le cuestan a journald ~2,7 % del núcleo del VPS. Por defecto PRENDIDA,
#   como siempre: apagarla en prod lo decide anonimo03 (`BANCO_VPS.md` §5).
LOG_CONSOLA = os.environ.get("R2_LOG_CONSOLA", "1") != "0"
MIRAR_CADA = 1.0                      # segundos entre «¿sigue siendo el mismo archivo?»
_fh = {"f": None, "ruta": None, "id": None, "mirado": 0.0}


def _cerrar_archivo():
    f, _fh["f"] = _fh["f"], None
    if f is not None:
        try:
            f.close()
        except OSError:
            pass


def _archivo():
    """El log abierto (y reabierto si lo rotaron). Se llama con `_loglock` tomado."""
    ahora = time.monotonic()
    f = _fh["f"]
    if f is not None and _fh["ruta"] == LOG and ahora - _fh["mirado"] < MIRAR_CADA:
        return f
    _fh["mirado"] = ahora
    try:
        st = os.stat(LOG)
        ident = (st.st_dev, st.st_ino)
    except OSError:
        ident = None                  # lo borraron (o lo movieron y todavía no hay otro)
    if f is not None and _fh["ruta"] == LOG and ident == _fh["id"]:
        return f
    _cerrar_archivo()
    f = open(LOG, "a", encoding="utf-8")
    st = os.fstat(f.fileno())
    _fh.update(f=f, ruta=LOG, id=(st.st_dev, st.st_ino))
    return f


def log(role, msg):
    line = f"{datetime.datetime.now():%H:%M:%S} [{role:5}] {msg}"
    with _loglock:
        if LOG_CONSOLA:
            print(line, flush=True)
        if LOG_ABIERTO:
            try:
                f = _archivo()
                f.write(line + "\n")
                f.flush()
                return
            except OSError:
                _cerrar_archivo()     # y se escribe como antes, abajo
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★ EL RESUMEN DE LOS PAQUETES DE ALTA FRECUENCIA (25-sep) — la prueba de carga de la charla
#     (`herramientas/medir_charla.py`) midió que con 40 en la sala el 90 % del CPU se iba en ESCRIBIR
#     EL LOG: cada paso (FF23) se reenvía a 39 y cada envío escribía su línea (y el cliente manda
#     el paso, que se logueaba con 2 más). Es como el CBT llegó a un log de 11 GB.
#     ⇒ No se SILENCIA (la regla del log: «se resume, no se esconde»): se CUENTA, y una vez por
#       minuto sale UNA línea con cuántos de cada uno y su ritmo. Los paquetes importantes siguen
#       saliendo todos, uno por uno.
#     Uso: `c.send_ff55(cmd, data, name=RESUMIR)` · `resumir("RX FF23")`.
# ══════════════════════════════════════════════════════════════════════════════════════════════
RESUMIR = "(resumido)"            # ★ el `name` que marca un envío como de alta frecuencia
_resumen = {}                     # clave -> conteo desde la última línea
_resumen_t = [0.0]
_resumen_lock = threading.Lock()
RESUMEN_CADA = 60.0


def resumir(clave):
    """Cuenta un paquete de alta frecuencia; una vez por minuto escribe UNA línea con todos."""
    import time as _t
    ahora = _t.time()
    with _resumen_lock:
        _resumen[clave] = _resumen.get(clave, 0) + 1
        if not _resumen_t[0]:
            _resumen_t[0] = ahora
        if ahora - _resumen_t[0] < RESUMEN_CADA:
            return
        mins = (ahora - _resumen_t[0]) / 60.0
        linea = " · ".join(f"{k} x{v} (~{v / mins:.0f}/min)" for k, v in sorted(_resumen.items()))
        _resumen.clear()
        _resumen_t[0] = ahora
    log("LOBBY", f"  📦 alta frecuencia, último minuto (resumido): {linea}")


def guardar_log_anterior(ruta=None):
    """Al ARRANCAR: el log de la corrida anterior se GUARDA con la fecha, no se vacía.

    ⛔⛔ 2026-09-24: `lobby.main()` hacía `open(LOG, "w")` y cada arranque BORRABA el log entero. En
      el deploy de ese día se perdieron tres días de historial de prod (21-sep 15:01 al 24-sep
      16:06): el `.1` que había era un renombre a mano de otro deploy, y `journalctl` guarda 1 hora.
    ⇒ Se renombra a `servidor.log.AAAAMMDD-HHMMSS` y el nuevo arranca vacío, igual que antes.
      Devuelve la ruta del guardado, o `None` si no había nada que guardar.
    ★ Si al lado del log hay `_trabajo/logs/` (la máquina de desarrollo) el guardado va AHÍ: en la
      raíz volvería a juntar los 88 logs que se barrieron el 16-sep (y lo caza `probar_estructura`).
      En prod esa carpeta no existe y queda al lado del log.
    """
    ruta = ruta or LOG
    guardado = None
    with _loglock:
        _cerrar_archivo()             # ★ el log que queda abierto (29-sep): se suelta antes de renombrarlo
    try:
        if os.path.exists(ruta) and os.path.getsize(ruta) > 0:
            _dir = os.path.join(os.path.dirname(os.path.abspath(ruta)), "_trabajo", "logs")
            _base = (os.path.join(_dir, os.path.basename(ruta)) if os.path.isdir(_dir)
                     else ruta)
            guardado = f"{_base}.{datetime.datetime.now():%Y%m%d-%H%M%S}"
            os.replace(ruta, guardado)
    except OSError as e:
        print(f"⚠ no pude guardar el log anterior ({e!r}): se sigue escribiendo al final", flush=True)
        return None
    open(ruta, "a").close()
    return guardado


def hx(b):
    return " ".join(f"{x:02x}" for x in b)


# ─────────────────────────── MODO PASO A PASO (R2_PASO=1) ───────────────────────────
# Para cazar QUE respuesta no le gusta al cliente: en vez de mandarle todo de un saque, el
# server frena ANTES de cada envio y espera que el operador diga que hacer. El ultimo que se
# manda antes de que el cliente muera es el culpable.
#
#   [Enter] mandar    ·    s = saltear este    ·    a = automatico (no frenar mas)    ·    q = cortar
#
# ⚠ La puerta va SIEMPRE fuera del `tx_lock`: si frenara adentro, cualquier otro hilo que quisiera
#   mandar quedaria trabado esperando un Enter que el operador no sabe que le estan pidiendo.
# ⚠ Saltear NO incrementa el contador del FF55: el cliente lleva su propio contador de recepcion y
#   adelantarlo le rompe el descifrado de todo lo que venga despues.
# ⚠ MEDIDO 2026-08-05: si se frena en el HANDSHAKE DE LOGIN el cliente se muere a los 3 s — no
#   tolera que RESP-1..RESP-4 tarden. Por eso el handshake pasa DERECHO salvo que se pida
#   `R2_PASO=2`, y se frena recien desde el FF55 en adelante, que es donde esta el problema.
PASO_A_PASO = os.environ.get("R2_PASO", "") not in ("", "0")
_paso_lock  = threading.Lock()


def puerta_paso(etiqueta, detalle="", handshake=False):
    """True = mandar, False = saltear."""
    global PASO_A_PASO
    if not PASO_A_PASO:
        return True
    if handshake and not PASO_HANDSHAKE:
        return True
    with _paso_lock:
        if not PASO_A_PASO:                    # otro hilo pudo desactivarlo mientras esperabamos
            return True
        print("\n" + "─" * 78, flush=True)
        print(f"  POR MANDAR ->  {etiqueta}", flush=True)
        if detalle:
            print(f"                 {detalle}", flush=True)
        print("  [Enter]=mandar   s=saltear   a=automatico   q=cortar", flush=True)
        try:
            r = sys.stdin.readline().strip().lower()
        except Exception:
            return True
        if r == "a":
            PASO_A_PASO = False
            print("  -> automatico: no freno mas.", flush=True)
            return True
        if r == "s":
            print("  -> SALTEADO (no se manda, no se toca el contador).", flush=True)
            return False
        if r == "q":
            print("  -> cortando el server.", flush=True)
            os._exit(0)
        return True
