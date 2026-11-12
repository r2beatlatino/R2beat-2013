# -*- coding: utf-8 -*-
"""cupon — «NUEVO · Ingresar cupón» del lobby (`FF158`): el jugador escribe un código y se lleva su premio.

★ 15-oct, anonimo03: «empezar aquí, con cupón» · «necesito en mi panel web una sección de admin para generar cupones,
  cantidad de usos, fecha de expiración, o generar cupones para pack de campanas, o piezas de ropa». Mapa del cliente:
  `documentacion/LOBBY_CUPON_MISION_BOTONES.md` §1 · doc: `documentacion/CUPON.md` · prueba: `pruebas/probar_cupon.py`
  · el panel: `panel_admin.py` (`/api/admin/cupones…`) + `web/src/pages/admin/cupones.astro`.

CÓMO LO ARMÓ EL JUEGO (todo del exe 2013, sin parches)
  · El botón flotante y la ventana son del cliente y salen SIEMPRE (no dependen del server). OK manda
      C→S `FF158 [u32 usn][u32 largo][texto]`  (máx. 12 letras; puede llegar VACÍO)
    y cierra la ventana. ⛔ Hasta hoy caía en «SIN handler»: en prod, 84 intentos sin respuesta (29-sep → 11-oct),
    casi todos `DULCE` / `TRUCO`.
  · La respuesta S→C `FF158 [u8 resultado]` (handler `0x5DD570`, tabla de saltos `0x5DD654`):
      0 = nada (el OK: el premio lo avisa otro paquete) · 2/3 = «El código de cupón no existe» (str#821) ·
      4 = «El cupón es inválido» (#823) · 5 = «El cupón está vencido» (#824) · 7 = «El código ya fue registrado»
      (#822) · 8 = «Ya tiene este ítem» (#68) · 1/6 = «coupon error : N» crudo (no se usan).
  · El premio: el `FFCE` (`CmdAddItem`, el handler escribe «Get Coupon Item : %u») — `regalo.dar_item` con `de=""`
    = el popup amarillo «¡Felicitaciones! Premios de Evento han llegado» con el ícono y el nombre. El Rcoin: con
    `db_add_rcoin`, el cliente pide su saldo solo (`FFAB`) y le sale el «recibiste X Rcoin».

LAS REGLAS (del server)
  · Los cupones viven en la base del juego (`datos.db`): `cupones` (el código y lo que da) y `cupones_usados` (quién
    canjeó qué). Las crea ESTE módulo (como la API del panel: no se toca `esquema.py`). Se cargan desde el panel.
  · Un cupón da una LISTA de ítems (cada uno con días y cantidad: ropa suelta, un set, un pack de campanas…) y/o Rcoin.
  · El texto se compara NORMALIZADO: mayúsculas, sólo letras y números, sin tildes (`-Dulce ` = `DULCE`).
  · Una vez por cuenta; `usos` = el tope ENTRE TODOS (0 = sin tope); `desde` / `vence`; `activo`.
  · Contestar SIEMPRE (el cliente dejó registrada la espera): ante cualquier error, «inválido».
  · El usn es el de la conexión (`st.usn`), no el del paquete. Tope de intentos por minuto y por cuenta.
"""
import json
import secrets
import struct
import threading
import time
import unicodedata
from datetime import datetime

from . import almacen
from .registro import log

OK, NO_EXISTE, INVALIDO, VENCIDO, YA_REGISTRADO, YA_TIENE = 0, 2, 4, 5, 7, 8
TEXTO = {OK: "OK", NO_EXISTE: "no existe", INVALIDO: "inválido", VENCIDO: "vencido",
         YA_REGISTRADO: "ya registrado", YA_TIENE: "ya tiene el ítem"}

LARGO_MAX = 12                   # la caja de texto del juego (`[caja+0xC0] = 12`)
INTENTOS_POR_MINUTO = 8          # más que esto en 60 s -> «inválido» sin mirar el código
PREMIOS_MAX = 10
GENERAR_MAX = 1000
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # sin 0/O ni 1/I: se dictan y se copian a mano

