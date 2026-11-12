# -*- coding: utf-8 -*-
"""charla — la SALA DE CONVERSACIÓN compartida (tipos 5..10: Libre y los cinco grupos de país).

El mapa cruzado CBT / 2013 / 2019 y el plan están en `documentacion/SALA_DE_CHARLA_2013.md`.
Hasta el 24-sep estaba la puerta (`FF11` -> `FF61` -> escena grande) pero cada uno quedaba SOLO en
su copia: el `FF0C` lo listaba a él, y el movimiento y el chat no le llegaban a nadie. Esto la
vuelve compartida:

  · ESTANCIAS: por tipo, `CHARLA_ESTANCIAS` permanentes numeradas **0..N-1** — el número que se ve
    es `A & 0x7FF` (anonimo03: *"no usaremos 965"*). El botón pide 965..969: se traduce a la primera
    estancia con lugar. Cupo `LUGAR_CAPACIDAD` (40, el `FF61` acepta slot < 0x28).
    ⛔ NO 1..N (probado en pantalla el 24-sep, y crasheaba): el panel «Lista» marca como elegido el
    RENGLÓN número `[sala+0x9508]` = el nº de la estancia (`0x585AA5..0x585AC8`, tipos 5..10) ⇒ con
    la «Libre 1» sola en la lista quedaba marcado el 2º renglón, VACÍO, y «Seleccionar» ahí mataba
    al cliente. Numeradas desde 0 el renglón n es la estancia n. (Es el «Libre 0, 1, 2» que anonimo03
    recordaba del CBT.)
  · EL COSTO (la lección del CBT, `FIX_NOTIFY_ROOM_CUADRATICO.md`): el ocupante se arma UNA vez,
    al entrar, y se guarda en la estancia; la lista para el que llega y el aviso a los que estaban
    se arman con eso, sin volver a la base. Entrar cuesta O(1) consultas, no N×N.
  · «POBLADOS»: sólo reciben avisos sueltos los que ya recibieron la lista entera (a uno que
    todavía carga la escena, un aviso suelto le crea gente con datos de ese instante; ver
    `salas.difundir_ocupante`).
  · El CHAT: el byte «speaker» del `FF08` es el índice de la BURBUJA (arreglo de 8 en `sala+0x148`,
    el destructor `0x5A80EE` libera 8) — con 9+ el cliente lee fuera del arreglo. ⛔ Iba `slot % 8`,
    y eso le ponía a cada asiento un globo DE LA TIENDA: desde el 25-sep va el estilo del jugador
    (`catalogo.estilo_chat_de`, 0 = el globo de siempre), siempre < 8.

  · LA SALA DEL CÍRCULO (tipo 12, 25-sep): la misma maquinaria, pero la estancia es `(12, id del
    círculo)` — el botón pide siempre el 970, así que el número no separa a nadie. Cada uno cae en
    la de SU círculo (se lee al entrar, una vez). El `A` que vuelve lleva `CIRCULO_SALA_NUMERO`: el
    título lo arma el cliente con el nombre del círculo pegado al número (`"%s%d"`, `0x5CD675`). Cupo
    `CIRCULO_SALA_CAPACIDAD` (30, el de `circleroom.xml`).

⚠ Mi Sala (11) NO pasa por acá: sigue solitaria.
"""
import struct

from .ajustes import (
    CHARLA_ESTANCIAS,
    CHARLA_FF0C_REAL,
    CIRCULO_SALA_CAPACIDAD,
    CIRCULO_SALA_COMPARTIDA,
    FF23_SLOT_AL_FRENTE,
    LUGAR_CAPACIDAD,
)
from .registro import RESUMIR, log

TIPO_CIRCULO = 12     # la «Sala de Conversación en Círculo» (nº 970, escena `circleroom.xml`)


def es_publica(tipo):
    """Las de todos: Libre y los cinco grupos de país, con estancias 0..N-1."""
    return 5 <= int(tipo) <= 10


