#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_login — el server ARRANCA y una cuenta ENTRA, por la red, como entra el juego.

    python pruebas/probar_login.py

Sin el juego y sin las tablas de Softnyx: si faltan, pone unas VACÍAS sólo mientras dura la prueba
(y las borra al final). La base, el log y el estado van a una carpeta temporal: nunca toca `datos/`.

QUÉ HACE (los mismos pasos que el juego, por sockets de verdad):
  1. crea una cuenta de prueba con una clave al azar (con las funciones del propio server);
  2. arranca `correr_servidor.py` con los puertos corridos (`R2_PUERTOS`), para no chocar con nada;
  3. LAUNCHER  `FF01 [0:u32][0][usuario][sha256 de la clave]`        -> estado 0, usn, vcode;
  4. JUEGO     `FF01 [usn][vcode]` -> RESP-1; `FF02` -> la lista de los 10 canales;
  5. CANAL     CheckVer `FF01 04 00` -> ACK; `FF02` (usn, challenge…) -> RESP-4 con A = challenge ^ 0xCACB1112;
  6. y ya CIFRADO: `FF03` adentro de un FF55 -> el server contesta un FF55 que abre y trae el FF03.

★ Y LOS REVESES, que tienen que fallar (si no fallan, la prueba no prueba nada):
  · la clave equivocada -> el launcher la rechaza;
  · un vcode inventado  -> el login del juego no abre;
  · un challenge mal ofuscado -> el A del RESP-4 NO cierra.