_intentos = {}                   # usn -> [tiempos de los últimos intentos]
_canje_lock = threading.Lock()
_tablas_ok = set()               # las conexiones (por hilo) que ya vieron el CREATE

TABLAS = """
CREATE TABLE IF NOT EXISTS cupones (
    codigo TEXT PRIMARY KEY,          -- normalizado (lo que se compara)
    premios TEXT NOT NULL DEFAULT '[]', -- json [{item, dias, cant}]
    rcoin INTEGER NOT NULL DEFAULT 0,
    usos INTEGER NOT NULL DEFAULT 0,  -- tope entre todos; 0 = sin tope
    desde REAL, vence REAL,           -- epoch o NULL
    activo INTEGER NOT NULL DEFAULT 1,
    lote TEXT, nota TEXT,
    creado REAL NOT NULL, creador TEXT);
CREATE TABLE IF NOT EXISTS cupones_usados (
    uid INTEGER NOT NULL, codigo TEXT NOT NULL, cuando REAL NOT NULL, PRIMARY KEY (uid, codigo));
CREATE INDEX IF NOT EXISTS cupones_usados_codigo ON cupones_usados (codigo);
"""


def _con():
    """La conexión del hilo a `datos.db`, con las tablas del cupón. ⚠ Llamar con `almacen._lock` tomado."""
    c = almacen.conectar()
    if id(c) not in _tablas_ok:
        c.executescript(TABLAS)
        _tablas_ok.add(id(c))
    return c


# ── el código ─────────────────────────────────────────────────────────────────────────────────────

