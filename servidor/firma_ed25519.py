# -*- coding: utf-8 -*-
"""firma_ed25519 — la firma Ed25519 (RFC 8032) en Python PURO, sin instalar nada. 11-nov-2026.

POR QUÉ ACÁ Y NO UNA BIBLIOTECA
-------------------------------
El portero (`servidor/portero.py`) firma los PASES que le da a otros juegos (EDA). El VPS no tiene `cryptography` ni
`nacl`, y el server de R2Beat corre sólo con la biblioteca estándar: sumar una dependencia para 60 líneas no vale la
pena. Es la implementación de referencia del RFC 8032 §6 (coordenadas extendidas), sin trucos.

⚠ NO es de tiempo constante. Sirve porque sólo FIRMA el portero, con su clave y a su ritmo (unos milisegundos por pase,
   y el login tiene freno de intentos); nadie puede pedirle que firme lo que quiera ni medirle el tiempo con precisión.
   El que VERIFICA (el server de EDA) usa la biblioteca de su lenguaje: Ed25519 es estándar en todas.

La prueba (`pruebas/probar_portero.py`) la compara con el vector 1 del RFC y con Node (`crypto.verify`, otra
implementación), y comprueba que una firma tocada NO pase.
"""
import hashlib

_P = 2 ** 255 - 19
_Q = 2 ** 252 + 27742317777372353535851937790883648493       # el orden del grupo (L en el RFC)


def _inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _inv(121666) % _P
_RAIZ_M1 = pow(2, (_P - 1) // 4, _P)


def _recuperar_x(y, signo):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if signo else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _RAIZ_M1 % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != signo:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recuperar_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)
_CERO = (0, 1, 1, 0)


def _sumar(a, b):
    A = (a[1] - a[0]) * (b[1] - b[0]) % _P
    B = (a[1] + a[0]) * (b[1] + b[0]) % _P
    C = 2 * a[3] * b[3] * _D % _P
    D = 2 * a[2] * b[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _por(s, pt):
    r = _CERO
    while s > 0:
        if s & 1:
            r = _sumar(r, pt)
        pt = _sumar(pt, pt)
        s >>= 1
    return r


def _iguales(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _comprimir(pt):
    zi = _inv(pt[2])
    x, y = pt[0] * zi % _P, pt[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _descomprimir(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    signo = y >> 255
    y &= (1 << 255) - 1
    x = _recuperar_x(y, signo)
    return None if x is None else (x, y, 1, x * y % _P)


def _h_mod_q(*partes):
    return int.from_bytes(hashlib.sha512(b"".join(partes)).digest(), "little") % _Q


def _expandir(semilla):
    if len(semilla) != 32:
        raise ValueError("la clave privada Ed25519 mide 32 bytes")
    h = hashlib.sha512(semilla).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def publica(semilla):
    """La clave pública (32 bytes) de una privada (la semilla de 32 bytes)."""
    a, _ = _expandir(semilla)
    return _comprimir(_por(a, _G))


def firmar(semilla, mensaje):
    """-> la firma de 64 bytes."""
    a, prefijo = _expandir(semilla)
    pub = _comprimir(_por(a, _G))
    r = _h_mod_q(prefijo, mensaje)
    R = _comprimir(_por(r, _G))
    s = (r + _h_mod_q(R, pub, mensaje) * a) % _Q
    return R + int.to_bytes(s, 32, "little")


def verificar(pub, mensaje, firma):
    """True sólo si la firma es de esa clave pública sobre ese mensaje."""
    if len(pub) != 32 or len(firma) != 64:
        return False
    A = _descomprimir(pub)
    R = _descomprimir(firma[:32])
    if A is None or R is None:
        return False
    s = int.from_bytes(firma[32:], "little")
    if s >= _Q:
        return False
    h = _h_mod_q(firma[:32], pub, mensaje)
    return _iguales(_por(s, _G), _sumar(R, _por(h, A)))
