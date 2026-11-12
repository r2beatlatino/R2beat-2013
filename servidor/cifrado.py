# -*- coding: utf-8 -*-
"""cifrado — el framing FFxx y los sobres FF55 / FF4E

Cortado de `server_login2013.py`. El código es el MISMO, movido tal cual.
"""
import os
import struct

from .ajustes import (
    CHALLENGE_XOR_CLIENTE,
    FF4E_LARGO,
)

# El módulo se lee con rutas relativas a la RAÍZ del proyecto, no a
# `servidor/`. Viene de cuando todo era un archivo solo; sacarlo rompe la
# lectura de las tablas del cliente (wing.txt / face.txt).
__file__ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "server_login2013.py")   # rutas relativas como en el original


def leer_challenge_ff02(payload):
    """Saca el challenge del FF02 de la LOBBY. Devuelve `[cfg+0x90]` ya des-ofuscado, o None.

    Layout (medido byte a byte el 2026-08-04, confirmado con 2 maquinas el 2026-08-05):
        [usn:u32][Location:u8][Age:u16][Gender:u8][u8]
        [len][IP local del cliente] [len=0] [len=0] [len][cuenta]
        [u32 CHALLENGE]  [len][MAC]
    Los campos son todos largo-prefijados, asi que el offset del challenge DEPENDE de cuanto midan
    la IP y el nombre de cuenta (57 B en el host, 59 B en la VM) — hay que caminarlos, no contar.
    """
    try:
        i = 4 + 5                       # usn + Location/Age/Gender/relleno
        for _ in range(4):              # IP local, dos campos vacios, y la cuenta
            i += 1 + payload[i]
        crudo = struct.unpack("<I", payload[i:i + 4])[0]
        i += 4
        # ★ Control de que caminamos bien: lo que queda es la MAC y tiene que cerrar JUSTO.
        #   Sin esto, un payload distinto daria un challenge basura sin que nos enteremos.
        if i + 1 + payload[i] != len(payload):
            return None
        return crudo ^ CHALLENGE_XOR_CLIENTE
    except (IndexError, struct.error):
        return None

# --- Framing ---
def frame(cmd, payload=b"", magic=0xFF):
    """[magic][cmd][len:u16 LE][payload]"""
    return bytes([magic, cmd]) + struct.pack("<H", len(payload)) + payload

def parse_frames(buf):
    """Extrae frames completos de buf. Devuelve (lista_de_(magic,cmd,payload), resto)."""
    out = []
    i = 0
    n = len(buf)
    while n - i >= 4:
        magic = buf[i]
        cmd   = buf[i+1]
        ln    = buf[i+2] | (buf[i+3] << 8)
        if n - i - 4 < ln:
            break                       # payload incompleto: esperar mas bytes
        payload = buf[i+4 : i+4+ln]
        out.append((magic, cmd, payload))
        i += 4 + ln
    return out, buf[i:]

def xor14(buf, key):
    """El cifrado del sobre `0x4E`. Es XOR ⇒ la misma función cifra y descifra."""
    buf = (buf + b"\x00" * FF4E_LARGO)[:FF4E_LARGO]
    return (struct.pack("<I", struct.unpack("<I", buf[0:4])[0] ^ key)
          + struct.pack("<I", struct.unpack("<I", buf[4:8])[0] ^ key)
          + struct.pack("<I", struct.unpack("<I", buf[8:12])[0] ^ key)
          + struct.pack("<H", struct.unpack("<H", buf[12:14])[0] ^ (key & 0xFFFF)))


def _encrypt_ff55_byte_a_byte(plain, pwd, edx):
    """La definición, tal cual era hasta el 29-sep. Queda como REFERENCIA (la prueba compara contra ésta)."""
    rv = edx & 0xFF
    return bytes(pwd[i % 256] ^ pwd[rv] ^ rv ^ plain[i] for i in range(len(plain)))


# ★ 29-sep (optimización para el VPS, `BANCO_VPS.md` §5): la clave de cada byte NO depende del texto —
#   `pwd[i % 256] ^ pwd[rv] ^ rv`— así que se arma UNA vez por (tabla, rv) y se aplica de un solo
#   XOR de enteros, en C. Antes era un generador de Python por BYTE: un MyRecord de 6 KB eran 6.000
#   vueltas, en CADA envío y en cada recibido. Da los MISMOS bytes (`probar_optimizaciones.py` §2).
_FLUJOS = {}                           # (pwd, rv) -> los 256 bytes de clave de ese rv


def encrypt_ff55(plain, pwd, edx):
    """out[i] = pwd[i%256] ^ pwd[rv] ^ rv ^ plain[i]   (rv = edx & 0xFF). Simetrico."""
    n = len(plain)
    if not n:
        return b""
    rv = edx & 0xFF
    clave = (pwd if isinstance(pwd, bytes) else bytes(pwd), rv)
    flujo = _FLUJOS.get(clave)
    if flujo is None:
        k = pwd[rv] ^ rv
        flujo = bytes(pwd[i] ^ k for i in range(256))
        if len(_FLUJOS) > 4096:        # una tabla por sesión es lo normal (hoy: UNA, la de ceros)
            _FLUJOS.clear()
        _FLUJOS[clave] = flujo
    if n > 256:
        flujo = flujo * (n // 256 + 1)
    return (int.from_bytes(plain, "little") ^ int.from_bytes(flujo[:n], "little")).to_bytes(n, "little")


decrypt_ff55 = encrypt_ff55            # el stream cipher es simetrico

def parse_ff55_inner(dec):
    """Extrae (cmd, data) del inner descifrado. Salta el relleno FF56. FE -> 0x100|cmd."""
    cmds = []; i = 0
    while i <= len(dec) - 4:
        prefix = dec[i]
        if prefix not in (0xFF, 0xFE):
            i += 1; continue
        cmd = dec[i + 1]
        ln = struct.unpack("<H", dec[i + 2:i + 4])[0]
        if prefix == 0xFF and cmd == 0x56:     # relleno/sync: saltarlo
            i += 4 + ln; continue
        if i + 4 + ln > len(dec):
            break
        cmds.append((cmd | (0x100 if prefix == 0xFE else 0), dec[i + 4:i + 4 + ln]))
        i += 4 + ln
    return cmds

def _lp(s):
    """string length-prefijado [u8 len][bytes] (ascii cp1252)."""
    b = s.encode("cp1252", "replace") if isinstance(s, str) else bytes(s)
    b = b[:255]
    return bytes([len(b)]) + b
