# -*- coding: utf-8 -*-
"""gm_npc — las cuentas «GM NPC»: desechables, de UNA sesión, vestidas de NPC (27-nov-2026).

LO QUE PIDIÓ EÑEÑOS
-------------------
  «generar cuenta "GM NPC", cuentas desechables cuyas acciones de poder: npc, rate exp o rate rcoin o tocar campanas
   […] con los nombres o ropas que están en el rar […] son cuentas de 1 solo uso y sus acciones quedan registradas
   "como que moderador generó y usó la cuenta"».
  Y eligió: usuario y clave de un uso · poderes «llenar la sala con NPC, rates de EXP y Rcoin, tocar campanas,
  anuncios» · dura UNA SESIÓN.

CÓMO
----
  · El moderador aprieta «Crear» en el Coordinador (acción asignable `gm_npc`). El Coordinador llama a
    `/api/interno/panel/gmnpc` y ESTE módulo hace todo: la cuenta en Cuenta Eñeños (usuario y clave al azar), el
    personaje con el traje del NPC puesto (`taller/traer_del_kr/traer_trajes_npc.py`: 101109xx chico, 101209xx chica)
    y campanas en el inventario. La clave se devuelve UNA vez y no se guarda en ningún lado.
  · Los poderes son SUS comandos de chat (`COMANDOS`) y las campanas de su inventario, que toca como cualquiera
    (el camino nativo: posición real, cartel real). Nada más: ni los de GM de más, ni los de desarrollo.
  · ★ Quién la usa queda en la auditoría como el MODERADOR: el actor es su uid del Coordinador (`externo_uid`, el
    mismo que usan sus otras acciones) y el uid tocado es la cuenta GM NPC.
  · UNA SESIÓN: se cierra cuando se va del juego (no cuando cambia de canal: eso también corta el socket), o si
    nadie entra en `SIN_USAR_H` horas, o a mano desde el Coordinador. Cerrada no entra más: lo dice `cerrada()` en
    los TRES logins (el pase del launcher, el FF01 del juego y el FF02 del lobby) y además se le pide a Cuenta Eñeños
    que la marque baneada, así el launcher ya no la deja ni pedir el pase.

⛔ LAS TRES TRAMPAS QUE ESTO ESQUIVA A PROPÓSITO
  1. NO se cierra con `banear_cuenta`: banear puede banear también LA PC (`BANEO_POR_MAQUINA`), y la PC es la del
     moderador. Se cierra con la tabla de acá + el estado en Cuenta Eñeños.
  2. El cambio de canal CORTA el socket igual que irse (`lobby.py`, FF3D): sin `st.cambio_canal` la cuenta se
     cerraría al primer cambio de canal.
  3. Los topes de cuentas por IP y por PC (`multicuenta`, `maquina`) la dejarían afuera: el moderador ya está
     conectado con SU cuenta desde esa misma PC. Por eso la cuenta GM NPC no cuenta para el tope, y su PC no se
     anota (si se anotara, el moderador saldría «multicuenta» de sus propias GM NPC).
"""
import secrets
import threading
import time

from .registro import log

