"""torneos — ★ 20-nov-2026: los TORNEOS del launcher (fase 1). El contrato: `documentacion/TORNEOS.md`.

anonimo03: *«me encanta, mételo al launcher»* (el popup del prototipo `_trabajo/torneo_kit/torneo.html`). Viven acá, en
`datos.db`: el torneo, la votación de la hora, la inscripción y la LLAVE. El launcher los muestra y deja votar e
inscribirse (`launcher_api`); el staff los maneja desde el Coordinador (`/api/interno/torneos`, ficha interna) y carga
los resultados A MANO (el juez automático es la fase 2).

    torneos           el torneo: nombre, modo (solo|pareja|circulo), estado, fecha, horas (JSON), cupo, info, el podio
    torneo_votos      un voto por CUENTA y torneo (votar otra vez CAMBIA el voto: cuenta el último)
    torneo_inscritos  una fila por PERSONAJE inscrito (y uno solo por cuenta); en pareja, cada uno de los dos tiene la suya
    torneo_cruces     la llave FIJA (desde `en_curso`): todas las rondas; las de adelante con a/b NULL hasta decidirse

★ La CUENTA de un personaje = `users.uid` del casillero 1 (`almacen._ubicacion` → usuario → `almacen._cuenta_fila`).
★ La llave: entrantes por orden de llegada (semilla 1..n), tamaño S = potencia de 2 ≥ n, orden de siembra estándar
  (`siembra`, el mismo del prototipo) y los LIBRES ganan solos la ronda 0 y avanzan.
  · pareja: entra la pareja CONFIRMADA; su id de entrante es el de la fila del que se inscribió PRIMERO, y la llegada
    es la de esa fila. Las pedidas sin confirmar no entran (y quedan como estaban).
⛔ Todo bajo `almacen._lock` (la misma base que el juego). Adentro NO se llama a funciones de `almacen` que lo vuelvan a
   tomar (`circulo_de`, `char_por_nick`…): el candado no es reentrante; esas consultas se hacen acá, con la conexión.
"""
import json
import time

from . import almacen

MODOS = ("solo", "pareja", "circulo")
ESTADOS = ("borrador", "votando", "inscripcion", "en_curso", "terminado", "cancelado")
ABIERTOS = ("votando", "inscripcion")                    # se puede inscribir y salir
VISIBLES = ("en_curso", "inscripcion", "votando", "terminado")   # el orden en que los ve el launcher
CUPO_MIN, CUPO_MAX = 2, 32
HORAS_MAX = 8
NOMBRE_MAX, INFO_MAX, CANCION_MAX = 60, 500, 80
TERMINADO_VISIBLE = 7 * 86400                            # el launcher ve los terminados de la última semana


class NoSePuede(Exception):
    """Lo que hizo el JUGADOR no se puede: el motivo en español neutro de «tú», para mostrarlo tal cual."""


class Invalido(Exception):
    """Lo que pidió el STAFF (el Coordinador) no se puede: el motivo en español neutro de «usted»."""


class PideForzar(Invalido):
    """★ 20-nov: se puede, pero borra resultados ya cargados: el panel lo confirma y lo vuelve a pedir con `forzar`.
    Sale como 409 + {"forzar": true} (así el panel no depende del texto del mensaje)."""


_ESQUEMA = """
CREATE TABLE IF NOT EXISTS torneos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL, modo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'borrador', fecha INTEGER, horas TEXT NOT NULL DEFAULT '[]', cupo INTEGER NOT NULL,
    info TEXT NOT NULL DEFAULT '', primero INTEGER, segundo INTEGER, tercero INTEGER, fin REAL,
    creado REAL NOT NULL, quien TEXT NOT NULL DEFAULT '', cambiado REAL NOT NULL);
CREATE INDEX IF NOT EXISTS ix_torneos_estado ON torneos(estado);
CREATE TABLE IF NOT EXISTS torneo_votos (
    torneo_id INTEGER NOT NULL, cuenta INTEGER NOT NULL, opcion INTEGER NOT NULL, cuando REAL NOT NULL,
    PRIMARY KEY (torneo_id, cuenta));
CREATE TABLE IF NOT EXISTS torneo_inscritos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, torneo_id INTEGER NOT NULL, cuenta INTEGER NOT NULL, usn INTEGER NOT NULL,
    nombre TEXT NOT NULL, pareja_usn INTEGER, pareja_nombre TEXT, pareja_ok INTEGER NOT NULL DEFAULT 0,
    circulo_id INTEGER, circulo_nombre TEXT, semilla INTEGER, cuando REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS ux_torneo_inscritos_cuenta ON torneo_inscritos(torneo_id, cuenta);
CREATE UNIQUE INDEX IF NOT EXISTS ux_torneo_inscritos_circulo ON torneo_inscritos(torneo_id, circulo_id)
    WHERE circulo_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS torneo_cruces (
    torneo_id INTEGER NOT NULL, ronda INTEGER NOT NULL, idx INTEGER NOT NULL, a INTEGER, b INTEGER, ganador TEXT,
    cancion TEXT, estado TEXT NOT NULL DEFAULT 'pendiente', quien TEXT NOT NULL DEFAULT '', cambiado REAL NOT NULL,
    PRIMARY KEY (torneo_id, ronda, idx));
"""
_LISTO = set()


def _con():
    """⚠ Llamar con `almacen._lock` tomado. Las tablas se crean la primera vez (por base)."""
    c = almacen.conectar()
    if almacen.BASE not in _LISTO:
        c.executescript(_ESQUEMA)
        _LISTO.add(almacen.BASE)
    return c


# ── la llave: cálculo puro ────────────────────────────────────────────────────────────────────────

