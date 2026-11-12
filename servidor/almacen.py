# -*- coding: utf-8 -*-
"""almacen — la persistencia sobre SQLite. Reemplaza a los dos archivos JSON.

POR QUE
-------
`db_save()` reescribía `chars_db.json` ENTERO en cada guardado, sin archivo temporal ni `rename`
atómico: dos guardados a la vez se pisaban y un corte a mitad dejaba el archivo roto — y ahí se
perdía **todo**, no una fila. El esquema es el del CBT (`servidor/esquema.py`), que está andando
hace meses con 5.376 cuentas.

★ LA FORMA DE LOS DICCIONARIOS NO CAMBIA. `leer_todos()` devuelve exactamente lo que devolvía
  `json.load(chars_db.json)`, y `leer_cuentas()` lo mismo con `cuentas.json`. Por eso las ~30
  funciones de `basedatos.py` y sus 11 consumidores siguen funcionando sin tocarles una línea:
  lo único que cambia es de dónde salen los datos.

★★ Y `guardar_todos()` escribe SOLO los personajes que cambiaron. Eso no es una optimización: es
  lo que arregla el problema de fondo. Con el JSON, dos jugadores guardando a la vez se pisaban
  entero; acá cada uno toca su propia fila y no se estorban.
  ⚠ Sigue habiendo una ventana si DOS conexiones tocan **el mismo** personaje a la vez. Eso se
    cierra recién cuando los que llaman actualicen campos sueltos en vez de mandar el dict entero.
    No lo arreglé: prefiero decirlo a dejarlo escrito como si estuviera resuelto.

⚠ WAL encendido: un lector no bloquea al que escribe. Deja `datos.db-wal` y `datos.db-shm` al lado,
  que son temporales de SQLite y están en el `.gitignore`.
"""
import io
import json
import os
import sqlite3
import threading
import time

from .esquema import ESQUEMA
from .registro import log

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("R2_BASE") or os.path.join(RAIZ, "datos.db")
_lock = threading.Lock()
_local = threading.local()