"""
import hashlib
import os
import random
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFSET = int(os.environ.get("R2_PUERTOS_PRUEBA") or 6000)
LOGIN = 48004 + OFFSET
CHALLENGE_XOR = 0xCACB1112            # el server devuelve A = challenge ^ esto (ajustes.CHALLENGE_XOR)
CHALLENGE_XOR_CLIENTE = 0xCCCCCCCC    # con esto ofusca el cliente su challenge en el FF02
TABLAS = ("servidor/shop_lt.txt", "servidor/tablas-cliente/music_lt.txt")

ok = []


def chequear(nombre, cond):
    print("  %s %s" % ("✅" if cond else "⛔", nombre))
    ok.append(bool(cond))


# ── el protocolo (copia chica e independiente: la prueba no le cree al server lo que mide) ──────────
def trama(cmd, payload=b""):
    return bytes([0xFF, cmd & 0xFF]) + struct.pack("<H", len(payload)) + payload


def lp(b):
    return bytes([len(b)]) + b


def leer_trama(s, buf, tope=10.0):
    s.settimeout(tope)
    while True:
        if len(buf[0]) >= 4:
            n = buf[0][2] | (buf[0][3] << 8)
            if len(buf[0]) >= 4 + n:
                t = buf[0][:4 + n]
                buf[0] = buf[0][4 + n:]
                return t[1], t[4:]
        try:
            d = s.recv(65536)
        except (socket.timeout, OSError):
            return None
        if not d:
            return None
        buf[0] += d


def flujo(pwd, n, rv):
    k = pwd[rv] ^ rv
    return bytes(pwd[i % 256] ^ k for i in range(n))


def xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def launcher(usuario, clave):
    """-> (estado, usn, vcode)"""
    with socket.create_connection(("127.0.0.1", LOGIN), 10) as s:
        h = hashlib.sha256(clave.encode()).hexdigest().upper().encode()
        s.sendall(trama(0x01, b"\x00" * 5 + lp(usuario.encode()) + lp(h)))
        r = leer_trama(s, [b""])
    if r is None or r[0] != 0x01:
        return None, 0, 0
    p = r[1]
    if p[0] != 0:
        return p[0], 0, 0
    return 0, struct.unpack_from("<I", p, 1)[0], int(p[10:10 + p[9]].decode("ascii"), 16)


def login_juego(usn, vcode):
    """-> la lista de canales [(puerto, nombre)], o None si no abre."""
    with socket.create_connection(("127.0.0.1", LOGIN), 10) as s:
        buf = [b""]
        s.sendall(trama(0x01, struct.pack("<IQ", usn, vcode)))
        r = leer_trama(s, buf, 5)
        if r is None or r[0] != 0x01 or r[1][:1] != b"\x00":
            return None
        s.sendall(trama(0x02))
        r = leer_trama(s, buf)
    if r is None or r[0] != 0x02:
        return None
    p, i, canales = r[1], 1, []
    for _ in range(p[0]):
        i += 4
        puerto = struct.unpack_from("<H", p, i)[0]
        i += 2
        i += 1 + p[i]                                  # ip
        i += 4 + 1                                     # gente, tope, cat
        nombre = p[i + 1:i + 1 + p[i]].decode("cp1252", "replace")
        i += 1 + p[i]
        canales.append((puerto, nombre))
    return canales


def canal(usn, puerto, ofuscar=True):
    """CheckVer + login al canal + un FF03 cifrado. -> (A cierra, cmds que volvieron del FF03)"""
    with socket.create_connection(("127.0.0.1", puerto), 10) as s:
        buf = [b""]
        s.sendall(trama(0x01, b"\x04\x00"))
        r = leer_trama(s, buf)
        if r is None or r[0] != 0x01:
            return False, []
        chal = random.getrandbits(32)
        enviado = (chal ^ CHALLENGE_XOR_CLIENTE) if ofuscar else chal
        s.sendall(trama(0x02, struct.pack("<I", usn) + b"\x00" * 5 + lp(b"192.168.1.20") + b"\x00\x00"
                        + lp(b"asdasdasd") + struct.pack("<I", enviado & 0xFFFFFFFF)
                        + lp(b"10-ff-e0-00-00-00")))
        r = leer_trama(s, buf)
        if r is None or r[0] != 0x02 or len(r[1]) < 9 + 256:
            return False, []
        A, B = struct.unpack_from("<II", r[1], 1)
        cierra = A == (chal ^ CHALLENGE_XOR) & 0xFFFFFFFF
        pwd = r[1][9:9 + 256]
        key = (B + usn) & 0xFFFFFFFF
        claro = b"\xFF\x56\x00\x00" + b"\xFF\x03\x00\x00"           # FF56 de relleno + FF03 vacío
        s.sendall(trama(0x55, xor(claro, flujo(pwd, len(claro), key & 0xFF))))   # contador 0
        vistos, fin = [], time.time() + 10
        while time.time() < fin and 0x03 not in vistos:
            r = leer_trama(s, buf, 3)
            if r is None:
                break
            if r[0] != 0x55 or len(r[1]) < 4:
                continue
            p = r[1]
            for rv in range(256):                       # rv se despeja de los dos bytes conocidos (FF 56)
                base = pwd[rv] ^ rv
                if pwd[0] ^ base ^ p[0] == 0xFF and pwd[1] ^ base ^ p[1] == 0x56:
                    d = xor(p, flujo(pwd, len(p), rv))
                    j = 0
                    while j <= len(d) - 4:
                        if d[j] not in (0xFF, 0xFE):
                            j += 1
                            continue
                        n = d[j + 2] | (d[j + 3] << 8)
                        if not (d[j] == 0xFF and d[j + 1] == 0x56):
                            vistos.append(d[j + 1] | (0x100 if d[j] == 0xFE else 0))
                        j += 4 + n
                    break
        return cierra, vistos


# ── el armado: tablas vacías, base temporal, cuenta de prueba, server ───────────────────────────────
def main():
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    tmp = tempfile.mkdtemp(prefix="r2b_prueba_")
    puestas = []
    for rel in TABLAS:
        p = os.path.join(RAIZ, *rel.split("/"))
        if not os.path.isfile(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").close()
            puestas.append(p)
    env = dict(os.environ, R2_PUERTOS=str(OFFSET), R2_BASE=os.path.join(tmp, "datos.db"),
               R2_CHARS_DB=os.path.join(tmp, "chars_db.json"), R2_CUENTAS=os.path.join(tmp, "cuentas.json"),
               R2_SESIONES=os.path.join(tmp, "sesiones.json"), R2_LOG=os.path.join(tmp, "servidor.log"),
               R2_STATUS=os.path.join(tmp, "status.json"), R2_IP="127.0.0.1", PYTHONIOENCODING="utf-8")
    usuario, clave = "prueba%04d" % random.randrange(10000), secrets.token_urlsafe(9)
    crear = ("import sys,os,time; sys.path.insert(0, %r)\n"
             "from servidor import almacen, basedatos, misiones\n"
             "c = almacen.conectar()\n"
             "c.execute('INSERT INTO users (uid, username, pass_hash, reg_time) VALUES (?,?,?,?)',"
             " (1001, %r, basedatos.hash_pass(%r), str(time.time())))\n"
             "c.commit()\n"
             "misiones.db_create_char(1001, {'char_id': 130900, 'nick': %r,"
             " 'parts': [210565, 310564, 410491, 510429]})\n") % (RAIZ, usuario, clave, usuario)
    srv = None
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", crear], env=env, cwd=RAIZ,
                           capture_output=True, text=True, timeout=60)
        chequear("se crea la cuenta de prueba (con las funciones del server)", r.returncode == 0)
        if r.returncode:
            print(r.stdout[-2000:], r.stderr[-2000:])
            return 1
        log = open(os.path.join(tmp, "consola.log"), "w", encoding="utf-8")
        srv = subprocess.Popen([sys.executable, "-X", "utf8", "correr_servidor.py"], env=env, cwd=RAIZ,
                               stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        listo, fin = False, time.time() + 60
        while time.time() < fin and srv.poll() is None:
            try:
                socket.create_connection(("127.0.0.1", LOGIN), 1).close()
                listo = True
                break
            except OSError:
                time.sleep(0.5)
        chequear("el server arranca y escucha el login (:%d)" % LOGIN, listo)
        if not listo:
            return 1
        time.sleep(1)                                   # que terminen de abrir los canales
        estado, usn, vcode = launcher(usuario, clave)
        chequear("LAUNCHER: la clave buena entra (usn %d)" % usn, estado == 0 and usn == 1001 and vcode)
        malo, _, _ = launcher(usuario, clave + "x")
        chequear("★ revés: la clave equivocada NO entra (estado %r)" % malo, malo not in (0, None))
        canales = login_juego(usn, vcode)
        chequear("JUEGO: el vcode abre y llega la lista de canales (%d)" % len(canales or []),
                 bool(canales) and len(canales) >= 2)
        chequear("★ revés: un vcode inventado NO abre", login_juego(usn, vcode ^ 0x5A5A5A5A) is None)
        if canales:
            estado, usn, vcode = launcher(usuario, clave)  # una sesión nueva para el canal
            login_juego(usn, vcode)
            puerto = canales[0][0]
            cierra, vistos = canal(usn, puerto)
            chequear("CANAL %s: el RESP-4 cierra (A = challenge ^ 0xCACB1112)" % canales[0][1], cierra)
            chequear("CIFRADO: el FF03 vuelve adentro de un FF55 que abre (%s)"
                     % " ".join("FF%02X" % c for c in vistos[:6]), 0x03 in vistos)
            estado, usn, vcode = launcher(usuario, clave)
            login_juego(usn, vcode)
            cierra_mal, _ = canal(usn, puerto, ofuscar=False)
            chequear("★ revés: con el challenge SIN ofuscar el A NO cierra", not cierra_mal)
    finally:
        if srv is not None:
            srv.terminate()
            try:
                srv.wait(10)
            except subprocess.TimeoutExpired:
                srv.kill()
        for p in puestas:
            os.remove(p)
        if not all(ok):
            try:
                print("\n── el log del server (lo último) ──")
                print(open(os.path.join(tmp, "consola.log"), encoding="utf-8", errors="replace").read()[-3000:])
            except OSError:
                pass
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    sys.exit(main())