def tamano(n):
    """La potencia de 2 que alcanza para n entrantes (mínimo 2)."""
    s = 2
    while s < n:
        s *= 2
    return s


def siembra(s):
    """El orden de siembra estándar (el del prototipo): [1] → [1,2] → [1,4,2,3] → [1,8,4,5,2,7,3,6]…
    El cruce i de la ronda 0 es (orden[2i], orden[2i+1]): el 1 contra el último, y los LIBRES le tocan a los primeros."""
    o = [1]
    while len(o) < s:
        m = len(o) * 2 + 1
        o = [y for x in o for y in (x, m - x)]
    return o


def rondas_de(s):
    r = 0
    while (1 << r) < s:
        r += 1
    return r


# ── lecturas chicas (con la conexión, sin el candado de almacen otra vez) ───────────────────────────

def _cuenta_de(c, usn):
    """La CUENTA del personaje: `users.uid` del casillero 1, o None si no es de nadie."""
    usuario, _ranura = almacen._ubicacion(c, int(usn))
    if not usuario:
        return None
    f = almacen._cuenta_fila(c, usuario)
    return int(f["uid"]) if f else None


def _apodo(c, usn):
    r = c.execute("SELECT nickname FROM chars WHERE uid = ?", (int(usn),)).fetchone()
    return (r["nickname"] or "") if r else ""


def _circulo(c, usn):
    """{id, nombre} del círculo del que es MIEMBRO, o None."""
    r = c.execute("SELECT k.id, k.nombre FROM circulo_miembros m JOIN circulos k ON k.id = m.circulo_id "
                  "WHERE m.uid = ?", (int(usn),)).fetchone()
    return {"id": int(r["id"]), "nombre": r["nombre"] or ""} if r else None


def _por_apodo(c, apodo):
    r = c.execute("SELECT uid, nickname FROM chars WHERE lower(nickname) = lower(?)", (str(apodo).strip(),)).fetchone()
    return (int(r["uid"]), r["nickname"]) if r else (None, None)


def _torneo(c, tid):
    try:
        tid = int(tid)
    except (TypeError, ValueError):
        return None
    return c.execute("SELECT * FROM torneos WHERE id = ?", (tid,)).fetchone()


def _horas(t):
    try:
        v = json.loads(t["horas"] or "[]")
        return [int(x) for x in v] if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def _inscritos(c, tid):
    return c.execute("SELECT * FROM torneo_inscritos WHERE torneo_id = ? ORDER BY id", (int(tid),)).fetchall()


def _cruces(c, tid):
    return c.execute("SELECT * FROM torneo_cruces WHERE torneo_id = ? ORDER BY ronda, idx", (int(tid),)).fetchall()


def entrantes(modo, filas):
    """Los que entran a la llave, en orden de llegada: [fila]. Pareja: la fila del primero de cada pareja CONFIRMADA."""
    if modo != "pareja":
        return list(filas)
    por_usn = {int(f["usn"]): f for f in filas}
    out = []
    for f in filas:
        if not f["pareja_ok"]:
            continue
        otro = por_usn.get(int(f["pareja_usn"] or 0))
        if otro is not None and int(otro["id"]) < int(f["id"]):
            continue                                       # el entrante es el que llegó primero
        out.append(f)
    return out


def _ocupados(modo, filas):
    """Lo que cuenta para el cupo: solo/círculo, las filas; pareja, las parejas CONFIRMADAS (las pedidas, no)."""
    return len(entrantes(modo, filas))


# ── el jugador (lo llama `launcher_api`) ──────────────────────────────────────────────────────────

def _escribir(hacer):
    with almacen._lock:
        c = _con()
        try:
            out = hacer(c)
            c.commit()
            return out
        except BaseException:
            c.rollback()
            raise


def votar(cuenta, tid, opcion):
    """Un voto por cuenta: votar otra vez CAMBIA el voto (cuenta el último). Sólo en `votando`."""
    def hacer(c):
        t = _torneo(c, tid)
        if not t or t["estado"] in ("borrador", "cancelado"):
            raise NoSePuede("Ese torneo no existe.")
        if t["estado"] != "votando":
            raise NoSePuede("La votación de este torneo está cerrada.")
        horas = _horas(t)
        try:
            o = int(opcion)
        except (TypeError, ValueError):
            o = -1
        if not 0 <= o < len(horas):
            raise NoSePuede("Esa hora no está entre las opciones.")
        c.execute("INSERT INTO torneo_votos (torneo_id, cuenta, opcion, cuando) VALUES (?, ?, ?, ?) "
                  "ON CONFLICT(torneo_id, cuenta) DO UPDATE SET opcion = excluded.opcion, cuando = excluded.cuando",
                  (int(t["id"]), int(cuenta), o, time.time()))
    _escribir(hacer)