def conectar():
    """Una conexión POR HILO. `sqlite3` no deja compartirlas entre hilos, y el server usa uno por
    conexión de jugador."""
    c = getattr(_local, "con", None)
    if c is None:
        c = sqlite3.connect(BASE, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(ESQUEMA)
        _local.con = c
    return c


# ───────────────────────── un personaje: dict <-> filas ─────────────────────────
# ★ Esta pareja de funciones es la MISMA que verificó `pruebas/migrar_a_sqlite.py` haciendo la ida
#   y vuelta sobre los 56 personajes. Vive acá para que exista UNA sola implementación: si el
#   migrador tuviera su propia copia, las dos se irían separando y la verificación dejaría de
#   valer para el server.

def _genero_para_guardar(p):
    """El sexo que va a la columna `gender`, sin dejar que un personaje del gacha lo dé vuelta.

    ⛔⛔ ACÁ DECÍA `int(p.get("char_id", 0)) & 1`, Y NOS CORROMPIÓ DATOS (2026-09-09).
      Esa regla vale para los personajes BASE (`130900` hombre / `130901` mujer) pero **no para los
      del gacha**: sus números no codifican el sexo (`130029` y `110275` son impares y de HOMBRE,
      lo dice `hero.txt`). Y como al equipar uno se pisa el `char_id`, **cada guardado le daba
      vuelta el sexo al jugador en la base**.
      Se vio en pantalla: *"un char M, al ponerse personaje de M, su ícono aparece como F"*.

    ⛔⛔ Y EL PRIMER ARREGLO TAMPOCO ALCANZABA — 2026-09-09, revisando la lista antes de subir.
      Quedó preguntando **primero a `hero.txt`**, o sea que el sexo se seguía sacando del personaje
      PUESTO. Sólo dejó de morder cuando los dos coinciden. Comprobado acá mismo:

          jugadora (gender=1) con el personaje 110275 puesto (hero.txt: HOMBRE)
              -> se guardaba gender = 0   ⛔ la jugadora quedaba hombre en la base

      Pasa cada vez que el sexo del personaje puesto no es el del jugador, y desde el 2026-09-09
      eso es **lo NORMAL, no un caso raro**: el sorteo del gacha ya no mira el sexo (era una
      invención que convertía máquinas en expendedoras — ver `gacha.sortear_para`), así que
      cualquiera puede ganarse y ponerse un personaje del otro sexo. Es lo que hacía el original.
      ⇒ Razón de más para que esta función NO derive nada: el `char_id` dejó de decir quién es el
        jugador **por diseño**, no por accidente.

    ★★ LA REGLA BUENA: **el `gender` guardado GANA SIEMPRE.** Es la identidad del jugador, se
      escribió al crear el personaje y ninguna cosa que se ponga encima la cambia. `hero.txt` dice
      el sexo de un DISFRAZ, no el de la persona.
      ⇒ Orden: el `gender` que ya está en la fila; si no hay (personaje recién creado, donde el
        `char_id` **es** el base), lo que diga `hero.txt`; y recién ahí el último dígito.

    ⚠ Para PINTAR el ícono es al revés y va aparte (`gacha.sexo` / `gacha.genero_visible`): ahí lo
      que se dibuja es el personaje que tiene puesto. Los dos existen y no son intercambiables.
    """
    cid = int(p.get("char_id", 0) or 0)
    if p.get("gender") is not None:
        return int(p["gender"]) & 1
    try:
        from . import gacha
        g = gacha.genero_de(cid)
        if g is not None:
            return int(g) & 1
    except Exception:
        pass
    return cid & 1


def char_a_filas(c, uid, p):
    # ★ 11-oct: `hair/top/bottom/skates` (del CBT, hasta hoy siempre 0) = el SET BÁSICO de la creación
    #   (`p["basico"]`, ver `catalogo.asegurar_basico`). Un dict que no lo trae NO lo borra: se conserva lo guardado.
    _b = p.get("basico")
    if _b is None:
        _f = c.execute("SELECT hair, top, bottom, skates FROM chars WHERE uid=?", (uid,)).fetchone()
        _b = list(_f) if _f else [0, 0, 0, 0]
    _b = [int(x or 0) for x in (list(_b) + [0, 0, 0, 0])[:4]]
    c.execute("""INSERT OR REPLACE INTO chars
        (uid,nickname,gender,char_id,hair,top,bottom,skates,exp,coin,cash,mission,created_at,
         licencia,rpoint,monedas_gorila,leccion_max,misiones_todas,age,bio,guild)
        VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?)""",
              (uid, p.get("nick", ""), _genero_para_guardar(p), int(p.get("char_id", 0)), *_b,
               int(p.get("exp", 0) or 0), int(p.get("rcoin", 0) or 0),
               int(p.get("mission", 0) or 0), p.get("created_at", ""),
               int(p.get("licencia", 0) or 0), int(p.get("rpoint", 0) or 0),
               int(p.get("monedas_gorila", 0) or 0), int(p.get("leccion_max", 0) or 0),
               1 if p.get("misiones_todas") else 0,
               int(p.get("age", 0) or 0), p.get("bio", "") or "", p.get("guild", "") or ""))
    # las tablas hijas se rehacen enteras para este uid: es una fila por prenda/misión y son
    # decenas, no miles, y así no hay que llevar la cuenta de qué se borró.
    for t in ("wear", "misiones_hechas", "misiones_grado", "misiones_mascaras",
              "premios", "lecciones", "inventory"):
        c.execute(f"DELETE FROM {t} WHERE uid=?", (uid,))
    # ⛔ `parts` es de largo VARIABLE y sin posición fija: va a `wear`, no a hair/top/bottom/skates.
    #   Ver el aviso de `servidor/esquema.py` — mapearlo a 4 columnas perdía ropa en silencio.
    for i, prenda in enumerate(p.get("parts") or []):
        c.execute("INSERT INTO wear (uid,role_id,item_id) VALUES (?,?,?)", (uid, i, int(prenda)))
    nib = (list(p.get("mision_nibbles") or []) + [0, 0, 0])[:3]
    c.execute("INSERT OR REPLACE INTO mision_nibbles (uid,n0,n1,n2) VALUES (?,?,?,?)",
              (uid, int(nib[0]), int(nib[1]), int(nib[2])))
    for g, lista in enumerate(p.get("misiones_hechas") or []):
        for m in lista or []:
            c.execute("INSERT OR IGNORE INTO misiones_hechas (uid,grupo,mision) VALUES (?,?,?)",
                      (uid, g, int(m)))
    for m, gr in (p.get("misiones_grado") or {}).items():
        c.execute("INSERT OR REPLACE INTO misiones_grado (uid,mision,grado) VALUES (?,?,?)",
                  (uid, int(m), str(gr)))
    for m in p.get("misiones_mascaras") or []:
        c.execute("INSERT OR IGNORE INTO misiones_mascaras (uid,mascara) VALUES (?,?)",
                  (uid, int(m)))
    for tipo in ("items", "rcoin"):
        for m in p.get("premios_" + tipo) or []:
            c.execute("INSERT OR IGNORE INTO premios (uid,mision,tipo) VALUES (?,?,?)",
                      (uid, int(m), tipo))
    for lec in p.get("lecciones") or []:
        c.execute("INSERT OR IGNORE INTO lecciones (uid,leccion) VALUES (?,?)", (uid, int(lec)))
    for e in p.get("inventory") or []:
        iid = e["id"] if isinstance(e, dict) else e
        c.execute("INSERT OR REPLACE INTO inventory (uid,item_id,end_time,count) VALUES (?,?,?,?)",
                  (uid, int(iid),
                   int(e.get("exp", 0) or 0) if isinstance(e, dict) else 0,
                   int(e.get("cant", 0) or 0) if isinstance(e, dict) else 0))


def filas_a_char(c, uid):
    """El dict del personaje, con la MISMA forma que tenía en `chars_db.json`."""
    f = c.execute("SELECT * FROM chars WHERE uid=?", (uid,)).fetchone()
    if not f:
        return None
    # ★ `gender` se EXPONE (2026-09-09): sin esto nadie podía saber si el jugador era hombre o
    #   mujer una vez que se ponía un personaje del gacha, porque el `char_id` deja de decirlo.
    p = {"char_id": f["char_id"], "nick": f["nickname"], "gender": f["gender"],
         "parts": [r["item_id"] for r in
                   c.execute("SELECT item_id FROM wear WHERE uid=? ORDER BY role_id", (uid,))],
         "exp": f["exp"], "rcoin": f["coin"], "mission": f["mission"],
         "licencia": f["licencia"]}
    for col in ("rpoint", "monedas_gorila", "leccion_max", "age"):
        if f[col]:
            p[col] = f[col]
    if any(f[k] for k in ("hair", "top", "bottom", "skates")):          # ★ 11-oct: el set básico
        p["basico"] = [int(f[k] or 0) for k in ("hair", "top", "bottom", "skates")]
    for col in ("bio", "created_at"):
        if f[col]:
            p[col] = f[col]
    # ★ `guild` = el nombre del CÍRCULO (24-sep). Sale de `circulo_miembros`, NO de la columna
    #   `chars.guild`: ésa quedaría vieja al salir o al ser echado. Con esto el MyRecord @44 y el
    #   str2 del FF0C (los dos leen `char["guild"]`) siguen al círculo solos. La columna queda muerta.
    _k = c.execute("SELECT k.nombre FROM circulo_miembros m JOIN circulos k ON k.id = m.circulo_id "
                   "WHERE m.uid=?", (uid,)).fetchone()
    if _k and _k[0]:
        p["guild"] = _k[0]
    if f["misiones_todas"]:
        p["misiones_todas"] = True
    n = c.execute("SELECT n0,n1,n2 FROM mision_nibbles WHERE uid=?", (uid,)).fetchone()
    p["mision_nibbles"] = [n["n0"], n["n1"], n["n2"]] if n else [0, 0, 0]
    hechas = [[], [], []]
    for r in c.execute("SELECT grupo,mision FROM misiones_hechas WHERE uid=? ORDER BY rowid",
                       (uid,)):
        while len(hechas) <= r["grupo"]:
            hechas.append([])
        hechas[r["grupo"]].append(r["mision"])
    p["misiones_hechas"] = hechas
    p["misiones_grado"] = {str(r["mision"]): r["grado"] for r in
                           c.execute("SELECT mision,grado FROM misiones_grado WHERE uid=? "
                                     "ORDER BY rowid", (uid,))}
    for tipo in ("items", "rcoin"):
        v = [r["mision"] for r in c.execute(
            "SELECT mision FROM premios WHERE uid=? AND tipo=? ORDER BY rowid", (uid, tipo))]
        if v:
            p["premios_" + tipo] = v
    v = [r["mascara"] for r in
         c.execute("SELECT mascara FROM misiones_mascaras WHERE uid=? ORDER BY rowid", (uid,))]
    if v:
        p["misiones_mascaras"] = v
    v = [r["leccion"] for r in
         c.execute("SELECT leccion FROM lecciones WHERE uid=? ORDER BY rowid", (uid,))]
    if v:
        p["lecciones"] = v
    inv = []
    for r in c.execute("SELECT item_id,end_time,count FROM inventory WHERE uid=? ORDER BY rowid",
                       (uid,)):
        e = {"id": r["item_id"], "exp": r["end_time"]}
        if r["count"]:
            e["cant"] = r["count"]
        inv.append(e)
    if inv:
        p["inventory"] = inv
    return p


# ───────────────────────── la interfaz que usa `basedatos.py` ─────────────────────────
def leer_char(uid):
    with _lock:
        return filas_a_char(conectar(), int(uid))


def uids_usados():
    """Sólo los uid, sin armar un personaje por cada uno. Para elegir un uid libre al crear
    una cuenta: antes se llamaba a `leer_todos()` y se tiraba todo menos las claves."""
    with _lock:
        c = conectar()
        # ★ 21-oct: también los uid RESERVADOS para los casilleros 2-4 de una cuenta (cuenta_personajes.py): si no,
        #   una cuenta nueva podía llevarse el uid de un personaje que se estaba creando
        return [int(r["uid"]) for r in c.execute("SELECT uid FROM chars UNION SELECT uid FROM cuenta_personajes")]


def cuenta_de_uid(uid):
    """-> (username, ranura) del personaje `uid`: la cuenta misma es la ranura 1 (`users.uid`); la 2-4 sale de
    `cuenta_personajes`. `(None, 0)` si no es de nadie. ★ 25-oct: el selector del juego se autentica con la SESIÓN
    (usn + vcode), no con la contraseña: de ahí hay que volver a la cuenta.
    ★ 25-oct (fusionar): un personaje MUDADO a otra cuenta tiene fila en `cuenta_personajes` Y sigue teniendo la de
      su cuenta vieja en `users` (bloqueada, `FUSIONADA:`). Manda la mudanza: por eso se mira primero acá."""
    with _lock:
        return _ubicacion(conectar(), uid)


# ═══ MUDAR PERSONAJES ENTRE CUENTAS (25-oct, anonimo03: «fusionar, separar cuentas… control total», en el panel) ═══════
#   ⛔ Nada se copia ni se borra: un personaje es su uid, y con él viajan su Rcoin, EXP, inventario, ropa, amigos,
#     círculo y récords. Mudarlo es cambiar DE QUÉ CUENTA cuelga: una fila de `cuenta_personajes`.
#   · El casillero 1 es la cuenta misma (`users.uid`). Si se lo llevan, esa cuenta queda BLOQUEADA: `FUSIONADA:`
#     delante del `pass_hash`, como el `BANNED:` del ban, así que todo login (juego, web, launcher) la rechaza sin
#     tocar una línea de ellos. `separar_cuenta` la devuelve tal cual.
#   · Cada mudanza va a `movimientos_personajes` (de dónde a dónde, quién, cuándo): con eso se deshace.
FUSIONADA = "FUSIONADA:"


def es_fusionada(pass_hash):
    """¿Esa cuenta está fusionada en otra? (también si encima está baneada: `BANNED:FUSIONADA:…`)"""
    p = str(pass_hash or "")
    return (p[7:] if p.startswith("BANNED:") else p).startswith(FUSIONADA)


def _ubicacion(c, uid):
    r = c.execute("SELECT username, ranura FROM cuenta_personajes WHERE uid = ?", (int(uid),)).fetchone()
    if r:
        return r["username"], int(r["ranura"])
    r = c.execute("SELECT username, pass_hash FROM users WHERE uid = ? ORDER BY rowid DESC LIMIT 1", (int(uid),)).fetchone()
    return (r["username"], 1) if r and not es_fusionada(r["pass_hash"]) else (None, 0)


def _cuenta_fila(c, usuario):
    return c.execute("SELECT uid, username, pass_hash FROM users WHERE username = ? COLLATE BINARY "
                     "ORDER BY rowid DESC LIMIT 1", (usuario,)).fetchone()


def _ranuras(c, usuario):
    """{ranura: uid} de una cuenta ACTIVA (la 1 es `users.uid`). Una fusionada no tiene ninguna."""
    u = _cuenta_fila(c, usuario)
    if not u or es_fusionada(u["pass_hash"]):
        return {}
    out = {1: int(u["uid"])}
    out.update({int(r["ranura"]): int(r["uid"]) for r in c.execute(
        "SELECT ranura, uid FROM cuenta_personajes WHERE username = ? COLLATE BINARY", (usuario,))})
    return out


def _anotar(c, uid, de, a, motivo, actor):
    c.execute("INSERT INTO movimientos_personajes (uid, de_cuenta, de_ranura, a_cuenta, a_ranura, motivo, actor, cuando) "
              "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))",
              (int(uid), de[0], de[1], a[0], a[1], motivo, int(actor or 0)))


def _bloquear(c, usuario, si):
    if si:
        c.execute("UPDATE users SET pass_hash = CASE WHEN pass_hash LIKE 'BANNED:%' THEN 'BANNED:' || ? || substr(pass_hash, 8) "
                  "ELSE ? || pass_hash END WHERE username = ? COLLATE BINARY", (FUSIONADA, FUSIONADA, usuario))
    else:
        c.execute("UPDATE users SET pass_hash = replace(pass_hash, ?, '') WHERE username = ? COLLATE BINARY",
                  (FUSIONADA, usuario))


def _transaccion(hacer):
    """Corre `hacer(c)` entera o nada. -> (True, lo que devuelva) · (False, el motivo)."""
    with _lock:
        c = conectar()
        try:
            out = hacer(c)
            c.commit()
            return True, out
        except ValueError as e:
            c.rollback()
            return False, str(e)


def cuenta_estado(usuario):
    """La cuenta para el panel: {usuario, usn, fusionada, baneada, ranuras {r: uid}} o None."""
    with _lock:
        c = conectar()
        u = _cuenta_fila(c, usuario)
        if not u:
            return None
        return {"usuario": u["username"], "usn": int(u["uid"]), "fusionada": es_fusionada(u["pass_hash"]),
                "baneada": str(u["pass_hash"] or "").startswith("BANNED:"), "ranuras": _ranuras(c, usuario)}


def _libre(c, usuario, ranura):
    rs = _ranuras(c, usuario)
    if not rs:
        raise ValueError(f"la cuenta {usuario!r} no existe o está fusionada")
    libres = [r for r in (2, 3, 4) if r not in rs]
    if ranura is None:
        if not libres:
            raise ValueError(f"la cuenta {usuario!r} no tiene casilleros libres")
        return libres[0]
    if int(ranura) not in (2, 3, 4):
        raise ValueError("el casillero tiene que ser 2, 3 o 4 (el 1 es la cuenta misma)")
    if int(ranura) not in libres:
        raise ValueError(f"el casillero {ranura} de {usuario!r} está ocupado")
    return int(ranura)


def mover_personaje(uid, a_cuenta, a_ranura=None, motivo="mover", actor=0):
    """Muda UN personaje a un casillero libre (2-4) de otra cuenta (o de la misma, a otro casillero).
    El casillero 1 sólo se muda si su cuenta no tiene otros: esa cuenta queda bloqueada (si no, `fusionar_cuentas`).
    -> (True, (cuenta, ranura) nueva) · (False, motivo)"""
    uid = int(uid)

    def hacer(c):
        de = _ubicacion(c, uid)
        if not de[0]:
            raise ValueError(f"el personaje {uid} no está en ninguna cuenta (¿borrado? usá restaurar)")
        r = _libre(c, a_cuenta, a_ranura)
        a = (_cuenta_fila(c, a_cuenta)["username"], r)
        if de[1] == 1:
            if de[0] == a[0]:
                raise ValueError("el casillero 1 es la cuenta misma: no se cambia de lugar")
            if len(_ranuras(c, de[0])) > 1:
                raise ValueError(f"{uid} es el casillero 1 de {de[0]!r}, que tiene más personajes: usá FUSIONAR la cuenta")
            _bloquear(c, de[0], True)
        else:
            c.execute("DELETE FROM cuenta_personajes WHERE uid = ?", (uid,))
        c.execute("INSERT INTO cuenta_personajes (username, ranura, uid) VALUES (?, ?, ?)", (a[0], a[1], uid))
        _anotar(c, uid, de, a, motivo, actor)
        return a
    return _transaccion(hacer)


def fusionar_cuentas(origen, destino, actor=0):
    """TODOS los personajes de `origen` pasan a los casilleros libres de `destino` (el 1 primero), y `origen` queda
    bloqueada. -> (True, [(uid, ranura_vieja, ranura_nueva)]) · (False, motivo). `separar_cuenta(origen)` lo deshace."""
    def hacer(c):
        uo, ud = _cuenta_fila(c, origen), _cuenta_fila(c, destino)
        if not uo or not ud:
            raise ValueError("no existe " + (repr(origen) if not uo else repr(destino)))
        if uo["username"] == ud["username"]:
            raise ValueError("es la misma cuenta")
        ro, rd = _ranuras(c, origen), _ranuras(c, destino)
        if not ro or not rd:
            raise ValueError(f"{origen if not ro else destino!r} ya está fusionada")
        libres = [r for r in (2, 3, 4) if r not in rd]
        if len(ro) > len(libres):
            raise ValueError(f"{destino!r} tiene {len(libres)} casillero(s) libre(s) y {origen!r} trae {len(ro)} personaje(s)")
        hechos = []
        for (r_vieja, uid), r_nueva in zip(sorted(ro.items()), libres):
            if r_vieja != 1:
                c.execute("DELETE FROM cuenta_personajes WHERE uid = ?", (uid,))
            c.execute("INSERT INTO cuenta_personajes (username, ranura, uid) VALUES (?, ?, ?)", (ud["username"], r_nueva, uid))
            _anotar(c, uid, (uo["username"], r_vieja), (ud["username"], r_nueva), "fusionar", actor)
            hechos.append((uid, r_vieja, r_nueva))
        _bloquear(c, uo["username"], True)
        return hechos
    return _transaccion(hacer)


def separar_cuenta(origen, actor=0):
    """Deshace la fusión de `origen`: cada personaje que SALIÓ de ella vuelve a su casillero (esté donde esté ahora) y
    la cuenta se desbloquea. -> (True, [(uid, ranura)]) · (False, motivo)"""
    def hacer(c):
        uo = _cuenta_fila(c, origen)
        if not uo:
            raise ValueError(f"no existe {origen!r}")
        if not es_fusionada(uo["pass_hash"]):
            raise ValueError(f"{origen!r} no está fusionada")
        if int(uo["uid"]) < 0:                                # ★ 07-nov: su base pasó al 1 de otra (`pasar_a_casillero_1`)
            base = -int(uo["uid"])
            hoy = c.execute("SELECT username FROM users WHERE uid = ?", (base,)).fetchone()
            if hoy:
                raise ValueError(f"su personaje {base} es hoy el casillero 1 de {hoy['username']!r}: primero pasá otro "
                                 f"personaje al casillero 1 de {hoy['username']!r} (así {base} baja a un 2-4)")
            c.execute("UPDATE users SET uid = ? WHERE uid = ?", (base, -base))
            uo = _cuenta_fila(c, origen)
        usuario = uo["username"]
        # sólo los que se fueron por FUSIÓN o MUDANZA y siguen en un casillero 2-4 (no el que después pasó a ser el
        #   casillero 1 de una cuenta propia: `separar_a_cuenta_nueva`)
        salidas = c.execute("SELECT id, uid, de_ranura FROM movimientos_personajes WHERE de_cuenta = ? COLLATE BINARY "
                            "AND deshecho = 0 AND motivo IN ('fusionar', 'mover') ORDER BY id", (usuario,)).fetchall()
        ultima = {}
        for m in salidas:                                     # por personaje, su PRIMERA salida (de dónde era)
            if c.execute("SELECT 1 FROM cuenta_personajes WHERE uid = ?", (int(m["uid"]),)).fetchone():
                ultima.setdefault(int(m["uid"]), int(m["de_ranura"]))
        if int(uo["uid"]) not in ultima:
            ultima[int(uo["uid"])] = 1
        _bloquear(c, usuario, False)
        vueltos = []
        for uid, r in sorted(ultima.items(), key=lambda x: x[1]):
            ahora = _ubicacion(c, uid) if c.execute("SELECT 1 FROM cuenta_personajes WHERE uid = ?", (uid,)).fetchone() \
                else (None, 0)
            c.execute("DELETE FROM cuenta_personajes WHERE uid = ?", (uid,))
            if r != 1:
                if c.execute("SELECT 1 FROM cuenta_personajes WHERE username = ? COLLATE BINARY AND ranura = ?",
                             (usuario, r)).fetchone():
                    raise ValueError(f"el casillero {r} de {usuario!r} está ocupado")
                c.execute("INSERT INTO cuenta_personajes (username, ranura, uid) VALUES (?, ?, ?)", (usuario, r, uid))
            _anotar(c, uid, ahora, (usuario, r), "separar", actor)
            vueltos.append((uid, r))
        c.execute("UPDATE movimientos_personajes SET deshecho = 1 WHERE de_cuenta = ? COLLATE BINARY AND deshecho = 0 "
                  "AND motivo IN ('fusionar', 'mover')", (usuario,))
        return vueltos
    return _transaccion(hacer)


def pasar_a_casillero_1(uid, actor=0):
    """★ 07-nov (anonimo03: «como admin no puedo mover el slot o borrar el char base»). El personaje `uid` (casillero 2-4)
    pasa a ser el casillero 1 de SU cuenta, y el que era el 1 baja al casillero que él dejó. Así la base vieja queda
    en un 2-4 y se puede mudar o borrar como cualquiera.
    ⛔ El casillero 1 es `users.uid` = el usn con el que se entra (launcher, web, juego): cambia de personaje, la
      cuenta (usuario, clave, ban) es la misma. -> (True, (cuenta, ranura donde quedó la base vieja)) · (False, motivo)
    ⛔ `users.uid` es la CLAVE PRIMARIA: un uid es de UNA sola fila. El personaje que fue el casillero 1 de una cuenta
      FUSIONADA (jugadorX 6361, de `jugador8` bloqueada) sigue siendo dueño de esa fila.
    ★ anonimo03: «¿y si jugador8 queda con el número pero con un x-xxxxxx?» ⇒ la cuenta FUSIONADA (nadie entra con ella)
      se queda con su número DADO VUELTA (6361 → -6361): la marca de cuál era su base, y el 6361 libre. `separar_cuenta`
      se lo devuelve, y frena mientras su base sea el casillero 1 de otra cuenta. Una cuenta ACTIVA no se toca."""
    uid = int(uid)

    def hacer(c):
        de = _ubicacion(c, uid)
        if not de[0] or de[1] == 1:
            raise ValueError("sólo pasa al casillero 1 un personaje de un casillero 2-4")
        u = _cuenta_fila(c, de[0])
        if not u or es_fusionada(u["pass_hash"]):
            raise ValueError(f"la cuenta {de[0]!r} no existe o está fusionada")
        viejo = int(u["uid"])
        fila = c.execute("SELECT rowid FROM users WHERE username = ? COLLATE BINARY ORDER BY rowid DESC LIMIT 1",
                         (de[0],)).fetchone()[0]
        otra = c.execute("SELECT username, pass_hash FROM users WHERE uid = ? AND rowid != ?", (uid, fila)).fetchone()
        if otra:
            if not es_fusionada(otra["pass_hash"]):
                raise ValueError(f"{uid} es el casillero 1 de la cuenta ACTIVA {otra['username']!r}")
            if c.execute("SELECT 1 FROM users WHERE uid = ?", (-uid,)).fetchone():
                raise ValueError(f"el número {-uid} ya está tomado: no puedo guardar ahí el de {otra['username']!r}")
            c.execute("UPDATE users SET uid = ? WHERE uid = ?", (-uid, uid))   # la fusionada: su número dado vuelta
        c.execute("UPDATE users SET uid = ? WHERE rowid = ?", (uid, fila))
        c.execute("UPDATE cuenta_personajes SET uid = ? WHERE uid = ?", (viejo, uid))
        _anotar(c, uid, de, (de[0], 1), "casillero1", actor)
        _anotar(c, viejo, (de[0], 1), de, "casillero1", actor)
        return de
    return _transaccion(hacer)


def separar_a_cuenta_nueva(uid, usuario, pass_hash, actor=0):
    """Un personaje de un casillero 2-4 pasa a ser el casillero 1 de una cuenta NUEVA (usuario + clave propios).
    -> (True, usuario) · (False, motivo)"""
    uid, usuario = int(uid), (usuario or "").strip()

    def hacer(c):
        if not (3 <= len(usuario) <= 16) or not usuario.replace("_", "").isalnum():
            raise ValueError("el usuario: de 3 a 16 letras, números o _")
        if _cuenta_fila(c, usuario):
            raise ValueError(f"el usuario {usuario!r} ya existe")
        de = _ubicacion(c, uid)
        if not de[0] or de[1] == 1:
            raise ValueError("sólo se separa así un personaje de un casillero 2-4")
        if c.execute("SELECT 1 FROM users WHERE uid = ?", (uid,)).fetchone():
            raise ValueError(f"{uid} ya es el casillero 1 de una cuenta (fusionada): usá SEPARAR esa cuenta")
        c.execute("DELETE FROM cuenta_personajes WHERE uid = ?", (uid,))
        c.execute("INSERT INTO users (uid, username, pass_hash, reg_time) VALUES (?, ?, ?, ?)",
                  (uid, usuario, str(pass_hash).upper(), time.time()))
        _anotar(c, uid, de, (usuario, 1), "separar_nueva", actor)
        return usuario
    return _transaccion(hacer)


def restaurar_borrado(uid, a_cuenta, a_ranura=None, actor=0):
    """Un personaje «borrado» (`personajes_borrados`) vuelve a un casillero libre. -> (True, (cuenta, ranura))"""
    uid = int(uid)

    def hacer(c):
        b = c.execute("SELECT username, ranura FROM personajes_borrados WHERE uid = ?", (uid,)).fetchone()
        if not b:
            raise ValueError(f"{uid} no está entre los borrados")
        r = _libre(c, a_cuenta, a_ranura)
        a = (_cuenta_fila(c, a_cuenta)["username"], r)
        c.execute("INSERT INTO cuenta_personajes (username, ranura, uid) VALUES (?, ?, ?)", (a[0], a[1], uid))
        c.execute("DELETE FROM personajes_borrados WHERE uid = ?", (uid,))
        _anotar(c, uid, (b["username"], int(b["ranura"])), a, "restaurar", actor)
        return a
    return _transaccion(hacer)


def borrados(usuario=None):
    """Los personajes «borrados» (ocultos), de una cuenta o de todas: [{uid, cuenta, ranura, apodo, cuando}]."""
    with _lock:
        q = "SELECT uid, username, ranura, apodo, cuando FROM personajes_borrados"
        filas = conectar().execute(q + (" WHERE username = ? COLLATE BINARY" if usuario else "") + " ORDER BY cuando DESC",
                                   (usuario,) if usuario else ()).fetchall()
    return [{"uid": int(r["uid"]), "cuenta": r["username"], "ranura": int(r["ranura"]), "apodo": r["apodo"] or "",
             "cuando": r["cuando"]} for r in filas]


def movimientos(uid=None, cuenta=None, limite=50):
    """La bitácora de mudanzas (lo más nuevo primero)."""
    donde, args = [], []
    if uid is not None:
        donde.append("uid = ?"); args.append(int(uid))
    if cuenta:
        donde.append("(de_cuenta = ? COLLATE BINARY OR a_cuenta = ? COLLATE BINARY)"); args += [cuenta, cuenta]
    with _lock:
        filas = conectar().execute("SELECT * FROM movimientos_personajes" + (" WHERE " + " AND ".join(donde) if donde else "")
                                   + " ORDER BY id DESC LIMIT ?", (*args, int(limite))).fetchall()
    return [dict(r) for r in filas]


def ranuras_de_cuenta(usuario):
    """{ranura: uid} de los casilleros 2-4 de esa cuenta (el 1 es la cuenta misma)."""
    with _lock:
        return {int(r["ranura"]): int(r["uid"]) for r in conectar().execute(
            "SELECT ranura, uid FROM cuenta_personajes WHERE username = ? COLLATE BINARY", (usuario,))}


def ocultar_ranura(usuario, ranura, apodo):
    """«Borra» el personaje del casillero 2-4: su fila pasa a `personajes_borrados` y el casillero queda libre. El
    personaje NO se toca (sigue en `chars` con todo lo suyo): se recupera a mano. -> el uid, o None si no había."""
    with _lock:
        c = conectar()
        r = c.execute("SELECT uid FROM cuenta_personajes WHERE username = ? COLLATE BINARY AND ranura = ?",
                      (usuario, ranura)).fetchone()
        if not r:
            return None
        uid = int(r["uid"])
        c.execute("INSERT OR REPLACE INTO personajes_borrados (uid, username, ranura, apodo, cuando) "
                  "VALUES (?, ?, ?, ?, datetime('now', 'localtime'))", (uid, usuario, ranura, apodo))
        c.execute("DELETE FROM cuenta_personajes WHERE username = ? COLLATE BINARY AND ranura = ?", (usuario, ranura))
        c.commit()
        return uid


def reservar_ranura(usuario, ranura):
    """Un uid libre para ese casillero (mirando cuentas, personajes y reservas), anotado ya. Bajo el candado: dos
    pedidos a la vez no se llevan el mismo."""
    with _lock:
        c = conectar()
        r = c.execute("SELECT uid FROM cuenta_personajes WHERE username = ? COLLATE BINARY AND ranura = ?",
                      (usuario, ranura)).fetchone()
        if r:
            return int(r["uid"])
        tope = c.execute("SELECT MAX(m) FROM (SELECT MAX(uid) AS m FROM users UNION ALL SELECT MAX(uid) FROM chars "
                         "UNION ALL SELECT MAX(uid) FROM cuenta_personajes)").fetchone()[0] or 0
        uid = int(tope) + 1
        c.execute("INSERT INTO cuenta_personajes (username, ranura, uid) VALUES (?, ?, ?)", (usuario, ranura, uid))
        c.commit()
        return uid


def leer_todos():
    with _lock:
        c = conectar()
        return {str(r["uid"]): filas_a_char(c, r["uid"])
                for r in c.execute("SELECT uid FROM chars")}


# ★ "campo ausente" y "campo en 0" son LO MISMO para todos los consumidores, que leen con
#   `.get(campo, 0)`. La base no puede distinguirlos: un `leccion_max = 0` vuelve como ausente.
#   Sin esto, `guardar_todos` creía que TODOS los personajes habían cambiado y reescribía las 56
#   filas en cada guardado — o sea, justo el problema que veníamos a resolver.
_VACIOS = (0, "", [], {}, None, False)


def _norm(p):
    return {k: v for k, v in (p or {}).items()
            if not (v in _VACIOS or (k == "misiones_hechas" and not any(v)))}


def guardar_todos(d):
    """★ Escribe SOLO los que cambiaron. Ver el aviso de arriba sobre por qué importa."""
    with _lock:
        c = conectar()
        with c:
            for k, p in d.items():
                if not (str(k).isdigit() and isinstance(p, dict)):
                    continue
                uid = int(k)
                if _norm(filas_a_char(c, uid)) != _norm(p):
                    char_a_filas(c, uid, p)


def char_por_nick(nick):
    with _lock:
        c = conectar()
        f = c.execute("SELECT uid FROM chars WHERE lower(nickname)=lower(?)",
                      ((nick or "").strip(),)).fetchone()
        return filas_a_char(c, f["uid"]) if f else None


# ───────────────────────── AMIGOS ─────────────────────────
# La tabla `friends` está en el esquema desde el 2026-09-05 (copiada del CBT) y hasta hoy
# (2026-09-10) **no la tocaba ni una línea de código**. Estas cuatro funciones son las primeras.
#
# ★ La amistad se guarda **en las dos direcciones**, una fila por sentido. Es como lo hace el CBT
#   y es lo que el cliente espera: cada uno tiene SU lista, y borrar es simétrico.
# ⚠ Las SOLICITUDES pendientes no se guardan: viven sólo mientras los dos están conectados, igual
#   que en el CBT. Si el destino está offline, el cliente ya tiene un cartel para eso
#   ("no existe o está desconectado"). Persistirlas es una decisión aparte, no un olvido.

def uid_por_nick(nick):
    """El `uid` del que se llama así, o `None`.

    ⚠⚠ EXISTE POR UN BUG MÍO (2026-09-10). `char_por_nick()` devuelve el personaje **sin su
    `uid`**: sus claves son `nick, char_id, gender, exp, rcoin, parts, licencia, mission, …` y
    ninguna es `uid`. Yo porté la lógica del CBT —donde el row SÍ lo trae— y escribí
    `otro["uid"]`. Resultado: `KeyError('uid')` con cada solicitud de amistad real.
    ⇒ Si necesitás el uid, pedilo ACÁ. No lo busques adentro del personaje.
    """
    with _lock:
        c = conectar()
        f = c.execute("SELECT uid FROM chars WHERE lower(nickname)=lower(?)",
                      ((nick or "").strip(),)).fetchone()
        return int(f["uid"]) if f else None


def nicks_de(uids):
    """{uid: apodo} de MUCHOS de una sola consulta (29-sep, optimización para el VPS). Lo usa el
    `status.json`, que antes armaba el personaje ENTERO (13 consultas) de cada conectado cada 3 s
    sólo para leerle el apodo: con 300 conectados era el 23 % del CPU del server (`BANCO_VPS.md` §5)."""
    uids = [int(u) for u in uids]
    fuera = {}
    with _lock:
        c = conectar()
        for i in range(0, len(uids), 500):                    # el tope de `?` de SQLite viejo es 999
            parte = uids[i:i + 500]
            for f in c.execute(f"SELECT uid, nickname FROM chars WHERE uid IN ({','.join('?' * len(parte))})", parte):
                fuera[int(f["uid"])] = f["nickname"] or ""
    return fuera


def uids_por_nick(nick):
    """**TODOS** los uid que se llaman así. Casi siempre uno — pero no siempre.

    ⚠⚠ EL APODO NO ES ÚNICO. Medido el 2026-09-10 sobre la base local (4807 personajes):
        · 203 apodos repetidos, que afectan a 483 cuentas (el 10 %)
        · `jugador40` aparece 18 veces · `jugador9` y `jugador7` 8 · `asdasd` 6
        · el esquema declara `nickname TEXT NOT NULL` — **sin `UNIQUE`**
        · y el `FF04` (crear personaje) **no chequea** si el apodo ya existe: se siguen creando

    ⇒ `uid_por_nick()` devuelve **uno cualquiera** de los que coinciden. Para "mandale una
      solicitud a X" eso no alcanza: le llegaría a la persona equivocada. Quien necesite
      desambiguar tiene que pedir la lista entera y elegir con un criterio propio
      (ver `_resolver_destino` en `lobby_social.py`, que prefiere al que está CONECTADO).
    """
    with _lock:
        c = conectar()
        filas = c.execute("SELECT uid FROM chars WHERE lower(nickname)=lower(?) ORDER BY uid",
                          ((nick or "").strip(),)).fetchall()
        return [int(f["uid"]) for f in filas]


def amigos_de(uid):
    """Los personajes que uid tiene en su lista, en el orden en que los agregó.

    ★ Cada uno viene **con su `uid` adentro** — a diferencia de `char_por_nick()`, que no lo trae.
      Lo necesita el `FF42`, que manda `[u32 uid]` por amigo. Sin esto iban todos en CERO, que es
      un paquete bien formado y completamente inútil: el cliente no puede identificar a nadie.
    """
    with _lock:
        c = conectar()
        filas = c.execute("SELECT friend_uid FROM friends WHERE uid=? ORDER BY added_at, friend_uid",
                          (int(uid),)).fetchall()
        salida = []
        for f in filas:
            ch = filas_a_char(c, f["friend_uid"])
            if ch:                                   # un amigo sin personaje se saltea
                ch["uid"] = int(f["friend_uid"])     # ← el que faltaba
                salida.append(ch)
        return salida


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★ PAREJA (tabla `couples`, del CBT tal cual: `uid PRIMARY KEY, partner_uid, since`)
#   ⚠ `uid` es PRIMARY KEY ⇒ **una pareja por persona**, garantizado por el esquema y no por
#     nosotros. Y como se guardan las DOS filas (A→B y B→A), romper es borrar las dos.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def pareja_de(uid):
    """El uid de mi pareja, o `0` si estoy soltero."""
    with _lock:
        c = conectar()
        f = c.execute("SELECT partner_uid FROM couples WHERE uid=?", (int(uid),)).fetchone()
        return int(f["partner_uid"]) if f else 0


def pareja_desde(uid):
    """El `since` guardado (texto ISO), o `""`."""
    with _lock:
        c = conectar()
        f = c.execute("SELECT since FROM couples WHERE uid=?", (int(uid),)).fetchone()
        return str(f["since"] or "") if f else ""


def poner_pareja(uid, otro, cuando=None):
    """Casa a los dos, **en las dos direcciones y en una sola transacción**.

    ⚠ Las dos filas o ninguna: si se escribiera sólo una, uno de los dos quedaría "casado con
      alguien que está soltero", y ese estado no lo arregla nadie solo.
    """
    import datetime
    if int(uid) == int(otro):
        return False
    cuando = cuando or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        c = conectar()
        with c:
            c.execute("INSERT OR REPLACE INTO couples(uid, partner_uid, since) VALUES(?,?,?)",
                      (int(uid), int(otro), cuando))
            c.execute("INSERT OR REPLACE INTO couples(uid, partner_uid, since) VALUES(?,?,?)",
                      (int(otro), int(uid), cuando))
            # ★ Casamiento NUEVO = confesiones en blanco, y la primera vuelve a ser gratis (anonimo03,
            #   27-sep: *"si una pareja rompe y se casa de nuevo, la confesión debe reiniciarse;
            #   sólo no se reinicia si la pareja hizo cambio de anillo"*). El cambio de anillo NO
            #   pasa por acá (es `poner_anillo`), así que ése la conserva.
            c.execute("DELETE FROM confesiones WHERE uid IN (?,?)", (int(uid), int(otro)))
    return True


def romper_pareja(uid, cuando=None):
    """Deshace la pareja de `uid` **por los dos lados**. Devuelve el ex, o 0.

    ⛔⛔ ACÁ SE **BORRABA** LA FILA DEL ANILLO, y con eso se borraba el recuerdo (2026-09-12).
      El motivo original era correcto —*"al romper deja de estar en uso, si no el enlace de la sala
      se sigue dibujando"*— pero la forma no: **el `DELETE` también se lleva la fecha de
      casamiento**, que es justo lo que el ítem de recuerdo tiene que mostrar.

    ★ La tabla YA tenía la columna para esto desde el esquema del CBT: `estado` (0 sin usar · 1 en
      uso · **2 roto**) y `hasta`. Estaban previstas y sin usar. ⇒ Se marca, no se borra.
    ★ `anillo_de_pareja` filtra por `estado=1`, así que el enlace de la sala deja de dibujarse
      igual que antes: el efecto buscado se conserva **sin perder el dato**.
    """
    import time as _t
    cuando = int(cuando if cuando is not None else _t.time())
    with _lock:
        c = conectar()
        f = c.execute("SELECT partner_uid FROM couples WHERE uid=?", (int(uid),)).fetchone()
        if not f:
            return 0
        ex = int(f["partner_uid"])
        with c:
            c.execute("DELETE FROM couples WHERE uid=? OR uid=?", (int(uid), ex))
            c.execute("UPDATE anillos SET estado=2, hasta=? WHERE uid IN (?,?) AND estado=1",
                      (cuando, int(uid), ex))
            # ★ Al romper, las confesiones de los dos se van (la del casamiento siguiente se escribe
            #   de nuevo, y gratis). Ver `poner_pareja`, que también las limpia.
            c.execute("DELETE FROM confesiones WHERE uid IN (?,?)", (int(uid), ex))
    return ex


def poner_anillo(uid, item_id, partner, cuando=None):
    """Guarda **qué anillo lleva puesto** esta pareja, en los dos lados.

    ★ Hace falta para el enlace de la sala: el cliente dibuja los corazones, el fondo del slot y
      el efecto **él solo**, pero necesita saber QUÉ anillo es (`ring.txt` tiene el `SlotBackId` y
      el `RoomFx` de cada uno). Sin este dato el enlace se hace con ítem 0 y sale vacío.
    ⚠ Se guarda el **Index** (el item_id), no el ChargeId: por el cable viaja el ChargeId, pero el
      que dibuja quiere el Index. La traducción es `catalogo.anillo_por_charge`.

    ★★ `desde` = **la fecha del casamiento**, y no es decorativa: es la que el cliente imprime en
      el ítem de la mochila (*"Registrarse como pareja con %s"* + `%d/%d/%d`). Antes se insertaba
      sin ella y quedaba en 0 ⇒ 1/1/1970.
    ⚠ El `DELETE` de acá sólo se lleva los `estado=1` (un anillo anterior de ESTA pareja que se
      esté reemplazando). Los `estado=2` —los recuerdos de relaciones pasadas— **no se tocan**.
    ★★ 07-nov (anonimo03: *"iban 29 días de casados y al cambiar de anillo se les reinició el
      contador"*): un CAMBIO de anillo pasaba por acá con la hora de ahora, y como el `DELETE` se
      llevaba la fila vigente, el «Aniversario» del perfil volvía a «1 días». En prod lo sufrían 19
      parejas. ⇒ Si ESTA pareja ya tiene un anillo puesto, se hereda su `desde`: cambiar de anillo
      no es casarse de nuevo. (Al romper, la fila pasa a `estado=2`, así que un re-casamiento con
      la misma persona sí arranca de cero.)
    """
    import time as _t
    with _lock:
        c = conectar()
        with c:
            if cuando is None:
                _f = c.execute("SELECT MIN(desde) FROM anillos WHERE estado=1 AND desde>0 AND "
                               "((uid=? AND partner_uid=?) OR (uid=? AND partner_uid=?))",
                               (int(uid), int(partner), int(partner), int(uid))).fetchone()
                cuando = _f[0] if _f and _f[0] else _t.time()
            cuando = int(cuando)
            c.execute("DELETE FROM anillos WHERE uid IN (?,?) AND estado=1", (int(uid), int(partner)))
            for _a, _b in ((uid, partner), (partner, uid)):
                c.execute("INSERT INTO anillos(uid, item_id, estado, partner_uid, desde) "
                          "VALUES(?,?,1,?,?)", (int(_a), int(item_id), int(_b), cuando))
    return True


def poner_confesion(uid, texto):
    """Guarda la confesión de pareja de `uid` (la pisa: hay una sola por jugador)."""
    import time as _t
    with _lock:
        c = conectar()
        with c:
            c.execute("INSERT INTO confesiones(uid, texto, cuando) VALUES(?,?,?) "
                      "ON CONFLICT(uid) DO UPDATE SET texto=excluded.texto, cuando=excluded.cuando",
                      (int(uid), str(texto), int(_t.time())))
    return True


def hay_confesion(uid):
    """¿Ya escribió una alguna vez? (la PRIMERA es gratis; las siguientes gastan el cupón 219)"""
    with _lock:
        c = conectar()
        return c.execute("SELECT 1 FROM confesiones WHERE uid=?", (int(uid),)).fetchone() is not None


def confesion_de(uid):
    """La confesión de pareja de `uid`, o ''."""
    with _lock:
        c = conectar()
        f = c.execute("SELECT texto FROM confesiones WHERE uid=?", (int(uid),)).fetchone()
        return str(f["texto"] or "") if f else ""


def anillo_de_pareja(uid):
    """El item_id del anillo que lleva puesto `uid` con su pareja, o 0."""
    with _lock:
        c = conectar()
        f = c.execute("SELECT item_id FROM anillos WHERE uid=? AND estado=1 "
                      "ORDER BY id DESC LIMIT 1", (int(uid),)).fetchone()
        return int(f["item_id"]) if f else 0


def borrar_recuerdo(uid, item_id):
    """Tira el/los recuerdo(s) **ROTOS** de ese anillo. Devuelve cuántas filas se fueron.

    ★ Es la **única salida del tercer estado**: el anillo roto no se va solo (lo dejó anotado el
      CBT, y el cliente lo pide con el `FF47`).
    ⚠⚠ **SÓLO `estado=2`.** Un `estado=1` es una pareja VIVA: borrarlo apagaría el enlace de la
      sala y le borraría la fecha de casamiento a dos personas que siguen juntas. El cliente no
      ofrece ese botón, pero el server no puede confiar en eso.
    ⚠ Y sólo las de **este** uid: el recuerdo del otro es suyo y lo tira él si quiere.
    """
    with _lock:
        c = conectar()
        with c:
            n = c.execute("DELETE FROM anillos WHERE uid=? AND item_id=? AND estado=2",
                          (int(uid), int(item_id))).rowcount
    return int(n or 0)


def anillos_de(uid):
    """**Todos** los anillos de `uid` — el puesto y los recuerdos —, del más viejo al más nuevo.

    Cada uno: `{item_id, estado, partner_uid, desde, hasta}`. Es lo que alimenta el `FF45`, que
    manda **un registro por relación**: el vigente con categoría `0x41` y los rotos con otra.

    ★ El orden es por `id` ascendente a propósito: el índice de cada registro dentro del `FF45` es
      el que el cliente usa para enganchar el ítem de la mochila (`0x4924C0`), así que tiene que
      ser **estable entre dos pedidos**. Ordenar por fecha lo haría saltar si dos comparten día.
    """
    with _lock:
        c = conectar()
        return [{"item_id": int(f["item_id"]), "estado": int(f["estado"]),
                 "partner_uid": int(f["partner_uid"] or 0),
                 "desde": int(f["desde"] or 0), "hasta": int(f["hasta"] or 0)}
                for f in c.execute(
                    "SELECT item_id, estado, partner_uid, desde, hasta FROM anillos "
                    "WHERE uid=? ORDER BY id ASC", (int(uid),))]


def son_amigos(uid, otro):
    with _lock:
        c = conectar()
        return c.execute("SELECT 1 FROM friends WHERE uid=? AND friend_uid=?",
                         (int(uid), int(otro))).fetchone() is not None


def agregar_amigo(uid, otro):
    """Alta en UN sentido (idempotente). Para el alta mutua se llama dos veces."""
    if int(uid) == int(otro):
        return
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO friends (uid, friend_uid, added_at) VALUES (?,?,?)",
                  (int(uid), int(otro), time.strftime("%Y-%m-%d %H:%M:%S")))
        c.commit()


