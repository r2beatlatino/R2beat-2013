#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
  ENTRAR AL JUEGO
=============================================================================

      python jugar.py

  Abre una ventanita para poner usuario y contraseña (o crear una cuenta), y
  arranca el juego.

  ¿POR QUÉ NO ALCANZA CON ABRIR R2Beat.exe?
  -----------------------------------------
  Porque el juego, solo, no sabe decir quién sos. No tiene pantalla de login
  propia: espera que alguien lo abra ya autenticado. Eso es lo que hace esto:

    1. Le manda al servidor tu usuario y el SHA-256 de tu contraseña (la
       contraseña en claro no sale de tu PC). El servidor abre una sesión y
       devuelve un permiso de un solo uso.
    2. Abre R2Beat.exe pasándole:   <usuario> <permiso> <puerto> test:<servidor>

  El `test:<servidor>` hace que el juego vaya a TU servidor aunque el exe tenga
  otra dirección grabada adentro.

  LA PRIMERA VEZ
  --------------
  Te va a pedir la dirección de tu servidor y dónde está instalado el juego.
  Las guarda en jugar.json y no vuelve a preguntar.
=============================================================================
"""
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys

CARPETA = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(CARPETA, "jugar.json")
PUERTO_LOGIN = 48004
ESPERA = 6


# ---------------------------------------------------------------- config ----

def leer_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        cfg = {"servidor": "", "juego": ""}
        try:                                   # si ya corriste extraer_datos.py, el juego se sabe
            with open(os.path.join(CARPETA, "datos", "juego.json"), encoding="utf-8") as f:
                cfg["juego"] = json.load(f).get("juego") or ""
        except (OSError, ValueError):
            pass
        return cfg


def guardar_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# -------------------------------------------------------------- protocolo ----

def hash_pass(clave):
    """SHA-256 en hex MAYÚSCULA: es lo único que viaja y lo único que guarda el servidor."""
    return hashlib.sha256(clave.encode("utf-8")).hexdigest().upper()


def _ida_y_vuelta(ip, cmd, cuerpo):
    pkt = bytes([0xFF, cmd]) + struct.pack("<H", len(cuerpo)) + cuerpo
    with socket.create_connection((ip, PUERTO_LOGIN), timeout=ESPERA) as s:
        s.sendall(pkt)
        data = s.recv(1024)
    if len(data) < 5 or data[0] != 0xFF or data[1] != cmd:
        raise RuntimeError(f"respuesta rara del servidor: {data.hex().upper()[:64]}")
    return data[4:]


def entrar(ip, usuario, clave):
    """FF01 [0:u32][0:u8][ulen][usuario][hlen][sha256] -> (usn, permiso). El permiso viene en HEX."""
    u, h = usuario.encode("ascii"), hash_pass(clave).encode("ascii")
    r = _ida_y_vuelta(ip, 0x01, struct.pack("<I", 0) + bytes([0, len(u)]) + u + bytes([len(h)]) + h)
    if not r or r[0] != 0x00:
        raise RuntimeError("usuario o contraseña incorrectos")
    usn = struct.unpack("<I", r[1:5])[0]
    permiso = r[10:10 + r[9]].decode("ascii", "replace").strip()
    return usn, int(permiso, 16)


def crear_cuenta(ip, usuario, clave):
    """FFF0 [ulen][usuario][hlen][sha256] -> [estado][largo][mensaje]. 0 = creada."""
    u, h = usuario.encode("ascii"), hash_pass(clave).encode("ascii")
    r = _ida_y_vuelta(ip, 0xF0, bytes([len(u)]) + u + bytes([len(h)]) + h)
    estado = r[0] if r else 2
    mensaje = r[2:2 + (r[1] if len(r) > 1 else 0)].decode("utf-8", "replace")
    if estado != 0:
        raise RuntimeError(mensaje or "no se pudo crear la cuenta")
    return mensaje or "cuenta creada"


def lanzar(juego, ip, usn, permiso):
    """⚠ El permiso viaja en DECIMAL: el juego lo lee con `_strtoi64`, que no entiende hex."""
    exe = os.path.join(juego, "R2Beat.exe")
    if not os.path.isfile(exe):
        raise RuntimeError(f"no encuentro {exe}")
    cmd = f'"{exe}" {int(usn)} {int(permiso)} {PUERTO_LOGIN} test:{ip}'
    return subprocess.Popen(cmd, cwd=juego)


# ---------------------------------------------------------------- ventana ----

def ventana():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    cfg = leer_config()
    raiz = tk.Tk()
    raiz.title("R2Beat 2013")
    raiz.resizable(False, False)

    campos = {}
    for fila, (clave, texto, oculto) in enumerate((("servidor", "Servidor (IP)", False),
                                                   ("usuario", "Usuario", False),
                                                   ("clave", "Contraseña", True))):
        tk.Label(raiz, text=texto).grid(row=fila, column=0, sticky="e", padx=8, pady=4)
        e = tk.Entry(raiz, width=28, show="•" if oculto else "")
        e.grid(row=fila, column=1, padx=8, pady=4)
        campos[clave] = e
    campos["servidor"].insert(0, cfg.get("servidor", ""))
    campos["usuario"].insert(0, cfg.get("usuario", ""))

    lbl_juego = tk.Label(raiz, text=cfg.get("juego") or "(elegí la carpeta del juego)", fg="#555")
    lbl_juego.grid(row=3, column=0, columnspan=2, padx=8)

    def elegir_juego():
        d = filedialog.askdirectory(title="La carpeta donde está R2Beat.exe")
        if d:
            cfg["juego"] = os.path.normpath(d)
            lbl_juego.config(text=cfg["juego"])

    def datos():
        ip, u, c = (campos[k].get().strip() for k in ("servidor", "usuario", "clave"))
        if not ip or not u or not c:
            raise RuntimeError("completá servidor, usuario y contraseña")
        if not u.isascii():
            raise RuntimeError("el usuario va sin acentos ni eñes")
        return ip, u, c

    def boton_entrar():
        try:
            ip, u, c = datos()
            if not cfg.get("juego"):
                raise RuntimeError("falta elegir la carpeta del juego")
            usn, permiso = entrar(ip, u, c)
            cfg.update(servidor=ip, usuario=u)
            guardar_config(cfg)
            lanzar(cfg["juego"], ip, usn, permiso)
            raiz.destroy()
        except (OSError, RuntimeError, ValueError) as e:
            messagebox.showerror("R2Beat", f"No se pudo entrar:\n{e}")

    def boton_crear():
        try:
            ip, u, c = datos()
            messagebox.showinfo("R2Beat", crear_cuenta(ip, u, c) + "\nAhora apretá «Entrar».")
        except (OSError, RuntimeError) as e:
            messagebox.showerror("R2Beat", f"No se pudo crear la cuenta:\n{e}")

    botones = tk.Frame(raiz)
    botones.grid(row=4, column=0, columnspan=2, pady=8)
    tk.Button(botones, text="Carpeta del juego…", command=elegir_juego).pack(side="left", padx=4)
    tk.Button(botones, text="Crear cuenta", command=boton_crear).pack(side="left", padx=4)
    tk.Button(botones, text="Entrar", command=boton_entrar, default="active").pack(side="left", padx=4)
    raiz.bind("<Return>", lambda _e: boton_entrar())
    (campos["clave"] if cfg.get("usuario") else campos["servidor"]).focus_set()
    raiz.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--probar":
        # python jugar.py --probar <ip> <usuario> <clave>: crea (si hace falta) y entra, sin abrir el juego
        _ip, _u, _c = sys.argv[2:5]
        try:
            print(crear_cuenta(_ip, _u, _c))
        except RuntimeError as e:
            print("crear:", e)
        print("entrar ->", entrar(_ip, _u, _c))
    else:
        ventana()