def es_del_circulo(tipo):
    return CIRCULO_SALA_COMPARTIDA and int(tipo) == TIPO_CIRCULO


def es_compartida(tipo):
    """Las que pasan por este módulo (las públicas y la del círculo)."""
    return es_publica(tipo) or es_del_circulo(tipo)


def cupo(tipo):
    return CIRCULO_SALA_CAPACIDAD if int(tipo) == TIPO_CIRCULO else LUGAR_CAPACIDAD


def circulo_de(st):
    """El id del círculo del jugador (la estancia de su sala), o `None`. UNA ida a la base."""
    try:
        from .basedatos import db_circulo_de
        k = db_circulo_de(int(getattr(st, "usn", 0) or 0))
        return int(k["id"]) if k else None
    except Exception:                                            # noqa: BLE001
        return None


def _lugares():
    from .salas import LUGARES, _lugar_lock
    return LUGARES, _lugar_lock


def _estancia(tipo, n):
    """La estancia (tipo, n), creándola si no existe. ⚠ Llamar con el lock tomado."""
    LUGARES, _ = _lugares()
    lg = LUGARES.setdefault((int(tipo), int(n)), {"ocupantes": {}})
    lg.setdefault("occ", {})          # usn -> el ocupante armado UNA vez al entrar
    lg.setdefault("poblados", set())  # usn que ya recibieron la lista entera
    return lg


def numero_para(tipo, pedido):
    """El número de estancia que le toca a un pedido: el mismo si es 0..N-1, o —si viene del botón
    (965..969) o de cualquier otro número— la primera estancia con lugar. `None` = todas llenas."""
    LUGARES, lock = _lugares()
    if 0 <= int(pedido) < CHARLA_ESTANCIAS:
        return int(pedido)
    with lock:
        for n in range(CHARLA_ESTANCIAS):
            if len(_estancia(tipo, n)["ocupantes"]) < LUGAR_CAPACIDAD:
                return n
    return None


def gente(tipo, n):
    LUGARES, lock = _lugares()
    with lock:
        lg = LUGARES.get((int(tipo), int(n)))
        return len(lg["ocupantes"]) if lg else 0


def entrar(st, tipo, n):
    """Sienta al jugador en la estancia y arma SU ocupante una vez. -> slot 0..39, o None si llena."""
    from .salas import _ocupante_de
    LUGARES, lock = _lugares()
    usn = int(getattr(st, "usn", 0) or 0)
    _limpiar_la_vieja(st)
    salir(st, "cambió de estancia")                     # nunca en dos a la vez (y avisa en la vieja)
    with lock:
        lg = _estancia(tipo, n)
        ocupados = set(lg["ocupantes"].values())
        slot = next((s for s in range(cupo(tipo)) if s not in ocupados), None)
        if slot is None:
            return None
        lg["ocupantes"][usn] = slot
        lg["poblados"].discard(usn)
        st.lugar_clave = (int(tipo), int(n))
    try:                                                # ★ 15-oct: misión de hoy 1003 «entrar a la sala de charla»
        from . import mision_hoy
        mision_hoy.sumar(usn, 1003, poner=1, motivo="entró a la charla")
    except Exception as _e_mh:                          # noqa: BLE001
        from .registro import log as _log
        _log("LOBBY", f"  ⚠ misión de hoy (charla): {_e_mh!r}")
    occ = _ocupante_de(usn, slot)                       # ★ la ida a la base de esta entrada
    pj = _pareja_de(usn)                                # ★ y su pareja + anillo, una sola vez
    with lock:
        if lg["ocupantes"].get(usn) == slot:
            lg["occ"][usn] = occ
            lg.setdefault("pareja", {})[usn] = pj
    return slot