def borrar_amigo(uid, otro):
    with _lock:
        c = conectar()
        c.execute("DELETE FROM friends WHERE uid=? AND friend_uid=?", (int(uid), int(otro)))
        c.commit()


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★ EL AMIGO DEL ALMA — la Joya de la Amistad (`FF40` sub 0x3B). Ver `lobby_alma.py`.
#
#  ⚠ Es SIMÉTRICO y se guardan LAS DOS FILAS, igual que `couples`. Guardar una sola obligaría a
#    consultar con un `OR` en todos lados, y el día que alguien se olvide del `OR` el amigo del
#    alma existe para uno y no para el otro. Ya pasó con la pareja y está anotado allá.
# ══════════════════════════════════════════════════════════════════════════════════════════════
def almas_de(uid):
    """`[{"otro_uid", "joya", "desde"}]` — los amigos del alma de ese uid."""
    with _lock:
        c = conectar()
        return [{"otro_uid": r[0], "joya": r[1], "desde": r[2]}
                for r in c.execute("SELECT otro_uid, joya, desde FROM almas "
                                   "WHERE uid=? ORDER BY desde", (int(uid),)).fetchall()]


def son_almas(uid, otro):
    with _lock:
        c = conectar()
        return c.execute("SELECT 1 FROM almas WHERE uid=? AND otro_uid=?",
                         (int(uid), int(otro))).fetchone() is not None


