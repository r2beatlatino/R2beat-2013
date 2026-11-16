# -*- coding: utf-8 -*-
"""nombre_publico — el server averigua su IP pública resolviendo SU NOMBRE, para anunciarla en los canales.

14-nov-2026 · anonimo03: «adelante» a la opción 0 de `documentacion/TOPOLOGIA_CONTENEDORES.md` §16. NO en prod.

PARA QUÉ
--------
El cliente entra al login por un nombre (`juego.xn--eeos-gqab.link`), pero la dirección de los CANALES se la anuncia el
server en el `FF02`, y en ese campo entran 15 letras: el nombre no entra, tiene que ir la IP. Hasta hoy esa IP se
escribía a mano en cada máquina (`R2_PUBLIC_IP`). Con `R2_NOMBRE_PUBLICO` el server la saca del DNS: mudar el juego de
máquina pasa a ser cambiar el registro del nombre, sin tocar el cliente ni escribir la IP en ningún lado.

LA REGLA (una sola, y contesta los casos difíciles)
---------------------------------------------------
★ **El server sólo anuncia la IP del nombre si por esa IP se llega a ÉL.**
  Cada vuelta resuelve el nombre y, antes de creerle, se conecta a `<esa IP>:<puerto del login>` y manda un «eco»
  (`FFEC`) con un desafío al azar. Sólo ESTE proceso puede contestarlo bien: la respuesta se arma con una ficha secreta
  que nace con el proceso y nunca viaja. Si la respuesta cierra, adopta la IP. Si no, no.

  · el DNS falla, o devuelve algo raro (vacío, IPv6, una privada)  -> no se adopta nada: sigue la última buena; y si
    nunca hubo una, lo de siempre (`R2_PUBLIC_IP`, o la IP por la que llegó el cliente).
  · MUDANZA, el server VIEJO, cuando el nombre ya apunta al nuevo  -> el eco no vuelve a él: NO adopta la IP nueva.
    Sigue anunciando la suya. Nunca manda a sus jugadores a otra máquina por su cuenta. Queda dicho en el log.
  · MUDANZA, el server NUEVO, prendido antes de cambiar el DNS     -> el nombre todavía apunta al viejo: el eco no
    vuelve, no adopta, anuncia lo de siempre. En cuanto el DNS cambia, la vuelta siguiente lo adopta solo.
  · alguien rompe el registro (lo pone «con nube», o con otra IP)  -> lo mismo: no se adopta, el server sigue igual.

⛔ NUNCA revienta un `FF02`: lo que sale de acá es una IPv4 escrita por `ipaddress` (15 letras como mucho) o `None`.

EL COSTO (el VPS tiene presupuesto de CPU)
------------------------------------------
Nada se resuelve en el login: `ip()` devuelve una variable. Un hilo aparte hace UNA consulta de DNS y UNA conexión a
sí mismo cada `NOMBRE_PUBLICO_CADA_S` (300 s, el TTL del registro); mientras todavía no adoptó ninguna, cada
`NOMBRE_PUBLICO_REINTENTO_S` (30 s). Sin la variable, el hilo ni arranca y todo queda exactamente como antes.

VARIABLES (en `ajustes.py`)
---------------------------
    R2_NOMBRE_PUBLICO                 el nombre del juego. Sin ella, nada de esto existe.
    R2_NOMBRE_PUBLICO_PRIVADAS=1      acepta IPs privadas o de esta máquina (LAN, pruebas). ⛔ En prod, no.
    R2_NOMBRE_PUBLICO_SIN_COMPROBAR=1 le cree al DNS sin el eco. Sólo si la máquina no puede conectarse a su propia IP
                                      pública. ⚠ Con esto el server viejo de una mudanza SÍ sigue al nombre.
"""
import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import threading
import time

from .ajustes import (
    LOGIN_PORT,
    NOMBRE_PUBLICO,
    NOMBRE_PUBLICO_CADA_S,
    NOMBRE_PUBLICO_PRIVADAS,
    NOMBRE_PUBLICO_REINTENTO_S,
    NOMBRE_PUBLICO_SIN_COMPROBAR,
)
from .cifrado import frame, parse_frames
from .registro import log

CMD_ECO = 0xEC                       # `FFEC [desafío:16]` -> `FFEC [firma:16]`. Sólo en el puerto del login.
_FICHA = secrets.token_bytes(32)     # nace con el proceso y NO viaja: otro server (o éste, reiniciado) tiene otra
_estado = {"ip": None, "motivo": "todavía no resolví", "vueltas": 0}


def ip():
    """La IP que hay que anunciar en los canales, o `None` (= «hacé lo de siempre»). No resuelve nada: lee una variable."""
    return _estado["ip"]


def estado():
    return dict(_estado)


def validar(texto, privadas=None):
    """-> (ip, None) si es una IPv4 anunciable, o (None, motivo). Lo que devuelve el DNS no se cree sin mirarlo."""
    privadas = NOMBRE_PUBLICO_PRIVADAS if privadas is None else privadas
    try:
        d = ipaddress.ip_address(str(texto or "").strip())
    except ValueError:
        return None, f"el DNS no devolvió una IP ({str(texto)[:40]!r})"
    if d.version != 4:
        return None, "el DNS devolvió una IPv6 (el cliente sólo entiende IPv4)"
    if d.is_unspecified or d.is_multicast or d.is_reserved:
        return None, f"el DNS devolvió una IP que no sirve ({d})"
    if (d.is_private or d.is_loopback or d.is_link_local) and not privadas:
        return None, f"el DNS devolvió una IP privada ({d}); en una LAN, R2_NOMBRE_PUBLICO_PRIVADAS=1"
    return str(d), None                     # una IPv4 escrita por `ipaddress`: 7 a 15 letras, siempre