def _limpiar_la_vieja(st):
    """Al MUDARSE de estancia (el «Seleccionar» de la lista manda el `FF11` directo, sin `FF12`), al
    que se muda se le borra la gente de la estancia vieja con `FF0E [apodo]` (uno por ocupante).

    ★ Medido el 24-sep: en «Libre 0» el `/besar` salía y al mudarse la pareja a «Libre 3» dejaba de
      salir — el cliente ni mandaba el `FF7B`. El gesto de a dos (`0x594590`) busca a la pareja POR
      NOMBRE en el gestor de jugadores (`[0x931660]` → `0x4EBCB0`) y después su SLOT en el mapa de la
      escena (`[sala+0x9C]`, `0x587A50`); sin salir de la vieja, el gestor seguía teniendo a la
      pareja con el slot VIEJO, que en la escena nueva no existe ⇒ aborta. En la primera estancia
      andaba porque no había nada viejo."""
    LUGARES, lock = _lugares()
    clave = getattr(st, "lugar_clave", None)
    if clave is None or not es_compartida(clave[0]):
        return 0
    usn = int(getattr(st, "usn", 0) or 0)
    with lock:
        lg = LUGARES.get(clave) or {}
        if usn not in lg.get("poblados", ()):
            return 0                                    # nunca recibió la lista: no tiene a nadie
        nicks = [str(o.get("nick", "") or "") for u, o in lg.get("occ", {}).items() if u != usn]
    for n in nicks:
        nb = n.encode("cp1252", "replace")[:15]
        if nb:
            st.send_ff55(0x0E, bytes([len(nb)]) + nb, name=f"FF0E charla: se muda, olvidar a {n!r}")
    return len(nicks)


def _pareja_de(usn):
    """`(uid de la pareja, anillo)` o `(0, 0)`. Se lee al ENTRAR y se guarda en la estancia."""
    try:
        from .basedatos import db_anillo_de_pareja, db_pareja_de
        pj = int(db_pareja_de(int(usn)) or 0)
        return (pj, int(db_anillo_de_pareja(int(usn)) or 0) if pj else 0)
    except Exception:                                            # noqa: BLE001
        return (0, 0)


def _con_pareja(lg, usn, occ):
    """El ocupante con el ENLACE de pareja si la pareja está en la estancia (`cola[12]` = su slot,
    `cola[0..3]` = el anillo). ★ Sin esto el cliente cree que la pareja NO está y el gesto de a dos
    (`/besar`, `/vals`) aborta antes de mandar el `FF7B` (`0x531080`): sonaba y no bailaba (24-sep).
    Sale de la caché: ninguna ida a la base."""
    pj, anillo = lg.get("pareja", {}).get(usn, (0, 0))
    sl = lg["ocupantes"].get(pj) if pj else None
    if sl is None:
        return occ
    return dict(occ, pareja_slot=sl, anillo=anillo)


def _ff0c(occ, k, sin_ropa=False):
    from .paquetes import build_ff0c_2013, build_ff0c_2013_real
    o = dict(occ, parts=[]) if sin_ropa else occ
    return build_ff0c_2013_real(o, k) if CHARLA_FF0C_REAL else build_ff0c_2013([o])


def _conexion(usn):
    from .salas import CONEXIONES
    c = CONEXIONES.get(int(usn))
    return None if c is None or getattr(c, "cerrado", False) else c