def agregar_alma(uid, otro, joya=0):
    """Alta MUTUA (idempotente). ⚠ Las dos filas o ninguna: ver la nota de arriba."""
    if int(uid) == int(otro):
        return
    _ahora = int(time.time())
    with _lock:
        c = conectar()
        c.executemany("INSERT OR IGNORE INTO almas (uid, otro_uid, joya, desde) VALUES (?,?,?,?)",
                      [(int(uid), int(otro), int(joya), _ahora),
                       (int(otro), int(uid), int(joya), _ahora)])
        c.commit()


def poner_joya_alma(uid, otro, joya):
    """Cambia la joya de esa amistad, **en las dos filas**.

    ⚠ Las dos o ninguna: si sólo se cambiara una, cada uno vería una joya distinta en su panel y
      el síntoma sería *"a veces se ve una y a veces otra"*, según quién mire.
    """
    with _lock:
        c = conectar()
        c.execute("UPDATE almas SET joya=? WHERE (uid=? AND otro_uid=?) OR (uid=? AND otro_uid=?)",
                  (int(joya), int(uid), int(otro), int(otro), int(uid)))
        c.commit()


def borrar_alma(uid, otro):
    """Baja MUTUA. ⚠ Romper de un solo lado deja al otro con un amigo del alma fantasma."""
    with _lock:
        c = conectar()
        c.execute("DELETE FROM almas WHERE (uid=? AND otro_uid=?) OR (uid=? AND otro_uid=?)",
                  (int(uid), int(otro), int(otro), int(uid)))
        c.commit()


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★ EL RÉCORD Y LAS MEDALLAS (24-sep). Ver `documentacion/MEDALLAS_Y_RECORD.md`.
# ══════════════════════════════════════════════════════════════════════════════════════════════
RECORD_CAMPOS = ("ganadas", "perdidas", "empates", "pd97", "allcombo", "exp_max", "rcoin_max",
                 "medalla")