def _firma(desafio, ficha):
    return hmac.new(ficha, bytes(desafio), hashlib.sha256).digest()[:16]


def responder_eco(payload, ficha=None):
    """Lo que contesta el login a un `FFEC`: el desafío firmado con la ficha de ESTE proceso. Le contesta a cualquiera
    (no revela nada: sin la ficha no se puede ni comprobar ni falsificar); un desafío de largo raro no se firma."""
    ficha = _FICHA if ficha is None else ficha
    return frame(CMD_ECO, _firma(payload, ficha) if 8 <= len(payload) <= 64 else b"")


def llega_a_mi(direccion, puerto=None, tope=4.0, ficha=None):
    """¿Conectando a `direccion:puerto` contesta ESTE proceso? Una conexión, un paquete de ida y uno de vuelta."""
    # ★ 15-nov: con la PUERTA del 48004 delante (dos servers en una máquina), el login escucha adentro en otro puerto
    #   (47004) y desde afuera se llega por el 48004: `R2_NOMBRE_PUBLICO_PUERTO` dice por cuál probar (vacío = el login).
    if puerto is None:
        puerto = int(os.environ.get("R2_NOMBRE_PUBLICO_PUERTO") or LOGIN_PORT)
    ficha = _FICHA if ficha is None else ficha
    desafio = secrets.token_bytes(16)                    # uno nuevo cada vez: una respuesta vieja no sirve
    try:
        with socket.create_connection((direccion, puerto), tope) as s:
            s.settimeout(tope)
            s.sendall(frame(CMD_ECO, desafio))
            buf = b""
            while len(buf) < 20:                          # 4 de marco + 16 de firma
                d = s.recv(64)
                if not d:
                    return False
                buf += d
            tramas, _resto = parse_frames(buf)
            return (bool(tramas) and tramas[0][1] == CMD_ECO
                    and hmac.compare_digest(tramas[0][2], _firma(desafio, ficha)))
    except OSError:
        return False


def una_vuelta(nombre=None, resolver=socket.gethostbyname, probar=llega_a_mi, privadas=None, sin_comprobar=None):
    """Resuelve, mira lo que vino y decide. -> la IP que queda anunciándose (o None). ⛔ Nunca lanza."""
    nombre = NOMBRE_PUBLICO if nombre is None else nombre
    sin_comprobar = NOMBRE_PUBLICO_SIN_COMPROBAR if sin_comprobar is None else sin_comprobar
    antes = (_estado["ip"], _estado["motivo"])
    _estado["vueltas"] += 1
    try:
        vino = resolver(nombre)
    except Exception as e:                                               # noqa: BLE001 — el DNS puede fallar de mil formas
        vino, motivo = None, f"no pude resolver {nombre} ({type(e).__name__})"
    else:
        vino, motivo = validar(vino, privadas)
    soy_yo = False
    if vino is not None:
        try:
            soy_yo = bool(sin_comprobar or probar(vino))
        except Exception:                                                # noqa: BLE001
            soy_yo = False
        if soy_yo:
            _estado["ip"], motivo = vino, ("sin comprobar (R2_NOMBRE_PUBLICO_SIN_COMPROBAR)" if sin_comprobar
                                           else "comprobado: por esa IP se llega a este server")
        else:
            motivo = f"{nombre} apunta a {vino}, pero por ahí NO se llega a este server (¿mudanza?, ¿el registro mal?)"
    _estado["motivo"] = motivo
    if (_estado["ip"], motivo) != antes:                                 # sólo cuando cambia algo: no una línea cada 5 min
        if soy_yo:
            log("MAIN", f"nombre público: los canales se anuncian con {_estado['ip']} · {motivo}")
        elif _estado["ip"]:
            log("MAIN", f"nombre público: ⚠ {motivo} -> sigo anunciando {_estado['ip']} (la última que comprobé)")
        else:
            log("MAIN", f"nombre público: ⚠ {motivo} -> los canales se anuncian como siempre "
                        f"(R2_PUBLIC_IP, o la IP por la que llega cada cliente)")
    return _estado["ip"]


def _bucle():
    time.sleep(1.0)                              # que los listeners ya estén escuchando: el eco se manda a uno mismo
    while True:
        try:
            una_vuelta()
        except Exception as e:                                           # noqa: BLE001 — este hilo no puede morirse
            log("MAIN", f"nombre público: ⚠ {e!r}")
        time.sleep(NOMBRE_PUBLICO_CADA_S if _estado["ip"] else NOMBRE_PUBLICO_REINTENTO_S)


def arrancar():
    """Lo llama `lobby.main()` después de levantar los listeners. Sin `R2_NOMBRE_PUBLICO` no hace NADA."""
    if not NOMBRE_PUBLICO:
        return None
    log("MAIN", f"nombre público: {NOMBRE_PUBLICO} (se resuelve cada {NOMBRE_PUBLICO_CADA_S} s; sólo se adopta la IP "
                f"si por ella se llega a este server)")
    t = threading.Thread(target=_bucle, daemon=True, name="nombre-publico")
    t.start()
    return t