# (código del traje, nombre, sexo: 1 chico · 2 chica). El sexo sale de `hero.txt` (Gender 0/1) de cada traje.
NPCS = {
    "king":    (10110901, "King",    1),
    "silver":  (10110902, "Silver",  1),
    "lindsey": (10120903, "Lindsey", 2),
    "marie":   (10120904, "Marie",   2),
    "nari":    (10120905, "Nari",    2),
    "sue":     (10120906, "Sue",     2),
}
# ★ Los comandos de chat que abre (además de los del juego, `CONSOLA_SIN_GM`). Uno por poder elegido:
#   NPC (`.npc`) · rates (`.rate`) · anuncios (`.aviso`/`.anuncio`/`.gm1..3`). Las campanas van por el inventario.
COMANDOS = ("npc", "npcs", "rate", "rates", "aviso", "anuncio", "gm1", "gm2", "gm3")
# ★ Las campanas que trae puestas: (ítem, cargas). Las de siempre, normal y «+», de oro y de plata.
#   El candado de «una por metal por sala» corre igual que para cualquiera (`lobby_campana`).
CAMPANAS = ((181, 10), (183, 10), (297, 10), (304, 10))
SIN_USAR_H = 12              # si nadie entra en estas horas, se cierra sola
# ★ 27-nov (la 1.ª en prod: GM-Sue se cerró a los 8 s): al ELEGIR en el selector de la dll el juego CORTA el lobby y vuelve
#   a entrar, igual que un cambio de canal pero sin el FF3D ⇒ «salió del juego» y el reingreso rechazado («el servidor
#   no responde»). La GM NPC ya no pasa por el selector (`cuenta_personajes`, el HOLA), y además irse la cierra recién
#   si en GRACIA_S no volvió a entrar: cualquier reconexión rápida (selector, canal, un micro-corte) no la mata.
GRACIA_S = 120
LICENCIA = 7                 # SOL: entra a todos los canales
LISTA_TOPE = 100

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS gm_npc (
    usn INTEGER PRIMARY KEY, enenos_id INTEGER, usuario TEXT NOT NULL, npc TEXT NOT NULL, nick TEXT NOT NULL,
    creado_por TEXT NOT NULL, creado REAL NOT NULL, entro REAL, cerrado REAL, motivo TEXT NOT NULL DEFAULT '');
