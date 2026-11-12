#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""importar2013 — le da charts a las canciones que el cliente 2013 YA tiene (Fase A).

QUE HACE
--------
El cliente 2013 lista 823 canciones con su audio y sus portadas, pero sin notas: en el
retail las servia el server, y nuestra carpeta `notes/` esta vacia. Este script busca el
chart de cada una y escribe `notes/<songid2013>.bin`.

QUE **NO** HACE (y por que importa)
-----------------------------------
No abre ni repaqueta ningun .pak, no toca el `music_lt`, no agrega canciones y no
renumera nada. El songid de cada cancion queda como esta. Por eso las 19 misiones -que
llevan su cancion hardcodeada (`Music="519"`)- no corren ningun riesgo: la 519 sigue
siendo la misma cancion, ahora con flechas. Todo el trabajo pasa dentro de `notes/`.

DE DONDE SALEN LOS CHARTS
-------------------------
1. **CBT** (`server/notes/<idxCBT>.bin`), que es la fuente principal. El cruce es por el
   `File` del music_lt, NO por el numero: de 811 canciones que coinciden solo 7 comparten
   Index. Cruzar por Index fue el error que dejo 451 canciones con las flechas de otra.
2. **R2Single offline**, de respaldo, para las que el CBT no tiene o cuyo .bin nunca se
   deployo a prod. Ahi el chart viene en XML y se convierte al blob FF57.

COMO SE VALIDA
--------------
Tres cosas del .bin contra lo que el propio cliente 2013 declara para esa cancion:
  · el combo que la formula del exe saca del chart  ==  el `Combo` del music_lt
  · el ultimo Coord del chart                       ~=  el `<LENGTH>` del chart del cliente
  · el BPM del chart                                ==  el BPM del chart del cliente
Son archivos independientes: si coinciden, es la cancion correcta.

USO
---
  python importador2013/importar2013.py --scan               # reporte, NO escribe nada
  python importador2013/importar2013.py --apply              # escribe las OK
  python importador2013/importar2013.py --apply --con-revisar # + las de otra revision
  python importador2013/importar2013.py --verify             # relee notes/ y comprueba