def record_de(uid):
    """`{campo: valor}` del récord de ese uid; todo en 0 si todavía no jugó."""
    with _lock:
        c = conectar()
        r = c.execute("SELECT " + ", ".join(RECORD_CAMPOS) + " FROM record WHERE uid=?",
                      (int(uid),)).fetchone()
    return {k: int((r[k] if r else 0) or 0) for k in RECORD_CAMPOS}


def sumar_record(uid, sumas=None, maximos=None, poner=None):
    """Suma (`sumas`), sube si es mayor (`maximos`) y pisa (`poner`), en UNA transacción.
    Devuelve el récord antes y después: `(viejo, nuevo)`."""
    for d in (sumas, maximos, poner):
        if d and set(d) - set(RECORD_CAMPOS):
            raise ValueError(f"campo de récord desconocido: {set(d) - set(RECORD_CAMPOS)}")
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO record (uid) VALUES (?)", (int(uid),))
        r = c.execute("SELECT " + ", ".join(RECORD_CAMPOS) + " FROM record WHERE uid=?",
                      (int(uid),)).fetchone()
        viejo = {k: int(r[k] or 0) for k in RECORD_CAMPOS}
        nuevo = dict(viejo)
        for k, v in (sumas or {}).items():
            nuevo[k] = max(0, nuevo[k] + int(v))
        for k, v in (maximos or {}).items():
            nuevo[k] = max(nuevo[k], int(v))
        for k, v in (poner or {}).items():
            nuevo[k] = max(0, int(v))
        c.execute("UPDATE record SET " + ", ".join(f"{k}=?" for k in RECORD_CAMPOS) + " WHERE uid=?",
                  [nuevo[k] for k in RECORD_CAMPOS] + [int(uid)])
        c.commit()
    return viejo, nuevo


def puesto_por_exp(uid):
    """El puesto de ese personaje en el server por EXP total (1 = el que más tiene; 0 = no existe).
    Es el «Ranking» del perfil (`FF77`): el cliente escribe `%dº` y «más de 1000º» si pasa de 1000."""
    with _lock:
        c = conectar()
        r = c.execute("SELECT exp FROM chars WHERE uid=?", (int(uid),)).fetchone()
        if not r:
            return 0
        return 1 + c.execute("SELECT COUNT(*) FROM chars WHERE exp > ?", (int(r[0] or 0),)).fetchone()[0]


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★ LOS CÍRCULOS (24-sep). Las reglas viven en `circulos.py`; acá sólo se lee y se escribe.
#     El líder es `circulos.lider_uid` — la columna `rango` sólo separa Jefe de Miembro (así da
#     igual si una fila vieja del CBT trae 0/1 en vez de los bytes del cliente).
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _circulo(c, r):
    return {"id": int(r["id"]), "nombre": r["nombre"], "aviso": r["aviso"] or "",
            "lider_uid": int(r["lider_uid"] or 0), "creado_at": r["creado_at"] or ""}


def circulo_de(uid):
    """El círculo de ese uid + su `rango` y `desde`, o `None` si no está en ninguno."""
    with _lock:
        c = conectar()
        r = c.execute("SELECT k.*, m.rango, m.desde FROM circulo_miembros m "
                      "JOIN circulos k ON k.id = m.circulo_id WHERE m.uid=?", (int(uid),)).fetchone()
        if not r:
            return None
        d = _circulo(c, r)
        d["rango"], d["desde"] = int(r["rango"] or 0), r["desde"] or ""
        return d


def circulo_por_nombre(nombre):
    """Sin distinguir mayúsculas: «Prueba» y «PRUEBA» son el mismo círculo."""
    with _lock:
        c = conectar()
        r = c.execute("SELECT * FROM circulos WHERE nombre = ? COLLATE NOCASE",
                      (str(nombre),)).fetchone()
        return _circulo(c, r) if r else None


def circulo_por_id(cid):
    with _lock:
        c = conectar()
        r = c.execute("SELECT * FROM circulos WHERE id=?", (int(cid),)).fetchone()
        return _circulo(c, r) if r else None


def miembros_circulo(cid):
    """`[{uid, nick, exp, rango, desde}]`, por antigüedad (el primero que entró, primero)."""
    with _lock:
        c = conectar()
        return [{"uid": int(r["uid"]), "nick": r["nickname"] or "", "exp": int(r["exp"] or 0),
                 "rango": int(r["rango"] or 0), "desde": r["desde"] or ""}
                for r in c.execute("SELECT m.uid, m.rango, m.desde, ch.nickname, ch.exp "
                                   "FROM circulo_miembros m LEFT JOIN chars ch ON ch.uid = m.uid "
                                   "WHERE m.circulo_id=? ORDER BY m.desde, m.rowid", (int(cid),))]