"""
_lock = threading.Lock()


_con_tabla = set()


def _db():
    from .panel_admin import _pdb
    c = _pdb()
    if id(c) not in _con_tabla:                  # una vez por conexión (es una por hilo)
        c.executescript(_ESQUEMA)
        _con_tabla.add(id(c))
    return c


def info(usn):
    """La fila de la cuenta GM NPC (dict), o None si `usn` no es una."""
    try:
        u = int(usn or 0)
    except (TypeError, ValueError):
        return None
    if u <= 0:
        return None
    try:
        r = _db().execute("SELECT * FROM gm_npc WHERE usn = ?", (u,)).fetchone()
    except Exception as e:                                               # noqa: BLE001
        log("LOBBY", f"  ⚠ GM NPC: no pude leer la tabla ({e!r})")
        return None
    return dict(r) if r else None


def de(st):
    """La fila de la conexión `st` si es una GM NPC que ENTRÓ (la marca `al_entrar`), o None."""
    return getattr(st, "gm_npc", None)


def es_cuenta(usn):
    return info(usn) is not None


def _estado(f, ahora=None):
    ahora = time.time() if ahora is None else ahora
    if f.get("cerrado"):
        return "cerrada"
    if not f.get("entro"):
        return "vencida" if ahora - float(f["creado"]) > SIN_USAR_H * 3600 else "sin usar"
    return "en uso"


def cerrada(usn):
    """El motivo por el que esa cuenta GM NPC ya no entra, o None (no es GM NPC, o todavía sirve).
    ⚠ Si la tabla no se puede leer y no se sabe, NO se cierra a nadie: `info` devuelve None (un jugador cualquiera)."""
    f = info(usn)
    if not f:
        return None
    e = _estado(f)
    if e == "cerrada":
        return f"la cuenta GM NPC ya se usó ({f.get('motivo') or 'cerrada'})"
    if e == "vencida":
        cerrar(f["usn"], f"nadie entró en {SIN_USAR_H} h")
        return f"la cuenta GM NPC venció sin usarse ({SIN_USAR_H} h)"
    return None


def _actor(f):
    """El uid del Coordinador de quien la creó. ★ Y se asegura su apodo en `actores_externos`: lo que hace la cuenta
    adentro del juego pasa FUERA de un pedido del Coordinador, y sin esa fila la auditoría diría «coordinador» a secas."""
    from .panel_admin import externo_uid
    uid = externo_uid(f["creado_por"])
    try:
        _db().execute("INSERT OR IGNORE INTO actores_externos (uid, nick, visto) VALUES (?, ?, ?)",
                      (uid, f["creado_por"], time.time()))
    except Exception as e:                                               # noqa: BLE001
        log("API", f"⚠ GM NPC: no pude anotar al actor {f['creado_por']!r}: {e!r}")
    return uid


def anotar(f, accion, detalle=None):
    """A la auditoría del panel, a nombre del MODERADOR que la creó, sobre la cuenta GM NPC."""
    from .panel_admin import auditar
    auditar(_actor(f), "gmnpc/" + accion, f["usn"], {"cuenta": f["nick"], "npc": f["npc"], **(detalle or {})})


def al_entrar(st, usn):
    """El FF02 la dejó pasar: se marca la conexión y la hora de entrada (la primera)."""
    f = info(usn)
    if not f:
        return None
    if not f.get("entro"):
        f["entro"] = time.time()
        _db().execute("UPDATE gm_npc SET entro = ? WHERE usn = ? AND entro IS NULL", (f["entro"], f["usn"]))
        anotar(f, "entro", {"ip": str(getattr(st, "addr", ("",))[0] or "")[:64]})
    st.gm_npc = f
    log("LOBBY", f"  ★ GM NPC: usn={f['usn']} {f['nick']!r} entró (la creó {f['creado_por']!r})")
    return f


def al_comando(st, texto):
    f = de(st)
    if f:
        anotar(f, "comando", {"texto": str(texto)[:200]})


def al_campana(st, item, sala):
    f = de(st)
    if f:
        anotar(f, "campana", {"item": int(item), "sala": sala})


def al_salir(st):
    """El `finally` de la conexión. ⛔ Un cambio de canal NO es irse (también corta el socket)."""
    f = de(st)
    if not f or getattr(st, "reemplazada", False):
        return
    if not getattr(st, "cambio_canal", False):
        _cerrar_si_no_vuelve(f["usn"])
    if (info(f["usn"]) or {}).get("cerrado"):
        _liberar_apodo(f["usn"])          # ★ acá, al FINAL del `finally`: ya nadie guarda el personaje con el apodo viejo


def _cerrar_si_no_vuelve(usn):
    """Se fue: la cierra en GRACIA_S, SI para entonces no volvió a entrar (ver GRACIA_S)."""
    def mirar():
        try:
            if not _conectada(usn):
                cerrar(usn, "salió del juego")
        except Exception as e:                                           # noqa: BLE001
            log("LOBBY", f"  ⚠ GM NPC: no pude cerrar usn={usn} tras la gracia: {e!r}")
    t = threading.Timer(GRACIA_S, mirar)
    t.daemon = True
    t.start()
    log("LOBBY", f"  ★ GM NPC: usn={usn} se fue — se cierra en {GRACIA_S} s si no vuelve")
    return t


def _conectada(usn):
    from .salas import CONEXIONES
    st = CONEXIONES.get(int(usn))
    return st is not None and not getattr(st, "cerrado", False)


def _liberar_apodo(usn):
    """El apodo «GM-King» vuelve a quedar libre para la próxima. ⚠ Sólo con la cuenta DESCONECTADA: si no, lo que
    guarde la conexión al irse (con su copia del personaje) le devolvería el apodo viejo."""
    try:
        from .basedatos import db_get_char, db_save_uno
        ch = db_get_char(usn)
        if ch and not str(ch.get("nick") or "").startswith("gmnpc"):
            ch["nick"] = f"gmnpc{int(usn)}"[:12]
            db_save_uno(int(usn), ch)
    except Exception as e:                                               # noqa: BLE001
        log("LOBBY", f"  ⚠ GM NPC: no pude liberar el apodo de usn={usn}: {e!r}")


def cerrar(usn, motivo, quien=None):
    """Cierra la cuenta para siempre. -> True si estaba abierta. Libera el apodo (para el próximo «GM-King»), le pide a
    Cuenta Eñeños que la marque baneada (en otro hilo: puede tardar y esto corre en el `finally` de una conexión) y
    la echa si está conectada (cuando la cierra un moderador)."""
    with _lock:
        f = info(usn)
        if not f or f.get("cerrado"):
            return False
        ahora = time.time()
        _db().execute("UPDATE gm_npc SET cerrado = ?, motivo = ? WHERE usn = ? AND cerrado IS NULL",
                      (ahora, str(motivo)[:120], f["usn"]))
    if not _conectada(f["usn"]):
        _liberar_apodo(f["usn"])          # (conectada, lo hace su `al_salir` cuando termine de irse)
    anotar(f, "cerrada", {"motivo": str(motivo)[:120], **({"por": quien} if quien else {})})
    if f.get("enenos_id"):
        threading.Thread(target=_bloquear_en_cuentas, args=(f["enenos_id"], f["usn"]), daemon=True).start()
    if quien:
        try:
            from .panel_admin import echar_conexion
            echar_conexion(f["usn"])
        except Exception as e:                                           # noqa: BLE001
            log("LOBBY", f"  ⚠ GM NPC: no pude echar a usn={f['usn']}: {e!r}")
    log("LOBBY", f"  ★ GM NPC: usn={f['usn']} {f['nick']!r} CERRADA ({motivo})")
    return True


def _bloquear_en_cuentas(eid, usn):
    from . import pase
    try:
        r = pase.poner_estado_interno(eid, "baneada", motivo="cuenta GM NPC usada (una sola sesión)")
        if r["estado"] != "ok":
            log("LOBBY", f"  ⚠ GM NPC: Cuenta Eñeños no marcó baneada a enenos_id={eid} (usn={usn}): {r['error']} "
                         f"— igual no entra: el juego la rechaza por su tabla")
    except Exception as e:                                               # noqa: BLE001
        log("LOBBY", f"  ⚠ GM NPC: no pude avisarle a Cuenta Eñeños (enenos_id={eid}): {e!r}")


def _apodo(nombre):
    from .basedatos import db_uids_por_nick
    base = f"GM-{nombre}"[:12]
    if not db_uids_por_nick(base):
        return base
    for n in range(2, 100):
        a = f"{base[:12 - len(str(n))]}{n}"
        if not db_uids_por_nick(a):
            return a
    return None


def _crear_cuenta(usuario, clave):
    """-> (usn, enenos_id, error). Con `R2_LOGIN=pase`, en Cuenta Eñeños; si no (local), una cuenta del juego."""
    from . import pase
    from .basedatos import cuenta_asegurar_uid, cuenta_crear, hash_pass
    if pase.modo_pase():
        r = pase.crear_cuenta_interna(usuario, hash_pass(clave))
        if r["estado"] != "ok":
            return None, None, r["error"] or "Cuenta Eñeños no creó la cuenta."
        eid = int((r.get("datos") or {}).get("uid") or 0)
        if eid <= 0:
            return None, None, "Cuenta Eñeños no devolvió el Eñeños ID."
        usn, motivo = cuenta_asegurar_uid(eid)
        if usn is None:
            threading.Thread(target=_bloquear_en_cuentas, args=(eid, 0), daemon=True).start()
            return None, eid, f"el juego no creó la cuenta ({motivo})"
        return usn, eid, None
    usn, motivo = cuenta_crear(usuario, hash_pass(clave))
    return usn, None, (None if usn else f"el juego no creó la cuenta ({motivo})")


def preparar(npc, quien):
    """Crea una GM NPC. -> (código HTTP, respuesta). La clave va en la respuesta y en NINGÚN otro lado."""
    from .basedatos import db_add_inventory, db_get_char, db_save_uno
    from .catalogo import asegurar_basico
    from .cuenta_personajes import CHAR_ID, OPCIONES_EXE
    from .misiones import db_create_char
    k = str(npc or "").strip().lower()
    if k not in NPCS:
        return 400, {"error": "NPC desconocido.", "npcs": list(NPCS)}
    traje, nombre, sexo = NPCS[k]
    apodo = _apodo(nombre)
    if not apodo:
        return 409, {"error": f"No hay apodo libre para {nombre}."}
    usuario = "gmnpc_" + secrets.token_hex(4)
    clave = secrets.token_urlsafe(9)[:12]
    usn, eid, err = _crear_cuenta(usuario, clave)
    if err:
        log("API", f"⚠ GM NPC: no se creó ({usuario!r}, por {quien!r}): {err}")
        return 502, {"error": err}
    db_create_char(usn, {"char_id": CHAR_ID[sexo], "gender": 1 if sexo == 2 else 0, "nick": apodo,
                         "parts": [fila[0] for fila in OPCIONES_EXE[sexo]]})
    asegurar_basico(usn)
    db_add_inventory(usn, traje, 0)
    for item, cargas in CAMPANAS:
        db_add_inventory(usn, item, 0, cargas)
    ch = db_get_char(usn) or {}
    ch.update(char_id=traje, rcoin=0, licencia=LICENCIA)          # ★ el traje PUESTO; sin Rcoin (no compra ni regala)
    db_save_uno(usn, ch)
    ahora = time.time()
    _db().execute("INSERT INTO gm_npc (usn, enenos_id, usuario, npc, nick, creado_por, creado) VALUES (?,?,?,?,?,?,?)",
                  (usn, eid, usuario, k, apodo, str(quien or "coordinador")[:80], ahora))
    f = info(usn)
    anotar(f, "creada", {"usuario": usuario})                       # ⛔ la clave NO
    log("API", f"★ GM NPC creada: usn={usn} {apodo!r} ({nombre}, traje {traje}) por {quien!r}")
    return 200, {"ok": True, "usuario": usuario, "clave": clave, "nick": apodo, "usn": usn, "npc": k,
                 "vence_sin_usar_h": SIN_USAR_H}


def lista(limite=LISTA_TOPE):
    ahora = time.time()
    filas = _db().execute("SELECT * FROM gm_npc ORDER BY creado DESC LIMIT ?", (int(limite),)).fetchall()
    return [{"usn": f["usn"], "usuario": f["usuario"], "npc": f["npc"], "nick": f["nick"], "creado_por": f["creado_por"],
             "creado": f["creado"], "entro": f["entro"], "cerrado": f["cerrado"], "motivo": f["motivo"],
             "estado": _estado(dict(f), ahora)} for f in filas]


def atender(h, metodo, partes, cuerpo, quien):
    """`/api/interno/panel/gmnpc[/cerrar]` — SÓLO desde el Coordinador (lo llama `contenido_interno.atender_panel`,
    detrás de la ficha). GET: la lista y los NPC · POST {npc}: crear · POST cerrar {usn}: cerrarla ya."""
    import json
    privado = "private, no-store"
    if metodo == "GET" and partes == ["gmnpc"]:
        return h._mandar(200, {"npcs": [{"id": k, "nombre": v[1], "traje": v[0]} for k, v in NPCS.items()],
                               "cuentas": lista(), "sin_usar_h": SIN_USAR_H, "comandos": list(COMANDOS)},
                         cache=privado)
    if metodo != "POST" or partes not in (["gmnpc"], ["gmnpc", "cerrar"]):
        return h._mandar(404, {"error": "no existe"})
    try:
        d = json.loads(cuerpo.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        d = None
    if not isinstance(d, dict):
        return h._mandar(400, {"error": "cuerpo inválido"})
    if partes == ["gmnpc"]:
        return h._mandar(*preparar(d.get("npc"), quien), cache=privado)
    try:
        usn = int(d.get("usn"))
    except (TypeError, ValueError):
        return h._mandar(400, {"error": "falta el usn"})
    if not es_cuenta(usn):
        return h._mandar(404, {"error": "no es una cuenta GM NPC"})
    hecho = cerrar(usn, "la cerró un moderador", quien=quien)
    return h._mandar(200, {"ok": True, "ya_estaba": not hecho, "cuentas": lista()}, cache=privado)
