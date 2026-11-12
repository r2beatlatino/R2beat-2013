#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""probar_nada_prohibido — que no se cuele al repo nada que no puede estar.

    python pruebas/probar_nada_prohibido.py

Revisa los archivos que sigue git (o, sin git, todos). Lo prohibido (ver CONTRIBUIR.md):
  · archivos del juego de Softnyx: .pak, .exe, música, gráficos, las notas (notes/*.bin), las tablas
    que saca extraer_datos.py (servidor/tablas-cliente/*.txt|*.xml, servidor/shop_lt.txt);
  · datos de un server: bases (.db), gm.txt / admin.txt / streamers.txt, sesiones, claves (.key, .pem);
  · datos personales en el texto: emails, rutas con el usuario de Windows, IPs públicas que no son
    las conocidas del juego, un hash de contraseña.
La única excepción binaria es nuestra `exe/d3d9.dll` (el fuente está en herramientas/dll_d3d9/).

★ Con su revés: antes de mirar el repo se comprueba que el detector SÍ caza cada cosa prohibida.
"""
import os
import re
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BINARIOS_PERMITIDOS = {"exe/d3d9.dll", "despliegue/ejemplo.env"}   # (el .env de ejemplo, sin claves)
TIPOS = (".pak", ".exe", ".dll", ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".bin", ".dak", ".key",
         ".pem", ".ogg", ".mp3", ".wav", ".dds", ".tga", ".bmp", ".png", ".jpg", ".jpeg", ".gif", ".zip",
         ".rar", ".7z", ".env")
ARCHIVOS = {"gm.txt", "admin.txt", "streamers.txt", "datos.db", "sesiones.json", "status.json", "jugar.json"}
DEL_CLIENTE = re.compile(r"^servidor/(?:shop_lt\.txt|notes_map_2013\.json|tablas-cliente/[^/]+\.(?:txt|xml|csv))$")
# IPs que SÍ pueden aparecer: locales, de ejemplo, el server original de Softnyx (lo que reemplaza
# el parche del exe) y la versión de una herramienta que tiene forma de IP.
IPS_CONOCIDAS = {"127.0.0.1", "0.0.0.0", "8.8.8.8", "216.177.209.25", "1.10.0.113"}
IP = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
TEXTO = [
    ("un email", re.compile(r"[\w.+-]+@(?:gmail|hotmail|outlook|yahoo|live|icloud|proton(?:mail)?)\.\w+", re.I)),
    ("una ruta con usuario de Windows", re.compile(r"(?i)[A-Z]:[\\/]+Users[\\/]+(?!<|USUARIO|tu_usuario|alguien)[^\\/\s\"'`]+")),
    ("una ruta de Git Bash con usuario",re.compile(r"/[cd]/Users/[^/\s]+", re.I)),
    ("un hash de contraseña", re.compile(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{20,}|pbkdf2_sha256\$\d+\$")),
    ("una clave privada", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
]


def privada(ip):
    a, b = int(ip[0]), int(ip[1])
    return a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)


def problemas(raiz, archivos):
    malos = []
    for rel in archivos:
        a = os.path.basename(rel)
        ruta = os.path.join(raiz, *rel.split("/"))
        if rel in BINARIOS_PERMITIDOS or not os.path.isfile(ruta):
            continue
        if a in ARCHIVOS or a.lower().endswith(TIPOS) or DEL_CLIENTE.match(rel):
            malos.append((rel, "ese archivo no puede ir al repo"))
            continue
        datos = open(ruta, "rb").read()
        if b"\0" in datos[:8192]:
            malos.append((rel, "es binario"))
            continue
        t = datos.decode("utf-8", "replace")
        for nombre, pat in TEXTO:
            m = pat.search(t)
            if m:
                malos.append((rel, "línea %d: %s" % (t.count("\n", 0, m.start()) + 1, nombre)))
        for m in IP.finditer(t):
            ip = m.group(0)
            if ip in IPS_CONOCIDAS or privada(m.groups()) or any(int(x) > 255 for x in m.groups()):
                continue
            malos.append((rel, "línea %d: una IP pública (%s)" % (t.count("\n", 0, m.start()) + 1, ip)))
    return malos


def archivos_de(raiz):
    r = subprocess.run(["git", "-C", raiz, "ls-files", "-co", "--exclude-standard"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return [x for x in r.stdout.splitlines() if x]
    out = []
    for base, dirs, fs in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "datos")]
        out += [os.path.relpath(os.path.join(base, f), raiz).replace("\\", "/") for f in fs]
    return out


def main():
    ok = []

    def chequear(nombre, c):
        print("  %s %s" % ("✅" if c else "⛔", nombre))
        ok.append(bool(c))

    # ★ el revés primero: un repo de mentira con una cosa prohibida por archivo (armadas por pedazos,
    #   así este archivo no se caza a sí mismo)
    casos = {"a.pak": "x", "servidor/gm.txt": "1", "datos.db": "x", "servidor/notes/1.bin": "x",
             "servidor/tablas-cliente/music_lt.txt": "x", "b.py": "# escribime a alguien" + "@gmail.com\n",
             "c.md": "en C:" + "\\Users\\pepe\\Desktop\n", "d.py": "HOST = '200.45." + "12.9'\n",
             "e.py": "# " + "$2b$12$" + "a" * 40 + "\n"}
    with tempfile.TemporaryDirectory() as tmp:
        for rel, contenido in casos.items():
            p = os.path.join(tmp, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(contenido)
        p = os.path.join(tmp, "limpio.py")
        open(p, "w", encoding="utf-8").write("IP = '127.0.0.1'  # o 192.168.1.50; ver C:\\Users\\<tu usuario>\n")
        cazados = {rel for rel, _ in problemas(tmp, list(casos) + ["limpio.py"])}
        chequear("★ revés: el detector caza cada cosa prohibida (%d/%d)" % (len(cazados & set(casos)), len(casos)),
                 cazados == set(casos))
        chequear("★ revés: y deja pasar lo de ejemplo (127.0.0.1, 192.168.1.50, <tu usuario>)",
                 "limpio.py" not in cazados)
    # y ahora el repo de verdad
    malos = problemas(RAIZ, archivos_de(RAIZ))
    for rel, por in malos:
        print("     ⛔ %s — %s" % (rel, por))
    chequear("el repo no tiene nada prohibido", not malos)
    print("\n%s" % ("→ TODO BIEN" if all(ok) else "→ ⛔ ALGO FALLA"))
    return 0 if all(ok) else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    sys.exit(main())
