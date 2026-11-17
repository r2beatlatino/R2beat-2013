# -*- coding: utf-8 -*-
"""presencia — quién está conectado al juego y DÓNDE, para la lista de amigos del launcher (16-nov-2026).

    GET /api/interno/presencia   (cabecera `X-Ficha-Interna` = `R2_CUENTAS_FICHA_INTERNA`; sin esa variable: 404)
    ★ o, donde no hay `api_web` (el server público / de prueba), su PROPIO puerto: `R2_PRESENCIA_PUERTO` → GET /presencia
    `R2_PRESENCIA_JUEGO` dice de qué server es (por omisión «r2beat2013»; el de prueba: «r2beat2013-prueba»).
    -> {"juego": "r2beat2013", "jugadores": [{eid, personaje, canal, sala: {n, nombre, cancion, dificultad,
                                              jugando, ocupantes, capacidad} | null}]}

La pide Cuenta Eñeños (servidor/social.py) cada pocos segundos por la red de adentro; ⛔ a internet no sale (Caddy
devuelve 404 a /api/interno/*). Lo de la SALA se lee de la sala (`SALAS_VIVAS`, `dificultad_de`), no de la conexión
(memoria: «estado de la conexión vs la sala»). Barato: sin base por pedido (el Eñeños ID y el apodo se guardan).
"""
import hmac
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import almacen, notas, salas
from .ajustes import CANALES_2013

_cache_eid = {}          # usn -> (eid | None, cuando)
_cache_pj = {}           # usn -> (apodo del personaje, cuando)
CACHE_EID = 600
CACHE_PJ = 60
_NOMBRE_CANAL = {c[4]: c[5] for c in CANALES_2013}


def ficha_ok(dada):
    esperada = (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip()
    return bool(esperada) and hmac.compare_digest(str(dada or "").strip(), esperada)


def _eid(usn, ahora):
    v = _cache_eid.get(usn)
    if v and ahora - v[1] < CACHE_EID:
        return v[0]
    eid = None
    try:
        usuario, _ranura = almacen.cuenta_de_uid(usn)
        if usuario:
            eid = (almacen.cuenta_estado(usuario) or {}).get("enenos_id")
    except Exception:                                                  # noqa: BLE001 — sin base, sin presencia
        eid = None
    _cache_eid[usn] = (eid, ahora)
    return eid


def _personaje(usn, ahora):
    v = _cache_pj.get(usn)
    if v and ahora - v[1] < CACHE_PJ:
        return v[0]
    nick = ""
    try:
        nick = str((almacen.leer_char(usn) or {}).get("nick") or "")
    except Exception:                                                  # noqa: BLE001
        nick = ""
    _cache_pj[usn] = (nick, ahora)
    return nick


_ARTISTAS = {}


def artista_de(song):
    """El artista del catálogo del cliente (`music_lt.txt`, el mismo que lee `notas.cargar_niveles`)."""
    if not _ARTISTAS:
        ruta = notas._buscar_music_lt()
        try:
            crudo = open(ruta, "rb").read() if ruta else b""
        except OSError:
            crudo = b""
        try:
            txt = crudo.decode("utf-8")
        except UnicodeDecodeError:
            txt = crudo.decode("cp949", "replace")
        for bloque in re.findall(r"<Music(.*?)</Music>", txt, re.S):
            i = re.search(r'Index="(\d+)"', bloque)
            a = re.search(r'Artist="([^"]*)"', bloque)
            if i and a:
                _ARTISTAS[int(i.group(1))] = a.group(1).strip()
        _ARTISTAS.setdefault(-1, "")                 # (no volver a leer si el catálogo no está)
    return _ARTISTAS.get(int(song or 0), "")


def _sala(rid):
    s = salas.SALAS_VIVAS.get(rid) if rid is not None else None
    if not s:
        return None
    # ★ la canción ELEGIDA vive en la selección de la sala (`seleccion_de`), no en `SALAS_VIVAS`; con «Aleatoria» (0),
    #   la que de verdad salió al arrancar está en los que corren (`room_song`, que pone el arranque de la carrera)
    try:
        cancion = int(salas.seleccion_de(rid).get("cancion") or 0)
    except Exception:                                                  # noqa: BLE001
        cancion = 0
    try:
        mesa = list(salas.mesa_de(rid).values())
    except Exception:                                                  # noqa: BLE001
        mesa = []
    jugando = bool(int(s.get("B") or 0) & 0x02)
    if not cancion and jugando:
        cancion = next((int(getattr(salas.CONEXIONES.get(u), "room_song", 0) or 0) for u in mesa
                        if getattr(salas.CONEXIONES.get(u), "room_song", 0)), 0)
    nivel = notas.nivel_de(cancion) if cancion else None
    return {"n": int(rid) & 0x7FF, "nombre": str(s.get("nombre") or "")[:40],
            "cancion": notas.titulo_de(cancion) if cancion else "", "artista": artista_de(cancion) if cancion else "",
            # ★ las ESTRELLAS del picker = Level × 0,5 (memoria «las estrellas de más de 10»)
            "estrellas": (nivel / 2) if nivel else None,
            "jugando": jugando, "ocupantes": len(mesa) if mesa else int(s.get("E") or 0),
            "capacidad": max(0, int(s.get("G") or 6) - 6)}


def presencia(ahora=None):
    ahora = time.time() if ahora is None else ahora
    fuera, vistos = [], set()
    for usn, st in list(salas.CONEXIONES.items()):
        if st is None or getattr(st, "cerrado", False) or usn in vistos:
            continue
        eid = _eid(usn, ahora)
        if not eid:
            continue
        vistos.add(usn)
        fuera.append({"eid": int(eid), "personaje": _personaje(usn, ahora),
                      "canal": _NOMBRE_CANAL.get(getattr(st, "canal", None), ""),
                      "sala": _sala(getattr(st, "room_id", None))})
    return {"juego": os.environ.get("R2_PRESENCIA_JUEGO") or "r2beat2013", "jugadores": fuera}


def arrancar():
    """El puerto PROPIO de la presencia (sólo con `R2_PRESENCIA_PUERTO` y la ficha): para donde no hay `api_web`.
    ⛔ No se publica afuera del contenedor: lo pide Cuenta Eñeños por la red de adentro."""
    puerto = int(os.environ.get("R2_PRESENCIA_PUERTO") or 0)
    if not puerto or not (os.environ.get("R2_CUENTAS_FICHA_INTERNA") or "").strip():
        return None

    class _Manejador(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def do_GET(self):
            ruta = self.path.split("?", 1)[0].rstrip("/")
            if ruta not in ("/presencia", "/api/interno/presencia") or not ficha_ok(self.headers.get("X-Ficha-Interna")):
                self.send_response(404); self.end_headers(); return
            cuerpo = json.dumps(presencia(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

    srv = ThreadingHTTPServer((os.environ.get("R2_PRESENCIA_HOST") or "0.0.0.0", puerto), _Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True, name="presencia").start()
    return srv