def normalizar(texto):
    """`-Dulce ` -> `DULCE`: mayúsculas, sin tildes, sólo letras y números (la ñ queda como N)."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.upper() if c.isascii() and c.isalnum())


def leer_ff158(data):
    """C→S `[u32 usn][u32 largo][texto]` -> el texto (cp1252), o None si no cierra."""
    b = bytes(data or b"")
    if len(b) < 8:
        return None
    n = struct.unpack_from("<I", b, 4)[0]
    if n > 64 or 8 + n > len(b):
        return None
    return b[8:8 + n].decode("cp1252", "replace")


def fecha(s):
    """'2026-10-31', '2026-10-31 23:59' o '2026-10-31T23:59' (hora del server) -> epoch, o None si viene vacía.
    Una fecha sola vale hasta el final de ese día. ⛔ ValueError si no se entiende."""
    if s in (None, ""):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace("T", " ")
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(t, f).timestamp() + (86399 if f == "%Y-%m-%d" else 0)
        except ValueError:
            continue
    raise ValueError(f"fecha que no entiendo: {s!r} (va AAAA-MM-DD o AAAA-MM-DD HH:MM)")


# ── la regla de un cupón ──────────────────────────────────────────────────────────────────────────

DURACION_TIENDA = {"P7": 7, "P30": 30, "P365": 365, "PI": 0}     # los plazos de la ropa en `shop_lt` (PI = permanente)
#   ★ 06-nov: + P365 (los «Rostro …» de (159) se venden por un año). Sin él el cupón los tomaba «por unidad» y les
#     ponía dias 0 = PERMANENTE.


def duraciones(iid):
    """Los plazos con que la tienda vende ese ítem, en días (0 = permanente): [7, 30, 0] para la ropa; [] si no."""
    from . import shop_catalog
    durs = (shop_catalog.get(iid) or {}).get("durations") or {}
    return [DURACION_TIENDA[k] for k in ("P7", "P30", "P365", "PI") if k in durs]


def por_unidades(iid):
    """¿Se da por UNIDADES (campanas, megáfonos y sus packs: se gastan, no vencen) y no por plazo?
    anonimo03 (15-oct): «si fuera un pack de campanas, ¿qué duración elijo?». La tienda lo dice: la ropa se vende
    `P7`/`P30`/`PI`; lo que se gasta, `PN` (por unidad) o `P` (el pack, una vez)."""
    from . import shop_catalog
    from .catalogo import desempacar_pack, tiene_cargas
    return tiene_cargas(iid) or desempacar_pack(iid)[1] > 0 or (not duraciones(iid) and not shop_catalog.es_set(iid))


def armar_regla(d):
    """Lo que manda el panel -> la regla validada {premios, rcoin, usos, desde, vence, activo, nota}.
    ⛔ ValueError con el motivo, en criollo, si algo no cierra."""
    from . import shop_catalog
    premios = []
    for p in (d.get("premios") or [])[:PREMIOS_MAX + 1]:
        iid = shop_catalog.normalize_id(int(p.get("item") or 0)) if str(p.get("item") or "").strip().isdigit() else None
        if iid is None:
            raise ValueError(f"El ítem {p.get('item')!r} no está en el catálogo.")
        dias, cant = int(p.get("dias") or 0), max(1, min(int(p.get("cant") or 1), 999))
        if por_unidades(iid):
            dias = 0                                       # se gasta de a una: no vence (la tienda lo vende «PN»/«P»)
        else:
            cant = 1                                       # ropa y sets: una prenda, por 7 / 30 días o permanente
            vale = duraciones(iid)
            if vale and dias not in vale:
                nombre = (shop_catalog.get(iid) or {}).get("name", iid)
                raise ValueError(f"«{nombre}» se da por {' / '.join('permanente' if x == 0 else f'{x} días' for x in vale)}.")
        premios.append({"item": int(iid), "dias": dias, "cant": cant})
    if len(premios) > PREMIOS_MAX:
        raise ValueError(f"Como mucho {PREMIOS_MAX} ítems por cupón.")
    rcoin = max(0, int(d.get("rcoin") or 0))
    # ★ 15-oct (anonimo03: «que el Rcoin del cupón sólo tenga las cantidades que el juego tiene con cartel e ícono»): los
    #   montos de las cajitas de nivel (`iconos_rcoin`); con otro, el cartel salía sin imagen.
    if rcoin and rcoin not in iconos_rcoin():
        raise ValueError("El Rcoin va en los montos con ícono: " + ", ".join(f"{x:,}".replace(",", ".") for x in iconos_rcoin()) + ".")
    if not premios and not rcoin:
        raise ValueError("El cupón no da nada: poné al menos un ítem o Rcoin.")
    desde, vence = fecha(d.get("desde")), fecha(d.get("vence"))
    if desde and vence and vence <= desde:
        raise ValueError("El vencimiento es antes del comienzo.")
    return {"premios": premios, "rcoin": rcoin, "usos": max(0, int(d.get("usos") or 0)), "desde": desde,
            "vence": vence, "activo": 1 if d.get("activo", True) else 0, "nota": str(d.get("nota") or "")[:200]}


def _fila(r, usados=None):
    return {"codigo": r["codigo"], "premios": json.loads(r["premios"] or "[]"), "rcoin": int(r["rcoin"]),
            "usos": int(r["usos"]), "desde": r["desde"], "vence": r["vence"], "activo": bool(r["activo"]),
            "lote": r["lote"], "nota": r["nota"] or "", "creado": r["creado"], "creador": r["creador"] or "",
            "usados": int(usados if usados is not None else 0)}


def regla(codigo):
    """El cupón por su código (normalizado o no), o None."""
    k = normalizar(codigo)
    with almacen._lock:
        r = _con().execute("SELECT * FROM cupones WHERE codigo=?", (k,)).fetchone() if k else None
    return _fila(r) if r else None


# ── el panel: crear, generar, listar, apagar, borrar ──────────────────────────────────────────────

def crear(codigo, d, creador=""):
    """Un cupón con nombre (DULCE). -> la fila. ⛔ ValueError si el código no sirve o ya existe."""
    k = normalizar(codigo)
    if not k:
        raise ValueError("Falta el código.")
    if len(k) > LARGO_MAX:
        raise ValueError(f"El código tiene {len(k)} letras y la caja del juego acepta {LARGO_MAX}.")
    r = armar_regla(d)
    with almacen._lock:
        c = _con()
        if c.execute("SELECT 1 FROM cupones WHERE codigo=?", (k,)).fetchone():
            raise ValueError(f"Ya existe el cupón {k}.")
        c.execute("INSERT INTO cupones (codigo, premios, rcoin, usos, desde, vence, activo, lote, nota, creado, creador) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)",
                  (k, json.dumps(r["premios"]), r["rcoin"], r["usos"], r["desde"], r["vence"], r["activo"],
                   r["nota"], time.time(), str(creador)))
        c.commit()
    return regla(k)


def generar(cantidad, d, prefijo="", largo=10, creador=""):
    """`cantidad` códigos AL AZAR (de un uso cada uno, salvo que `d` diga otro `usos`), todos del mismo lote.
    -> {lote, codigos}. Para repartir de a uno (streamers, sorteos)."""
    cantidad = int(cantidad or 0)
    if not 1 <= cantidad <= GENERAR_MAX:
        raise ValueError(f"Se generan de 1 a {GENERAR_MAX} por vez.")
    pre = normalizar(prefijo)
    largo = max(6, min(int(largo or 10), LARGO_MAX))
    if len(pre) > largo - 4:
        raise ValueError(f"El prefijo es muy largo: tienen que quedar al menos 4 letras al azar en {largo}.")
    d = dict(d)
    d.setdefault("usos", 1)
    r = armar_regla(d)
    lote = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    hechos = []
    with almacen._lock:
        c = _con()
        while len(hechos) < cantidad:
            k = pre + "".join(secrets.choice(ALFABETO) for _ in range(largo - len(pre)))
            if c.execute("SELECT 1 FROM cupones WHERE codigo=?", (k,)).fetchone():
                continue
            c.execute("INSERT INTO cupones (codigo, premios, rcoin, usos, desde, vence, activo, lote, nota, creado, creador) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (k, json.dumps(r["premios"]), r["rcoin"], r["usos"], r["desde"], r["vence"], r["activo"],
                       lote, r["nota"], time.time(), str(creador)))
            hechos.append(k)
        c.commit()
    return {"lote": lote, "codigos": hechos}


def listar(q="", lote=None, tope=500):
    """Los cupones (los más nuevos primero) con cuántas veces se canjearon, y el resumen de los lotes."""
    k = normalizar(q)
    with almacen._lock:
        c = _con()
        donde, args = [], []
        if k:
            donde.append("c.codigo LIKE ?")
            args.append(f"%{k}%")
        if lote:
            donde.append("c.lote = ?")
            args.append(str(lote))
        filas = c.execute("SELECT c.*, (SELECT COUNT(*) FROM cupones_usados u WHERE u.codigo = c.codigo) AS n FROM cupones c "
                          + (("WHERE " + " AND ".join(donde)) if donde else "") + " ORDER BY c.creado DESC LIMIT ?",
                          (*args, int(tope))).fetchall()
        lotes = c.execute("SELECT c.lote, COUNT(*) AS codigos, MIN(c.creado) AS creado, "
                          "SUM((SELECT COUNT(*) FROM cupones_usados u WHERE u.codigo = c.codigo)) AS canjes "
                          "FROM cupones c WHERE c.lote IS NOT NULL GROUP BY c.lote ORDER BY creado DESC").fetchall()
    from . import shop_catalog
    out = [_fila(r, r["n"]) for r in filas]
    for f in out:
        for p in f["premios"]:
            p["nombre"] = (shop_catalog.get(p["item"]) or {}).get("name", "")
    return {"cupones": out, "rcoin_con_icono": list(iconos_rcoin()),
            "lotes": [{"lote": r["lote"], "codigos": int(r["codigos"]), "canjes": int(r["canjes"] or 0), "creado": r["creado"]}
                      for r in lotes]}


def cambiar(codigos, activo=None, borrar=False):
    """Prender / apagar / borrar uno o varios cupones. Borrar también borra sus canjes. -> cuántos tocó."""
    ks = [normalizar(x) for x in (codigos or []) if normalizar(x)]
    if not ks:
        return 0
    with almacen._lock:
        c = _con()
        marcas = ",".join("?" * len(ks))
        if borrar:
            n = c.execute(f"DELETE FROM cupones WHERE codigo IN ({marcas})", ks).rowcount
            c.execute(f"DELETE FROM cupones_usados WHERE codigo IN ({marcas})", ks)
        else:
            n = c.execute(f"UPDATE cupones SET activo=? WHERE codigo IN ({marcas})", [1 if activo else 0, *ks]).rowcount
        c.commit()
    return n


def canjes(codigo, tope=500):
    """Quién canjeó este cupón y cuándo (el más nuevo primero)."""
    from .basedatos import db_get_char
    k = normalizar(codigo)
    with almacen._lock:
        filas = _con().execute("SELECT uid, cuando FROM cupones_usados WHERE codigo=? ORDER BY cuando DESC LIMIT ?",
                               (k, int(tope))).fetchall()
    return [{"uid": int(r["uid"]), "apodo": (db_get_char(int(r["uid"])) or {}).get("nick", ""), "cuando": r["cuando"]}
            for r in filas]


# ── el canje ──────────────────────────────────────────────────────────────────────────────────────

def _tiene_permanente(uid, item):
    """¿Ya tiene ese ítem para siempre? (lo que va por cargas, los packs y los sets no cuentan)."""
    from . import shop_catalog
    from .basedatos import db_get_char
    from .catalogo import desempacar_pack, tiene_cargas
    if tiene_cargas(item) or desempacar_pack(item)[1] > 0 or shop_catalog.es_set(item):
        return False
    return any(isinstance(e, dict) and int(e.get("id", 0)) == int(item) and not int(e.get("exp", 0) or 0)
               for e in (db_get_char(int(uid)) or {}).get("inventory") or [])


def canjear(uid, texto, ahora=None):
    """Decide y, si vale, ANOTA el canje. -> (resultado, regla o None, motivo). No entrega nada (eso es `entregar`)."""
    ahora = time.time() if ahora is None else ahora
    k = normalizar(texto)
    r = regla(k) if k else None
    if r is None or not r["activo"]:
        return NO_EXISTE, None, "vacío" if not k else f"{k!r} no existe" + ("" if r is None else " (apagado)")
    if r["desde"] and ahora < r["desde"]:
        return INVALIDO, r, "todavía no empezó"
    if r["vence"] and ahora > r["vence"]:
        return VENCIDO, r, "vencido"
    if r["premios"] and not r["rcoin"] and all(_tiene_permanente(uid, p["item"]) for p in r["premios"]):
        return YA_TIENE, r, "ya tiene permanente todo lo que da"
    with _canje_lock, almacen._lock:
        c = _con()
        if c.execute("SELECT 1 FROM cupones_usados WHERE uid=? AND codigo=?", (int(uid), k)).fetchone():
            return YA_REGISTRADO, r, "esta cuenta ya lo canjeó"
        if r["usos"] and c.execute("SELECT COUNT(*) FROM cupones_usados WHERE codigo=?", (k,)).fetchone()[0] >= r["usos"]:
            return INVALIDO, r, f"agotado ({r['usos']} usos)"
        c.execute("INSERT INTO cupones_usados (uid, codigo, cuando) VALUES (?, ?, ?)", (int(uid), k, ahora))
        c.commit()
    return OK, r, "canjeado"


def deshacer(uid, codigo):
    """Si la entrega falló, el canje no cuenta."""
    with almacen._lock:
        c = _con()
        c.execute("DELETE FROM cupones_usados WHERE uid=? AND codigo=?", (int(uid), normalizar(codigo)))
        c.commit()


DE_RCOIN = "Cupon"                # el «de %s» de los carteles (sin tilde: el popup no la dibuja)


def iconos_rcoin():
    """{monto: ítem} — los premios de las CAJITAS DE NIVEL («100 Rcoin», «1,000 Rcoin»…, familia `gift_levelup`): son
    ítems con el ícono de Rcoin. Sale del catálogo, no se escribe a mano."""
    import re
    from . import shop_catalog
    shop_catalog.get(0)
    out = {}
    for iid, d in shop_catalog.CATALOG.items():
        m = re.fullmatch(r"([\d,.]+) Rcoin", (d.get("name") or "").strip())
        if m and d.get("family") == "gift_levelup":
            out.setdefault(int(m.group(1).replace(",", "").replace(".", "")), int(iid))
    return dict(sorted(out.items()))


def entregar(uid, r, st=None):
    """El premio, con el cartel CELESTE del regalo (anonimo03, 15-oct: «me gusta más ese que la ventana amarilla, que es
    para eventos»):
      · cada ítem: `regalo.dar_item(…, de="Cupon")` = el `FFCE` silencioso (entra al inventario) + el `FF54` «Ha
        recibido [ítem] de Cupon» con su imagen;
      · el Rcoin: `db_add_rcoin` + `FFAB [u32 saldo]` (fija el número, sin cartel) + el `FF54`. ⛔ «El cliente pide su
        saldo solo» NO pasa en el lobby (medido 15-oct: ningún FFAB). El cartel (`0x423920`, ítem/apodo/rcoin) dice
        «Ha recibido [ítem] de %s» (326) si va sin Rcoin, «%d Rcoin de %s» (328) con ítem 0 — SIN imagen —, y «[ítem] y
        %d Rcoin» (327) con los dos. ⇒ si el monto tiene su cajita de nivel (`iconos_rcoin`), va como ÍTEM («Ha
        recibido [1,000 Rcoin] de Cupon», con el ícono) y Rcoin 0; si no, 328 sin ícono."""
    from .basedatos import db_add_rcoin
    from .regalo import armar_ff54, dar_item
    hecho = {"items": []}
    for p in r["premios"]:
        hecho["items"].append(dar_item(uid, p["item"], p["dias"], p["cant"], de=DE_RCOIN, motivo=f"cupón {r['codigo']}"))
    if r["rcoin"]:
        hecho["rcoin"] = r["rcoin"]
        hecho["saldo"] = saldo = int(db_add_rcoin(uid, r["rcoin"]))
        if st is not None and not getattr(st, "cerrado", False):
            icono = iconos_rcoin().get(int(r["rcoin"]), 0)
            st.send_ff55(0xAB, struct.pack("<I", saldo & 0xFFFFFFFF), name=f"FFAB saldo {saldo} (+{r['rcoin']} cupón)")
            st.send_ff55(0x54, armar_ff54([(DE_RCOIN, icono, 0 if icono else r["rcoin"])]),
                         name=f"FF54 «Ha recibido {r['rcoin']} Rcoin»" + (f" (ícono {icono})" if icono else " (sin ícono)"))
    return hecho


def _demasiados(uid, ahora):
    t = [x for x in _intentos.get(uid, []) if ahora - x < 60] + [ahora]
    _intentos[uid] = t
    return len(t) > INTENTOS_POR_MINUTO


def atender(st, data):
    """C→S `FF158`. Contesta SIEMPRE `FF158 [u8 resultado]` y, si vale, entrega el premio."""
    uid = int(getattr(st, "usn", 0) or 0)
    texto = leer_ff158(data)
    res, r, motivo = INVALIDO, None, "paquete que no cierra"
    try:
        if texto is not None and _demasiados(uid, time.time()):
            res, motivo = INVALIDO, f"más de {INTENTOS_POR_MINUTO} intentos en un minuto"
        elif texto is not None:
            res, r, motivo = canjear(uid, texto)
    except Exception as e:                                                 # noqa: BLE001
        res, motivo = INVALIDO, f"error: {e!r}"
    hecho = None
    if res == OK:
        try:
            hecho = entregar(uid, r, st)
        except Exception as e:                                             # noqa: BLE001
            deshacer(uid, r["codigo"])
            res, motivo = INVALIDO, f"la entrega falló ({e!r}): el canje no cuenta"
    st.send_ff55(0x158, bytes([res]), name=f"FF158 cupón {TEXTO.get(res, res)}")
    log("LOBBY", f"  🎟 FF158 usn={uid} escribió {texto!r} -> {TEXTO.get(res, res)} ({motivo})"
                 + (f" · premio {hecho}" if hecho else ""))