def crear_circulo(uid, nombre, ahora):
    """Crea el círculo con `uid` de líder. Devuelve el id, o `None` si el nombre ya existe o si
    `uid` ya está en otro (se vuelve a mirar ADENTRO de la transacción: dos pedidos a la vez)."""
    with _lock:
        c = conectar()
        if c.execute("SELECT 1 FROM circulo_miembros WHERE uid=?", (int(uid),)).fetchone():
            return None
        if c.execute("SELECT 1 FROM circulos WHERE nombre = ? COLLATE NOCASE", (str(nombre),)).fetchone():
            return None
        cur = c.execute("INSERT INTO circulos (nombre, aviso, lider_uid, creado_at) VALUES (?, '', ?, ?)",
                        (str(nombre), int(uid), ahora))
        cid = int(cur.lastrowid)
        c.execute("INSERT INTO circulo_miembros (uid, circulo_id, rango, desde) VALUES (?, ?, 0, ?)",
                  (int(uid), cid, ahora))
        c.execute("DELETE FROM circulo_solicitudes WHERE uid=?", (int(uid),))
        c.commit()
        return cid


def agregar_miembro(uid, cid, ahora, tope):
    """Mete a `uid` en el círculo `cid` y borra su solicitud. `False` si ya está en uno o si el
    círculo llegó al `tope` (mirado adentro de la transacción)."""
    with _lock:
        c = conectar()
        if c.execute("SELECT 1 FROM circulo_miembros WHERE uid=?", (int(uid),)).fetchone():
            return False
        n = c.execute("SELECT COUNT(*) FROM circulo_miembros WHERE circulo_id=?", (int(cid),)).fetchone()[0]
        if n >= int(tope):
            return False
        c.execute("INSERT INTO circulo_miembros (uid, circulo_id, rango, desde) VALUES (?, ?, 0, ?)",
                  (int(uid), int(cid), ahora))
        c.execute("DELETE FROM circulo_solicitudes WHERE uid=?", (int(uid),))
        c.commit()
        return True


def quitar_miembro(uid):
    with _lock:
        c = conectar()
        c.execute("DELETE FROM circulo_miembros WHERE uid=?", (int(uid),))
        c.commit()


def poner_rango_circulo(uid, rango):
    with _lock:
        c = conectar()
        c.execute("UPDATE circulo_miembros SET rango=? WHERE uid=?", (int(rango), int(uid)))
        c.commit()


def poner_lider_circulo(cid, uid):
    """El nuevo líder deja de ser Jefe (su `rango` vuelve a 0: el líder lo dice `lider_uid`)."""
    with _lock:
        c = conectar()
        c.execute("UPDATE circulos SET lider_uid=? WHERE id=?", (int(uid), int(cid)))
        c.execute("UPDATE circulo_miembros SET rango=0 WHERE uid=?", (int(uid),))
        c.commit()


def poner_aviso_circulo(cid, aviso):
    with _lock:
        c = conectar()
        c.execute("UPDATE circulos SET aviso=? WHERE id=?", (str(aviso), int(cid)))
        c.commit()


def borrar_circulo(cid):
    """Lo borra con sus miembros y sus solicitudes. Devuelve los uid que eran miembros."""
    with _lock:
        c = conectar()
        uids = [int(r[0]) for r in c.execute("SELECT uid FROM circulo_miembros WHERE circulo_id=?",
                                             (int(cid),))]
        c.execute("DELETE FROM circulo_miembros WHERE circulo_id=?", (int(cid),))
        c.execute("DELETE FROM circulo_solicitudes WHERE circulo_id=?", (int(cid),))
        c.execute("DELETE FROM circulo_economia WHERE circulo_id=?", (int(cid),))
        c.execute("DELETE FROM circulo_donaciones WHERE circulo_id=?", (int(cid),))
        c.execute("DELETE FROM circulo_items WHERE circulo_id=?", (int(cid),))
        c.execute("DELETE FROM circulos WHERE id=?", (int(cid),))
        c.commit()
        return uids


def pedir_circulo(uid, cid, ahora):
    """Anota el pedido de `uid` de entrar a `cid` (pisa uno anterior a otro círculo)."""
    with _lock:
        c = conectar()
        c.execute("INSERT OR REPLACE INTO circulo_solicitudes (uid, circulo_id, fecha) VALUES (?, ?, ?)",
                  (int(uid), int(cid), ahora))
        c.commit()


def solicitud_de(uid):
    """El id del círculo al que `uid` pidió entrar, o 0."""
    with _lock:
        r = conectar().execute("SELECT circulo_id FROM circulo_solicitudes WHERE uid=?",
                               (int(uid),)).fetchone()
        return int(r[0]) if r else 0


def solicitudes_circulo(cid):
    """`[{uid, nick, exp, fecha}]` de los que pidieron entrar, el más viejo primero."""
    with _lock:
        c = conectar()
        return [{"uid": int(r["uid"]), "nick": r["nickname"] or "", "exp": int(r["exp"] or 0),
                 "fecha": r["fecha"] or ""}
                for r in c.execute("SELECT s.uid, s.fecha, ch.nickname, ch.exp FROM circulo_solicitudes s "
                                   "LEFT JOIN chars ch ON ch.uid = s.uid WHERE s.circulo_id=? "
                                   "ORDER BY s.fecha, s.rowid", (int(cid),))]


def borrar_solicitud(uid):
    with _lock:
        c = conectar()
        c.execute("DELETE FROM circulo_solicitudes WHERE uid=?", (int(uid),))
        c.commit()


ECONOMIA_CAMPOS = ("nivel", "exp", "dinero", "marca")


def economia_circulo(cid):
    """`{nivel, exp, dinero, marca}` del círculo; nivel 1 y lo demás en 0 si nunca se tocó."""
    with _lock:
        r = conectar().execute("SELECT " + ", ".join(ECONOMIA_CAMPOS) + " FROM circulo_economia "
                               "WHERE circulo_id=?", (int(cid),)).fetchone()
    if not r:
        return {"nivel": 1, "exp": 0, "dinero": 0, "marca": 0}
    return {k: int(r[k] or 0) for k in ECONOMIA_CAMPOS} | {"nivel": max(1, int(r["nivel"] or 1))}


def poner_economia_circulo(cid, **campos):
    """Pisa los campos dados, en UNA transacción (crea la fila si no existe)."""
    if set(campos) - set(ECONOMIA_CAMPOS):
        raise ValueError(f"campo de economía desconocido: {set(campos) - set(ECONOMIA_CAMPOS)}")
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO circulo_economia (circulo_id) VALUES (?)", (int(cid),))
        for k, v in campos.items():
            c.execute(f"UPDATE circulo_economia SET {k}=? WHERE circulo_id=?", (int(v), int(cid)))
        c.commit()


def donar_a_circulo(uid, cid, monto, tope_de, ahora, exp_bruta=None, dinero=None):
    """Acredita una donación YA COBRADA, en UNA transacción (dos a la vez no se pisan el tope):
    EXP += min(exp_bruta, TOPE - EXP) (0 en el nivel 10), dinero += `dinero`, y anota los Rcoin a
    nombre de `uid`. Sin `exp_bruta`/`dinero` es la cuenta original del cliente (`0x5E3B70`): 1:1 y
    monto // 100. -> `(exp_ganada, dinero_ganado)`."""
    monto = int(monto)
    exp_bruta = monto if exp_bruta is None else int(exp_bruta)
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO circulo_economia (circulo_id) VALUES (?)", (int(cid),))
        r = c.execute("SELECT nivel, exp FROM circulo_economia WHERE circulo_id=?", (int(cid),)).fetchone()
        nivel, exp = max(1, int(r["nivel"] or 1)), int(r["exp"] or 0)
        ganada = 0 if nivel >= 10 else max(0, min(exp_bruta, int(tope_de(nivel)) - exp))
        dinero = monto // 100 if dinero is None else int(dinero)
        c.execute("UPDATE circulo_economia SET exp=exp+?, dinero=dinero+? WHERE circulo_id=?",
                  (ganada, dinero, int(cid)))
        c.execute("INSERT OR IGNORE INTO circulo_donaciones (uid, circulo_id) VALUES (?, ?)", (int(uid), int(cid)))
        c.execute("UPDATE circulo_donaciones SET total=total+?, ultima=? WHERE uid=? AND circulo_id=?",
                  (monto, ahora, int(uid), int(cid)))
        c.commit()
        return ganada, dinero


ITEM_CAMPOS = ("clave", "circulo_id", "item", "vence", "estado", "x", "y", "z", "padre", "enganche")


def items_circulo(cid):
    """El inventario del círculo, por clave."""
    with _lock:
        return [{k: int(r[k] or 0) for k in ITEM_CAMPOS} for r in conectar().execute(
            "SELECT * FROM circulo_items WHERE circulo_id=? ORDER BY clave", (int(cid),))]


def comprar_item_circulo(cid, item, precio, dias, uid, ahora_ts, ahora, clave=0):
    """Compra (clave 0) o EXTIENDE (clave del ítem) pagando con el DINERO del círculo, en UNA
    transacción. `dias` 0 = permanente. -> `(dinero que queda, fila)` o `(dinero, None)` si no
    alcanza o la clave no es de ese ítem en ese círculo."""
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO circulo_economia (circulo_id) VALUES (?)", (int(cid),))
        dinero = int(c.execute("SELECT dinero FROM circulo_economia WHERE circulo_id=?",
                               (int(cid),)).fetchone()[0] or 0)
        if dinero < int(precio):
            return dinero, None
        seg = int(dias) * 86400
        if clave:
            r = c.execute("SELECT vence FROM circulo_items WHERE clave=? AND circulo_id=? AND item=?",
                          (int(clave), int(cid), int(item))).fetchone()
            if not r or not int(r[0] or 0) or not seg:           # no existe, o es permanente
                return dinero, None
            c.execute("UPDATE circulo_items SET vence=? WHERE clave=?",
                      (max(int(r[0]), int(ahora_ts)) + seg, int(clave)))
        else:
            cur = c.execute("INSERT INTO circulo_items (circulo_id, item, vence, comprado_por, fecha) "
                            "VALUES (?, ?, ?, ?, ?)", (int(cid), int(item),
                                                       int(ahora_ts) + seg if seg else 0, int(uid), ahora))
            clave = cur.lastrowid
        c.execute("UPDATE circulo_economia SET dinero=dinero-? WHERE circulo_id=?", (int(precio), int(cid)))
        c.commit()
        r = c.execute("SELECT * FROM circulo_items WHERE clave=?", (int(clave),)).fetchone()
        return dinero - int(precio), {k: int(r[k] or 0) for k in ITEM_CAMPOS}


def acomodar_items_circulo(cid, filas):
    """Guarda cómo quedó cada ítem en la sala (el «guardar» del arreglo, `FFD8`): estado ('0'+n
    colocado / 'X' guardado), x, y, z, enganche y padre, TAL CUAL los manda el cliente. Sólo toca
    ítems de ESE círculo con esa clave y ese Index. -> las filas actualizadas."""
    with _lock:
        c = conectar()
        claves = []
        for f in filas:
            cur = c.execute("UPDATE circulo_items SET estado=?, x=?, y=?, z=?, enganche=?, padre=? "
                            "WHERE clave=? AND circulo_id=? AND item=?",
                            (int(f["estado"]), int(f["x"]), int(f["y"]), int(f["z"]), int(f["enganche"]),
                             int(f["padre"]), int(f["clave"]), int(cid), int(f["item"])))
            if cur.rowcount:
                claves.append(int(f["clave"]))
        c.commit()
        return [{k: int(r[k] or 0) for k in ITEM_CAMPOS} for r in (
            c.execute("SELECT * FROM circulo_items WHERE clave=?", (k,)).fetchone() for k in claves)]