"""
import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalogos                                   # noqa: E402
from combo_exe import TOPE_BLOB, armar_blob, combo_del_exe, leer_blob   # noqa: E402

# Margenes de la validacion.
RATIO_MIN, RATIO_MAX = 0.90, 1.02   # ultimo Coord / LENGTH. La mediana real da 1.000.
BPM_TOL = 0.51                      # el music_lt guarda el BPM con 2 decimales

def canciones_de_mision(script_dir):
    """Los songids que las misiones piden por numero fijo, leidos del propio cliente.

    Salen del atributo `Music=` de `rnr_script/mission/*.txt`. Hay que gritar si alguna
    queda sin chart: una mision sin chart es un FF57 con `result=0`, y eso auto-mata al
    cliente (ver RECETA §1).

    ⚠ Un archivo puede tener VARIOS bloques `<Mission>`: `add_8.txt` trae cinco. Leer solo
      el primero da 18 canciones cuando en realidad son 22 — asi se pasaron por alto la
      109, 195, 196 y 430. Por eso se recorre con `finditer` y no con `search`.
    """
    d = os.path.join(script_dir, "mission")
    if not os.path.isdir(d):
        return []
    ids = set()
    for f in sorted(os.listdir(d)):
        crudo = open(os.path.join(d, f), "rb").read()
        ids.update(int(x) for x in re.findall(rb'<Mission\b[^>]*?Music="(\d+)"', crudo))
    return sorted(ids)


def solo_de_mision(file_attr):
    """La cancion NO es del catalogo: su chart es el de una mision (`mission01.xml`).

    ⛔ Estas TIENEN que tener su `.bin` -si la mision se juega sin chart el cliente se
      auto-mata- pero NO pueden entrar en la lista del picker. Es la unica diferencia
      entre esta importacion y la del proyecto viejo, donde el picker se llenaba entero:
      su lista de 769 arrancaba en la 109 y no incluia las 50-55. Metiendolas, el cliente
      arma el picker con 16 canciones en vez de las 800 y pico.
      El aviso ya estaba escrito en `servidor/ajustes.py`:
        \"50-55 = mission01-06.xml (canciones de MISION, filtradas del picker -> NO usar)\"
    """
    return os.path.basename(file_attr).lower().startswith(("mission", "new_mission"))


def _mismo_tempo(chart, cliente):
    """¿El chart corre al tempo que el cliente declara para esa canción?

    Se compara el **primer** BPM y nada más. Comparar el timeline entero da falsos
    positivos a mansalva: el `.xml` del cliente 2013 es una definición recortada y suele
    traer un solo `<BPM>`, mientras el chart real trae el timeline completo — a veces 20
    marcadores del mismo valor (`Musica 1`, 212.5 × 20), a veces con micro-variaciones
    (`Musica 10`, 161/160/159/161). En todos esos casos el tempo es el mismo y las
    flechas caen donde tienen que caer. Lo que sí importa —y esto lo detecta— es un chart
    que corra a otra velocidad.
    """
    if not chart or not cliente:
        return False
    return abs(chart[0][1] - cliente[0][1]) < BPM_TOL


def analizar(rutas):
    """Una fila por cancion del music_lt 2013 que tenga `File`. No escribe nada."""
    sd13 = catalogos.desempacar_script(rutas["cliente_2013"], rutas["cache"], rutas["r2pak"], "2013")
    lt13, tapadas = catalogos.efectivas(catalogos.leer_music_lt(sd13))
    cbt_por_file = {}
    if rutas["cbt_cliente"] and rutas["cbt_notes"]:          # la fuente 1 es opcional
        sdcb = catalogos.desempacar_script(rutas["cbt_cliente"], rutas["cache"], rutas["r2pak"], "cbt")
        cbt_por_file = catalogos.por_file(catalogos.leer_music_lt(sdcb))
    respaldo = rutas["respaldo_charts"]
    for e in tapadas:
        print(f"  ⚠ Index={e['idx']} duplicado en el music_lt: se ignora "
              f"{os.path.basename(e['file'])} (combo {e['combo']}) porque el cliente se "
              f"queda con la PRIMERA entrada de ese indice")

    misiones = canciones_de_mision(sd13)
    filas = []
    for e in lt13:
        if not e["file"]:
            continue
        fila = dict(sid=e["idx"], nombre=e["name"], file=os.path.basename(e["file"]),
                    nivel=e["level"], mision=e["idx"] in misiones,
                    solo_mision=solo_de_mision(e["file"]),
                    fuente="", cbt_idx="", combo_lt=e["combo"], combo_chart="",
                    length="", ultimo_coord="", ratio="", bpm_lt="", bpm_chart="",
                    notas="", bytes="", veredicto="", motivo="")

        # el chart del propio cliente 2013: no trae <AREA>, pero SI el LENGTH y el BPM
        # contra los que se valida
        p13 = catalogos.chart_de(sd13, e["file"])
        if not os.path.isfile(p13):
            fila.update(veredicto="RECHAZADO", motivo="el cliente 2013 no trae el chart")
            filas.append(fila)
            continue
        c13 = catalogos.leer_chart(p13)
        fila["length"] = c13["length"] or ""
        fila["bpm_lt"] = ";".join(f"{b:g}" for _f, b in c13["bpms"])

        # ── fuente 1: el .bin del CBT, cruzado por File ────────────────────────
        bpms = notas = None
        y = cbt_por_file.get(fila["file"].lower())
        if y:
            fila["cbt_idx"] = y["idx"]
            pbin = os.path.join(rutas["cbt_notes"], f"{y['idx']}.bin")
            if os.path.isfile(pbin):
                try:
                    bpms, notas = leer_blob(open(pbin, "rb").read())
                    fila["fuente"] = "cbt"
                except Exception as ex:
                    fila["motivo"] = f"el .bin del CBT no se puede leer: {ex}"

        # ── fuente 2: el chart XML del R2Single ────────────────────────────────
        if notas is None:
            pxml = os.path.join(respaldo, fila["file"])
            if os.path.isfile(pxml):
                cr = catalogos.leer_chart(pxml)
                if cr["notas"]:
                    bpms, notas = cr["bpms"], cr["notas"]
                    fila["fuente"] = "r2single"

        if notas is None:
            fila.update(veredicto="RECHAZADO",
                        motivo=fila["motivo"] or "ninguna fuente tiene el chart")
            filas.append(fila)
            continue

        # ── validacion ────────────────────────────────────────────────────────
        fila["notas"] = len(notas)
        fila["combo_chart"] = combo_del_exe(notas)
        fila["bpm_chart"] = ";".join(f"{b:g}" for _f, b in bpms)
        blob = armar_blob(bpms, notas)
        fila["bytes"] = len(blob)

        malos = []
        if not notas:
            malos.append("chart sin notas")
        if len(blob) > TOPE_BLOB:
            malos.append(f"blob de {len(blob)} B > tope u16 del FF57")
        if malos:
            fila.update(veredicto="RECHAZADO", motivo=" · ".join(malos))
            filas.append(fila)
            continue

        fila["ultimo_coord"] = notas[-1][0]
        dudas = []
        if c13["length"]:
            fila["ratio"] = round(notas[-1][0] / c13["length"], 4)
            if not (RATIO_MIN <= fila["ratio"] <= RATIO_MAX):
                dudas.append(f"el chart no termina con la cancion (ratio {fila['ratio']})")
        else:
            dudas.append("el cliente no declara LENGTH")
        if e["combo"].isdigit() and fila["combo_chart"] != int(e["combo"]):
            dudas.append(f"combo {fila['combo_chart']} != {e['combo']} del music_lt")
        if not _mismo_tempo(bpms, c13["bpms"]):
            dudas.append("tempo distinto del que declara el cliente")

        # El ratio es el criterio DURO: si el chart no termina cuando termina la cancion,
        # no es esa cancion (o es una edicion incompatible) y no se sirve. Combo y BPM
        # dicen "es la cancion pero otra revision": suena sincronizado y no hay popup en
        # este cliente, asi que van a REVISAR y los decide el usuario.
        if fila["ratio"] == "" or not (RATIO_MIN <= fila["ratio"] <= RATIO_MAX):
            fila.update(veredicto="RECHAZADO", motivo=" · ".join(dudas))
        elif dudas:
            fila.update(veredicto="REVISAR", motivo=" · ".join(dudas))
        else:
            fila.update(veredicto="OK", motivo="")
        filas.append(fila)
    return filas, sd13, misiones


def blob_de(fila, rutas, sd13):
    """Reconstruye el blob de una fila ya analizada (misma fuente, mismo criterio)."""
    if fila["fuente"] == "cbt":
        bpms, notas = leer_blob(
            open(os.path.join(rutas["cbt_notes"], f"{fila['cbt_idx']}.bin"), "rb").read())
    else:
        c = catalogos.leer_chart(os.path.join(rutas["respaldo_charts"], fila["file"]))
        bpms, notas = c["bpms"], c["notas"]
    return armar_blob(bpms, notas)


def escribir_reporte(filas, path):
    cols = ["sid", "nombre", "file", "nivel", "mision", "solo_mision", "fuente", "cbt_idx", "combo_lt",
            "combo_chart", "length", "ultimo_coord", "ratio", "notas", "bytes",
            "bpm_lt", "bpm_chart", "veredicto", "motivo"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        w.writeheader()
        for fi in filas:
            w.writerow({c: fi.get(c, "") for c in cols})


def resumen(filas, aceptadas, misiones):
    cuenta = {}
    for fi in filas:
        cuenta[fi["veredicto"]] = cuenta.get(fi["veredicto"], 0) + 1
    print(f"\n  canciones del music_lt 2013 con File : {len(filas)}")
    for v in ("OK", "REVISAR", "RECHAZADO"):
        print(f"    {v:10} {cuenta.get(v, 0)}")
    fu = {}
    for fi in filas:
        if fi["veredicto"] != "RECHAZADO":
            fu[fi["fuente"]] = fu.get(fi["fuente"], 0) + 1
    print(f"  fuente: " + " · ".join(f"{k}={v}" for k, v in sorted(fu.items())))

    print("\n  MISIONES (cada una TIENE que quedar con chart):")
    faltan = []
    for sid in misiones:
        fi = next((x for x in filas if x["sid"] == sid), None)
        if fi is None:
            faltan.append((sid, "no esta en el music_lt"))
        elif sid not in aceptadas:
            faltan.append((sid, f"{fi['veredicto']}: {fi['motivo']}"))
    if faltan:
        for sid, por in faltan:
            fi = next((x for x in filas if x["sid"] == sid), None)
            print(f"    ⛔ {sid:>4} {(fi['nombre'] if fi else '?')[:24]:26} {por}")
        print(f"    ⛔⛔ {len(faltan)} mision(es) sin chart -> el cliente se auto-mata al jugarlas")
    else:
        print(f"    ✓ las {len(misiones)} tienen chart")

    rech = [f for f in filas if f["veredicto"] == "RECHAZADO"]
    if rech:
        print(f"\n  RECHAZADAS ({len(rech)}):")
        for fi in rech[:25]:
            print(f"    {fi['sid']:>5} {fi['nombre'][:24]:26} {fi['motivo'][:70]}")
        if len(rech) > 25:
            print(f"    ... y {len(rech) - 25} mas (estan en el reporte)")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--scan", action="store_true", help="analiza y reporta; NO escribe notas")
    g.add_argument("--apply", action="store_true", help="escribe notes/*.bin y el mapa")
    g.add_argument("--verify", action="store_true", help="relee lo escrito y lo comprueba")
    ap.add_argument("--con-revisar", action="store_true",
                    help="incluye tambien las de otra revision del chart (veredicto REVISAR)")
    args = ap.parse_args()

    rutas = catalogos.cargar_rutas()
    if args.verify:
        return verificar(rutas)

    filas, sd13, misiones = analizar(rutas)
    acept_v = ("OK", "REVISAR") if args.con_revisar else ("OK",)
    aceptadas = {f["sid"] for f in filas if f["veredicto"] in acept_v}
    rep = os.path.join(rutas["cache"], "reporte.csv")
    escribir_reporte(filas, rep)
    print(f"reporte -> {rep}")
    resumen(filas, aceptadas, misiones)

    if args.scan:
        n_rev = sum(1 for f in filas if f["veredicto"] == "REVISAR")
        print(f"\n  (scan: no se escribio ninguna nota)")
        print(f"  --apply escribiria {len(aceptadas)} canciones"
              + (f"; con --con-revisar serian {len(aceptadas) + n_rev}" if not args.con_revisar else ""))
        return

    # ── apply ─────────────────────────────────────────────────────────────────
    destino = rutas["notes_destino"]
    os.makedirs(destino, exist_ok=True)
    escritas, fallos = [], []
    for fi in filas:
        if fi["sid"] not in aceptadas:
            continue
        try:
            blob = blob_de(fi, rutas, sd13)
            with open(os.path.join(destino, f"{fi['sid']}.bin"), "wb") as f:
                f.write(blob)
            escritas.append(fi)
        except Exception as ex:
            fallos.append((fi["sid"], repr(ex)))

    # `notes/` tiene que quedar siendo EXACTAMENTE el resultado de esta corrida: un .bin
    # que sobrevive de una corrida anterior sigue haciendo que el picker ofrezca esa
    # cancion (el server verifica el archivo, no el mapa) y nadie lo volveria a mirar.
    vivos = {f"{fi['sid']}.bin" for fi in escritas}
    borrados = 0
    for nom in os.listdir(destino):
        if nom.endswith(".bin") and nom not in vivos:
            os.remove(os.path.join(destino, nom))
            borrados += 1

    mapa = {
        "_doc": ("Charts propios del proyecto 2013 (Fase A, importador2013). El .bin se llama "
                 "con el songid DEL 2013, asi que el mapa es la identidad: no hay traduccion de "
                 "indices que pueda desalinearse. `cbt_idx` queda solo como trazabilidad de de "
                 "donde salio cada chart. Regenerar con: "
                 "python importador2013/importar2013.py --apply"),
        "map": {str(f["sid"]): f["sid"] for f in escritas},
        # ★ el picker NO lleva las canciones de mision: su .bin se escribe igual (sin chart
        #   la mision auto-mata al cliente) pero ofrecerlas en la lista rompe el picker
        #   entero. Ver `solo_de_mision`.
        "owned_songs": sorted(f["sid"] for f in escritas if not f["solo_mision"]),
        "titles": {str(f["sid"]): f["nombre"] for f in escritas},
        "combo_mismatch": sorted(f["sid"] for f in escritas
                                 if "combo" in f["motivo"]),
        "cbt_idx": {str(f["sid"]): f["cbt_idx"] for f in escritas if f["fuente"] == "cbt"},
        "fuente": {str(f["sid"]): f["fuente"] for f in escritas},
    }
    with open(rutas["notes_map"], "w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=1)

    print(f"\n  escritas {len(escritas)} notas en {destino}"
          + (f" ({borrados} .bin viejos borrados)" if borrados else ""))
    print(f"  mapa     {rutas['notes_map']} ({len(mapa['owned_songs'])} jugables, "
          f"{len(mapa['combo_mismatch'])} con otra revision)")
    if fallos:
        print(f"  ⛔ {len(fallos)} fallaron al escribir: {fallos[:5]}")


def verificar(rutas):
    """Relee `notes/` como lo haria el cliente y comprueba contra el music_lt."""
    sd13 = catalogos.desempacar_script(rutas["cliente_2013"], rutas["cache"], rutas["r2pak"], "2013")
    usadas, _ = catalogos.efectivas(catalogos.leer_music_lt(sd13))
    lt = {e["idx"]: e for e in usadas}
    destino = rutas["notes_destino"]
    bins = sorted(int(f[:-4]) for f in os.listdir(destino) if f.endswith(".bin") and f[:-4].isdigit())
    print(f"  {len(bins)} .bin en {destino}")
    malos, sin_lt, combo_ok = [], [], 0
    for sid in bins:
        p = os.path.join(destino, f"{sid}.bin")
        try:
            bpms, notas = leer_blob(open(p, "rb").read())
        except Exception as ex:
            malos.append((sid, repr(ex)))
            continue
        if os.path.getsize(p) > TOPE_BLOB:
            malos.append((sid, "supera el tope u16 del FF57"))
        e = lt.get(sid)
        if e is None:
            sin_lt.append(sid)
        elif e["combo"].isdigit() and combo_del_exe(notas) == int(e["combo"]):
            combo_ok += 1
    print(f"  ilegibles / fuera de formato : {len(malos)} {malos[:5]}")
    print(f"  sin entrada en el music_lt   : {len(sin_lt)} {sin_lt[:10]}"
          + ("   ⛔ el cliente escupe 'Music Not Found' y crashea" if sin_lt else ""))
    print(f"  combo exacto                 : {combo_ok}/{len(bins)}")
    misiones = canciones_de_mision(sd13)
    faltan = [s for s in misiones if s not in set(bins)]
    print(f"  misiones con chart           : {len(misiones) - len(faltan)}/{len(misiones)}"
          + (f"   ⛔ faltan {faltan}" if faltan else "  ✓"))


if __name__ == "__main__":
    main()