def mandar_lista(st):
    """La respuesta al `FF0C` que pide el cliente al terminar de cargar: TODOS los de la estancia
    (armados de la caché, sin base), y recién ahí se lo anuncia a los que ya estaban."""
    from .ajustes import FF0C_YO_SIN_ROPA
    LUGARES, lock = _lugares()
    clave = getattr(st, "lugar_clave", None)
    usn = int(getattr(st, "usn", 0) or 0)
    if clave is None:
        return 0
    with lock:
        lg = _estancia(*clave)
        # ★ sólo los POBLADOS (y él): el que entró y todavía carga le llega después con SU aviso.
        #   Metiéndolo también acá, al que pidió la lista le llegaba DOS veces (25-sep, la prueba §9).
        todos = sorted(((s, u, _con_pareja(lg, u, lg["occ"][u]) if u in lg["occ"] else None)
                        for u, s in lg["ocupantes"].items() if u in lg["poblados"] or u == usn),
                       key=lambda x: x[0])
        lg["poblados"].add(usn)
        mio = _con_pareja(lg, usn, lg["occ"][usn]) if usn in lg["occ"] else None
        otros = [u for u in lg["poblados"] if u != usn]
        pj = lg.get("pareja", {}).get(usn, (0, 0))
        pj_nick = (lg["occ"].get(pj[0]) or {}).get("nick", "") if pj[0] in lg["ocupantes"] else ""
    n = 0
    for i, (s, u, occ) in enumerate(todos):
        if occ is None:
            continue
        st.send_ff55(0x0C, _ff0c(occ, 1 if i == 0 else 2, sin_ropa=(u == usn and FF0C_YO_SIN_ROPA)),
                     name=f"FF0C charla: slot {s} {occ.get('nick')!r}")
        n += 1
    # el aviso a los que ya estaban: UN paquete armado una vez, el mismo para todos
    if mio is not None and otros:
        p = _ff0c(mio, 1)
        p48 = None
        if pj_nick:
            # ★ el enlace para los que YA estaban (el FF0C sólo enlaza al CREAR): el FF48 busca por
            #   NOMBRE, así que va DETRÁS del FF0C que dibuja al que llega (`salas.difundir_ocupante`)
            from .lobby_pareja import _s2c_pareja_en_sala
            p48 = _s2c_pareja_en_sala(pj[1], mio.get("nick", ""), pj_nick)
        for u in otros:
            c = _conexion(u)
            if c is not None:
                c.send_ff55(0x0C, p, name=f"FF0C charla: entró {mio.get('nick')!r} (slot {mio.get('slot')})")
                if p48 is not None:
                    c.send_ff55(0x48, p48, name=f"FF48 charla: enlace «{mio.get('nick')} & {pj_nick}»")
    log("LOBBY", f"  💬 CHARLA {clave}: lista de {n} a usn={usn}; aviso a {len(otros)}")
    if es_del_circulo(clave[0]):
        # ★ el que entra no pregunta quién está sentado: se le manda (FFF5), DETRÁS de la lista
        with lock:
            sentados = dict(_estancia(*clave).get("sentado", {}))
        if sentados:
            st.send_ff55(0xF5, _fff5(_estancia(*clave)), name=f"FFF5 sala del círculo: {len(sentados)} sentado(s)")
    return n


def salir(st, motivo=""):
    """Lo saca de su estancia y les manda `FF0E [len][apodo]` (borra por NOMBRE) a los poblados."""
    LUGARES, lock = _lugares()
    clave = getattr(st, "lugar_clave", None)
    if clave is None:
        return None
    usn = int(getattr(st, "usn", 0) or 0)
    p5 = None
    with lock:
        lg = LUGARES.get(clave)
        occ = None
        otros = []
        if lg is not None:
            lg["ocupantes"].pop(usn, None)
            occ = lg.get("occ", {}).pop(usn, None)
            lg.get("pareja", {}).pop(usn, None)
            lg.get("poblados", set()).discard(usn)
            otros = list(lg.get("poblados", ()))
            estaba_sentado = _parar(lg, usn)
            p5 = _fff5(lg) if estaba_sentado else None
        st.lugar_clave = None
    if p5 is not None:
        # ★ si estaba SENTADO: la foto de sentados SIN él, ANTES del FF0E — borrar al personaje no
        #   libera el asiento del mueble y quedaba «ocupado» en las pantallas de los demás
        for u in otros:
            c = _conexion(u)
            if c is not None:
                c.send_ff55(0xF5, p5, name="FFF5 sala del círculo: se fue uno que estaba sentado")
    if occ is not None and es_compartida(clave[0]):
        nb = str(occ.get("nick", "") or "").encode("cp1252", "replace")[:15]   # buffer de 16 con NUL
        for u in otros:
            c = _conexion(u)
            if c is not None:
                c.send_ff55(0x0E, bytes([len(nb)]) + nb, name=f"FF0E charla: se fue {occ.get('nick')!r}")
        log("LOBBY", f"  💬 CHARLA {clave}: sale usn={usn} ({motivo}) -> avisado a {len(otros)}")
    return clave