def subir_nivel_circulo(cid, costo_de, tope_de, regalos, vence_ts, ahora):
    """Sube UN nivel, en UNA transacción: exige nivel < 10, EXP en el tope y dinero >= el costo;
    cobra, suma el nivel y mete los `regalos` (Index) al inventario con vencimiento `vence_ts`.
    -> `(nuevo_nivel, dinero que queda, filas de regalo)` o `(None, motivo, [])`."""
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO circulo_economia (circulo_id) VALUES (?)", (int(cid),))
        r = c.execute("SELECT nivel, exp, dinero FROM circulo_economia WHERE circulo_id=?", (int(cid),)).fetchone()
        nivel, exp, dinero = max(1, int(r["nivel"] or 1)), int(r["exp"] or 0), int(r["dinero"] or 0)
        if nivel >= 10:
            return None, "ya es nivel 10", []
        if exp < int(tope_de(nivel)):
            return None, f"la EXP no llegó al tope ({exp}/{tope_de(nivel)})", []
        costo = int(costo_de(nivel))
        if dinero < costo:
            return None, f"falta dinero ({dinero}/{costo})", []
        c.execute("UPDATE circulo_economia SET nivel=nivel+1, dinero=dinero-? WHERE circulo_id=?", (costo, int(cid)))
        claves = []
        for it in regalos:
            claves.append(c.execute("INSERT INTO circulo_items (circulo_id, item, vence, comprado_por, fecha) "
                                    "VALUES (?, ?, ?, 0, ?)", (int(cid), int(it), int(vence_ts), ahora)).lastrowid)
        c.commit()
        filas = [{k: int(x[k] or 0) for k in ITEM_CAMPOS} for x in (
            c.execute("SELECT * FROM circulo_items WHERE clave=?", (k,)).fetchone() for k in claves)]
        return nivel + 1, dinero - costo, filas


def poner_marca_circulo(cid, marca, item_logo, item_fondo):
    """Registra la marca GASTANDO un logo y un fondo del inventario (circle.csv #13/#62: «se
    disminuirá en una unidad»), en UNA transacción. -> las claves borradas, o `None` si falta alguno."""
    with _lock:
        c = conectar()
        claves = []
        for it in (int(item_logo), int(item_fondo)):
            r = c.execute("SELECT clave FROM circulo_items WHERE circulo_id=? AND item=? ORDER BY clave LIMIT 1",
                          (int(cid), it)).fetchone()
            if not r:
                c.rollback()
                return None
            claves.append(int(r[0]))
        for k in claves:
            c.execute("DELETE FROM circulo_items WHERE clave=?", (k,))
        c.execute("INSERT OR IGNORE INTO circulo_economia (circulo_id) VALUES (?)", (int(cid),))
        c.execute("UPDATE circulo_economia SET marca=? WHERE circulo_id=?", (int(marca), int(cid)))
        c.commit()
        return claves


def insignia_circulo(uid):
    """`(marca, nivel)` del círculo de `uid` en UNA consulta (para la tarjeta de la sala), o `(0, 0)`."""
    with _lock:
        r = conectar().execute("SELECT COALESCE(e.marca, 0), COALESCE(e.nivel, 1) FROM circulo_miembros m "
                               "LEFT JOIN circulo_economia e ON e.circulo_id = m.circulo_id "
                               "WHERE m.uid=?", (int(uid),)).fetchone()
    return (int(r[0] or 0), max(1, int(r[1] or 1))) if r else (0, 0)


def estilo_chat(uid):
    """`(item del globo, item del crayón)` tildados por `uid` (0 = ninguno)."""
    with _lock:
        r = conectar().execute("SELECT globo, crayon FROM estilo_chat WHERE uid=?", (int(uid),)).fetchone()
    return (int(r[0] or 0), int(r[1] or 0)) if r else (0, 0)


def poner_estilo_chat(uid, campo, item):
    """Pone (o saca, con 0) el globo o el crayón activo de `uid`."""
    if campo not in ("globo", "crayon"):
        raise ValueError(campo)
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO estilo_chat (uid) VALUES (?)", (int(uid),))
        c.execute(f"UPDATE estilo_chat SET {campo}=? WHERE uid=?", (int(item), int(uid)))
        c.commit()


def lapiz_apodo(uid):
    """El lápiz del apodo tildado por `uid` (0 = ninguno)."""
    with _lock:
        r = conectar().execute("SELECT lapiz FROM color_apodo WHERE uid=?", (int(uid),)).fetchone()
    return int(r[0] or 0) if r else 0


def poner_lapiz_apodo(uid, item):
    with _lock:
        c = conectar()
        c.execute("INSERT OR REPLACE INTO color_apodo (uid, lapiz) VALUES (?, ?)", (int(uid), int(item)))
        c.commit()


def lapiz_circulo(uid):
    """El crayón de círculo tildado por `uid` (0 = ninguno)."""
    with _lock:
        r = conectar().execute("SELECT lapiz FROM color_circulo WHERE uid=?", (int(uid),)).fetchone()
    return int(r[0] or 0) if r else 0


def poner_lapiz_circulo(uid, item):
    with _lock:
        c = conectar()
        c.execute("INSERT OR REPLACE INTO color_circulo (uid, lapiz) VALUES (?, ?)", (int(uid), int(item)))
        c.commit()


def presentacion_de(uid):
    """`(marca, edad, texto)` de la tabla `presentacion`, o `None` si nunca se guardó nada."""
    with _lock:
        r = conectar().execute("SELECT marca, edad, texto FROM presentacion WHERE uid=?",
                               (int(uid),)).fetchone()
    return (r[0] or "", int(r[1] or 0), r[2] or "") if r else None


def poner_presentacion(uid, marca, edad, texto, ahora):
    with _lock:
        c = conectar()
        c.execute("INSERT OR REPLACE INTO presentacion (uid, marca, edad, texto, fecha) VALUES (?,?,?,?,?)",
                  (int(uid), str(marca or ""), int(edad or 0), str(texto or ""), int(ahora)))
        c.commit()


def tira_anuncios():
    """Los anuncios de la tira del lobby, en el orden en que se cargaron."""
    with _lock:
        return [{"id": r[0], "texto": r[1], "hasta": r[2], "activo": r[3], "quien": r[4], "creado": r[5]}
                for r in conectar().execute(
                    "SELECT id, texto, hasta, activo, quien, creado FROM tira_anuncios ORDER BY id")]


def agregar_tira(texto, hasta=0, quien="", ahora=0):
    with _lock:
        c = conectar()
        cur = c.execute("INSERT INTO tira_anuncios (texto, hasta, activo, quien, creado) VALUES (?,?,1,?,?)",
                        (str(texto), int(hasta or 0), str(quien or ""), int(ahora)))
        c.commit()
        return cur.lastrowid


def editar_tira(id_, texto, hasta=0, activo=1):
    with _lock:
        c = conectar()
        cur = c.execute("UPDATE tira_anuncios SET texto=?, hasta=?, activo=? WHERE id=?",
                        (str(texto), int(hasta or 0), 1 if activo else 0, int(id_)))
        c.commit()
        return cur.rowcount


def quitar_tira(id_=None):
    """Borra un anuncio (o TODOS con `id_=None`). Devuelve cuántos borró."""
    with _lock:
        c = conectar()
        cur = (c.execute("DELETE FROM tira_anuncios") if id_ is None
               else c.execute("DELETE FROM tira_anuncios WHERE id=?", (int(id_),)))
        c.commit()
        return cur.rowcount


# ───────────────────────── LOS AVISOS DE REGALO PENDIENTES (regalo.py) ─────────────────────────

def aviso_regalo(uid, de, item, rcoin=0):
    import time as _t
    with _lock:
        c = conectar()
        c.execute("INSERT INTO regalos_avisos (uid, de, item, rcoin, cuando) VALUES (?, ?, ?, ?, ?)",
                  (int(uid), str(de), int(item), int(rcoin), _t.time()))
        c.commit()


def sacar_avisos_regalo(uid, tope=20):
    """Los avisos pendientes de `uid` (los más viejos primero, hasta `tope`) y los BORRA. -> [(de, item, rcoin)]."""
    with _lock:
        c = conectar()
        filas = c.execute("SELECT rowid, de, item, rcoin FROM regalos_avisos WHERE uid=? ORDER BY rowid LIMIT ?",
                          (int(uid), int(tope))).fetchall()
        c.executemany("DELETE FROM regalos_avisos WHERE rowid=?", [(f[0],) for f in filas])
        c.commit()
        return [(f[1], int(f[2]), int(f[3])) for f in filas]


# ───────────────────────── «MIS PREFERIDOS» DE LA TIENDA (preferidos.py) ─────────────────────────

def preferidos_de(uid):
    with _lock:
        return [int(r[0]) for r in conectar().execute(
            "SELECT item FROM preferidos_tienda WHERE uid=? ORDER BY rowid", (int(uid),))]


def agregar_preferido(uid, item):
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO preferidos_tienda (uid, item) VALUES (?, ?)", (int(uid), int(item)))
        c.commit()


def sacar_preferido(uid, item):
    with _lock:
        c = conectar()
        cur = c.execute("DELETE FROM preferidos_tienda WHERE uid=? AND item=?", (int(uid), int(item)))
        c.commit()
        return cur.rowcount == 1


# ───────────────────────── LOS SETS DEL ARMARIO (conjuntos.py) ─────────────────────────

def conjuntos_de(uid):
    """`{conjunto: [ítems]}` de `uid`."""
    with _lock:
        return {int(r["conjunto"]): [int(x) for x in r["items"].split(",") if x]
                for r in conectar().execute("SELECT conjunto, items FROM conjuntos WHERE uid=?", (int(uid),))}


def guardar_conjunto(uid, conjunto, items):
    import time as _t
    with _lock:
        c = conectar()
        c.execute("INSERT OR REPLACE INTO conjuntos (uid, conjunto, items, cuando) VALUES (?, ?, ?, ?)",
                  (int(uid), int(conjunto), ",".join(str(int(x)) for x in items), _t.time()))
        c.commit()


# ───────────────────────── «¿QUIÉN TE INVITÓ?» (referido.py) ─────────────────────────

def referido_pendiente(uid, cuando):
    """Creó su personaje: el cliente le abre la ventana. Una vez por cuenta (si ya existe, no se toca)."""
    with _lock:
        c = conectar()
        c.execute("INSERT OR IGNORE INTO referidos (uid, creado) VALUES (?, ?)", (int(uid), float(cuando)))
        c.commit()


def referido_de(uid):
    """La fila de `uid` como dict, o None si nunca tuvo la ventana."""
    with _lock:
        f = conectar().execute("SELECT * FROM referidos WHERE uid=?", (int(uid),)).fetchone()
        return dict(f) if f else None


def referido_omitir(uid):
    """Apretó «Omitir»: ya no puede registrar a nadie. -> True si estaba pendiente."""
    import time as _t
    with _lock:
        c = conectar()
        cur = c.execute("UPDATE referidos SET invitador=0, cuando=? WHERE uid=? AND invitador IS NULL",
                        (_t.time(), int(uid)))
        c.commit()
        return cur.rowcount == 1


def referido_registrar(uid, invitador, apodo, rcoin, ip):
    """Lo registra SÓLO si seguía pendiente (el `WHERE` es el candado: dos respuestas no pagan dos veces)."""
    import time as _t
    with _lock:
        c = conectar()
        cur = c.execute("UPDATE referidos SET invitador=?, apodo=?, cuando=?, rcoin=?, ip=? "
                        "WHERE uid=? AND invitador IS NULL",
                        (int(invitador), str(apodo), _t.time(), int(rcoin), str(ip or ""), int(uid)))
        c.commit()
        return cur.rowcount == 1


