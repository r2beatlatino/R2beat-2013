# -*- coding: utf-8 -*-
"""telemetria — el `status.json` que lee el PANEL WEB del VPS.

DE DÓNDE SALE
-------------
Portado de `D:\\R2Beat\\server\\servidor\\telemetry.py` (el del CBT). El panel
(`https://patch.r2beatlatino.com/admin`) NO habla con el servidor de juego: **lee un archivo**.

    server de juego  ──escribe──>  /opt/r2beat/data/status.json  <──lee──  patch server  ──>  /admin

El endpoint `/status` del `patchserver.py` abre ese archivo, y si tiene **más de 15 segundos**
lo marca `stale` y el panel muestra el server como caído. O sea que "aparecer en el panel" es,
literalmente, **escribir este archivo cada pocos segundos**.

⚠ DIFERENCIA CON EL DEL CBT: aquel server es `asyncio` y el escritor es una corrutina. El nuestro
  es de **hilos**, así que acá el escritor es un `threading.Thread` daemon. El resto es lo mismo.

★ El panel también lee la **base** (`users` y `chars`) por su cuenta, y ahí no hay nada que hacer:
  nuestro esquema ya es el del CBT (`BASE_SQLITE.md`), con las mismas columnas que él consulta
  (`users.uid/username/reg_time/last_ip/last_time` y `chars.uid/nickname/exp/coin`).

QUÉ SE MANDA, Y QUÉ NO
----------------------
Sólo agregados: cuántos hay conectados, su nick y en qué pantalla están. **Read-only**: esto no le
da al panel ninguna forma de tocar el server.
"""
import json
import os
import threading
import time

RUTA = os.environ.get("R2_STATUS") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "status.json")
CADA = 3.0                             # segundos entre snapshots (el panel corta a los 15)

_ESTADO = {}                           # usn -> {"estado", "desde", "login"}
_lock = threading.Lock()


def _estado_para(cmd, data):
    """A qué pantalla lo manda ese comando. None = este comando no cambia el estado.

    ⚠ NO son los mismos comandos que en el CBT. Allá el `0x3A` con `type 2/3` marcaba entrar y
      salir de la partida; en el 2013 la carrera arranca con el **`FF24` START** y se vuelve a la
      sala cuando el cliente pide el **`FF13` ROOMINFO** (es lo primero que hace al volver — el
      mismo hecho que usa el traspaso de anfitrión para soltar su aviso diferido).
    """
    if cmd == 0x06:                    # FF06 JOINCHANNEL
        return "lobby"
    if cmd in (0x10, 0x11):            # FF10 CREATEROOM · FF11 ENTERROOM
        return "sala"
    if cmd == 0x12:                    # FF12 EXITROOM
        return "lobby"
    if cmd == 0x24:                    # FF24 START -> a la pista
        return "jugando"
    if cmd == 0x13:                    # FF13 ROOMINFO -> está (o volvió) en la sala
        return "sala"
    return None


def observar(st, cmd, data=b""):
    """Se engancha en el despacho. Nunca lanza: la telemetría no puede voltear el server."""
    try:
        usn = getattr(st, "usn", None)
        if not usn:
            return
        ahora = time.time()
        with _lock:
            e = _ESTADO.get(usn)
            if e is None:
                e = _ESTADO[usn] = {"estado": "lobby", "desde": ahora, "login": ahora}
            nuevo = _estado_para(cmd, data)
            if nuevo and nuevo != e["estado"]:
                e["estado"] = nuevo
                e["desde"] = ahora
    except Exception:
        pass


def snapshot(conexiones, nick_de=None, nicks_de=None):
    """★ `nicks_de(uids) -> {uid: apodo}` (29-sep): TODOS los apodos de una consulta. Antes era sólo
    `nick_de(uid)`, uno por uno, y armaba el personaje entero de cada conectado cada 3 s: el 23 % del
    CPU del server con 300 conectados. Si falla, se cae a `nick_de` como antes."""
    ahora = time.time()
    online = {u for u, c in conexiones.items() if not getattr(c, "cerrado", False)}
    lote = None
    if nicks_de and online:
        try:
            lote = nicks_de(sorted(online))
        except Exception:
            lote = None
    with _lock:
        for usn in list(_ESTADO):
            if usn not in online:
                _ESTADO.pop(usn, None)      # se fue: que no quede de fantasma en el panel
        gente = []
        for usn in sorted(online):
            e = _ESTADO.get(usn) or {"estado": "lobby", "desde": ahora, "login": ahora}
            try:
                nick = (lote.get(usn, "") if lote is not None else (nick_de(usn) if nick_de else "")) or ""
            except Exception:
                nick = ""
            gente.append({"uid": usn, "nick": nick or f"usn{usn}", "state": e["estado"],
                          "online_s": int(ahora - e["login"]),
                          "state_s": int(ahora - e["desde"])})
    cuentas = {"lobby": 0, "sala": 0, "jugando": 0}
    for g in gente:
        if g["state"] in cuentas:
            cuentas[g["state"]] += 1
    return {"ts": int(ahora), "online": len(gente), "counts": cuentas, "users": gente}


def escribir_una_vez(conexiones, nick_de=None, ruta=None, nicks_de=None):
    """Escribe el snapshot de forma ATÓMICA (tmp + rename).

    ⚠ El `os.replace` no es cosmético: el patch server puede estar leyendo el archivo justo
      mientras lo escribimos, y un JSON a medio escribir le explota el `json.load`.
    """
    ruta = ruta or RUTA
    try:
        d = snapshot(conexiones, nick_de, nicks_de)
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, ruta)
        return d
    except Exception:
        return None


def arrancar(conexiones, nick_de=None, ruta=None, cada=CADA, nicks_de=None):
    """Lanza el hilo que escribe el snapshot. Daemon: no impide que el server cierre."""
    def bucle():
        while True:
            escribir_una_vez(conexiones, nick_de, ruta, nicks_de)
            time.sleep(cada)
    h = threading.Thread(target=bucle, daemon=True, name="telemetria")
    h.start()
    return h