def destinos(st, con_yo=False):
    """Las conexiones POBLADAS de la estancia de `st` (para reenviar movimiento y chat)."""
    LUGARES, lock = _lugares()
    clave = getattr(st, "lugar_clave", None)
    if clave is None or not es_compartida(clave[0]):
        return []
    usn = int(getattr(st, "usn", 0) or 0)
    with lock:
        lg = LUGARES.get(clave) or {}
        us = [u for u in lg.get("poblados", ()) if con_yo or u != usn]
    return [c for c in (_conexion(u) for u in us) if c is not None]


def mi_slot(st):
    LUGARES, lock = _lugares()
    clave = getattr(st, "lugar_clave", None)
    with lock:
        return (LUGARES.get(clave) or {}).get("ocupantes", {}).get(int(getattr(st, "usn", 0) or 0))


def reenviar_ff23(st, data):
    """El movimiento (`FF23`, 12 B, sin slot) a los demás, con el slot del que se movió al frente."""
    sl = mi_slot(st)
    if sl is None or len(data) < 9:
        return 0
    if es_del_circulo((getattr(st, "lugar_clave", None) or (0,))[0]):
        # la última posición (C→S `[u8][f32 X][f32 Z]...`): es adonde vuelve al pararse de un mueble
        LUGARES, lock = _lugares()
        with lock:
            (LUGARES.get(st.lugar_clave) or {}).setdefault("pos", {})[int(st.usn)] = struct.unpack_from("<ff", data, 1)
    out = bytes([sl & 0xFF]) + bytes(data) if FF23_SLOT_AL_FRENTE else bytes(data)
    ds = destinos(st)
    for c in ds:
        c.send_ff55(0x23, out, name=RESUMIR)             # ⚠ sin log por paquete: el CBT llegó a 11 GB
    return len(ds)


# ══════════════════════════════════════════════════════════════════════════════════════════════
#  ★★ SENTARSE / USAR LOS MUEBLES de la sala del círculo (25-sep) — `documentacion/CIRCULO_EXE_MUEBLES.md`
#     Por estancia: `asientos[(clave del mueble, asiento)] = usn` y `sentado[usn] = (clave, asiento,
#     x, z)` (x, z = la última posición antes de sentarse: adonde vuelve al pararse).
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _parar(lg, usn):
    """Lo levanta (libera su asiento). ⚠ Con el lock tomado. -> si estaba sentado."""
    s = lg.get("sentado", {}).pop(int(usn), None)
    if s is not None:
        lg.get("asientos", {}).pop((s[0], s[1]), None)
    return s is not None


def _fff5(lg):
    """`FFF5` S→C (`0x5DB900`) = la FOTO de los sentados: `[u8 n] + n x ([u8 slot][f32 x][f32 z]
    [u32 clave][u8 asiento])`. Es una foto ENTERA: el que no está, queda parado (`0x587760` levanta
    a todos; cada entrada lo pone en (x, z) y `0x587810` lo sienta sin caminar). ⚠ Con el lock."""
    filas = [(lg["ocupantes"][u], s) for u, s in lg.get("sentado", {}).items() if u in lg["ocupantes"]]
    out = bytes([len(filas) & 0xFF])
    for slot, (k, a, x, z) in filas:
        out += bytes([slot & 0xFF]) + struct.pack("<ffIB", float(x), float(z), int(k) & 0xFFFFFFFF, a & 0xFF)
    return out