def preferidas_de(uid):
    """Las canciones PREFERIDAS de `uid`, en el orden en que se marcaron."""
    with _lock:
        return [int(r[0]) for r in conectar().execute(
            "SELECT cancion FROM preferidas WHERE uid=? ORDER BY rowid", (int(uid),))]


def cambiar_preferidas(uid, agregar=(), quitar=()):
    with _lock:
        c = conectar()
        c.executemany("INSERT OR IGNORE INTO preferidas (uid, cancion) VALUES (?, ?)",
                      [(int(uid), int(x)) for x in agregar])
        c.executemany("DELETE FROM preferidas WHERE uid=? AND cancion=?",
                      [(int(uid), int(x)) for x in quitar])
        c.commit()


def record_cancion_de(uid, cancion):
    """`{veces, mejor_combo, mejor_pd, allcombo}` de `uid` en esa canción, o None si nunca la terminó."""
    with _lock:
        r = conectar().execute("SELECT veces, mejor_combo, mejor_pd, allcombo FROM record_cancion "
                               "WHERE uid=? AND cancion=?", (int(uid), int(cancion))).fetchone()
    return ({"veces": int(r[0] or 0), "mejor_combo": int(r[1] or 0), "mejor_pd": int(r[2] or 0),
             "allcombo": bool(r[3])} if r else None)


def anotar_record_cancion(uid, cancion, combo, pd_x1000, allcombo, dia, ahora, frame=0):
    """Suma UNA carrera terminada: el récord de (uid, canción) y la jugada del día de la canción.
    ★ Si es récord NUEVO (más precisión, o la misma con más combo), anota CUÁNDO y en qué TIEMPO llegó
      (`record_mejor`, TOP 5 RANK)."""
    with _lock:
        c = conectar()
        viejo = c.execute("SELECT mejor_pd, mejor_combo FROM record_cancion WHERE uid=? AND cancion=?",
                          (int(uid), int(cancion))).fetchone()
        if (viejo is None or int(pd_x1000) > int(viejo[0] or 0)
                or (int(pd_x1000) == int(viejo[0] or 0) and int(combo) > int(viejo[1] or 0))):
            c.execute("INSERT OR REPLACE INTO record_mejor (uid, cancion, fecha, frame) VALUES (?, ?, ?, ?)",
                      (int(uid), int(cancion), int(ahora), max(0, int(frame or 0))))
        c.execute("""INSERT INTO record_cancion (uid, cancion, veces, mejor_combo, mejor_pd, allcombo, ultima)
                     VALUES (?, ?, 1, ?, ?, ?, ?)
                     ON CONFLICT(uid, cancion) DO UPDATE SET
                        veces = veces + 1,
                        mejor_combo = MAX(mejor_combo, excluded.mejor_combo),
                        mejor_pd = MAX(mejor_pd, excluded.mejor_pd),
                        allcombo = MAX(allcombo, excluded.allcombo),
                        ultima = excluded.ultima""",
                  (int(uid), int(cancion), int(combo), int(pd_x1000), 1 if allcombo else 0, int(ahora)))
        c.execute("""INSERT INTO jugadas_dia (dia, cancion, veces) VALUES (?, ?, 1)
                     ON CONFLICT(dia, cancion) DO UPDATE SET veces = veces + 1""", (str(dia), int(cancion)))
        c.commit()


# ★ TOP 5 RANK (09-oct): el orden del ranking de una canción. La precisión manda; a igual precisión, más
#   combo; y a igual todo, el que llegó ANTES. `uid` desempata lo que quede (que el orden sea total: el puesto
#   propio se cuenta con la misma regla).
_TOP_DESDE = """FROM record_cancion r JOIN chars c ON c.uid = r.uid
                LEFT JOIN record_mejor f ON f.uid = r.uid AND f.cancion = r.cancion
                WHERE r.cancion = ? AND r.mejor_pd > 0"""


def top_cancion(cancion, n, uid=0):
    """`(filas, mio)` del ranking de una canción. `filas` = los `n` mejores, cada uno
    `{uid, nick, combo, pd, fecha, allcombo, frame}` (pd = precisión ×1000; frame = el tiempo de llegada, 0 = no
    se sabe); `mio` = `(puesto, fila)` de `uid`, o None si nunca la terminó."""
    cols = ("r.uid, c.nickname, r.mejor_combo, r.mejor_pd, COALESCE(f.fecha, r.ultima, 0) AS fe, r.allcombo, "
            "COALESCE(f.frame, 0)")
    orden = "ORDER BY r.mejor_pd DESC, r.mejor_combo DESC, fe ASC, r.uid ASC"
    with _lock:
        c = conectar()
        filas = [_fila_top(f) for f in c.execute(f"SELECT {cols} {_TOP_DESDE} {orden} LIMIT ?",
                                                  (int(cancion), int(n)))]
        mio = None
        if uid:
            f = c.execute(f"SELECT {cols} {_TOP_DESDE} AND r.uid = ?", (int(cancion), int(uid))).fetchone()
            if f:
                yo = _fila_top(f)
                antes = c.execute(
                    f"""SELECT COUNT(*) {_TOP_DESDE} AND (r.mejor_pd > ? OR (r.mejor_pd = ? AND (r.mejor_combo > ?
                        OR (r.mejor_combo = ? AND (COALESCE(f.fecha, r.ultima, 0) < ?
                        OR (COALESCE(f.fecha, r.ultima, 0) = ? AND r.uid < ?))))))""",
                    (int(cancion), yo["pd"], yo["pd"], yo["combo"], yo["combo"], yo["fecha"], yo["fecha"],
                     yo["uid"])).fetchone()[0]
                mio = (int(antes) + 1, yo)
    return filas, mio


def _fila_top(f):
    return {"uid": int(f[0]), "nick": f[1] or "", "combo": int(f[2] or 0), "pd": int(f[3] or 0),
            "fecha": int(f[4] or 0), "allcombo": bool(f[5]), "frame": int(f[6] or 0)}


def jugadas_por_cancion(desde_dia, hasta_dia):
    """`{canción: veces}` sumando los días `desde_dia..hasta_dia` (incluidos, 'AAAA-MM-DD')."""
    with _lock:
        return {int(r[0]): int(r[1]) for r in conectar().execute(
            "SELECT cancion, SUM(veces) FROM jugadas_dia WHERE dia BETWEEN ? AND ? GROUP BY cancion",
            (str(desde_dia), str(hasta_dia)))}


def puesto_circulo(cid):
    """El puesto del círculo por EXP entre todos (1 = el de más EXP). Sin fila de economía = 0 EXP."""
    with _lock:
        c = conectar()
        r = c.execute("SELECT exp FROM circulo_economia WHERE circulo_id=?", (int(cid),)).fetchone()
        mia = int(r[0] or 0) if r else 0
        n = c.execute("SELECT COUNT(*) FROM circulo_economia e JOIN circulos k ON k.id = e.circulo_id "
                      "WHERE e.exp > ?", (mia,)).fetchone()[0]
    return 1 + int(n)


def donaciones_circulo(cid):
    """`{uid: total donado}` de los que donaron a `cid`."""
    with _lock:
        return {int(r[0]): int(r[1] or 0) for r in conectar().execute(
            "SELECT uid, total FROM circulo_donaciones WHERE circulo_id=?", (int(cid),))}


def cuenta_de(usuario):
    """LA cuenta de ese `username` —exacto, respetando mayúsculas— con la forma de `leer_cuentas()[u]`,
    o `None`. ★ 29-sep (optimización para el VPS, `BANCO_VPS.md` §5): cada login armaba el diccionario
    de las 5.400 cuentas para mirar UNA; cuando se cae el server y vuelven todos juntos, eso pesa.
    ⚠ Tiene que dar LO MISMO que `leer_cuentas().get(u)`:
      · `COLLATE BINARY`: exacto aunque la tabla viniera con otra intercalación (ver la nota de abajo:
        `Junior` y `junior` son dos cuentas distintas);
      · si hubiera dos filas iguales, el diccionario se quedaba con la ÚLTIMA: por eso `rowid DESC`."""
    with _lock:
        r = conectar().execute("SELECT uid,username,pass_hash,reg_time FROM users WHERE username = ? COLLATE BINARY "
                               "ORDER BY rowid DESC LIMIT 1", (usuario,)).fetchone()
    return ({"usn": r["uid"], "pass": r["pass_hash"], "creada": r["reg_time"] or 0, "username": r["username"]}
            if r else None)


def leer_cuentas():
    """`{username: {usn, pass, creada, username}}` — **la clave respeta las mayúsculas**.

    ⛔⛔ ACÁ HUBO UN BUG QUE TAPABA A 1.866 CUENTAS (2026-09-05), y la historia importa:
      `basedatos.cuenta_verificar` buscaba con `.lower()` y acá se devolvía el `username` **crudo**
      ⇒ **toda cuenta con una mayúscula quedaba fuera**: el `.get()` no la encontraba y contestaba
      `None`, que el server lee como "clave incorrecta".

      ★ Por qué nadie lo vio: `cuenta_crear` bajaba a minúsculas **antes de guardar**, así que toda
        cuenta nacida en nuestro server era minúscula y entraba. El bug sólo mordía a cuentas que
        vinieran de AFUERA — y mordió de golpe al importar las del CBT: **1.866 de 4.802 (38%)**.
        Era una regresión de la mudanza a SQLite (los `cuentas.json` ya guardaban la clave abajo).

    ★★★ Y SE ARREGLÓ HACIENDO EL LOGIN **SENSIBLE A MAYÚSCULAS**, como el CBT — no al revés.
      El motivo no es de estilo: en el CBT `Junior` y `junior` son **dos cuentas distintas**, y hay
      **60 pares así, con 122 cuentas y 71 de ellas jugando en serio**. Bajar todo a minúsculas
      las fusiona y **borra una de cada par en silencio**. Comparar exacto es lo que ya hace el
      CBT (`SELECT … WHERE username=?`), o sea que cada jugador entra escribiendo lo de siempre.
      ⚠ El costo asumido: quien se equivoque de mayúscula no entra. Es como funciona hoy allá.
    """
    with _lock:
        return {r["username"]: {"usn": r["uid"], "pass": r["pass_hash"],
                                "creada": r["reg_time"] or 0,
                                "username": r["username"]}
                for r in conectar().execute("SELECT uid,username,pass_hash,reg_time FROM users")}


def guardar_cuentas(d):
    with _lock:
        c = conectar()
        with c:
            for usuario, v in d.items():
                # ★ el nombre REAL (con mayúsculas) si viene en el valor; si no, la clave. Así una
                #   cuenta importada no pierde su forma al reescribirse, y una creada acá —que ya
                #   nace en minúsculas— sigue igual.
                c.execute("INSERT OR REPLACE INTO users (uid,username,pass_hash,reg_time) "
                          "VALUES (?,?,?,?)",
                          (int(v["usn"]), str(v.get("username") or usuario),
                           str(v.get("pass", "")), str(v.get("creada", ""))))


def sembrar_desde_json():
    """Si la base está vacía y los JSON existen, se migra sola. Así nadie se encuentra con un
    server sin cuentas por haber olvidado correr el migrador."""
    with _lock:
        c = conectar()
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return False
    # ⚠ Los JSON de este proyecto se renombraron a `*.json.migrado-20260905` justo para que nadie
    #   los edite creyendo que el server los lee. Esta siembra queda para el caso de alguien que
    #   llegue con los archivos originales.
    cu_p = os.path.join(RAIZ, "cuentas.json")
    ch_p = os.path.join(RAIZ, "chars_db.json")
    if not (os.path.isfile(cu_p) and os.path.isfile(ch_p)):
        return False
    cu = json.load(io.open(cu_p, encoding="utf-8"))
    ch = json.load(io.open(ch_p, encoding="utf-8"))
    guardar_cuentas(cu)
    guardar_todos({k: v for k, v in ch.items() if str(k).isdigit() and isinstance(v, dict)})
    log("DB", f"★ base vacía: migrados {len(cu)} cuentas y {len(ch)} personajes desde los JSON")
    return True