def inscribir(usn, tid, pareja=None):
    """Inscribe a ESE personaje (ya se comprobó que es de la cuenta). -> {aviso?} · ⛔ NoSePuede."""
    def hacer(c):
        t = _torneo(c, tid)
        if not t or t["estado"] in ("borrador", "cancelado"):
            raise NoSePuede("Ese torneo no existe.")
        if t["estado"] not in ABIERTOS:
            raise NoSePuede("La inscripción está cerrada.")
        cuenta = _cuenta_de(c, usn)
        if cuenta is None:
            raise NoSePuede("Ese personaje no es de ninguna cuenta.")
        nombre = _apodo(c, usn)
        if not nombre:
            raise NoSePuede("Ese personaje no existe.")
        filas = _inscritos(c, t["id"])
        ya = next((f for f in filas if int(f["cuenta"]) == cuenta), None)
        if ya is not None:
            raise NoSePuede("Ya estás inscrito en este torneo." if int(ya["usn"]) == int(usn) else
                            f"Ya tienes otro personaje inscrito en este torneo ({ya['nombre']}): es uno por cuenta.")
        modo, ahora, aviso = t["modo"], time.time(), None
        lleno = _ocupados(modo, filas) >= int(t["cupo"])
        if modo == "solo":
            if lleno:
                raise NoSePuede("El torneo ya está lleno.")
            c.execute("INSERT INTO torneo_inscritos (torneo_id, cuenta, usn, nombre, cuando) VALUES (?, ?, ?, ?, ?)",
                      (int(t["id"]), cuenta, int(usn), nombre, ahora))
        elif modo == "circulo":
            k = _circulo(c, usn)
            if not k:
                raise NoSePuede("Para un torneo de círculos tienes que ser miembro de un círculo.")
            if any(int(f["circulo_id"] or 0) == k["id"] for f in filas):
                raise NoSePuede(f"Tu círculo ({k['nombre']}) ya está inscrito en este torneo.")
            if lleno:
                raise NoSePuede("El torneo ya está lleno.")
            c.execute("INSERT INTO torneo_inscritos (torneo_id, cuenta, usn, nombre, circulo_id, circulo_nombre, cuando) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?)", (int(t["id"]), cuenta, int(usn), k["nombre"], k["id"], k["nombre"], ahora))
        else:                                                   # pareja
            apodo = " ".join(str(pareja or "").split())[:32]
            if not apodo:
                raise NoSePuede("Para un torneo de parejas tienes que escribir el apodo de tu compañero.")
            p_usn, p_nombre = _por_apodo(c, apodo)
            if p_usn is None:
                raise NoSePuede(f"No existe ningún personaje con el apodo «{apodo}».")
            if p_usn == int(usn):
                raise NoSePuede("No puedes formar pareja contigo mismo.")
            if _cuenta_de(c, p_usn) == cuenta:
                raise NoSePuede("Tu compañero tiene que ser de otra cuenta.")
            suya = next((f for f in filas if int(f["usn"]) == p_usn), None)
            if suya is not None and int(suya["pareja_usn"] or 0) != int(usn):
                raise NoSePuede(f"{p_nombre} ya está inscrito con otra pareja.")
            if suya is not None:                                # ★ me nombró a mí: la pareja queda CONFIRMADA
                if lleno:
                    raise NoSePuede("El torneo ya está lleno.")
                c.execute("UPDATE torneo_inscritos SET pareja_ok = 1, pareja_nombre = ? WHERE id = ?",
                          (nombre, int(suya["id"])))
                ok_ = 1
            else:
                ok_ = 0
                aviso = (f"Tu compañero tiene que inscribirse nombrándote a ti para confirmar la pareja "
                         f"(hasta entonces {p_nombre} y tú no entran a la llave).")
            c.execute("INSERT INTO torneo_inscritos (torneo_id, cuenta, usn, nombre, pareja_usn, pareja_nombre, pareja_ok, "
                      "cuando) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (int(t["id"]), cuenta, int(usn), nombre, p_usn, p_nombre, ok_, ahora))
        return {"aviso": aviso} if aviso else {}
    return _escribir(hacer)


def salir(usn, tid):
    """Se sale ESE personaje. En pareja, el compañero queda con su pedido sin confirmar."""
    def hacer(c):
        t = _torneo(c, tid)
        if not t or t["estado"] in ("borrador", "cancelado"):
            raise NoSePuede("Ese torneo no existe.")
        if t["estado"] not in ABIERTOS:
            raise NoSePuede("Ya no te puedes salir: la llave está cerrada.")
        f = c.execute("SELECT * FROM torneo_inscritos WHERE torneo_id = ? AND usn = ?", (int(t["id"]), int(usn))).fetchone()
        if not f:
            raise NoSePuede("No estás inscrito en este torneo.")
        _borrar_inscrito(c, t, f)
    _escribir(hacer)


def _borrar_inscrito(c, t, f):
    c.execute("DELETE FROM torneo_inscritos WHERE id = ?", (int(f["id"]),))
    if t["modo"] == "pareja" and f["pareja_ok"]:
        c.execute("UPDATE torneo_inscritos SET pareja_ok = 0 WHERE torneo_id = ? AND usn = ? AND pareja_usn = ?",
                  (int(t["id"]), int(f["pareja_usn"] or 0), int(f["usn"])))


# ── lo que ve el launcher ────────────────────────────────────────────────────────────────────────

def yo(usn):
    """{cuenta, usn, nombre, circulo: {id, nombre}|None} del personaje elegido."""
    with almacen._lock:
        c = _con()
        return {"cuenta": _cuenta_de(c, usn), "usn": int(usn), "nombre": _apodo(c, usn), "circulo": _circulo(c, usn)}


def _votos(c, tid):
    return {int(r[0]): int(r[1]) for r in c.execute(
        "SELECT opcion, COUNT(*) FROM torneo_votos WHERE torneo_id = ? GROUP BY opcion", (int(tid),))}


def _podio(t):
    return {"primero": t["primero"], "segundo": t["segundo"], "tercero": t["tercero"]}


def _cruce(r):
    return {"ronda": int(r["ronda"]), "idx": int(r["idx"]), "a": r["a"], "b": r["b"], "ganador": r["ganador"],
            "cancion": r["cancion"], "estado": r["estado"]}


def _para_launcher(c, t, cuenta, usn):
    """TORNEO (el del contrato, §2) visto por ese personaje / esa cuenta."""
    tid, modo = int(t["id"]), t["modo"]
    votos = _votos(c, tid)
    mv = c.execute("SELECT opcion FROM torneo_votos WHERE torneo_id = ? AND cuenta = ?", (tid, int(cuenta or 0))).fetchone()
    filas = _inscritos(c, tid)
    por_usn = {int(f["usn"]): f for f in filas}
    inscritos, mi, pendiente = [], None, None
    for f in filas:
        if int(f["cuenta"]) == int(cuenta or -1):
            mi = f
    if modo != "pareja":
        for f in filas:
            e = {"id": int(f["id"]), "nombre": f["nombre"], "es_mio": int(f["cuenta"]) == int(cuenta or -1)}
            if f["semilla"] is not None:
                e["semilla"] = int(f["semilla"])
            inscritos.append(e)
    else:
        for f in filas:
            otro = por_usn.get(int(f["pareja_usn"] or 0))
            confirmada = bool(f["pareja_ok"]) and otro is not None
            if confirmada and int(otro["id"]) < int(f["id"]):
                continue                                        # la pareja ya salió con la fila del primero
            es_mio = int(f["cuenta"]) == int(cuenta or -1) or (confirmada and int(otro["cuenta"]) == int(cuenta or -1))
            nombrado = usn is not None and int(f["pareja_usn"] or 0) == int(usn)
            if not confirmada and not (es_mio or nombrado):
                continue                                        # ⛔ la pedida sin confirmar: sólo la ven los dos
            e = {"id": int(f["id"]), "nombre": f["nombre"], "pareja_nombre": f["pareja_nombre"],
                 "pareja_ok": confirmada, "es_mio": es_mio}
            if f["semilla"] is not None:
                e["semilla"] = int(f["semilla"])
            inscritos.append(e)
    ins_id = None
    if mi is not None:
        ins_id = int(mi["id"])
        if modo == "pareja":
            otro = por_usn.get(int(mi["pareja_usn"] or 0))
            if mi["pareja_ok"] and otro is not None:
                ins_id = min(int(mi["id"]), int(otro["id"]))   # el id del ENTRANTE (el de la llave)
            else:
                pendiente = {"para": mi["pareja_nombre"]}
    elif modo == "pareja" and usn is not None:
        f = next((x for x in filas if int(x["pareja_usn"] or 0) == int(usn) and not x["pareja_ok"]), None)
        if f is not None:
            pendiente = {"de": f["nombre"]}
    mio = {"inscrito": mi is not None, "ins_id": ins_id, "pareja_pendiente": pendiente}
    if mi is not None:
        mio["usn"] = int(mi["usn"])
    horas = _horas(t)
    return {"id": tid, "nombre": t["nombre"], "modo": modo, "estado": t["estado"], "fecha": t["fecha"],
            "horas": [{"t": h, "votos": votos.get(i, 0)} for i, h in enumerate(horas)],
            "mi_voto": int(mv[0]) if mv else None, "cupo": int(t["cupo"]), "info": t["info"] or "",
            "ocupados": _ocupados(modo, filas), "inscritos": inscritos,
            "cruces": [_cruce(r) for r in _cruces(c, tid)] if t["estado"] in ("en_curso", "terminado") else [],
            "podio": _podio(t), "yo": mio}


def _orden(t):
    cuando = t["fecha"] or (min(_horas(t)) if _horas(t) else None) or int(t["creado"])
    pos = VISIBLES.index(t["estado"])
    return (pos, -cuando if t["estado"] == "terminado" else cuando, int(t["id"]))


def lista_launcher(cuenta, usn=None, ahora=None):
    """Lo que ve el launcher: sin borradores ni cancelados; los terminados, sólo los de los últimos 7 días.
    Orden: en curso, inscripción, votando, terminado; dentro, por fecha (los terminados, el más nuevo primero)."""
    ahora = time.time() if ahora is None else ahora
    with almacen._lock:
        c = _con()
        filas = [t for t in c.execute("SELECT * FROM torneos WHERE estado IN (?, ?, ?, ?)", VISIBLES)
                 if t["estado"] != "terminado" or (t["fin"] or t["cambiado"]) >= ahora - TERMINADO_VISIBLE]
        return [_para_launcher(c, t, cuenta, usn) for t in sorted(filas, key=_orden)]


def uno_launcher(tid, cuenta, usn=None):
    with almacen._lock:
        c = _con()
        t = _torneo(c, tid)
        return _para_launcher(c, t, cuenta, usn) if t and t["estado"] in VISIBLES else None


def cuenta_de_usn(usn):
    with almacen._lock:
        return _cuenta_de(_con(), usn)


def cuenta_de_usuario(usuario):
    with almacen._lock:
        f = almacen._cuenta_fila(_con(), usuario)
        return int(f["uid"]) if f else None


# ── el staff (lo llama la puerta del Coordinador) ───────────────────────────────────────────────

def _para_staff(c, t):
    tid = int(t["id"])
    votos = _votos(c, tid)
    horas = _horas(t)
    ganadora = max(range(len(horas)), key=lambda i: (votos.get(i, 0), -i)) if horas and votos else None
    filas = _inscritos(c, tid)
    return {"id": tid, "nombre": t["nombre"], "modo": t["modo"], "estado": t["estado"], "fecha": t["fecha"],
            "horas": [{"t": h, "votos": votos.get(i, 0)} for i, h in enumerate(horas)], "hora_ganadora": ganadora,
            "votos_total": sum(votos.values()), "cupo": int(t["cupo"]), "info": t["info"] or "",
            "ocupados": _ocupados(t["modo"], filas), "entrantes": [int(f["id"]) for f in entrantes(t["modo"], filas)],
            "inscritos": [{"id": int(f["id"]), "cuenta": int(f["cuenta"]), "usn": int(f["usn"]), "nombre": f["nombre"],
                           "pareja_usn": f["pareja_usn"], "pareja_nombre": f["pareja_nombre"],
                           "pareja_ok": bool(f["pareja_ok"]), "circulo_id": f["circulo_id"],
                           "circulo_nombre": f["circulo_nombre"], "semilla": f["semilla"], "cuando": f["cuando"]}
                          for f in filas],
            "cruces": [{**_cruce(r), "quien": r["quien"], "cambiado": r["cambiado"]} for r in _cruces(c, tid)],
            "podio": _podio(t), "fin": t["fin"], "creado": t["creado"], "quien": t["quien"], "cambiado": t["cambiado"]}


def todos_staff():
    with almacen._lock:
        c = _con()
        return [_para_staff(c, t) for t in c.execute("SELECT * FROM torneos ORDER BY id DESC")]


def uno_staff(tid):
    with almacen._lock:
        c = _con()
        t = _torneo(c, tid)
        return _para_staff(c, t) if t else None


def _texto(v, tope, que, vacio_ok=True):
    s = " ".join(str(v or "").split()) if que != "info" else str(v or "").strip()
    if not s and not vacio_ok:
        raise Invalido(f"Falta {que}.")
    if len(s) > tope:
        raise Invalido(f"{que.capitalize()}: como mucho {tope} caracteres.")
    return s


def _cupo(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise Invalido(f"El cupo va de {CUPO_MIN} a {CUPO_MAX}.") from None
    if not CUPO_MIN <= n <= CUPO_MAX:
        raise Invalido(f"El cupo va de {CUPO_MIN} a {CUPO_MAX}.")
    return n


def _epoch(v, que="la fecha"):
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise Invalido(f"{que.capitalize()} no es válida (segundos epoch).") from None
    if n <= 0:
        raise Invalido(f"{que.capitalize()} no es válida (segundos epoch).")
    return n


def _lista_horas(v):
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise Invalido("Las horas van en una lista de fechas (segundos epoch).")
    out = []
    for x in v:
        n = _epoch(x, "una hora")
        if n not in out:
            out.append(n)
    if len(out) > HORAS_MAX:
        raise Invalido(f"Como mucho {HORAS_MAX} horas para votar.")
    return out


def _quien(q):
    return " ".join(str(q or "").split())[:60] or "coordinador"


def _toque(c, tid, quien):
    c.execute("UPDATE torneos SET cambiado = ?, quien = ? WHERE id = ?", (time.time(), quien, int(tid)))


def _cruce_de(c, t, d):
    try:
        ronda, idx = int(d.get("ronda")), int(d.get("idx"))
    except (TypeError, ValueError):
        raise Invalido("Indique la ronda y el número del cruce.") from None
    r = c.execute("SELECT * FROM torneo_cruces WHERE torneo_id = ? AND ronda = ? AND idx = ?",
                  (int(t["id"]), ronda, idx)).fetchone()
    if not r:
        raise Invalido("Ese cruce no existe en la llave.")
    return r


def _total_rondas(c, tid):
    r = c.execute("SELECT MAX(ronda) FROM torneo_cruces WHERE torneo_id = ?", (int(tid),)).fetchone()
    return (int(r[0]) + 1) if r and r[0] is not None else 0


def _avanzar(c, tid, ronda, idx, ganador_id, quien, ahora):
    """Pone al ganador del cruce (ronda, idx) en su lugar de la ronda siguiente (idx//2; lado a si idx es par)."""
    lado = "a" if idx % 2 == 0 else "b"
    c.execute(f"UPDATE torneo_cruces SET {lado} = ?, quien = ?, cambiado = ? WHERE torneo_id = ? AND ronda = ? AND idx = ?",
              (ganador_id, quien, ahora, int(tid), ronda + 1, idx // 2))


def fijar_llave(c, t, quien, ahora):
    """Arma la llave FIJA (al pasar a `en_curso`). -> n.º de entrantes · ⛔ Invalido si no alcanzan."""
    tid = int(t["id"])
    filas = entrantes(t["modo"], _inscritos(c, tid))
    n = len(filas)
    if n < 2:
        raise Invalido("Para armar la llave hacen falta al menos 2 participantes"
                       + (" (parejas confirmadas)." if t["modo"] == "pareja" else "."))
    c.execute("UPDATE torneo_inscritos SET semilla = NULL WHERE torneo_id = ?", (tid,))
    c.execute("DELETE FROM torneo_cruces WHERE torneo_id = ?", (tid,))
    ids = {}
    for k, f in enumerate(filas, 1):
        ids[k] = int(f["id"])
        c.execute("UPDATE torneo_inscritos SET semilla = ? WHERE id = ?", (k, int(f["id"])))
        if t["modo"] == "pareja":                               # el compañero lleva la misma semilla (para dibujarla)
            c.execute("UPDATE torneo_inscritos SET semilla = ? WHERE torneo_id = ? AND usn = ? AND pareja_ok = 1",
                      (k, tid, int(f["pareja_usn"] or 0)))
    s = tamano(n)
    orden = siembra(s)
    for ronda in range(rondas_de(s)):
        for idx in range(s >> (ronda + 1)):
            a = b = None
            if ronda == 0:
                a, b = ids.get(orden[2 * idx]), ids.get(orden[2 * idx + 1])
            c.execute("INSERT INTO torneo_cruces (torneo_id, ronda, idx, a, b, estado, quien, cambiado) "
                      "VALUES (?, ?, ?, ?, ?, 'pendiente', ?, ?)", (tid, ronda, idx, a, b, quien, ahora))
    for idx in range(s // 2):                                   # los LIBRES: ganan solos y avanzan
        a, b = ids.get(orden[2 * idx]), ids.get(orden[2 * idx + 1])
        if (a is None) != (b is None):
            lado, gid = ("a", a) if a is not None else ("b", b)
            c.execute("UPDATE torneo_cruces SET ganador = ?, estado = 'terminado' WHERE torneo_id = ? AND ronda = 0 "
                      "AND idx = ?", (lado, tid, idx))
            _avanzar(c, tid, 0, idx, gid, quien, ahora)
    return n


def _deshacer_adelante(c, t, ronda, idx, quien, ahora):
    """Saca de la ronda siguiente al que había ganado (ronda, idx) y, si ese cruce ya tenía resultado, lo reinicia
    también (y así hasta el final). La final: se borra el podio y el torneo vuelve a `en_curso`."""
    tid = int(t["id"])
    total = _total_rondas(c, tid)
    if ronda + 1 >= total:                                      # era la final
        c.execute("UPDATE torneos SET primero = NULL, segundo = NULL, fin = NULL, "
                  "estado = CASE WHEN estado = 'terminado' THEN 'en_curso' ELSE estado END WHERE id = ?", (tid,))
        return
    sig = c.execute("SELECT * FROM torneo_cruces WHERE torneo_id = ? AND ronda = ? AND idx = ?",
                    (tid, ronda + 1, idx // 2)).fetchone()
    if sig["ganador"]:
        c.execute("UPDATE torneo_cruces SET ganador = NULL, estado = 'pendiente', quien = ?, cambiado = ? "
                  "WHERE torneo_id = ? AND ronda = ? AND idx = ?", (quien, ahora, tid, ronda + 1, idx // 2))
        _deshacer_adelante(c, t, ronda + 1, idx // 2, quien, ahora)
    lado = "a" if idx % 2 == 0 else "b"
    c.execute(f"UPDATE torneo_cruces SET {lado} = NULL, estado = CASE WHEN estado = 'jugando' THEN 'pendiente' "
              f"ELSE estado END, quien = ?, cambiado = ? WHERE torneo_id = ? AND ronda = ? AND idx = ?",
              (quien, ahora, tid, ronda + 1, idx // 2))


def _hay_jugados(c, tid):
    """¿Algún cruce con resultado que NO sea un pase libre?"""
    return c.execute("SELECT 1 FROM torneo_cruces WHERE torneo_id = ? AND ganador IS NOT NULL AND a IS NOT NULL "
                     "AND b IS NOT NULL LIMIT 1", (int(tid),)).fetchone() is not None


def accion(d):
    """POST /api/interno/torneos {accion, …}. -> (código, datos). Cada cambio, a la auditoría del panel viejo."""
    from . import panel_admin
    if not isinstance(d, dict):
        return 400, {"error": "Pedido mal armado."}
    que = str(d.get("accion") or "")
    hacer = _ACCIONES.get(que)
    if not hacer:
        return 400, {"error": "Acción desconocida: " + " · ".join(_ACCIONES)}
    quien = _quien(d.get("quien"))
    try:
        tid, detalle = _escribir(lambda c: hacer(c, d, quien, time.time()))
    except PideForzar as e:
        return 409, {"error": str(e), "forzar": True}
    except Invalido as e:
        return 400, {"error": str(e)}
    panel_admin.auditar_externo(quien, "torneos/" + que, {"torneo": tid, **detalle})
    return 200, {"ok": True, "torneo": uno_staff(tid)}


def _t_o_falla(c, d):
    t = _torneo(c, d.get("torneo"))
    if not t:
        raise Invalido("Ese torneo no existe.")
    return t


def _a_crear(c, d, quien, ahora):
    nombre = _texto(d.get("nombre"), NOMBRE_MAX, "el nombre", vacio_ok=False)
    modo = str(d.get("modo") or "")
    if modo not in MODOS:
        raise Invalido("El modo es: " + " · ".join(MODOS) + ".")
    cupo, horas = _cupo(d.get("cupo")), _lista_horas(d.get("horas"))
    fecha, info = _epoch(d.get("fecha")), _texto(d.get("info"), INFO_MAX, "info")
    cur = c.execute("INSERT INTO torneos (nombre, modo, estado, fecha, horas, cupo, info, creado, quien, cambiado) "
                    "VALUES (?, ?, 'borrador', ?, ?, ?, ?, ?, ?, ?)",
                    (nombre, modo, fecha, json.dumps(horas), cupo, info, ahora, quien, ahora))
    return int(cur.lastrowid), {"nombre": nombre, "modo": modo, "cupo": cupo, "horas": horas, "fecha": fecha}


def _a_editar(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    tid, cambios = int(t["id"]), {}
    cerrada = t["estado"] in ("en_curso", "terminado")
    if "nombre" in d:
        cambios["nombre"] = _texto(d.get("nombre"), NOMBRE_MAX, "el nombre", vacio_ok=False)
    if "info" in d:
        cambios["info"] = _texto(d.get("info"), INFO_MAX, "info")
    if "fecha" in d:
        cambios["fecha"] = _epoch(d.get("fecha"))
    if "cupo" in d:
        if cerrada:
            raise Invalido("Con la llave armada ya no se puede cambiar el cupo.")
        cupo = _cupo(d.get("cupo"))
        ya = _ocupados(t["modo"], _inscritos(c, tid))
        if cupo < ya:
            raise Invalido(f"Ya hay {ya} inscritos: el cupo no puede ser menor.")
        cambios["cupo"] = cupo
    if "horas" in d:
        if cerrada:
            raise Invalido("Con la llave armada ya no se pueden cambiar las horas.")
        nuevas, viejas = _lista_horas(d.get("horas")), _horas(t)
        # los votos siguen a SU hora (por la fecha, no por el número): si esa hora ya no está, el voto se va
        for cuenta, opcion in c.execute("SELECT cuenta, opcion FROM torneo_votos WHERE torneo_id = ?", (tid,)).fetchall():
            h = viejas[opcion] if 0 <= opcion < len(viejas) else None
            if h in nuevas:
                c.execute("UPDATE torneo_votos SET opcion = ? WHERE torneo_id = ? AND cuenta = ?", (nuevas.index(h), tid, cuenta))
            else:
                c.execute("DELETE FROM torneo_votos WHERE torneo_id = ? AND cuenta = ?", (tid, cuenta))
        cambios["horas"] = json.dumps(nuevas)
    if not cambios:
        raise Invalido("No indicó nada para cambiar.")
    c.execute("UPDATE torneos SET " + ", ".join(f"{k} = ?" for k in cambios) + " WHERE id = ?", (*cambios.values(), tid))
    _toque(c, tid, quien)
    return tid, {"antes": {k: t[k] for k in cambios}, "despues": cambios}


def _a_estado(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    tid, nuevo, antes = int(t["id"]), str(d.get("estado") or ""), t["estado"]
    if nuevo not in ESTADOS:
        raise Invalido("El estado es: " + " · ".join(ESTADOS) + ".")
    detalle = {"antes": antes, "despues": nuevo}
    if nuevo == antes:
        return tid, detalle
    hay_llave = _total_rondas(c, tid) > 0
    if nuevo == "votando" and not _horas(t):
        raise Invalido("Para votar hacen falta horas para elegir: cárguelas con «editar».")
    if nuevo == "en_curso" and not hay_llave:
        detalle["entrantes"] = fijar_llave(c, t, quien, ahora)
    if nuevo in ("borrador", "votando", "inscripcion") and hay_llave:
        if _hay_jugados(c, tid) and not d.get("forzar"):
            raise PideForzar("La llave ya tiene resultados: si la deshace, se pierden.")
        c.execute("DELETE FROM torneo_cruces WHERE torneo_id = ?", (tid,))
        c.execute("UPDATE torneo_inscritos SET semilla = NULL WHERE torneo_id = ?", (tid,))
        c.execute("UPDATE torneos SET primero = NULL, segundo = NULL, tercero = NULL WHERE id = ?", (tid,))
        detalle["llave_borrada"] = True
    c.execute("UPDATE torneos SET estado = ?, fin = ? WHERE id = ?",
              (nuevo, ahora if nuevo == "terminado" else None, tid))
    _toque(c, tid, quien)
    return tid, detalle


def _a_fijar_hora(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    if d.get("opcion") not in (None, ""):
        horas = _horas(t)
        try:
            o = int(d.get("opcion"))
        except (TypeError, ValueError):
            o = -1
        if not 0 <= o < len(horas):
            raise Invalido("Esa opción no está entre las horas del torneo.")
        fecha = horas[o]
    else:
        fecha = _epoch(d.get("fecha"))
        if fecha is None:
            raise Invalido("Indique la opción ganadora o una fecha.")
    c.execute("UPDATE torneos SET fecha = ? WHERE id = ?", (fecha, int(t["id"])))
    _toque(c, t["id"], quien)
    return int(t["id"]), {"antes": t["fecha"], "despues": fecha}


def _en_curso(t):
    if t["estado"] != "en_curso":
        raise Invalido("El torneo no está en curso.")


def _a_resultado(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    _en_curso(t)
    r = _cruce_de(c, t, d)
    g = str(d.get("ganador") or "")
    if g not in ("a", "b"):
        raise Invalido("El ganador es «a» o «b».")
    if r["a"] is None or r["b"] is None:
        raise Invalido("Ese cruce todavía no tiene a sus dos participantes.")
    if r["ganador"]:
        raise Invalido("Ese cruce ya tiene ganador: para cambiarlo, reinícielo primero.")
    tid, ronda, idx = int(t["id"]), int(r["ronda"]), int(r["idx"])
    gid, pid = (r["a"], r["b"]) if g == "a" else (r["b"], r["a"])
    c.execute("UPDATE torneo_cruces SET ganador = ?, estado = 'terminado', quien = ?, cambiado = ? "
              "WHERE torneo_id = ? AND ronda = ? AND idx = ?", (g, quien, ahora, tid, ronda, idx))
    detalle = {"ronda": ronda, "idx": idx, "ganador": g, "gana": gid, "pierde": pid}
    if ronda + 1 >= _total_rondas(c, tid):                      # ★ la final: el torneo termina solo
        c.execute("UPDATE torneos SET primero = ?, segundo = ?, estado = 'terminado', fin = ? WHERE id = ?",
                  (gid, pid, ahora, tid))
        detalle["terminado"] = True
    else:
        _avanzar(c, tid, ronda, idx, gid, quien, ahora)
    _toque(c, tid, quien)
    return tid, detalle


def _a_reiniciar(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    if t["estado"] not in ("en_curso", "terminado"):
        raise Invalido("El torneo no está en curso.")
    r = _cruce_de(c, t, d)
    tid, ronda, idx = int(t["id"]), int(r["ronda"]), int(r["idx"])
    if not r["ganador"]:
        raise Invalido("Ese cruce no tiene resultado para reiniciar.")
    if r["a"] is None or r["b"] is None:
        raise Invalido("Ese cruce es un pase libre: no se reinicia.")
    if ronda + 1 < _total_rondas(c, tid):
        sig = c.execute("SELECT ganador FROM torneo_cruces WHERE torneo_id = ? AND ronda = ? AND idx = ?",
                        (tid, ronda + 1, idx // 2)).fetchone()
        if sig["ganador"] and not d.get("forzar"):
            raise PideForzar(f"El cruce siguiente (ronda {ronda + 2}) ya tiene resultado: si reinicia este, "
                             "se borra también.")
    c.execute("UPDATE torneo_cruces SET ganador = NULL, estado = 'pendiente', quien = ?, cambiado = ? "
              "WHERE torneo_id = ? AND ronda = ? AND idx = ?", (quien, ahora, tid, ronda, idx))
    _deshacer_adelante(c, t, ronda, idx, quien, ahora)
    _toque(c, tid, quien)
    return tid, {"ronda": ronda, "idx": idx, "antes": r["ganador"], "forzar": bool(d.get("forzar"))}


def _a_cancion(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    if t["estado"] not in ("en_curso", "terminado"):
        raise Invalido("El torneo no está en curso.")
    r = _cruce_de(c, t, d)
    cancion = _texto(d.get("cancion"), CANCION_MAX, "la canción") or None
    c.execute("UPDATE torneo_cruces SET cancion = ?, quien = ?, cambiado = ? WHERE torneo_id = ? AND ronda = ? AND idx = ?",
              (cancion, quien, ahora, int(t["id"]), int(r["ronda"]), int(r["idx"])))
    _toque(c, t["id"], quien)
    return int(t["id"]), {"ronda": int(r["ronda"]), "idx": int(r["idx"]), "antes": r["cancion"], "despues": cancion}


def _a_jugando(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    _en_curso(t)
    r = _cruce_de(c, t, d)
    si = bool(d.get("si"))
    if r["ganador"]:
        raise Invalido("Ese cruce ya terminó.")
    if si and (r["a"] is None or r["b"] is None):
        raise Invalido("Ese cruce todavía no tiene a sus dos participantes.")
    c.execute("UPDATE torneo_cruces SET estado = ?, quien = ?, cambiado = ? WHERE torneo_id = ? AND ronda = ? AND idx = ?",
              ("jugando" if si else "pendiente", quien, ahora, int(t["id"]), int(r["ronda"]), int(r["idx"])))
    _toque(c, t["id"], quien)
    return int(t["id"]), {"ronda": int(r["ronda"]), "idx": int(r["idx"]), "si": si}


def _a_tercero(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    tid = int(t["id"])
    if _total_rondas(c, tid) == 0:
        raise Invalido("El torneo todavía no tiene llave.")
    ins = d.get("ins_id")
    if ins not in (None, ""):
        try:
            ins = int(ins)
        except (TypeError, ValueError):
            ins = -1
        if ins not in {int(f["id"]) for f in _inscritos(c, tid) if f["semilla"] is not None} or \
                c.execute("SELECT 1 FROM torneo_cruces WHERE torneo_id = ? AND (a = ? OR b = ?)", (tid, ins, ins)).fetchone() is None:
            raise Invalido("Ese inscrito no está en la llave.")
        if ins in (t["primero"], t["segundo"]):
            raise Invalido("Ese inscrito ya está en el podio.")
    else:
        ins = None
    c.execute("UPDATE torneos SET tercero = ? WHERE id = ?", (ins, tid))
    _toque(c, tid, quien)
    return tid, {"antes": t["tercero"], "despues": ins}


def _a_quitar(c, d, quien, ahora):
    t = _t_o_falla(c, d)
    if t["estado"] in ("en_curso", "terminado"):
        raise Invalido("Con la llave armada ya no se puede sacar a nadie.")
    try:
        ins = int(d.get("ins_id"))
    except (TypeError, ValueError):
        ins = -1
    f = c.execute("SELECT * FROM torneo_inscritos WHERE torneo_id = ? AND id = ?", (int(t["id"]), ins)).fetchone()
    if not f:
        raise Invalido("Ese inscrito no está en este torneo.")
    _borrar_inscrito(c, t, f)
    _toque(c, t["id"], quien)
    return int(t["id"]), {"ins_id": ins, "usn": int(f["usn"]), "nombre": f["nombre"]}


_ACCIONES = {"crear": _a_crear, "editar": _a_editar, "estado": _a_estado, "fijar_hora": _a_fijar_hora,
             "resultado": _a_resultado, "reiniciar": _a_reiniciar, "cancion": _a_cancion, "jugando": _a_jugando,
             "tercero": _a_tercero, "quitar": _a_quitar}


# ── la puerta del Coordinador (/api/interno/torneos, dentro de api_web) ─────────────────────────────

def atender_interno(h, metodo, partes, cuerpo=b""):
    """`partes` = lo que sigue a /api/interno/torneos. ⛔ La ficha se mira ANTES que nada (sin ella, 404).
    `X-Coordinador-Quien` dice quién (para la auditoría); si el cuerpo trae `quien`, manda la cabecera."""
    from . import presencia
    if not presencia.ficha_ok(h.headers.get("X-Ficha-Interna")):
        return h._mandar(404, {"error": "no existe"})
    privado = "private, no-store"
    if partes:
        return h._mandar(404, {"error": "no existe"})
    if metodo == "GET":
        return h._mandar(200, {"torneos": todos_staff(), "modos": list(MODOS), "estados": list(ESTADOS),
                               "cupo_min": CUPO_MIN, "cupo_max": CUPO_MAX, "horas_max": HORAS_MAX}, cache=privado)
    try:
        d = json.loads(cuerpo.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return h._mandar(400, {"error": "cuerpo inválido"})
    if not isinstance(d, dict):
        return h._mandar(400, {"error": "cuerpo inválido"})
    cab = h.headers.get("X-Coordinador-Quien")
    if cab:
        d["quien"] = cab
    return h._mandar(*accion(d), cache=privado)