def fff5_de(st):
    """La foto de sentados de la estancia de `st` (lo que se contesta al `FFF5` vacío: al salir del
    modo edición el cliente levantó a todos y la necesita para volver a sentarlos)."""
    LUGARES, lock = _lugares()
    with lock:
        lg = LUGARES.get(getattr(st, "lugar_clave", None))
        return _fff5(lg) if lg else bytes([0])


def armar_fff4(slot, clave, asiento):
    """`FFF4` S→C (`0x5DB730`) = `[u32 (ignorado)][u8 slot del que actúa][u32 clave][u8 asiento]`.
    clave 0 = se para · asiento 0xFF = «clic» en un objeto (anima el objeto, no se mueve)."""
    return struct.pack("<IBIB", 0, slot & 0xFF, int(clave) & 0xFFFFFFFF, asiento & 0xFF)


def accion_objeto(st, clave, asiento, colocado):
    """`FFF4 [u32 clave][u8 asiento]` C→S (`0x5DB5B0`). El cliente NO hace nada hasta que vuelve el
    eco, y NO controla si el asiento está libre: eso es del server. Va a TODOS los de la sala, el
    que actúa incluido (si no, se queda con la marca «pendiente» y no puede volver a pedir).
    `colocado(clave)` dice si es un mueble COLOCADO de ese círculo. -> cuántos lo recibieron."""
    LUGARES, lock = _lugares()
    cl = getattr(st, "lugar_clave", None)
    usn = int(getattr(st, "usn", 0) or 0)
    if cl is None or not es_del_circulo(cl[0]):
        return 0
    with lock:
        lg = LUGARES.get(cl) or {}
        slot = lg.get("ocupantes", {}).get(usn)
    if slot is None:
        return 0
    if clave and not colocado(clave):
        clave, asiento = 0, 0                               # un mueble que no es de la sala: se para
    with lock:
        if not clave:                                        # pararse
            _parar(lg, usn)
            eco, a_todos = armar_fff4(slot, 0, 0), True
        elif asiento == 0xFF:                                # clic en un objeto
            eco, a_todos = armar_fff4(slot, clave, 0xFF), True
        elif usn in lg.setdefault("sentado", {}) or (clave, asiento) in lg.setdefault("asientos", {}):
            eco, a_todos = armar_fff4(slot, 0, 0), False     # ocupado (o ya sentado): no, sólo a él
        else:
            x, z = lg.get("pos", {}).get(usn, (0.0, 0.0))
            lg["asientos"][(clave, asiento)] = usn
            lg["sentado"][usn] = (clave, asiento, x, z)
            eco, a_todos = armar_fff4(slot, clave, asiento), True
    ds = destinos(st, con_yo=True) if a_todos else [st]
    for c in ds or [st]:
        c.send_ff55(0xF4, eco, name=f"FFF4 objeto de la sala: slot {slot} clave {clave} asiento {asiento}")
    return len(ds)


def soltar_asientos(clave_estancia):
    """Levanta a todos (tras rearmar la sala: el FFDE modo 1 ya los levanta en el cliente)."""
    LUGARES, lock = _lugares()
    with lock:
        lg = LUGARES.get(clave_estancia)
        if lg:
            lg["sentado"], lg["asientos"] = {}, {}


def lista_ff65(tipo):
    """Las filas del `FF65` (el panel «Lista»): TODAS las estancias 0..N-1 del tipo, con su gente.
    `[u16 n]` + por fila `[u16 A][u8 gente]` (handler `0x5D09C0`; sólo el tipo 11 lleva texto
    extra, y éstos son 5..10). El cupo /40 lo pone el cliente. ⚠ La cuenta real ≠ 0: la teoría
    de que «pisa el contador» está refutada (`TIPOS_DE_SALA_Y_CANAL_2013.md` §3.3)."""
    filas = [(((int(tipo) & 0x1F) << 11) | n, min(gente(tipo, n), 0xFF)) for n in range(CHARLA_ESTANCIAS)]
    return struct.pack("<H", len(filas)) + b"".join(struct.pack("<HB", a, g) for a, g in filas)


