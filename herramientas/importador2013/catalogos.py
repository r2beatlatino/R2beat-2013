#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""catalogos — leer el `music_lt` y los charts de un cliente R2Beat.

Los dos catalogos que cruzamos (el del cliente 2013 y el del CBT) viven dentro de
`rnr_script.pak`, asi que hay que desempacarlos antes de poder leerlos. El desempacado
se cachea (en `datos/importador2013/`) porque el scan se corre muchas veces.

★ LA LLAVE ENTRE CATALOGOS ES EL `File`, NO EL `Index`.
  El `File` es la ruta del chart (`rnr_script/music/n_song519.xml`) y es la misma en los
  dos clientes. El `Index` NO: de 811 canciones que coinciden por `File`, solo 7 comparten
  numero. Cruzar por Index fue el error que en julio dejo 451 canciones con las flechas de
  otra cancion, sin sintoma visible mas que el desfase.
"""
import json
import os
import re
import shutil
import sys

# herramientas/importador2013/catalogos.py -> la raíz está DOS carpetas más arriba.
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from pak import Paks  # noqa: E402

# Lo que el importador necesita y no tiene un valor obvio. Lo relativo se resuelve contra la RAÍZ.
DEFECTO = {
    "cliente_2013": "", "cbt_cliente": "", "cbt_notes": "", "respaldo_charts": "",
    "notes_destino": "servidor/notes",
    "notes_map": "servidor/notes_map_2013.json",
    "cache": "datos/importador2013",
}


def cargar_rutas():
    """Las rutas de `config.json` (al lado de este archivo), ya absolutas.

    ⚠ `cbt_notes` y `respaldo_charts` son FUENTES de charts: si no tenés una, dejala vacía y el
      importador sigue con la otra. `cbt_cliente` hace falta para cruzar por `File` con el CBT.
    """
    ruta = os.path.join(AQUI, "config.json")
    if not os.path.isfile(ruta):
        raise SystemExit(f"⛔ falta {ruta}\n   Copiá config-ejemplo.json a config.json y poné tus rutas.")
    with open(ruta, encoding="utf-8") as f:
        r = dict(DEFECTO, **{k: v for k, v in json.load(f).items() if not k.startswith("_")})
    out = {}
    for k, v in r.items():
        if not isinstance(v, str):
            continue
        out[k] = "" if not v else (v if os.path.isabs(v) else os.path.join(RAIZ, v))
    out.setdefault("r2pak", "")                      # ya no hace falta: los .pak se leen con `pak.py`
    os.makedirs(out["cache"], exist_ok=True)
    return out


# ── desempacado del rnr_script.pak ─────────────────────────────────────────────

def desempacar_script(cliente, cache, _r2pak, nombre):
    """Saca `rnr_script/*` de los .pak de `<cliente>` a `<cache>/<nombre>/rnr_script` y devuelve esa carpeta.

    Se rehace sólo si el `rnr_script.pak` cambió (tamaño + fecha contra un sello).
    """
    pak = os.path.join(cliente, "rnr_script.pak")
    if not os.path.isfile(pak):
        raise SystemExit(f"⛔ no encuentro {pak}")
    dest = os.path.join(cache, nombre)
    st = os.stat(pak)
    sello_actual = f"{st.st_size}:{int(st.st_mtime)}"
    sello = os.path.join(dest, ".sello")
    if os.path.isfile(sello) and open(sello, encoding="utf-8").read() == sello_actual:
        return os.path.join(dest, "rnr_script")

    shutil.rmtree(dest, ignore_errors=True)
    paks = Paks(cliente)
    n = 0
    for ruta in paks.ix:
        if not ruta.startswith("rnr_script/"):
            continue
        destino = os.path.join(dest, *ruta.split("/"))
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "wb") as f:
            f.write(paks.sacar(ruta))
        n += 1
    if not n:
        raise SystemExit(f"⛔ no pude sacar nada de rnr_script/ en {cliente}")
    with open(sello, "w", encoding="utf-8") as f:
        f.write(sello_actual)
    return os.path.join(dest, "rnr_script")


# ── music_lt ──────────────────────────────────────────────────────────────────

_ATTR = re.compile(rb'(\w+)\s*=\s*"([^"]*)"')


def _texto(b):
    return b.decode("cp949", "replace")


def leer_music_lt(script_dir):
    """Las entradas del `music_lt.txt`, en orden de archivo.

    Se parsea partiendo por `<Music` en vez de con un parser XML porque el archivo es
    euc-kr con `\\n` literales dentro de los atributos y ningun parser lo acepta entero.
    """
    p = os.path.join(script_dir, "music_lt.txt")
    raw = open(p, "rb").read()
    out = []
    for bloque in raw.split(b"<Music")[1:]:
        bloque = bloque.split(b"</Music>")[0]
        a = {k.decode("ascii").lower(): v for k, v in _ATTR.findall(bloque)}
        idx = a.get("index", b"")
        if not idx.isdigit():
            continue
        out.append({
            "idx": int(idx),
            "file": _texto(a.get("file", b"")),
            "name": _texto(a.get("name", b"")),
            "level": _texto(a.get("level", b"")),
            "genre": _texto(a.get("genre", b"")),
            "artist": _texto(a.get("artist", b"")),
            "combo": _texto(a.get("combo", b"")),
            "time": _texto(a.get("time", b"")),
        })
    return out


def efectivas(entradas):
    """`(las que el cliente realmente usa, las tapadas)`, con la regla del propio exe.

    El `music_lt` puede traer el mismo `Index` dos veces (en el cliente 2013 pasa con el
    3997: `e_song3997.xml` combo 172 y `h_song4001.xml` combo 942). El catálogo del cliente
    es un `std::map<u16, entrada>` y el insert de `0x40D2F0`, cuando la clave ya está,
    devuelve el iterador existente con el `bool` del par en 0 (`0x40D3DB`) — o sea que **no
    sobrescribe**. Como el parser lee el archivo de arriba a abajo, **gana la primera
    aparición** y la segunda es dato muerto que el cliente nunca alcanza.
    """
    usadas, tapadas, vistos = [], [], set()
    for e in entradas:
        if e["idx"] in vistos:
            tapadas.append(e)
        else:
            vistos.add(e["idx"])
            usadas.append(e)
    return usadas, tapadas


def por_file(entradas):
    """`{nombre_de_chart_en_minuscula: entrada}`. La llave de cruce entre catalogos."""
    d = {}
    for e in entradas:
        if e["file"]:
            d.setdefault(os.path.basename(e["file"]).lower(), e)
    return d


# ── charts (los .xml de rnr_script/music) ─────────────────────────────────────

_BPM = re.compile(rb'<BPM\b([^>]*)>')
_AREA = re.compile(rb'<AREA\b([^>]*)>')
_LEN = re.compile(rb'<LENGTH\s+Value\s*=\s*"([\d.\-]+)"')
_BGM = re.compile(rb'<BGM\s+Name\s*=\s*"([^"/]*)/')


def leer_chart(path):
    """`{bpms, length, pak, notas}` de un chart XML. `notas` vacia si el chart no trae `<AREA>`.

    Los charts del cliente 2013 NO traen `<AREA>` (las notas las servia el server): de ellos
    solo se usan `bpms` y `length`, que son la vara contra la que se valida el .bin del CBT.
    """
    d = open(path, "rb").read()
    bpms = []
    for m in _BPM.finditer(d):
        a = {k.decode("ascii").lower(): v.decode("ascii", "replace")
             for k, v in _ATTR.findall(m.group(1))}
        if "frame" in a and "bpm" in a:
            try:
                bpms.append((float(a["frame"]), float(a["bpm"])))
            except ValueError:
                pass
    notas, vistos = [], set()
    for m in _AREA.finditer(d):
        a = {k.decode("ascii").lower(): v.decode("ascii", "replace")
             for k, v in _ATTR.findall(m.group(1))}
        try:
            coord = int(round(float(a["coord"])))
            kind = int(round(float(a["kind"])))
            level = int(round(float(a["level"])))
            fx = int(round(float(a["fxsndindex"])))
        except (KeyError, ValueError):
            continue
        ap = a.get("autoplay")
        if ap is not None and ap.strip() not in ("", "0"):
            fx |= 0x8000                      # ver RECETA_NOTAS_2013.md §2
        if coord in vistos:
            continue                          # coords duplicados: el juez los toma como uno solo
        vistos.add(coord)
        notas.append((coord, kind, level, fx))
    notas.sort(key=lambda n: n[0])
    ml = _LEN.search(d)
    mb = _BGM.search(d)
    return {
        "bpms": bpms,
        "length": float(ml.group(1)) if ml else None,
        "pak": (mb.group(1).decode("cp949", "replace") + ".pak") if mb else None,
        "notas": notas,
    }


def chart_de(script_dir, file_attr):
    """Ruta al XML del chart que nombra el `File` de una entrada del music_lt."""
    return os.path.join(script_dir, "music", os.path.basename(file_attr))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = cargar_rutas()
    for nom, cli in (("2013", r["cliente_2013"]), ("cbt", r["cbt_cliente"])):
        sd = desempacar_script(cli, r["cache"], r["r2pak"], nom)
        e = leer_music_lt(sd)
        print(f"{nom}: {len(e)} entradas, {len(por_file(e))} con File  ->  {sd}")
