# -*- coding: utf-8 -*-
"""puerta_ip — la IP DE VERDAD del jugador cuando el login entra por una puerta (un repartidor delante del 48004).

Con una puerta delante (dos servers en la misma máquina, prod y prueba), el server ve en el LOGIN la IP de la puerta,
no la del jugador; los CANALES van directo y ahí sí ve la de verdad. El FF02 del lobby exige un login del juego desde
la MISMA IP (`lobby.login_previo_ok`): sin esto, detrás de la puerta no entraba nadie (26-nov, server de prueba).

La puerta manda, ANTES del primer paquete, una línea del PROXY protocol v1 (la de HAProxy, texto):

    PROXY TCP4 <ip del jugador> <ip de la puerta> <puerto del jugador> <puerto de la puerta>\\r\\n

y el server la cree SÓLO si la conexión viene de una dirección de `R2_PUERTA_IPS` (ips, redes o nombres, separados por
coma; ej. `puerta` en docker). Sin `R2_PUERTA_IPS` no se lee nada: todo como antes. De cualquier otro, una línea así
no se mira (y como no es un paquete del juego, ese login no abre): un cliente no puede inventarse la IP.
Si la puerta de confianza no manda la línea (todavía no la tiene prendida), se sigue con la IP que se ve.
"""
import ipaddress
import socket
import time

from .ajustes import PUERTA_IPS
from .registro import log

TOPE_LINEA = 107                 # el largo máximo de una línea v1 (con el \r\n), según la especificación
PLAZO_S = 10                     # esperando la línea; ⚠ después se vuelve a SIN plazo (el login no lo tolera)
_RESOLVER_CADA_S = 60            # los nombres (docker) se vuelven a resolver: la puerta puede cambiar de IP

_redes = None                    # [ip_network] de las ips y redes de R2_PUERTA_IPS
_nombres = ()                    # los que no son ip ni red: se resuelven
_resueltos = (0.0, frozenset())  # (cuándo, ips de los nombres)


def _cargar(texto):
    global _redes, _nombres, _resueltos
    redes, nombres = [], []
    for x in (t.strip() for t in (texto or "").split(",")):
        if not x:
            continue
        try:
            redes.append(ipaddress.ip_network(x, strict=False))
        except ValueError:
            nombres.append(x)
    _redes, _nombres, _resueltos = redes, tuple(nombres), (0.0, frozenset())


def _ips_de_nombres():
    global _resueltos
    cuando, ips = _resueltos
    if _nombres and time.time() - cuando > _RESOLVER_CADA_S:
        nuevas = set()
        for n in _nombres:
            try:
                nuevas.update(a[4][0] for a in socket.getaddrinfo(n, None))
            except OSError:
                pass
        ips = frozenset(nuevas)
        _resueltos = (time.time(), ips)
    return ips


def activa():
    if _redes is None:
        _cargar(PUERTA_IPS)
    return bool(_redes or _nombres)


def de_confianza(ip):
    if not activa():
        return False
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return any(a in r for r in _redes) or str(a) in _ips_de_nombres()


def leer_linea(linea):
    """`PROXY TCP4 …` → (ip, puerto) del jugador, o None (UNKNOWN, mal formada, ip inválida)."""
    try:
        partes = linea.decode("ascii").split(" ")
    except UnicodeDecodeError:
        return None
    if len(partes) != 6 or partes[0] != "PROXY" or partes[1] not in ("TCP4", "TCP6"):
        return None
    try:
        ip = ipaddress.ip_address(partes[2])
        puerto = int(partes[4])
    except ValueError:
        return None
    if (ip.version == 4) != (partes[1] == "TCP4") or not 0 <= puerto <= 65535:
        return None
    return str(ip), puerto


def real(conn, addr):
    """-> (addr del jugador, bytes ya leídos que van al login).

    Si `addr` es una puerta de confianza y lo primero que llega es una línea PROXY, devuelve la IP que dice la línea
    y lo que vino detrás. En cualquier otro caso devuelve `addr` como está (y lo leído, para no perderlo)."""
    if not de_confianza(addr[0]):
        return addr, b""
    buf = b""
    try:
        conn.settimeout(PLAZO_S)
        while b"\r\n" not in buf and len(buf) < TOPE_LINEA and b"PROXY "[:len(buf)] == buf[:6]:
            datos = conn.recv(TOPE_LINEA)
            if not datos:
                break
            buf += datos
    except OSError:                                    # incluye el plazo vencido
        pass
    finally:
        try:
            conn.settimeout(None)
        except OSError:
            pass
    if not buf.startswith(b"PROXY "):
        return addr, buf                               # la puerta no mandó la línea: la IP que se ve
    linea, _, resto = buf.partition(b"\r\n")
    jugador = leer_linea(linea) if _ else None
    if jugador is None:
        log("LOGIN", f"  ⚠ PUERTA {addr[0]}: línea PROXY que no se entiende ({linea[:60]!r}): sigo con la IP que veo")
        return addr, resto
    return jugador, resto