def lista_ff65_circulo(st, numero):
    """El `FF65` de la sala del círculo: UN renglón, con el MISMO nº que le dimos al entrar
    (`CIRCULO_SALA_NUMERO`: el renglón marcado lo busca por número, `0x58D990`) y la gente de SU
    círculo. Sin círculo, 0."""
    clave = getattr(st, "lugar_clave", None)
    cid = clave[1] if clave and int(clave[0]) == TIPO_CIRCULO else circulo_de(st)
    g = min(gente(TIPO_CIRCULO, cid), 0xFF) if cid is not None else 0
    return struct.pack("<H", 1) + struct.pack("<HB", ((TIPO_CIRCULO & 0x1F) << 11) | (int(numero) & 0x7FF), g)


def reenviar_ff7b(st, eco):
    """El gesto DE PAREJA (`FF7B`, ya validado y recortado por `lobby_pareja`) a los de la estancia,
    incluido el que lo hizo: el baile lo reproduce el handler de RECEPCIÓN, sin eco no baila nadie."""
    ds = destinos(st, con_yo=True)
    for c in ds:
        c.send_ff55(0x7B, eco, name="FF7B baile de pareja (charla)")
    return len(ds)


def refrescar_apariencia(st, motivo="", recrear=True):
    """Cambió de ropa o de personaje ESTANDO en la charla: re-arma su ocupante (1 ida a la base),
    lo guarda en la caché y lo repinta a los de la estancia como en las salas de carrera
    (`lobby_tienda.refrescar_apariencia_en_sala`): FF0E + FF0C (re-crear) + FF15 (recargar el modelo).
    Sin esto la caché quedaba vieja y los demás lo seguían viendo con el personaje de antes —
    y los gestos atados al personaje (`[Ice]` = Ice Observador) no le salían."""
    from .ajustes import REAPARECER_AL_CAMBIAR_PERSONAJE, REFRESCO_ROPA_FF15
    from .paquetes import build_ff0c_2013_real
    from .salas import _ocupante_de, ff15_de
    LUGARES, lock = _lugares()
    clave = getattr(st, "lugar_clave", None)
    if clave is None or not es_compartida(clave[0]):
        return 0
    usn = int(getattr(st, "usn", 0) or 0)
    sl = mi_slot(st)
    if sl is None:
        return 0
    occ = _ocupante_de(usn, sl)
    with lock:
        lg = LUGARES.get(clave) or {}
        if lg.get("ocupantes", {}).get(usn) == sl:
            lg.setdefault("occ", {})[usn] = occ
    with lock:
        occ = _con_pareja(LUGARES.get(clave) or {"ocupantes": {}}, usn, occ)
    nb = str(occ.get("nick", "") or "").encode("cp1252", "replace")[:15]
    p0c, p15 = build_ff0c_2013_real(occ, 1), (ff15_de(occ, None) if REFRESCO_ROPA_FF15 else None)
    ds = destinos(st, con_yo=True)
    for c in ds:
        if recrear and REAPARECER_AL_CAMBIAR_PERSONAJE and nb:
            c.send_ff55(0x0E, bytes([len(nb)]) + nb, name=f"FF0E charla: re-crear a {occ.get('nick')!r}{motivo}")
        c.send_ff55(0x0C, p0c, name=f"FF0C charla: apariencia nueva de {occ.get('nick')!r}{motivo}")
        if p15 is not None:
            c.send_ff55(0x15, p15, name=f"FF15 charla: recargar a {occ.get('nick')!r}")
    log("LOBBY", f"  💬 CHARLA {clave}: apariencia de usn={usn} repintada a {len(ds)}{motivo}")
    return len(ds)
